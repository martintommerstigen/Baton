# B1/B5 — Cooperative PAUSE_UI_WRITES writer (2026-11-10)

**Status: tested-simulated only; no Greg installation and no existing-chat A→B→C wake.**

## Source and distinction

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3) defines actual existing-chat acceptance, not an SIWC worker or local forum.
- [PR #4](https://github.com/martintommerstigen/Baton/pull/4) introduced the per-host `wake_ui_lock.ui_controller_lock` held by both UI runners through their browser session.
- [PR #10](https://github.com/martintommerstigen/Baton/pull/10) replaced fail-open `Path.exists()` checks with fail-closed `pause_active` in the actual driver and CLI entrypoints.
- [Ronja's forum response](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6766420033) identifies the missing cooperative pause-writer contract.
- GTRCM method: a local admission or a pause observation is not proof of a remote assistant turn. Preserve **unverified** for unobserved source events.

## Implemented contract

`wake_pause_writer.py` is a **one-way local PAUSE command**. It acquires the *same* nonblocking host `flock` as both existing-chat UI runners **before** creating the marker. It uses directory-descriptor-relative `O_DIRECTORY|O_NOFOLLOW` traversal and `O_EXCL|O_NOFOLLOW` file creation with private mode, then fsyncs the marker and parent directory. It never removes a marker, starts a browser, sends a message, or modifies a ledger. The production CLI has no arbitrary path or lock override.

The contract has two serializable outcomes for **cooperating** participants:

1. Pause writer gets the lock first → marker committed → a later Baton UI runner checks the marker while holding the same lock → **zero clicks**.
2. Baton UI runner gets the lock first → its already-authorized send may occur → writer fails to acquire lock, **does not create the marker and does not report success**. An operator may explicitly retry once the active controller exits.

The writer does **not** guarantee immediate cancellation of an in-flight send. The host lock is currently held throughout observation and reply waiting, so a pause request may be refused for that whole interval. For emergency intervention, manual pause creation may block future checks but **cannot prove** no click raced the request. No process should report `paused` merely because an advisory health/status response was `unpaused` earlier.

## Falsifiers and limitations

- A noncooperating pause writer, browser extension, person, or other machine is not serialized by the host `flock`.
- The shared host-lock implementation now rejects symlinked ancestor directories, hardlinked lock files, relative/traversed paths and an inode that differs from the just-opened descriptor before entering the critical section. **A malicious same-UID process can still unlink/replace the path after that check**, or a different host can use another inode. This is a cooperating-process contract, not a security boundary against an adversarial process with the same filesystem privileges.
- A pause marker is not a command to clear the browser composer, terminate an active response, or retry an uncertain delivery.
- An already-existing symlink marker is left untouched; `pause_active` treats it as paused. Missing/symlinked ancestors reject creation.
- This implementation does not provide a public remote control endpoint or permission to change Greg's actual pause switch.

## Verification

`python3 -m unittest -v test_wake_pause_writer.py` checks private marker creation, idempotence, leaf and ancestor symlink safety, missing ancestors, relative/traversal paths, sender-first and writer-first orderings, and cross-process lock contention. Offline synthetic pages are **not** real ChatGPT pages. `test_wake_lock_path.py` adds four lock-path regression tests. Local isolated execution of both new test modules: **12/12 PASS** using the extracted existing lock and pause logic with synthetic UI stand-ins. Record the GitHub Actions run separately when available; a local pass does not imply CI or Greg-live.

## Next test

Create a controlled inode-replacement race test under a disposable test UID and decide whether stronger supervision (e.g. an independent privileged lock broker) is necessary. The current shared file lock cannot prevent a noncooperating same-UID process from replacing its pathname. Integrate an explicit pause request interface with pending/confirmed semantics if immediate cancellation is required; never silently retry an ambiguous send.
