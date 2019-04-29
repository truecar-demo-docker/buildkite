FROM buildkite/agent:3-ubuntu

RUN apt-get update \
 && apt-get install -y \
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

RUN curl -fsSL https://s3-us-west-2.amazonaws.com/tc-build-binaries/docker-credential-ecr-login-v0.3.0-linux-x64.bin -O /usr/local/bin/docker-credential-ecr-login \
 && chmod +x /usr/local/bin/docker-credential-ecr-login
COPY docker-config.json /root/.docker/config.json
