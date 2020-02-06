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

ARG DOCKER_VERSION="5:18.09.8~*"
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add - \
 && apt-key fingerprint 0EBFCD88 \
 && add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
 && apt-get update \
 && apt-get install -y "docker-ce-cli=${DOCKER_VERSION}"

ARG DOCKER_COMPOSE_VERSION=1.24.1
RUN curl -fsSL "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose \
 && chmod +x /usr/local/bin/docker-compose

ARG JQ_VERSION=1.6
RUN set -x \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/jq-release.key | gpg --import \
  && curl -fsSL https://github.com/stedolan/jq/releases/download/jq-${JQ_VERSION}/jq-linux64 -o /usr/local/bin/jq \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/v${JQ_VERSION}/jq-linux64.asc | gpg --verify - /usr/local/bin/jq \
  && chmod +x /usr/local/bin/jq

# https://github.com/awslabs/amazon-ecr-credential-helper/releases
ARG ECR_HELPER_VERSION=0.3.1
RUN cd /tmp \
  && curl -fsSLO https://amazon-ecr-credential-helper-releases.s3.us-east-2.amazonaws.com/${ECR_HELPER_VERSION}/linux-amd64/docker-credential-ecr-login \
  && curl -fsSL https://amazon-ecr-credential-helper-releases.s3.us-east-2.amazonaws.com/${ECR_HELPER_VERSION}/linux-amd64/docker-credential-ecr-login.sha256 | sha256sum -c \
  && install -v docker-credential-ecr-login /usr/local/bin/docker-credential-ecr-login

# https://github.com/buildkite/agent/releases
ARG BUILDKITE_AGENT_VERSION="3.13.2-3097"
RUN set -x \
 && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 32A37959C2FA5C3C99EFBC32A79206696452D198 \
 && add-apt-repository "deb https://apt.buildkite.com/buildkite-agent stable main" \
 && apt-get update \
 && apt-get install -y "buildkite-agent=${BUILDKITE_AGENT_VERSION}"

RUN set -x \
  && add-apt-repository ppa:git-core/ppa \
  && apt-get update \
  && apt-get install --only-upgrade -y git \
  && apt-get install -y git-lfs \
  && git lfs install

RUN pip3 install boto3==1.9.149 awscli==1.16.204

RUN mkdir -pv \
      /buildkite/builds \
      /buildkite/hooks \
      /buildkite/plugins \
      /buildkite/bin

# allow ecr login and credential helper to coexist
# https://github.com/awslabs/amazon-ecr-credential-helper/issues/154#issuecomment-472988526
COPY ./docker-credential-ecr-login-no-error /usr/local/bin/docker-credential-ecr-login-no-error
RUN chmod +x /usr/local/bin/docker-credential-ecr-login-no-error

COPY ./buildkite/ /buildkite
COPY ./build-tools/* /usr/local/bin/
COPY docker-config.json /root/.docker/config.json

RUN cp /usr/bin/buildkite-agent /buildkite/bin/buildkite-agent
VOLUME /buildkite/bin

ENV BUILDKITE_BUILD_PATH=/buildkite/builds \
    BUILDKITE_HOOKS_PATH=/buildkite/hooks \
    BUILDKITE_PLUGINS_PATH=/buildkite/plugins \
    BUILDKITE_RESOURCES_PATH=/buildkite/resources \
    BUILDKITE_AGENT_BINARY_PATH=/buildkite/bin/buildkite-agent \
    BUILDKITE_AGENT_CONFIG=''

ENV AWS_SDK_LOAD_CONFIG=true

ENV PYTHONIOENCODING=utf8

ENTRYPOINT ["/buildkite/entrypoint-agent.sh"]
CMD ["/usr/bin/buildkite-agent", "start"]
