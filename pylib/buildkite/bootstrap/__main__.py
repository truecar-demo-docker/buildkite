import os
import json

from buildkite.util import print_debug
from buildkite.bootstrap import build_container_config, create_container


print('~~~ Creating Bootstrap container')
bootstrap_container_config = build_container_config()

print_debug('~~~ Container config:')
# FIXME: this is insecure, disable eventually!
print_debug(json.dumps(bootstrap_container_config))

container = create_container(bootstrap_container_config)
print_debug(f'Bootstrap container created. name={container.name} id={container.id}')

print(f'~~~ Starting Bootstrap container')
os.execl('/usr/bin/docker', 'docker', 'start', '--attach', container.id)
