#!/bin/bash

set -euo pipefail
[[ ${BUILDKITE_AGENT_DEBUG:-false} = true ]] && set -x

if [[ -f /run/ec2-metadata ]]; then
    set -o allexport
    source /run/ec2-metadata
    set +o allexport
fi

[[ -n ${EC2_INSTANCE_ID:-} ]] && {
    export BUILDKITE_AGENT_NAME="${EC2_INSTANCE_ID}-%hostname"
    export BUILDKITE_AGENT_TAGS="instance_id=${EC2_INSTANCE_ID},${BUILDKITE_AGENT_TAGS:-}"
}

[[ -n ${EC2_PRIVATE_IP:-} ]] && export BUILDKITE_AGENT_TAGS="ip_address=${EC2_PRIVATE_IP},${BUILDKITE_AGENT_TAGS:-}"

[[ -n ${CONFIG_SHA:-} ]] && export BUILDKITE_AGENT_TAGS="config_sha=${CONFIG_SHA},${BUILDKITE_AGENT_TAGS:-}"

container_id="$(awk -F/ '/1:name=systemd/ {print $NF}' /proc/self/cgroup)"
this_image_id="$(docker inspect "${container_id:?}" | jq -r '.[0].Image')"
[[ -n ${this_image_id:-} ]] && export BUILDKITE_AGENT_TAGS="agent_docker_image=${this_image_id},${BUILDKITE_AGENT_TAGS:-}"

exec "$@"
