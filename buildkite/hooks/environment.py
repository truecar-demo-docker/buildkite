# This is the `environment` agent / global hook; it is invoked by and its
# output evaled by the bash script called `environment` which is then sourced
# by the bootstrap

import os
import sys
import re
import subprocess

import boto3
from botocore.exceptions import ClientError, ParamValidationError
from botocore.config import Config

boto_config = Config(retries=dict(max_attempts=30))
ssm = boto3.client('ssm', config=boto_config)

ssm_param_pattern = re.compile('^ssm-parameter:(.+)$')
metadata_param_pattern = re.compile('^buildkite-meta-data:(.+)$')


def buildkite_metadata_get(var, key):
    try:
        command = ['buildkite-agent', 'meta-data', 'get', key]
        return subprocess.check_output(command).decode().rstrip('\n')
    except subprocess.CalledProcessError as e:
        print(f'ERROR while attempting to resolve ${var} using buildkite '
              f'meta-data {key}: exit={e.returncode}',
              file=sys.stderr)


def resolve_ssm_var(var, param_path):
    try:
        resp = ssm.get_parameter(Name=param_path, WithDecryption=True)
        return resp['Parameter']['Value']
    except ssm.exceptions.ParameterNotFound:
        print(f'ERROR while resolving var {var} using SSM parameter {key}: '
              'ParameterNotFound', file=sys.stderr)
    except ParamValidationError as e:
        print("ERROR boto3.ParamValidationError while resolving var {var} "
              f"using SSM parameter {key}: {e}", file=sys.stderr)
    except ClientError as e:
        print(f'ERROR boto3.ClientError while resolving var {var} using SSM '
              f'parameter {key}: {e}', file=sys.stderr)


def export_var(var, value):
    if value:
        print(f"export {var}='{value}'")
    else:
        print("^^^ +++", file=sys.stderr) # tell buildkite to expand this section in the log output, to reveal this warning
        print(f"WARNING: Variable {var} was resolved to None (likely an error "
              "occurred); variable will NOT be present in build.",
              file=sys.stderr)
        print(f'unset {var}')


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
