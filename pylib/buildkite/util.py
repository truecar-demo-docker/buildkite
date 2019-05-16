import os

def print_debug(msg):
    if os.environ.get('BUILDKITE_AGENT_DEBUG', False):
        print(msg)

def print_warn(msg):
    print(msg)
    # expand this section
    print(f'^^^ +++')
