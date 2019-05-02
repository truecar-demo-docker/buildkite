# This is the `environment` agent / global hook; it is invoked by and its
# output evaled by the bash script called `environment` which is then sourced
# by the bootstrap

import os
import sys
import re

import boto3

ssm_client = boto3.client('ssm')

ssm_param_pattern = re.compile('^ssm-parameter:([a-zA-Z0-9_./-]+)$')

for var, value in os.environ.items():
    match = ssm_param_pattern.match(value)
    if match is None:
        continue
    param_path = match.group(1)
    resp = ssm_client.get_parameter(Name=param_path, WithDecryption=True)

    print(f'Resolved ENV {var} value from SSM parameter {param_path}',
          file=sys.stderr)

    value = resp['Parameter']['Value']

    print(f"export {var}='{value}'")
