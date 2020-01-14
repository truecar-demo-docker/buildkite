#!/bin/bash

set -euo pipefail
set -x

# ensure the rest of these tools are at least runnable
jq --version
docker-compose version
docker version
aws --version
docker-credential-ecr-login version
git version
git lfs version
