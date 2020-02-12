#!/bin/bash

set -euo pipefail
[[ ${BUILDKITE_DEBUG:-false} = true ]] && set -x

function copy_binary() {
    # /buildkite/bin is mounted as a host volume to make the binary available for
    # builds to share with their constituent containers. because it's a host volume,
    # it may end up empty or containing an old binary, so copy our binary to it in
    # that case. # FIXME: this doesn't seem terribly robust, but it works for now.
    local binary_path
    binary_path="$(command -v buildkite-agent)"

    [[ -x /buildkite/bin/buildkite-agent ]] && diff -q "$binary_path" /buildkite/bin/buildkite-agent && return 0
    cp -v "$binary_path" /buildkite/bin/
}

function container_id() {
    awk -F/ '/:name=systemd/ {print $NF}' /proc/self/cgroup
}

function parent_cgroup() {
    if [[ -n "${ECS_CONTAINER_METADATA_URI:-}" ]] ; then
        DOCKER_CONTAINER_ID=$(curl -s $ECS_CONTAINER_METADATA_URI | jq -r .DockerId)
        ECS_TASK_CGROUP=$(docker inspect --format='{{.HostConfig.CgroupParent}}' ${DOCKER_CONTAINER_ID})
        export ECS_TASK_CGROUP
    fi
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
copy_binary
parent_cgroup

exec "$@"
