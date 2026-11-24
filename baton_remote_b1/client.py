"""Minimal testable loopback client for the read-only Baton Remote gateway."""
import argparse
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from .agent import load_token_file

ALLOWED = {'health': '/v1/health', 'pause-status': '/v1/pause-status'}


def request_status(base_url, token, operation, timeout=3):
    parsed = urlsplit(base_url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port is None):
        raise ValueError('only http://127.0.0.1:PORT is accepted; use SSH forwarding')
    if operation not in ALLOWED:
        raise ValueError('operation not allowlisted')
    req = Request('http://127.0.0.1:%d%s' % (parsed.port, ALLOWED[operation]),
                  headers={'Authorization': 'Bearer ' + token}, method='GET')
    # Do not leak the local authorization header to an environment-configured proxy.
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError('unexpected response')
        raw = response.read(2049)
        if len(raw) > 2048:
            raise ValueError('oversized gateway response')
        return json.loads(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only Baton gateway client')
    parser.add_argument('operation', choices=sorted(ALLOWED))
    parser.add_argument('--url', default='http://127.0.0.1:8787')
    parser.add_argument('--token-file', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(request_status(args.url, load_token_file(args.token_file), args.operation), sort_keys=True))


if __name__ == '__main__':
    main()
