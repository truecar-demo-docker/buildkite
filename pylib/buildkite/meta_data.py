import subprocess


def exists(key):
    command = ['buildkite-agent', 'meta-data', 'exists', key]
    return subprocess.check_call(command)


def get(key, default_value=None):
    command = ['buildkite-agent', 'meta-data', 'get', key]
    if default_value is not None:
        command.append(['--default', default_value])
    return subprocess.check_output(command).decode().rstrip('\n')


def set(key, value):
    command = ['buildkite-agent', 'meta-data', 'set', key, value]
    return subprocess.check_call(command)
