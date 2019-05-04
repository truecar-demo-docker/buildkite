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

[[ ${EC2_PRIVATE_IP:-} ]] && export BUILDKITE_AGENT_TAGS="ip_address=${EC2_PRIVATE_IP},${BUILDKITE_AGENT_TAGS:-}"

[[ ${CONFIG_SHA:-} ]] && export BUILDKITE_AGENT_TAGS="config_sha=${CONFIG_SHA},${BUILDKITE_AGENT_TAGS:-}"

container_id="$(awk -F/ '/1:name=systemd/ {print $NF}' /proc/self/cgroup)"
[[ ${container_id:-} ]] && this_image_id="$(docker inspect "${container_id:?}" | jq -r '.[0].Image')"
[[ ${this_image_id:-} ]] && export BUILDKITE_AGENT_TAGS="agent_docker_image=${this_image_id},${BUILDKITE_AGENT_TAGS:-}"


if [[ -n ${REGISTRY_HOST:-} ]]; then
    conf_path="$HOME/.docker/config.json"
    conf='{}'
    if [[ -f ${conf_path} ]]; then
        conf="$(< "$conf_path")"
    fi
    echo "${conf}" | jq --arg host "${REGISTRY_HOST}" '. + { credHelpers: ((.credHelpers // {}) + { ($host): "ecr-login" }) } | if .credsStore == "ecr-login" then del(.credsStore) else . end' > "${conf_path}"
fi

# /buildkite/bin is mounted as a host volume to make the binary available for
# builds to share with their constituent containers. because it's a host volume,
# it may end up empty or containing an old binary, so copy our binary to it in
# that case. # FIXME: this doesn't seem terribly robust, but it works for now.
[[ -x /buildkite/bin/buildkite-agent ]] && diff -q /usr/local/bin/buildkite-agent /buildkite/bin/buildkite-agent || cp -v /usr/local/bin/buildkite-agent /buildkite/bin/

exec "$@"
