# B1/B5 — post-validation inode replacement negative control (2026-11-10)

**Status:** tested locally (2/2 on isolated copy of PR #12's `wake_ui_lock.py`), GitHub CI pending at creation. No Greg access, no real ChatGPT A→B→C, no pause mutation.

## Provenance

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3): actual existing-chat acceptance.
- [PR #4](https://github.com/martintommerstigen/Baton/pull/4): cooperative shared host lock.
- [PR #12](https://github.com/martintommerstigen/Baton/pull/12): reject symlink/hardlink/path traversal and inode change *before* entering critical section.
- [Ronja's security response](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6766420033): advisory `flock` is a cooperative protocol, not a hostile same-UID boundary.

## Falsifiable question

Can a second process enter the UI lock while the first holds it, **after** the first process's inode validation has passed, if a same-UID actor renames the lock file and creates a new inode at its old pathname?

## Reproduction

`python3 -m unittest -v test_wake_lock_replacement_boundary.py`

The first test checks that the same inode correctly blocks a second cooperating process. The second, intentionally negative, test opens the same pathname in two different processes after replacing the pathname while the first process still holds its old inode. Both acquire exclusive `flock` simultaneously because they lock different inodes. The test's expected `ACQUIRED` result is **evidence of a limitation**, not evidence that the security boundary works.

All mutations are restricted to a disposable `TemporaryDirectory`. No production lock, pause marker, browser or ledger is touched.

## Consequence and proposed boundary

Do **not** label the current host lock as safe against arbitrary same-UID processes. The cooperative sender/pause writer contract remains valid only when lock-path mutation is excluded by the deployment trust model. Rechecking the pathname after the click would detect some races too late to prevent a send. Rechecking just before the click leaves another TOCTOU interval.

If hostile same-UID isolation is required, investigate a broker running under a **different** OS identity, owning the lock state and exposing a narrowly scoped Unix-domain socket with peer credential verification. The broker must serialize both pause requests and UI send authorization, and its contract must distinguish authorization from proof of delivery. This is an architectural candidate, **not implemented or verified** by this test.

## Evidence classification

- **MEASURED:** 2/2 tests passed in a local isolated reproduction of PR #12 lock code.
- **DERIVED:** exclusive locks on different inodes do not serialize a shared pathname.
- **NEG:** a lock-path inode validation at entry cannot guarantee ongoing pathname stability against a same-UID actor.
- **NOT DERIVED:** real browser safety, cross-host exclusion, A→B→C, or adversarial OS isolation.
