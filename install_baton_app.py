"""Install one local Baton app entry for Kubuntu's application menu.

No user secrets, no system-level install, and no modification of official
model clients. The Exec target is Baton's own integrated native UI launcher.
"""
import argparse
import os
from pathlib import Path
import tempfile


def _quoted_desktop_exec(path):
    value = str(path)
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("invalid launcher path")
    # Desktop entry Exec uses double-quote escaping, not a shell command.
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"/usr/bin/bash" "' + escaped + '"'


def install_entry(destination, launcher):
    destination = Path(destination).expanduser()
    launcher = Path(launcher).resolve(strict=True)
    if not launcher.is_file() or launcher.name != "run_baton_direct.sh":
        raise ValueError("Baton launcher not found")
    if destination.is_symlink():
        raise ValueError("desktop entry symlink forbidden")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.parent.is_symlink():
        raise ValueError("applications directory symlink forbidden")
    text = "\n".join((
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Baton",
        "Comment=Models, local Core and recipient-controlled messaging",
        "Exec=" + _quoted_desktop_exec(launcher),
        "Path=" + str(launcher.parent),
        "Icon=utilities-terminal",
        "Terminal=false",
        "StartupNotify=true",
        "Categories=Network;Development;Utility;",
        ""
    ))
    if destination.exists():
        if not destination.is_file():
            raise ValueError("not a regular desktop entry")
        prior = destination.read_text(encoding="utf-8")
        if prior == text:
            return "already-installed"
        if "[Desktop Entry]" not in prior or "Name=Baton" not in prior:
            raise ValueError("existing application entry differs and is not managed by Baton")
    fd, tmp = tempfile.mkstemp(prefix=".baton-launcher-", dir=destination.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return "installed"


def main():
    parser = argparse.ArgumentParser(description="Install Baton desktop shortcut")
    parser.add_argument("--desktop-file",
                        default=str(Path.home()/".local/share/applications/baton.desktop"))
    parser.add_argument("--launcher",
                        default=str(Path(__file__).with_name("run_baton_direct.sh")))
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("run as desktop user, not root")
    try:
        outcome = install_entry(args.desktop_file, args.launcher)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Baton application launcher:", outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
