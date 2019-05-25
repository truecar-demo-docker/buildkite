import os
import json
import re
from datetime import datetime, timedelta
from time import sleep
from urllib.request import urlopen
from urllib.parse import urlsplit, urlunsplit, urljoin

import requests
import boto3

from buildkite.util import print_debug
from buildkite.errors import UnsupportedCloneURL, AccessDocumentFormatError


env_var_placeholder_pattern = re.compile('@@([a-zA-Z0-9_]+)@@')
sts = boto3.client('sts')


def request_access(access_document):
    url = urljoin(os.environ['MASTERMIND_ENDPOINT'], 'role')
    body = role_request(access_document)
    print_debug(f'Requesting role from Mastermind:\n{body}')
    deadline = datetime.now() + timedelta(minutes=10)
    while True:
        resp = requests.post(url, auth=('buildkite', os.environ['MASTERMIND_API_KEY']), json=body)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 202:
            now = datetime.now()
            if now > deadline:
                raise TimeoutError('Timeout while waiting for Mastermind approval. Recommend retrying this job.')
            print(f'Waiting {(deadline - now).total_seconds()}s longer for approval...')
            sleep(10)
        else:
            print(f'Error {resp.status_code} from Mastermind while requesting role')
            print(resp.text)
            resp.raise_for_status()


def role_request(access_document):
    slug = os.environ["BUILDKITE_PIPELINE_SLUG"]
    aws_region = os.environ['AWS_REGION']
    aws_account_id = os.environ['AWS_ACCOUNT_ID']
    caller_identity = sts.get_caller_identity()

    print_debug({'caller_identity': caller_identity})

    default_permissions = [
        {
            'arns': [
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/build/common/*',
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/build/{slug}/*',
            ],
            'actions': [
                'ssm:getparameter',
                'ssm:getparameters',
                'ssm:getparametersbypath',
            ]
        },
        {
            'arns': [
                'arn:aws:lambda:us-west-2:221344006312:function:build-numbers',
            ],
            'actions': [
                'lambda:invokefunction',
            ]
        },
        {
            'arns': [
                'arn:aws:s3:::tc-build-scratch',
                'arn:aws:s3:::tc-build-scratch/*',
            ],
            'actions': [
                's3:getobject',
                's3:putobject',
                's3:deleteobject',
                's3:getobjectversion',
                's3:listbucket',
            ]
        },
        {
            'arns': [
                f'arn:aws:ecr:{aws_region}:{aws_account_id}:*',
            ],
            'actions': [
                'ecr:getauthorizationtoken',
                'ecr:describerepositories',
            ],
        },
        {
            'arns': [
                f'arn:aws:ecr:{aws_region}:{aws_account_id}:repository/*',
            ],
            'actions': [
                'ecr:batchchecklayeravailability',
                'ecr:getdownloadurlforlayer',
                'ecr:getrepositorypolicy',
                'ecr:listimages',
                'ecr:describeimages',
                'ecr:batchgetimage',
                'ecr:initiatelayerupload',
                'ecr:uploadlayerpart',
                'ecr:completelayerupload',
                'ecr:putimage',
            ],
        },
    ]

    resources = default_permissions
    if access_document is not None:
        resources = resources + access_document.get('common', {}).get('resources', [])

    return {
        'project_identifier': f'buildkite/{slug}',
        'environment': 'build',
        'principal': {
            'type': 'AWS',
            'value': caller_identity['Arn'],
        },
        'permissions': {
            'resources': resources,
        },
    }


def github_raw_url_from_clone_url(clone_url, ref, path):
    url = urlsplit(clone_url)
    if not url.scheme == 'https':
        raise UnsupportedCloneURL("only https clone URLs are supported")
    if url.path.endswith('.git'):
        url = url._replace(path=url.path[0:-4])
    if url.netloc == 'git.corp.tc':
        url = url._replace(netloc='raw.git.corp.tc',
                           path=f'{url.path}/{ref}/{path}')
    elif url.netloc == 'github.com':
        url = url._replace(netloc='raw.github.com',
                           path=f'{url.path}/{ref}/{path}')
    else:
        raise UnsupportedCloneURL(f"don't know how to retrieve raw files from git repo on domain {url.netloc}")
        # FIXME: maybe should just move code checkout to this context to enable
        # other clone URL situations and to provision the bootstrap container
        # with a more specific/jailed build directory
    return urlunsplit(url)


def get_access_document(build_env):
    def sub_env(node):
        if isinstance(node, dict):
            return {k: sub_env(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [sub_env(v) for v in node]
        elif isinstance(node, str):
            def resolve_var(match):
                return build_env[match.group(1)]
            return env_var_placeholder_pattern.sub(resolve_var, node)
        else:
            return node

    clone_url = build_env['BUILDKITE_REPO']
    ref = build_env['BUILDKITE_COMMIT']
    access_path = build_env.get('MASTERMIND_ACCESS_DOCUMENT_PATH',
                                '.buildkite/aws_access.json')
    url = github_raw_url_from_clone_url(clone_url, ref, access_path)
    contents = urlopen(url)
    doc = json.load(contents)
    doc = sub_env(doc)

    if 'common' not in doc or 'resources' not in doc['common']:
        raise AccessDocumentFormatError('Access document is missing requisite ".common.resources" list')

    return doc
