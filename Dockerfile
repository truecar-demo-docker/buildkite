FROM ubuntu:18.04

RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        git \
        gnupg-agent \
        openssh-client \
        python3-pip \
        software-properties-common

ARG DOCKER_VERSION="5:18.09.5~*"
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add - \
 && apt-key fingerprint 0EBFCD88 \
 && add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
 && apt-get update \
 && apt-get install -y "docker-ce-cli=${DOCKER_VERSION}"

ARG DOCKER_COMPOSE_VERSION=1.24.0
RUN curl -fsSL "https://github.com/docker/compose/releases/download/1.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose \
 && chmod +x /usr/local/bin/docker-compose

RUN pip3 install awscli

ARG JQ_VERSION=1.6
RUN set -x \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/jq-release.key | gpg --import \
  && curl -fsSL https://github.com/stedolan/jq/releases/download/jq-${JQ_VERSION}/jq-linux64 -o /usr/local/bin/jq \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/v${JQ_VERSION}/jq-linux64.asc | gpg --verify - /usr/local/bin/jq \
  && chmod +x /usr/local/bin/jq

# https://github.com/awslabs/amazon-ecr-credential-helper/releases
ARG ECR_HELPER_VERSION=0.3.0

RUN curl -fsSL https://s3-us-west-2.amazonaws.com/tc-build-binaries/docker-credential-ecr-login-v${ECR_HELPER_VERSION}-linux-x64.bin -o /usr/local/bin/docker-credential-ecr-login \
  && chmod +x /usr/local/bin/docker-credential-ecr-login

# https://github.com/buildkite/agent/releases
ARG BUILDKITE_AGENT_VERSION="3.12.*"

RUN set -x \
 && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 32A37959C2FA5C3C99EFBC32A79206696452D198 \
 && add-apt-repository "deb https://apt.buildkite.com/buildkite-agent stable main" \
 && apt-get update \
 && apt-get install -y "buildkite-agent=${BUILDKITE_AGENT_VERSION}"

RUN set -x \
  && add-apt-repository ppa:git-core/ppa \
  && apt-get update \
  && apt-get upgrade -y git \
  && apt-get install -y git-lfs \
  && git lfs install

# user buildkite-agent was created by apt package buildkite-agent
RUN mkdir -v /buildkite \
  && chown buildkite-agent /buildkite \
  # FIXME ideally we have a `docker` group
  && usermod -aG root buildkite-agent
USER buildkite-agent
# this is the $HOME
WORKDIR /var/lib/buildkite-agent

RUN mkdir -pv \
      /buildkite/builds \
      /buildkite/hooks \
      /buildkite/plugins \
      /buildkite/bin

ENV BUILDKITE_BUILD_PATH=/buildkite/builds \
    BUILDKITE_HOOKS_PATH=/buildkite/hooks \
    BUILDKITE_PLUGINS_PATH=/buildkite/plugins \
    BUILDKITE_RESOURCES_PATH=/buildkite/resources

# For each container, these start out empty unless a host path is mounted
VOLUME /buildkite/builds
VOLUME /buildkite/plugins

# make the binary available in a volume for sharing with bootstrap containers
RUN cp /usr/bin/buildkite-agent /buildkite/bin/buildkite-agent
VOLUME /buildkite/bin

COPY --chown=999:999 pylib/requirements.txt ./pylib/
RUN cd ./pylib/ && pip3 install -r requirements.txt

COPY --chown=999:999 pylib/ ./pylib/
ENV PYTHONPATH "${PYTHONPATH}:/var/lib/buildkite-agent/pylib"

COPY --chown=999:999 docker-config.json ./.docker/config.json
COPY --chown=999:999 ./buildkite/ /buildkite

ENV BASH_ENV=$BUILDKITE_RESOURCES_PATH/bash_env \
    BUILDKITE_BOOTSTRAP_SCRIPT_PATH=/buildkite/bootstrap.sh \
    # Use no config file, we'll config Buildkite exclusively via ENV
    BUILDKITE_AGENT_CONFIG=''

STOPSIGNAL SIGINT
ENTRYPOINT ["/buildkite/entrypoint-agent.sh"]
CMD ["/buildkite/bin/buildkite-agent", "start"]
