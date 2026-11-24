"""One-shot local entrypoint for an authenticated Baton Greg job.

The transport must be an independently authenticated Baton connector. Never
pipe untrusted chat text directly to this program. Supply the secret via a
private file; do not put it on a command line or in the repository.
"""
import argparse
import json
import os
import stat
import sys
from remote_security.chatgpt_greg_dispatch import AuthenticatedGregDispatcher

def read_secret(path):
    fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise PermissionError("secret file must be owner-only regular file")
        data=os.read(fd,257)
        if not 32 <= len(data) <= 256:
            raise ValueError("secret length must be 32..256 bytes")
        return data
    finally:
        os.close(fd)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--secret-file",required=True)
    p.add_argument("--socket",required=True)
    p.add_argument("--conversations",required=True,
                   help="comma-separated allowlisted conversation IDs")
    p.add_argument("--executables",required=True,
                   help="comma-separated exact executable paths")
    a=p.parse_args()
    raw=sys.stdin.buffer.read(16385)
    if len(raw)>16384: raise ValueError("oversized input")
    doc=json.loads(raw)
    if type(doc) is not dict or set(doc)!={"request","signature"}:
        raise ValueError("invalid signed job")
    dispatcher=AuthenticatedGregDispatcher(
        a.database,read_secret(a.secret_file),a.socket,
        set(a.conversations.split(",")),set(a.executables.split(",")))
    result=dispatcher.dispatch(doc["request"],doc["signature"])
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
