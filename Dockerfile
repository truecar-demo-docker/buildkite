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

RUN pip3 install \
  awscli \
  boto3 \
  docker

ARG JQ_VERSION=1.6
RUN set -x \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/jq-release.key | gpg --import \
  && curl -fsSL https://github.com/stedolan/jq/releases/download/jq-${JQ_VERSION}/jq-linux64 -o /usr/local/bin/jq \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/v${JQ_VERSION}/jq-linux64.asc | gpg --verify - /usr/local/bin/jq \
  && chmod +x /usr/local/bin/jq

ARG ECR_HELPER_VERSION=0.3.0
RUN curl -fsSL https://s3-us-west-2.amazonaws.com/tc-build-binaries/docker-credential-ecr-login-v${ECR_HELPER_VERSION}-linux-x64.bin -o /usr/local/bin/docker-credential-ecr-login \
  && chmod +x /usr/local/bin/docker-credential-ecr-login

RUN mkdir -p /buildkite/builds /buildkite/hooks /buildkite/plugins /buildkite/bin
VOLUME /buildkite/builds
VOLUME /buildkite/plugins
VOLUME /buildkite/hooks

ARG BUILDKITE_AGENT_VERSION="3.11.*"
RUN set -x \
 && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 32A37959C2FA5C3C99EFBC32A79206696452D198 \
 && add-apt-repository "deb https://apt.buildkite.com/buildkite-agent stable main" \
 && apt-get update \
 && apt-get install -y "buildkite-agent=${BUILDKITE_AGENT_VERSION}" \
 && ln /usr/bin/buildkite-agent /buildkite/bin/buildkite-agent

# make the binary available in a volume for sharing with bootstrap containers
VOLUME /buildkite/bin

COPY docker-config.json /root/.docker/config.json
COPY entrypoint.sh /buildkite-entrypoint.sh

ENTRYPOINT ["/buildkite-entrypoint.sh"]
CMD ["buildkite-agent", "start"]
