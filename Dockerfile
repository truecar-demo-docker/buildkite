FROM ubuntu:18.04

RUN apt-get update \
 && apt-get install -y \
      apt-transport-https \
      ca-certificates \
      curl \
      gnupg-agent \
      software-properties-common \
      python-pip

ARG DOCKER_VERSION="5:18.09.5~*"
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add - \
 && apt-key fingerprint 0EBFCD88 \
 && add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
 && apt-get update \
 && apt-get install -y "docker-ce-cli=${DOCKER_VERSION}"

RUN pip install awscli

ARG BUILDKITE_AGENT_VERSION="3.11.*"
RUN set -x \
 && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 32A37959C2FA5C3C99EFBC32A79206696452D198 \
 && add-apt-repository "deb https://apt.buildkite.com/buildkite-agent stable main" \
 && apt-get update \
 && apt-get install -y "buildkite-agent=${BUILDKITE_AGENT_VERSION}"
