import os
from os.path import basename
import json
from pathlib import Path

import boto3
import docker
from docker.types import LogConfig
from jinja2 import Template

import buildkite.mastermind as mastermind

docker_client = docker.from_env()
sts = boto3.client('sts')

maven_settings_template_path = Path(os.environ['BUILDKITE_RESOURCES_PATH']).joinpath('maven/settings.xml.j2')

# environment variables from os.environ to pass on to bootstrap container
environment_whitelist = [
    'AWS_EXECUTION_ENV',
    'AWS_REGION',
    'BASH_ENV',
    'REGISTRY_HOST',
    'REGISTRY_HOST_ECR',
    'REGISTRY_HOST_ARTIFACTORY',
    'ARTIFACTORY_API_KEY',
    'ARTIFACTORY_API_USER',
]

aws_env_vars = [
    'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_SESSION_TOKEN',
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


def entrypoint():
    return self_container().attrs.get('Config', {})['Entrypoint']


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

    env['BUILDKITE_BUILD_CHECKOUT_PATH'] = os.path.join(env['BUILDKITE_BUILD_PATH'], env['BUILDKITE_JOB_ID'])
    return env


def provision_aws_access(build_env):
    if os.environ.get('BUILDKITE_USE_MASTERMIND', 'false') == 'true':
        return mastermind.provision_aws_access_environ(build_env)
    else:
        return passthru_aws_env(build_env)


def passthru_aws_env(build_env):
    for var in aws_env_vars:
        if var in os.environ:
            build_env[var] = os.environ[var]
    return build_env


def build_container_config():
    build_env = provision_aws_access(build_environment(os.environ))
    job_id = build_env['BUILDKITE_JOB_ID']
    build_id = build_env['BUILDKITE_BUILD_ID']
    job_label = build_env.get('BUILDKITE_LABEL', '')
    project_slug = build_env.get('BUILDKITE_PROJECT_SLUG', '')
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
        'entrypoint': ['/buildkite/entrypoint-bootstrap.sh'],
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
        'log_config': LogConfig(type='local'),
    }

    if cgroup_parent():
        config['cgroup_parent'] = cgroup_parent()

    return config


def create_container(config):
    return docker_client.containers.create(**config)


def is_maven_agent():
    return os.environ['BUILDKITE_AGENT_META_DATA_QUEUE'] == 'maven'


def maven_docker_mount():
    vol_name, mount_path = os.environ['MAVEN_DOCKER_MOUNT'].split(':')
    return vol_name, Path(mount_path)


def provision_maven_settings():
    artifactory_api_key = os.environ['ARTIFACTORY_API_KEY']
    artifactory_api_user = os.environ['ARTIFACTORY_API_USER']
    volume_name, mount_path = maven_docker_mount()
    settings_path = mount_path.joinpath('settings.xml')
    template = Template(maven_settings_template_path.read_text(encoding='utf-8'))
    settings_xml = template.render(username=artifactory_api_user, password=artifactory_api_key)
    print({'settings.xml': settings_xml})
    with open(settings_path, 'w') as f:
        print(settings_xml, file=f)
