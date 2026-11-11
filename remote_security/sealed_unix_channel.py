"""B5/R26: seal an already connected, source-pinned AF_UNIX snapshot channel.

This is a *post-connect* capability reduction, not an endpoint authenticator,
ChatGPT-authorship proof, host attestation, or UI-write authorization. The
caller must install R25 first, perform R24 before opening the channel, and
keep exactly one authenticated AF_UNIX stream descriptor. The socket remains
usable via send/recv; no new socket or connect is possible afterwards.

This is deliberately not wired into B1 H24: its current observer opens several
new sockets and repeats R24 preflight. That contract must change first.
"""
from __future__ import annotations

import ctypes
import errno
import os
import socket
import stat
import struct
import sys


class ChannelSealDenied(PermissionError):
    pass


class _ArgCmp(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_uint),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]


_SCMP_ALLOW = 0x7fff0000
_SCMP_ERRNO = 0x00050000 | errno.EPERM
# No argv, paths, network or arbitrary command execution in this module.
_DENY = ("socket", "socketpair", "connect", "bind", "listen", "accept",
         "accept4", "sendmsg", "sendmmsg", "recvmsg", "recvmmsg",
         "pidfd_getfd", "ptrace", "process_vm_readv", "process_vm_writev",
         "io_uring_setup", "io_uring_enter", "io_uring_register")


def _r25_kernel_prerequisite() -> None:
    """Probe R25 effects on disposable sockets, never on source data."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(21, 0, 0, 0, 0) != 2:  # PR_GET_SECCOMP
        raise ChannelSealDenied("R25 seccomp prerequisite missing")
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family, socket.SOCK_STREAM):
                pass
        except OSError as exc:
            if exc.errno == errno.EPERM:
                continue
        raise ChannelSealDenied("R25 TCP creation denial missing")
    # A disposable pair avoids consuming any bytes of the live source stream.
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        a.setblocking(False)
        for operation in (lambda: a.recvmsg(1), lambda: a.sendmsg([b"x"])):
            try:
                operation()
            except OSError as exc:
                if exc.errno == errno.EPERM:
                    continue
            raise ChannelSealDenied("R25 message syscall denial missing")
    finally:
        a.close()
        b.close()


def _only_this_socket(fd: int) -> None:
    try:
        for name in os.listdir("/proc/self/fd"):
            if not name.isdigit():
                continue
            number = int(name)
            try:
                target = os.readlink(f"/proc/self/fd/{name}")
            except FileNotFoundError:
                continue
            if target.startswith("socket:") and number != fd:
                raise ChannelSealDenied("unexpected inherited socket capability")
    except OSError as exc:
        raise ChannelSealDenied("cannot audit inherited descriptors") from exc


def _check_path(path: str, expected_uid: int):
    if (type(path) is not str or not path.startswith("/") or "\x00" in path
            or any(p in ("", ".", "..") for p in path.split("/")[1:])):
        raise ChannelSealDenied("canonical absolute socket path required")
    parts = path.split("/")[1:]
    fd = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW |
                          os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = nxt
        info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != expected_uid
                or info.st_mode & 0o002):
            raise ChannelSealDenied("socket owner/type/world-write denied")
        return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
    except OSError as exc:
        raise ChannelSealDenied("unsafe socket path or parent") from exc
    finally:
        os.close(fd)


def _load_filter():
    try:
        lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
        lib.seccomp_init.argtypes = [ctypes.c_uint32]
        lib.seccomp_init.restype = ctypes.c_void_p
        lib.seccomp_release.argtypes = [ctypes.c_void_p]
        lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
        lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
        lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.c_int, ctypes.c_uint,
                                               ctypes.POINTER(_ArgCmp)]
        lib.seccomp_rule_add_array.restype = ctypes.c_int
        lib.seccomp_load.argtypes = [ctypes.c_void_p]
        lib.seccomp_load.restype = ctypes.c_int
    except (OSError, AttributeError) as exc:
        raise ChannelSealDenied("libseccomp unavailable") from exc
    ctx = lib.seccomp_init(_SCMP_ALLOW)
    if not ctx:
        raise ChannelSealDenied("seccomp context unavailable")
    try:
        for name in _DENY:
            number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0 or lib.seccomp_rule_add_array(ctx, _SCMP_ERRNO,
                                                         number, 0, None) != 0:
                raise ChannelSealDenied("seccomp rule unavailable: " + name)
        # socketcall exists on some 32-bit architectures. Deny if resolvable.
        number = lib.seccomp_syscall_resolve_name(b"socketcall")
        if number >= 0 and lib.seccomp_rule_add_array(ctx, _SCMP_ERRNO,
                                                       number, 0, None) != 0:
            raise ChannelSealDenied("socketcall restriction unavailable")
        if lib.seccomp_load(ctx) != 0:
            raise ChannelSealDenied("kernel rejected seccomp seal")
    finally:
        lib.seccomp_release(ctx)


def seal_unix_channel(sock: socket.socket, *, endpoint: str, peer_uid: int) -> str:
    """Irreversibly prevent all new Unix/TCP connections in this process.

    Must run in dedicated non-root observer *after* R25 and a single verified
    connection, never in a shared process. Caller owns the returned live socket.
    A failed seal is terminal for this worker; do not retry a source request.
    """
    if (not sys.platform.startswith("linux") or os.getuid() != os.geteuid()
            or os.geteuid() == 0 or type(peer_uid) is not int
            or peer_uid <= 0 or peer_uid == os.geteuid()):
        raise ChannelSealDenied("distinct non-root Linux observer/collector required")
    if not isinstance(sock, socket.socket) or sock.fileno() < 0:
        raise ChannelSealDenied("connected socket required")
    if (sock.family != socket.AF_UNIX or sock.type & 0xf != socket.SOCK_STREAM
            or sock.getpeername() != endpoint):
        raise ChannelSealDenied("only a pathname AF_UNIX stream peer is allowed")
    before = _check_path(endpoint, peer_uid)
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", creds)
    if pid <= 0 or uid != peer_uid or gid < 0:
        raise ChannelSealDenied("kernel peer credentials mismatch")
    _only_this_socket(sock.fileno())
    _r25_kernel_prerequisite()
    if _check_path(endpoint, peer_uid) != before:
        raise ChannelSealDenied("socket endpoint replaced")
    _load_filter()
    # A real kernel-negative self-test. Any failure terminates this worker.
    for operation in (lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
                      lambda: socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)):
        try:
            result = operation()
            if isinstance(result, tuple):
                for item in result:
                    item.close()
            else:
                result.close()
        except OSError as exc:
            if exc.errno == errno.EPERM:
                continue
        raise ChannelSealDenied("post-seal socket creation still possible")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.connect.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    libc.connect.restype = ctypes.c_int
    if libc.connect(-1, None, 0) != -1 or ctypes.get_errno() != errno.EPERM:
        raise ChannelSealDenied("post-seal connect syscall still possible")
    return "single_unix_channel_sealed_not_host_attestation"
