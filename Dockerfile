FROM buildkite/agent:3-ubuntu

RUN apt-get update \
 && apt-get install -y \
      apt-transport-https \
      ca-certificates \
      curl \
      gnupg-agent \
      software-properties-common \
      python-pip

RUN pip install awscli
