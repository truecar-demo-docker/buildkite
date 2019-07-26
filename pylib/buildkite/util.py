import sys
import os
from urllib.parse import urlsplit, urlunsplit

from buildkite.errors import UnsupportedCloneURL


def print_debug(msg):
    if os.environ.get('BUILDKITE_AGENT_DEBUG', 'false') == 'true':
        print(msg)


def print_warn(msg):
    print(msg, file=sys.stderr)
    # expand this section
    print(f'^^^ +++', file=sys.stderr)


def enable_http_debug_logging():
    import logging

    # These two lines enable debugging at httplib level (requests->urllib3->http.client)
    # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
    # The only thing missing will be the response.body which is not logged.
    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        import httplib as http_client
    http_client.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


def github_http_url_from_clone_url(clone_url, ref, path):
    url = urlsplit(clone_url)
    if not url.scheme == 'https':
        raise UnsupportedCloneURL("only https clone URLs are supported")
    if url.path.endswith('.git'):
        url = url._replace(path=url.path[0:-4])
    if url.netloc == 'git.corp.tc' or url.netloc == 'github.com':
        url = url._replace(path=f'{url.path}/{ref}/{path}')
    else:
        raise UnsupportedCloneURL(f"don't know how to reshape git clone url for domain {url.netloc}")
    return urlunsplit(url)


def github_raw_url_from_clone_url(clone_url, ref, path):
    url = urlsplit(clone_url)
    if not url.scheme == 'https':
        raise UnsupportedCloneURL("only https clone URLs are supported")
    if url.path.endswith('.git'):
        url = url._replace(path=url.path[0:-4])
    if url.netloc == 'git.corp.tc':
        url = url._replace(netloc='raw.git.corp.tc',
                           path=f'{url.path}/{ref}/{path}')
    elif url.netloc == 'github.com':
        url = url._replace(netloc='raw.github.com',
                           path=f'{url.path}/{ref}/{path}')
    else:
        raise UnsupportedCloneURL(f"don't know how to retrieve raw files from git repo on domain {url.netloc}")
        # FIXME: maybe should just move code checkout to this context to enable
        # other clone URL situations and to provision the bootstrap container
        # with a more specific/jailed build directory
    return urlunsplit(url)
