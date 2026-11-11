# B5-RJ11 — desktop installer parent-symlink and overwrite counterexample (2026-11-11)

**Scope:** independent read-only review and isolated execution of the existing [Baton desktop integration installer](https://github.com/martintommerstigen/Baton/blob/integration/baton-desktop-launcher-2026-11-10/desktop/install_baton_launcher.py), exact Git blob `76a626255bd5018d9ee26a2dc9754488ad5a7c86`. No changes to the integration branch or Greg; not a deployed fix.

## Source-priority and delta

[R13](https://github.com/martintommerstigen/Baton/blob/research/ronja-r13-source-broker-startup-rollback-2026-11-11/docs/ronja/2026-11-11-r13-source-broker-startup-rollback.md) had **already identified** unsafe desktop installer ancestors and existing-file ownership as an unresolved gate. R14–R16 subsequently pinned source-broker directories and endpoint inodes, not desktop installation. This is **a reproducible test of a previously reported concern**, not a new filesystem theorem or new GTRCM physics. [Project map B5/RustWorld/525](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md) requires safe installation.

## Two isolated negative controls, exact code bytes

Copied the original installer byte-for-byte into a disposable Python container; `git hash-object desktop/install_baton_launcher.py` returned **`76a626255bd5018d9ee26a2dc9754488ad5a7c86`**, matching GitHub.

1. Create temporary `target/` directory and `alias -> target/` directory symlink. Call `install(client.py, alias/baton-local.desktop)`. **Observed: accepted** and created `target/baton-local.desktop`. The code checks `destination.is_symlink()` but does not reject a symlinked *parent*.
2. Replace the target desktop file with `preexisting user data`, then call the same installer. **Observed: preexisting file overwritten** by `os.replace` without verifying expected ownership, file identity or opt-in replacement. This is a local destructive side effect, not just a simulated predicate.

These results require an attacker-influenced destination or parent to become a privilege/path abuse; they do not establish a remote exploit, actual Greg compromise, or a UI wake. The `temp.open('x')` exclusive creation is a useful existing safeguard but does not secure the parent or replacement target.

**Required fix before release:** resolve only trusted installation roots, pin a checked directory file descriptor (no symlink ancestors), reject nonregular or non-owned existing entries, avoid overwriting an unexpected file, use nofollow/exclusive creation and durable rename/dir fsync with inode checks. Add negatives for parent symlink, replaced parent during rename, preexisting unexpected file, symlinked final path, and unsafe modes. The current R18 branch does not modify B1/integration-owned installer files. An actual installed icon on Greg is **not** verified.

**Test classification:** tested-simulated with exact original GitHub code bytes in isolated Linux/Python; no Greg/Mac access, no DC quota, no UI writes. This is a security counterexample to feed the product/installation owner, not a claim that the R18 read-only manifest itself installs anything.
