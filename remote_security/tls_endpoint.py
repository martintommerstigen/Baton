"""Pinned TLS endpoint authentication before Baton bearer/payload disclosure.

TLS is transport authentication, not a ChatGPT wake or source completeness
proof. The service private key must be protected by a dedicated service UID.
No certificates or private keys are stored in Git.
"""
from __future__ import annotations

import os
import ssl
import stat
from pathlib import Path


def _private_pem(path, *, limit=65536):
    """Read a bounded, owner-only PEM without following links or FIFOs.

    Requires a non-symlink absolute path under an owner-only directory. This
    protects against other UIDs, not a malicious process with the same UID.
    """
    from remote_security.private_store import _validate_path

    p = _validate_path(path)
    flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_CLOEXEC', 0))
    fd = os.open(p, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise PermissionError('TLS PEM must be owner-only regular file, no hardlinks')
        data = os.read(fd, limit + 1)
        if not data or len(data) > limit:
            raise ValueError('TLS PEM is empty or oversized')
        return data
    finally:
        os.close(fd)


def pinned_client_context(certificate_file):
    """Trust only the explicit PEM CA/certificate, never ambient trust roots.

    HTTPSConnection checks the IP SAN 127.0.0.1 before sending HTTP headers.
    """
    pem = _private_pem(certificate_file).decode('ascii')
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cadata=pem)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def server_tls_context(certificate_file, private_key_file):
    """Validate private paths before SSL reads; never log PEM material."""
    _private_pem(certificate_file)
    _private_pem(private_key_file)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.options |= ssl.OP_NO_COMPRESSION
    # The service must use a dedicated UID; same-UID pathname races remain
    # outside this filesystem policy's protection boundary.
    ctx.load_cert_chain(certfile=str(Path(certificate_file)),
                        keyfile=str(Path(private_key_file)))
    return ctx
