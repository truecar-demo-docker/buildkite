#!/bin/bash

# just throw w/e seems like it would be useful to check in a real cluster setting I guess

set -euo pipefail

ARTIFACTORY_REGISTRY=registry.dev.true.sh
ECR_REGISTRY=221344006312.dkr.ecr.us-west-2.amazonaws.com
ARTIFACTORY_TAG="${ARTIFACTORY_REGISTRY}"/test
ECR_TAG="${ECR_REGISTRY}"/test

docker login "${ARTIFACTORY_REGISTRY}" -u "${ARTIFACTORY_USER}" -p "${ARTIFACTORY_PASS}"

docker build --no-cache -f test/Dockerfile.int -t "${ECR_TAG}" .

docker tag "${ECR_TAG}" "${ARTIFACTORY_TAG}"

docker push "${ECR_TAG}"

docker push "${ARTIFACTORY_TAG}"
