"""Pinned TLS endpoint authentication before Baton bearer/payload disclosure.

TLS is transport authentication, not a ChatGPT wake or source completeness
proof. The service private key must be protected by a dedicated service UID.
No certificates or private keys are stored in Git.
"""
from __future__ import annotations

import hashlib
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


def pinned_client_context_and_leaf_digest(certificate_file):
    """Return a CA-verifying context AND the exact pinned leaf SHA-256.

    The same bounded owner-only read supplies both values. Trusting a PEM as a
    CA alone is NOT exact certificate pinning: a CA may sign a different leaf
    with the same IP SAN. The caller must check the peer DER certificate before
    writing even the first HTTP header.
    """
    pem = _private_pem(certificate_file).decode('ascii')
    if (pem.count('-----BEGIN CERTIFICATE-----') != 1
            or pem.count('-----END CERTIFICATE-----') != 1):
        raise ValueError('pin must contain exactly one PEM certificate')
    der = ssl.PEM_cert_to_DER_cert(pem)
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cadata=pem)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx, hashlib.sha256(der).digest()


def pinned_client_context(certificate_file):
    """Compatibility helper for TLS verification; does not check leaf pin.

    Use pinned_client_context_and_leaf_digest with ExactLeafHTTPSConnection
    for an authenticated Baton request.
    """
    return pinned_client_context_and_leaf_digest(certificate_file)[0]

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
