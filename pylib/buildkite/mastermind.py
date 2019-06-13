import os
import json
import re
from datetime import timedelta
from urllib.request import urlopen
from urllib.parse import urljoin
from urllib.error import HTTPError

import requests
import boto3
import botocore.exceptions
from retrying import retry, RetryError

from buildkite.util import print_debug, github_raw_url_from_clone_url
from buildkite.errors import AccessDocumentFormatError


env_var_placeholder_pattern = re.compile('@@([a-zA-Z0-9_]+)@@')
sts = boto3.client('sts')


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


def request_access(build_env, access_document):
    def value_is_none(value):
        return value is None

    @retry(retry_on_result=value_is_none,
           retry_on_exception=exception_is_http,
           stop_max_delay=timedelta(minutes=10) / timedelta(milliseconds=1),
           wait_random_min=1000,
           wait_random_max=5000)
    def make_request(url, body):
        resp = requests.post(url, auth=('buildkite', os.environ['MASTERMIND_API_KEY']), json=body)
        if resp.status_code == 200:
            print(f'Mastermind access request successful.')
            return resp.json()
        elif resp.status_code == 202:
            print(f'Waiting for Mastermind access request to be approved...')
            return None
        else:
            print(f'Error {resp.status_code} from Mastermind while requesting role: {resp.text}')
            resp.raise_for_status()

    url = urljoin(os.environ['MASTERMIND_ENDPOINT'], 'role')
    body = role_request(build_env, access_document)
    print_debug(f'Requesting role from Mastermind:\n{body}')
    return make_request(url, body)


def role_request(build_env, access_document):
    aws_region = os.environ['AWS_REGION']
    aws_account_id = os.environ['AWS_ACCOUNT_ID']
    buildkite_pipeline_slug = build_env['BUILDKITE_PIPELINE_SLUG']
    role_arn = os.environ['BUILDKITE_TASK_ROLE_ARN']

    default_permissions = [
        {
            'arns': [
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/common/ENVIRONMENT',
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/common/ENVIRONMENT_NAME',
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/build/common/*',
                f'arn:aws:ssm:{aws_region}:{aws_account_id}:parameter/build/{buildkite_pipeline_slug}/*',
            ],
            'actions': [
                'ssm:GetParameter',
                'ssm:GetParameters',
                'ssm:GetParametersByPath',
            ]
        },

        {
            'arns': ['arn:aws:lambda:us-west-2:221344006312:function:build-numbers'],
            'actions': ['lambda:InvokeFunction']
        },

        {
            'arns': [
                'arn:aws:s3:::tc-build-scratch',
                'arn:aws:s3:::tc-build-scratch/*',
            ],
            'actions': [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:GetObjectVersion',
                's3:ListBucket',
            ]
        },

        {
            'arns': [
                f'arn:aws:ecr:{aws_region}:{aws_account_id}:*',
            ],
            'actions': [
                'ecr:GetAuthorizationToken',
                'ecr:DescribeRepositories',
            ],
        },

        {
            'arns': [
                f'arn:aws:ecr:{aws_region}:{aws_account_id}:repository/*',
            ],
            'actions': [
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:GetRepositoryPolicy',
                'ecr:ListImages',
                'ecr:DescribeImages',
                'ecr:BatchGetImage',
                'ecr:InitiateLayerUpload',
                'ecr:UploadLayerPart',
                'ecr:CompleteLayerUpload',
                'ecr:PutImage',
            ],
        },
    ]

    resources = default_permissions
    if access_document is not None:
        resources = resources + access_document.get('common', {}).get('resources', [])

    return {
        'project_identifier': project_identifier(build_env),
        'environment': 'build',
        'principal': {
            'type': 'AWS',
            'value': role_arn,
        },
        'permissions': {
            'resources': resources,
        },
    }


def provision_aws_access_environ(build_env):
    def exception_is_http_and_not_404(exception):
        will_retry = isinstance(exception, HTTPError) and exception.code != 404
        print(f'ERROR {"(will retry)" if will_retry else ""}: {exception}')
        return will_retry

    def exception_is_boto_clienterror(exception):
        will_retry = isinstance(exception, botocore.exceptions.ClientError)
        print(f'ERROR {"(will retry)" if will_retry else ""}: {exception}')
        return will_retry

    @retry(stop_max_attempt_number=4,
           retry_on_exception=exception_is_http_and_not_404,
           wait_exponential_multiplier=1000)
    def _get_access_document():
        return get_access_document(build_env)

    @retry(stop_max_delay=60000,
           retry_on_exception=exception_is_boto_clienterror,
           wait_exponential_multiplier=1000)
    def _get_mm_credentials(role_arn, session_name):
        return sts.assume_role(RoleArn=role_arn, RoleSessionName=session_name)['Credentials']

    # TODO: only do this once per build, save the artifact to meta-data and check there first
    print('~~~ Provision AWS access via Mastermind')

    try:
        print('Retrieving .buildkite/aws_access.json file for this commit')
        access_document = _get_access_document()
    except HTTPError:
        print(f"NOTICE: Failed to retrieve Mastermind access document, providing only default permissions.")
        access_document = None

    resp = request_access(build_env, access_document)
    role_arn = resp['arn']

    job_id = build_env['BUILDKITE_JOB_ID']
    credentials = _get_mm_credentials(role_arn, session_name=f'buildkite-{job_id}')

    build_env['MASTERMIND_ACCESS_KEY_ID'] = credentials['AccessKeyId']
    build_env['MASTERMIND_SECRET_ACCESS_KEY'] = credentials['SecretAccessKey']
    build_env['MASTERMIND_SESSION_TOKEN'] = credentials['SessionToken']

    mastermind_bucket = os.environ['MASTERMIND_CONFIGS_BUCKET']
    build_env['MASTERMIND_AWS_CONFIG_FILE_URL'] = '/'.join([f's3://{mastermind_bucket}', 'aws_configs',
                                                            project_identifier(build_env), 'build', 'config'])
    return build_env


def project_identifier(build_env):
    return f"buildkite:{build_env['BUILDKITE_PIPELINE_SLUG']}"


def exception_is_http(exception):
    will_retry = isinstance(exception, HTTPError)
    print(f'ERROR {"(will retry)" if will_retry else ""}: {exception}')
    return will_retry
