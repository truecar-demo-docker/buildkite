import os
import json

from buildkite.util import print_debug, enable_http_debug_logging
from buildkite.bootstrap import build_container_config, create_container, is_maven_agent, provision_maven_settings

if os.environ.get('BUILDKITE_AGENT_DEBUG_HTTP', 'false') == 'true':
    enable_http_debug_logging()

if is_maven_agent():
    print('~~~ Provisioning Maven settings.xml with Artifactory credentials')
    provision_maven_settings()

bootstrap_container_config = build_container_config()

print('~~~ Creating Bootstrap container')
print_debug(f'config = {json.dumps(bootstrap_container_config, indent=2)}') # FIXME: this is insecure, disable eventually!
container = create_container(bootstrap_container_config)
print_debug(f'Bootstrap container created. name={container.name} id={container.id}')

print_debug(f'~~~ Starting Bootstrap container')
os.execl('/usr/bin/docker', 'docker', 'start', '--attach', container.id)
