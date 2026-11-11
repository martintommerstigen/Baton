"""B5/R25 Linux seccomp lifetime restriction for B1's snapshot-only observer.

Call before any snapshot request. This narrows future FD acquisition, not
browser authorship, host attestation or UI-write authorization. No shell API.
Requires libseccomp.so.2, Linux, separate non-root observer UID, and R24.
"""
from __future__ import annotations

import ctypes
import errno
import os
import socket
import sys


class LifetimeGuardDenied(PermissionError):
    """Required kernel restriction was unavailable or not enforced."""


class _ArgCmp(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_uint),
                ('datum_a', ctypes.c_uint64), ('datum_b', ctypes.c_uint64)]


_SCMP_ALLOW = 0x7fff0000
_SCMP_ERRNO = 0x00050000 | errno.EPERM
_SCMP_CMP_EQ = 4
_BLOCKED_SYSCALLS = (
    'recvmsg', 'recvmmsg', 'sendmsg', 'sendmmsg', 'pidfd_getfd',
    'ptrace', 'process_vm_readv', 'process_vm_writev',
    'io_uring_setup', 'io_uring_enter', 'io_uring_register',
)


def _load_libseccomp():
    try:
        lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
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
        return lib
    except (OSError, AttributeError) as exc:
        raise LifetimeGuardDenied('libseccomp unavailable') from exc


def _rule(lib, ctx, name, comparison=None):
    number = lib.seccomp_syscall_resolve_name(name.encode('ascii'))
    if number < 0:
        raise LifetimeGuardDenied('required syscall unavailable: ' + name)
    ptr = ctypes.pointer(comparison) if comparison is not None else None
    result = lib.seccomp_rule_add_array(ctx, _SCMP_ERRNO, number,
                                        1 if comparison is not None else 0, ptr)
    if result != 0:
        raise LifetimeGuardDenied('seccomp rule rejected: ' + name)


def install_observer_lifetime_guard():
    """Permanently deny TCP creation and descriptor-passing/duplication syscalls.

    Irreversible for this process and descendants. Run in a dedicated observer
    process, never a shared Python process. Fail closed if any rule cannot load.
    R24's point-in-time preflight remains required independently by B1.
    """
    if not sys.platform.startswith('linux') or os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise LifetimeGuardDenied('non-root non-setuid Linux observer required')
    try:
        from remote_security.observer_boundary import _no_inherited_socket_capabilities
        _no_inherited_socket_capabilities()
    except (ImportError, OSError, PermissionError) as exc:
        raise LifetimeGuardDenied('R24 inherited socket audit failed') from exc
    lib = _load_libseccomp()
    ctx = lib.seccomp_init(_SCMP_ALLOW)
    if not ctx:
        raise LifetimeGuardDenied('seccomp context unavailable')
    try:
        for name in _BLOCKED_SYSCALLS:
            _rule(lib, ctx, name)
        for family in (socket.AF_INET, socket.AF_INET6):
            _rule(lib, ctx, 'socket', _ArgCmp(0, _SCMP_CMP_EQ, family, 0))
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                               ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise LifetimeGuardDenied('no_new_privs unavailable')
        if lib.seccomp_load(ctx) != 0:
            raise LifetimeGuardDenied('kernel rejected seccomp policy')
    finally:
        lib.seccomp_release(ctx)
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family, socket.SOCK_STREAM):
                pass
        except OSError as exc:
            if exc.errno == errno.EPERM:
                continue
        raise LifetimeGuardDenied('TCP socket restriction did not take effect')
    # Verify the kernel actually enforces the descriptor-transfer restriction.
    # recvmsg must fail immediately even on a valid connected AF_UNIX pair.
    pair = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        for attempt in (lambda: pair[0].recvmsg(1),
                        lambda: pair[0].sendmsg([b'x'])):
            try:
                attempt()
            except OSError as exc:
                if exc.errno == errno.EPERM:
                    continue
            raise LifetimeGuardDenied('descriptor-transfer restriction did not take effect')
    finally:
        pair[0].close()
        pair[1].close()
    return 'lifetime_guard_loaded_not_host_attestation'


def main(argv=None):
    """Only supported entry point: B1's fixed snapshot observer, no shell."""
    install_observer_lifetime_guard()
    from run_b1_snapshot_observer import main as observer_main
    observer_main(sys.argv[1:] if argv is None else argv)


if __name__ == '__main__':
    main()
