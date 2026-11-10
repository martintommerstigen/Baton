#!/usr/bin/env python3
"""Install a local-only Baton CLI launcher; no credentials, service or shell.

Security review 2026-11-10: install through a pinned directory descriptor.
Reject symlinked ancestors and shared-writable destination directories.
"""
import argparse
import os
from pathlib import Path
import secrets
import stat
import sys

DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Baton (local CLI)
Comment=Open Baton command-line help; no server or network started
Exec={command}
Icon=utilities-terminal
Terminal=true
Categories=Utility;Development;
StartupNotify=false
"""


def desktop_entry(python_executable, client_path):
    python_executable = Path(python_executable).resolve(strict=True)
    client_path = Path(client_path).resolve(strict=True)
    if not python_executable.is_file() or not client_path.is_file():
        raise ValueError("Expected regular files")
    if client_path.name != "client.py":
        raise ValueError("Select the Baton client.py")
    # Desktop Exec is not a shell. Reject Desktop Entry escapes/field codes.
    for path in (python_executable, client_path):
        if any(c in str(path) for c in ('%', '"', '\\', '\n', '\r')):
            raise ValueError("Unsupported character in executable path")
    command = f'"{python_executable}" "{client_path}" --help'
    return DESKTOP_TEMPLATE.format(command=command)


def _open_private_install_directory(parent):
    """Return fd for parent, never following any directory symlink.

    New directories are private. Existing final directory must belong to
    this effective user and not be group/other writable. This protects
    against other local users, not a malicious process with the same UID.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for component in parent.parts[1:]:
            try:
                os.mkdir(component, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o022:
            raise PermissionError("Launcher directory must be owned by user and not shared-writable")
        return fd
    except BaseException:
        os.close(fd)
        raise


def install(client_path, destination=None):
    destination = Path(os.path.abspath(os.fspath(
        destination if destination is not None else
        Path.home() / '.local/share/applications/baton-local.desktop'
    )))
    data = desktop_entry(sys.executable, client_path)
    dir_fd = _open_private_install_directory(destination.parent)
    temp_name = '.baton-launcher-' + secrets.token_hex(12) + '.tmp'
    try:
        try:
            old = os.stat(destination.name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(old.st_mode) or old.st_uid != os.geteuid():
                raise ValueError("Refusing symlink, nonregular or foreign-owned destination")
        # O_EXCL and O_NOFOLLOW make temporary creation fail closed.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        file_fd = os.open(temp_name, flags, 0o600, dir_fd=dir_fd)
        with os.fdopen(file_fd, 'w', encoding='utf-8') as output:
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temp_name, destination.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        os.close(dir_fd)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', default=str(Path(__file__).resolve().parents[1] / 'client.py'))
    parser.add_argument('--destination', default=None)
    args = parser.parse_args()
    print(install(args.client, args.destination))


if __name__ == '__main__':
    main()
