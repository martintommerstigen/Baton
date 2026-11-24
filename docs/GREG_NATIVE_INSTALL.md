# Baton → Greg: local write-capable executor (installation candidate)

This installs a **local Unix-socket command executor** with the file permissions
of the Greg desktop user. It does **not** grant ChatGPT access on its own.
No Desktop Commander, public HTTP listener, or cloud relay is involved.

## Important security boundary

Any process running under the dedicated caller UID can run arbitrary programs
as the Greg desktop user via this socket, including writing, deleting or
changing files accessible to that user. Treat that UID as highly privileged.
Do not assign it to a browser, general LLM worker, untrusted plugin or public
network service. This component is not a sandbox and is not a proof of ChatGPT
conversation identity. Never use root as the executor user.

## One-time local preparation on Greg

From a trusted local Greg terminal, review the code in PR #51 before running.
Create a dedicated caller user and a shared group, if they do not already exist:

```bash
sudo groupadd --system baton-greg-access
sudo useradd --system --no-create-home --shell /usr/sbin/nologin baton-greg-caller
sudo usermod -aG baton-greg-access baton-greg-caller
sudo usermod -aG baton-greg-access "$(id -un)"
```

Skip commands for already-existing accounts/groups. **Log out and back in**
after adding the desktop user to the group. Check `id -nG` and
`id -nG baton-greg-caller` before proceeding. Do not use these examples to
overwrite an existing deployment's identity policy.

Check out the reviewed branch in a dedicated directory, then from the
repository root, while logged in as the intended desktop user:

```bash
bash ops/install_greg_executor.sh baton-greg-caller baton-greg-access
systemctl --user status baton-greg-executor.service
```

The installer refuses root, missing group membership, same-UID caller,
existing service files, and existing sockets. It installs a systemd *user*
service; no persistent root service is installed. The socket lives under
`~/.local/share/baton-greg/exec.sock`.

## Local smoke test (after installation)

The caller must have access to the socket via the dedicated group. Execute
the test as the dedicated caller, not as the desktop user:

```bash
sudo -u baton-greg-caller python3 -c '
import sys
sys.path.insert(0, "/home/olliver/Baton")
from remote_security.greg_executor_client import run_local
print(run_local("/home/olliver/.local/share/baton-greg/exec.sock",
                ["/usr/bin/id"]))
'
```

**Replace** `/home/olliver/Baton` with the actual checkout path. To test a
write, use a uniquely named harmless file in a preapproved scratch directory
and verify its contents from Greg. Do not use a production project as the
first write target.

## Not yet wired

A trusted Baton dispatcher must authenticate and authorize the actual
ChatGPT-originated job, bind it to a unique durable job ID and approved payload
digest, enforce replay policy, and then call `run_local` under the dedicated
caller UID. Its result must be persisted before claiming completion. Do not
forward raw message bodies as commands. This dispatcher is **not** supplied by
this installer. No existing ChatGPT conversation can invoke this socket from
the ChatGPT app merely because it is installed.

## Stop and rollback

```bash
systemctl --user stop baton-greg-executor.service
systemctl --user disable baton-greg-executor.service
```

Do not blindly unlink a socket that might belong to another process. Inspect
its inode, ownership and listening process before removing a stale endpoint.
Do not expose the socket over a public TCP bridge.
