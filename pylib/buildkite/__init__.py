import sys
import os
import time
from os.path import basename
import json
import re
from urllib.request import urlopen
from urllib.parse import urlsplit, urlunsplit
from urllib.error import HTTPError

import docker
from docker.types import LogConfig

from buildkite.util import print_warn

docker_client = docker.from_env()


def self_container_id():
    with open('/proc/self/cgroup', 'r') as f:
        for line in f.readlines():
            idx, labels, cgroup = line.strip().split(':', 3)
            if labels == 'name=systemd':
                return basename(cgroup)

    return None


def self_container():
    return docker_client.containers.get(self_container_id())


def cgroup_parent():
    return self_container().attrs.get('HostConfig', {}).get('CgroupParent')


def docker_image():
    image = os.environ.get('BUILDKITE_BOOTSTRAP_DOCKER_IMAGE',
                           self_container().attrs['Image'])  # default to this container's image
    try:
        return docker_client.images.get(image)
    except docker.errors.ImageNotFound:
        pass  # image doesn't exist locally, so attempt to pull

    parts = image.split(':', 2)
    repo = parts[0]
    if len(parts) == 2:
        tag = parts[1]
    else:
        tag = 'latest'

    print(f'~~~ Pulling bootstrap docker image {repo}:{tag} ...')
    return docker_client.images.pull(repo, tag)


def build_environment():
    def unescape_value(value):
        '''
        values in this file are encoded via Golang fmt.Sprintf('%q'), so they
        are wrapped with " and any " within are backslash-escaped
        '''
        return value.strip('"').replace('\\"', '"')

    # environment variables from os.environ to pass on to bootstrap container
    whitelist = [
        'AWS_DEFAULT_REGION',
        'AWS_EXECUTION_ENV',
        'AWS_REGION',
        'BASH_ENV',
        'REGISTRY_HOST',
    ]

    # Copy all BUILDKITE_* vars
    env = {var: os.environ[var] for var in os.environ
           if var.startswith('BUILDKITE_')}

    # additional vars specified in the whitelist
    for var in whitelist:
        if var in os.environ:
            env[var] = os.environ[var]

    # job vars from the env file
    env_file = os.environ.get('BUILDKITE_ENV_FILE', None)
    if env_file:
        with open(env_file, 'r') as f:
            for line in f.readlines():
                var, value = line.strip().split('=', 1)
                value = unescape_value(value)
                env[var] = value
        # since the file isn't available to the bootstrap container, unset this var
        del env['BUILDKITE_ENV_FILE']
    return env


def provision_aws_access(build_env):
    print('~~~ Provision AWS access via Mastermind')
    access_document = {}
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            access_document = get_mastermind_access_document(build_env)
            break
        except HTTPError as e:
            print_warn(f'ERROR: Received HTTP {e.code} while attempting to retrieve Mastermind access document from {e.url}.')
        except Exception as e:
            print_warn(f'ERROR: {e}')
            break # no retry
        if attempt != max_attempts:
            print_warn(f'Will retry. Retries remaining: {max_attempts-attempt} times...')
            time.sleep(4**(attempt))

    for attempt in range(max_attempts):
        try:
            resp = mastermind_request_access(access_document)
            break
        except Exception as e:
            print_warn(f'WARN: Error while provisioning access: {e}')
            if attempt == max_attempts:
                raise(e)
        print_warn(f'Will retry. Retries remaining: {max_attempts-attempt} times...')
        time.sleep(4**(attempt))

    os.environ['AWS_ACCESS_KEY_ID'] = resp.access_key
    os.environ['AWS_SECRET_ACCESS_KEY'] = resp.secret_key
    os.environ['AWS_SESSION_TOKEN'] = resp.session_token


def build_container_config():
    job_id = os.environ['BUILDKITE_JOB_ID']
    build_id = os.environ['BUILDKITE_BUILD_ID']
    job_label = os.environ.get('BUILDKITE_LABEL', '')
    project_slug = os.environ.get('BUILDKITE_PROJECT_SLUG', '')
    image = docker_image()
    datadog_logs_config = {
        'buildkite.bootstrap.docker_image': image.id,
        'buildkite.build-id': build_id,
        'buildkite.job-id': job_id,
        'buildkite.label': job_label,
        'buildkite.project_slug': project_slug,
        'service': 'buildkite',
        'source': 'buildkite-agent',
    }
    volumes = {}
    config = {
        'image': image.id,
        'entrypoint': '/buildkite-entrypoint.sh',
        'command': ['buildkite-agent', 'bootstrap'],
        'name': f'buildkite-build-{build_id}-bootstrap-{job_id}',
        'labels': {
            'tc.buildkite.build_id': build_id,
            'tc.buildkite.job_id': job_id,
            'com.datadoghq.ad.logs': json.dumps(datadog_logs_config,
                                                indent=None, sort_keys=True,
                                                separators=(',', ':')),
        },
        'volumes_from': [self_container_id()],
        'volumes': volumes,
        'environment': build_environment(),
        'network_mode': f'container:{self_container_id()}',
        'log_config': LogConfig(
            type='local',
        ),
    }

    if cgroup_parent():
        config['cgroup_parent'] = cgroup_parent()

    return config
