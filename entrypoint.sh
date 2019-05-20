#!/bin/bash

set -euo pipefail
[[ ${BASH_DEBUG:-false} = true ]] && set -x

function copy_binary() {
    # /buildkite/bin is mounted as a host volume to make the binary available for
    # builds to share with their constituent containers. because it's a host volume,
    # it may end up empty or containing an old binary, so copy our binary to it in
    # that case. # FIXME: this doesn't seem terribly robust, but it works for now.
    local binary_path="$(which buildkite-agent)"
    [[ -x /buildkite/bin/buildkite-agent ]] && diff -q "$binary_path" /buildkite/bin/buildkite-agent && return 0
    cp -v "$binary_path" /buildkite/bin/
}

function container_id() {
    awk -F/ '/:name=systemd/ {print $NF}' /proc/self/cgroup
}

function configure_environment() {
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

    local this_image_id="$(docker inspect "$(container_id)" | jq -r '.[0].Image')"
    [[ ${this_image_id:-} ]] && agent_tags+=( "agent_docker_image=${this_image_id}" )

    for tag in ${agent_tags[@]}; do
        export BUILDKITE_AGENT_TAGS="${BUILDKITE_AGENT_TAGS+${BUILDKITE_AGENT_TAGS},}${tag}"
    done
}

function configure_docker() {
    # if credsStore=ecr-login we'll see warnings when pulling from any non-ECR
    # repo so this refines the config to just use ecr-login for our one REGISTRY_HOST

    [[ ${REGISTRY_HOST:-} ]] || return 0
    local conf_path="$HOME/.docker/config.json"
    local conf='{}'
    [[ -f ${conf_path} ]] && conf="$(< "$conf_path")"
    echo "${conf}" | jq --arg host "${REGISTRY_HOST}" '. + { credHelpers: ((.credHelpers // {}) + { ($host): "ecr-login" }) } | if .credsStore == "ecr-login" then del(.credsStore) else . end' > "${conf_path}"
}

configure_environment
configure_docker
copy_binary
exec "$@"
