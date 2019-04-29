FROM buildkite/agent:3-ubuntu

RUN apt-get update \
 && apt-get install -y \
      amazon-ecr-credential-helper \
      apt-transport-https \
      ca-certificates \
      curl \
      gnupg-agent \
      python-pip \
      software-properties-common

RUN pip install awscli

RUN set -x \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/jq-release.key | gpg --import \
  && curl -fsSL https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 -o /usr/local/bin/jq \
  && curl -fsSL https://raw.githubusercontent.com/stedolan/jq/master/sig/v1.6/jq-linux64.asc | gpg --verify - /usr/local/bin/jq

COPY docker-config.json /root/.docker/config.json
