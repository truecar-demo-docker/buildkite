# This is the `environment` agent / global hook; it is invoked by and its
# output evaled by the bash script called `environment` which is then sourced
# by the bootstrap

import os
import re
import subprocess

import boto3
from botocore.exceptions import ClientError, ParamValidationError
from botocore.config import Config

from buildkite.util import print_warn

boto_config = Config(retries=dict(max_attempts=30))
ssm = boto3.client('ssm', config=boto_config)
# s3 = boto3.client('s3', config=boto_config)

ssm_param_pattern = re.compile('^ssm-parameter:(.+)$')
metadata_param_pattern = re.compile('^buildkite-meta-data:(.+)$')


def warn(str):
    print_warn(f'\x1b[31m{str}\x1b[0m')


def buildkite_metadata_get(var, key):
    try:
        command = ['buildkite-agent', 'meta-data', 'get', key]
        return subprocess.check_output(command).decode().rstrip('\n')
    except subprocess.CalledProcessError as e:
        warn(f'ERROR while attempting to resolve ${var} using buildkite meta-data {key}: exit={e.returncode}')


def resolve_ssm_var(var, param_path):
    try:
        resp = ssm.get_parameter(Name=param_path, WithDecryption=True)
        return resp['Parameter']['Value']
    except ssm.exceptions.ParameterNotFound:
        warn(f'ERROR while resolving var {var} using SSM parameter {param_path}: ParameterNotFound')
    except ParamValidationError as e:
        warn(f"ERROR boto3.ParamValidationError while resolving var {var} using SSM parameter {param_path}: {e}")
    except ClientError as e:
        warn(f'ERROR boto3.ClientError while resolving var {var} using SSM parameter {param_path}: {e}')


def export_var(var, value):
    if value is None:
        warn(f"WARNING: Variable {var} was resolved to None (likely an error "
             "occurred); variable value will be set null ('').")
        value = ''
    print(f"export {var}='{value}'")


def print_environment_exports():
    for var, value in os.environ.items():
        match = ssm_param_pattern.match(value)
        if match is not None:
            key = match.group(1)
            value = resolve_ssm_var(var, key)
            export_var(var, value)
            continue

        match = metadata_param_pattern.match(value)
        if match is not None:
            key = match.group(1)
            value = buildkite_metadata_get(var, key)
            export_var(var, value)
            continue

        # else: no-op, don't export an overriden value for this var


def main():
    print_environment_exports()


if __name__ == '__main__':
    main()
