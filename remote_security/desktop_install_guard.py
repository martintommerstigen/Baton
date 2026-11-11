"""B5/B2: create-only, directory-fd-pinned local Baton desktop launcher.

Linux/POSIX only. No service, UI action, network connection, credentials, or retry.
The destination is a *new* desktop entry; existing entries are never replaced.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import secrets
import stat
import sys

NAME = "baton-local.desktop"
SAFE_EXEC = re.compile(r"^/[A-Za-z0-9_./-]+$")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


class UnsafeInstallation(RuntimeError):
    """A path or race cannot be trusted. Do not automatically retry."""


def _parts(path):
    raw = os.fspath(path)
    if type(raw) is not str or not raw.startswith("/") or raw == "/":
        raise UnsafeInstallation("absolute canonical path required")
    pieces = raw.split("/")[1:]
    if any(x in ("", ".", "..") for x in pieces):
        raise UnsafeInstallation("noncanonical path component")
    return pieces


def _safe_dir(s):
    if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.geteuid()):
        raise UnsafeInstallation("unexpected directory owner or type")
    if s.st_mode & 0o022 and not (s.st_uid == 0 and s.st_mode & stat.S_ISVTX):
        raise UnsafeInstallation("mutable ancestor")


def _open_chain(path):
    """Walk without following symlinks; return all descriptors for later rechecks."""
    parts = _parts(path)
    chain = []
    try:
        root = os.open("/", DIR_FLAGS)
        chain.append((root, None))
        _safe_dir(os.fstat(root))
        for name in parts:
            parent = chain[-1][0]
            try:
                fd = os.open(name, DIR_FLAGS, dir_fd=parent)
            except FileNotFoundError:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass  # A concurrent creator won; verify type, owner and mode.
                fd = os.open(name, DIR_FLAGS, dir_fd=parent)
            _safe_dir(os.fstat(fd))
            chain.append((fd, name))
        _verify_chain(chain)
        return chain
    except BaseException:
        for fd, _ in reversed(chain):
            os.close(fd)
        raise


def _verify_chain(chain):
    for i in range(1, len(chain)):
        parent, _ = chain[i - 1]
        fd, name = chain[i]
        try:
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(fd)
        except OSError as exc:
            raise UnsafeInstallation("ancestor disappeared") from exc
        if (not stat.S_ISDIR(named.st_mode) or
            (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
            raise UnsafeInstallation("ancestor replaced")
        _safe_dir(named)


def _entry(client_path, python_executable):
    client = os.path.realpath(os.fspath(client_path))
    python = os.path.realpath(os.fspath(python_executable))
    if Path(client).name != "client.py":
        raise UnsafeInstallation("only Baton client.py is supported")
    for path in (client, python):
        if not SAFE_EXEC.fullmatch(path):
            raise UnsafeInstallation("unsupported executable path")
        if not os.path.isfile(path):
            raise UnsafeInstallation("missing executable or client")
    return ("[Desktop Entry]\nType=Application\nName=Baton (local CLI)\n"
            "Comment=Open local Baton help; no network service started\n"
            f"Exec={python} {client} --help\nIcon=utilities-terminal\n"
            "Terminal=true\nCategories=Utility;Development;\n"
            "StartupNotify=false\n").encode("utf-8")


def install(client_path, destination_dir=None, *, python_executable=sys.executable):
    """Atomically publish a *new* desktop entry. Never replace existing content.

    A caller-controlled destination_dir is an explicit opt-in, not a privilege
    elevation. This function cannot defend against a malicious same-UID actor
    who controls the directory after the last identity check.
    """
    data = _entry(client_path, python_executable)
    directory = os.fspath(destination_dir or Path.home() / ".local/share/applications")
    chain = _open_chain(directory)
    parent = chain[-1][0]
    temp = ".baton-local.tmp-" + secrets.token_hex(16)
    fd = None
    created = False
    identity = None
    try:
        _verify_chain(chain)
        fd = os.open(temp, FILE_FLAGS, 0o600, dir_fd=parent)
        identity = os.fstat(fd)
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise UnsafeInstallation("temporary file not exclusive regular file")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
        os.fchmod(fd, 0o644)
        os.fsync(fd)
        named = os.stat(temp, dir_fd=parent, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (identity.st_dev, identity.st_ino):
            raise UnsafeInstallation("temporary file replaced")
        _verify_chain(chain)
        try:
            os.link(temp, NAME, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError as exc:
            raise UnsafeInstallation("existing launcher must not be overwritten") from exc
        created = True
        installed = os.stat(NAME, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(installed.st_mode) or
            (installed.st_dev, installed.st_ino) != (identity.st_dev, identity.st_ino)):
            raise UnsafeInstallation("published entry replaced")
        _verify_chain(chain)
        os.fsync(parent)
        return str(Path(directory) / NAME)
    except BaseException:
        if created:
            try:
                current = os.stat(NAME, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    os.unlink(NAME, dir_fd=parent)
            except OSError:
                pass
        raise
    finally:
        if fd is not None:
            os.close(fd)
        try:
            named = os.stat(temp, dir_fd=parent, follow_symlinks=False)
            if identity is not None and (named.st_dev, named.st_ino) == (identity.st_dev, identity.st_ino):
                os.unlink(temp, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            pass
        for directory_fd, _ in reversed(chain):
            os.close(directory_fd)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", required=True)
    p.add_argument("--destination-dir", default=None)
    args = p.parse_args(argv)
    try:
        print(install(args.client, args.destination_dir))
    except (UnsafeInstallation, OSError, ValueError) as exc:
        print(f"installation rejected: {type(exc).__name__}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
