import sys
import time
import json
import re
from urllib.request import urlopen
from urllib.parse import urlsplit, urlunsplit
from urllib.error import HTTPError

class AccessDocumentFormatError(Exception):
    pass

class UnsupportedCloneURL(Exception):
    pass


env_var_placeholder_pattern = re.compile('@@([a-zA-Z0-9_]+)@@')


def request_access(access_document):
    pass


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
