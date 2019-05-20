import os
import time
from os.path import basename
import json
from urllib.error import HTTPError
from urllib.parse import urljoin

import boto3
import docker
from docker.types import LogConfig

from buildkite.util import print_warn
import buildkite.mastermind as mastermind

docker_client = docker.from_env()
sts = boto3.client('sts')

# environment variables from os.environ to pass on to bootstrap container
environment_whitelist = [
    'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI',
    'AWS_EXECUTION_ENV',
    'AWS_REGION',
    'BASH_ENV',
    'REGISTRY_HOST',
]


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


def build_environment(environ):
    def unescape_value(value):
        '''
        values in the env file are encoded via Golang fmt.Sprintf('%q'), so they
        are wrapped with ", and any " within are backslash-escaped
        '''
        return value.strip('"').replace('\\"', '"')

    # Copy all BUILDKITE_* vars
    env = {var: environ[var] for var in environ if var.startswith('BUILDKITE_')}

    # additional vars specified in the whitelist
    for var in environment_whitelist:
        if var in environ:
            env[var] = environ[var]

    if 'AWS_REGION' in env:
        env['AWS_DEFAULT_REGION'] = env['AWS_REGION']

    # job vars from the env file
    env_file = env.get('BUILDKITE_ENV_FILE', None)
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
    # TODO: only do this once per build, save the artifact to meta-data and check there first
    print('~~~ Provision AWS access via Mastermind')
    access_document = None
    max_attempts = 4
    for attempt in range(max_attempts):
        # TODO: from retrying import retry <-- clean up this retry logic
        try:
            access_document = mastermind.get_access_document(build_env)
            break
        except HTTPError as e:
            print_warn(f'ERROR: Received HTTP {e.code} while attempting to retrieve Mastermind access document from {e.url}.')
            if e.code == 404:
                break # no retry for 404s; avoid a long delay for Mastermind-unaware projects
        except Exception as e:
            print_warn(f'ERROR: {e}')
            break # no retry
        if attempt != max_attempts:
            print_warn(f'Will retry. Retries remaining: {max_attempts-attempt}')
            time.sleep(4**(attempt))
    if access_document is None:
        print_warn("Failed to retrieve Mastermind access document, providing only default permissions.")

    for attempt in range(max_attempts):
        try:
            resp = mastermind.request_access(access_document)
            break
        except HTTPError as e:
            print_warn(f'ERROR: Received HTTP {e.code} while attempting to retrieve Mastermind access document from {e.url}.')
            if attempt == max_attempts:
                raise(e)
        except Exception as e:
            print_warn(f'ERROR: Error while provisioning access:')
            raise(e)
        print_warn(f'Will retry. Retries remaining: {max_attempts-attempt}')
        time.sleep(4**(attempt))

    role_arn = resp['arn']
    build_id = build_env['BUILDKITE_BUILD_ID']

    assume_role_response = sts.assume_role(RoleArn=role_arn, RoleSessionName=f'buildkite@build-{build_id}')

    build_env['MASTERMIND_ACCESS_KEY_ID'] = assume_role_response['Credentials']['AccessKeyId']
    build_env['MASTERMIND_SECRET_ACCESS_KEY'] = assume_role_response['Credentials']['SecretAccessKey']
    build_env['MASTERMIND_SESSION_TOKEN'] = assume_role_response['Credentials']['SessionToken']

    mastermind_bucket = os.environ['MASTERMIND_CONFIGS_BUCKET']
    build_env['MASTERMIND_AWS_CONFIG_FILE_URL'] = '/'.join([f's3://{mastermind_bucket}', 'aws_configs',
                                                 'buildkite', build_env["BUILDKITE_PIPELINE_SLUG"],
                                                 'build', 'config'])

    # disable access to the ECS task role which may have been passed from the agent
    del build_env['AWS_CONTAINER_CREDENTIALS_RELATIVE_URI']

    return build_env


def build_container_config():
    build_env = build_environment(os.environ)
    if os.environ.get('BUILDKITE_USE_MASTERMIND', 'false') == 'true':
        build_env = provision_aws_access(build_env)

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
        'environment': build_env,
        'network_mode': f'container:{self_container_id()}',
        'log_config': LogConfig(
            type='local',
        ),
    }

    if cgroup_parent():
        config['cgroup_parent'] = cgroup_parent()

    return config


def create_container(config):
    return docker_client.containers.create(**config)
