#!/bin/bash

set -euo pipefail
[[ ${BUILDKITE_AGENT_DEBUG:-false} == true ]] && set -x

function configure_docker() {
    local conf_path="$HOME/.docker/config.json"
    local conf='{}'
    [[ -f ${conf_path} ]] && conf="$(< "$conf_path")"
    echo "${conf}" | \
        jq --arg ecr_host "${REGISTRY_HOST_ECR}" \
           --arg artifactory_password "${ARTIFACTORY_API_KEY}" \
           --arg artifactory_user "${ARTIFACTORY_API_USER}" \
           --arg artifactory_host "${REGISTRY_HOST_ARTIFACTORY}" \
        '. + {
            credHelpers: ((.credHelpers // {}) + {
                ($ecr_host): "ecr-login",
            }),
            auths: ((.auths // {}) + {
                ($artifactory_host): {
                    auth: ("\($artifactory_user):\($artifactory_password)" | @base64)
                },
            }),
        } | if .credsStore == "ecr-login" then del(.credsStore) else . end' > "${conf_path}"
}

setup_aws_config() {
    [[ ${MASTERMIND_AWS_CONFIG_FILE_URL:-} ]] || return 0

    mkdir -pv "$HOME/.aws"

    cat <<EOF > "$HOME/.aws/credentials"
[mastermind]
role_arn = ${MASTERMIND_ROLE_ARN}
session_name = buildkite-${BUILDKITE_JOB_ID}
credential_source = EcsContainer
EOF

    while true; do
        # retry this, as sometimes (when freshly provisioned) it can take a moment to become readable
        aws s3 --profile mastermind cp "${MASTERMIND_AWS_CONFIG_FILE_URL}" "$HOME/.aws/config" && break
        sleep 1
    done

    # FIXME: perhaps move this into Mastermind?
    sed -i "s:credential_source\s*=\s*EcsContainer:source_profile = mastermind\nsession_name = buildkite-${BUILDKITE_JOB_ID}:g" "$HOME/.aws/config"

    [[ ${BUILDKITE_AGENT_DEBUG:-false} = true ]] && cat "$HOME/.aws/config"

    # explicitly instruct clients to use shared config file
    export AWS_SDK_LOAD_CONFIG=true
    # instruct clients to use profile "default" from the mastermind config
    export AWS_PROFILE=default

    # retry this, as sometimes (when freshly provisioned) it can take a moment to become assumable
    failures=0
    while true; do
        # sanity check that default config works as expected
        debug_arg=()
        [[ $failures -gt 4 ]] && debug_arg+=(--debug)
        aws "${debug_arg[@]}" \
            sts get-caller-identity --output json \
            | tee /dev/stderr \
            | jq -er .Arn \
            | grep -Eq 'assumed-role/mm(_dev)?_role_' \
            && break
        sleep "$failures"
        ((failures+=1))
    done
}

configure_docker
setup_aws_config

exec "$@"
