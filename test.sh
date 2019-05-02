#!bin/bash

set -euo pipefail

test -x /buildkite/bootstrap-via-docker
# ensure /buildkite volume has captured the binary linked into the /buildkite/bin dir before volume's creation
/buildkite/bin/buildkite-agent --version
# ensure the rest of these tools are at least runnable
jq --version
docker-compose version
docker version
aws --version
docker-credential-ecr-login version
