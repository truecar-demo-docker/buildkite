#!/bin/bash

set -euo pipefail
[[ ${BUILDKITE_DEBUG:-false} = true ]] && set -x

function container_id() {
    awk -F/ '/:name=systemd/ {print $NF}' /proc/self/cgroup
}

function configure_agent() {
    if [[ -f /run/ec2-metadata ]]; then
        set -o allexport # this file is lines of `VAR=value` so use allexport to make those vars exported automatically
        source /run/ec2-metadata
        set +o allexport
    fi

    agent_tags=(
        "started=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    )

    [[ -n ${EC2_INSTANCE_ID:-} ]] && {
        export BUILDKITE_AGENT_NAME="${EC2_INSTANCE_ID}-${HOSTNAME:-$(hostname)}"
        agent_tags+=( "instance_id=${EC2_INSTANCE_ID}" )
    }

    [[ ${EC2_PRIVATE_IP:-} ]] && agent_tags+=( "ip_address=${EC2_PRIVATE_IP}" )

    local this_image_id
    this_image_id="$(docker inspect "$(container_id)" | jq -r '.[0].Image')"
    [[ ${this_image_id:-} ]] && agent_tags+=( "agent_docker_image=${this_image_id}" )

    for tag in "${agent_tags[@]}"; do
        export BUILDKITE_AGENT_TAGS="${BUILDKITE_AGENT_TAGS+${BUILDKITE_AGENT_TAGS},}${tag}"
    done
}

configure_agent

exec "$@"
