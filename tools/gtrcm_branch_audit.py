"""Read-only, fail-closed GTRCM branch/tree provenance inventory.

Branch tips and tree filenames are NOT a review of historical source contents.
No remote writes, code execution, automatic retry or credential persistence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = "martintommerstigen/GTRCM"
PAGE_SIZE = 100
MAX_PAGES = 100
DATE = re.compile(r"20\d{2}[-_]\d{2}[-_]\d{2}")
RELEVANT = re.compile(r"(^|/)(README|METHOD|NEGATIVE_RESULTS|OPEN_PROBLEMS|GTRCM_KANONISK_GRUNNPROGRAM)(\.|$)|(^|/)(research|experiments|tests|docs|source)/", re.I)


class IncompleteInventory(RuntimeError):
    pass


def scan_branches(fetch, repo=REPO):
    found = {}
    for page in range(1, MAX_PAGES + 1):
        items = fetch(f"/repos/{repo}/branches?per_page={PAGE_SIZE}&page={page}")
        if not isinstance(items, list) or len(items) > PAGE_SIZE:
            raise IncompleteInventory(f"invalid page {page}")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise IncompleteInventory("invalid branch record")
            name = item["name"]
            sha = item.get("commit", {}).get("sha")
            if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha):
                raise IncompleteInventory("invalid commit SHA")
            if name in found:
                raise IncompleteInventory(f"duplicate branch across pages: {name}")
            found[name] = sha
        if len(items) < PAGE_SIZE:
            return found
    raise IncompleteInventory("pagination exceeded limit")


def collect(fetch, repo=REPO, *, with_trees=True, with_dates=True):
    first = scan_branches(fetch, repo)
    entries = []
    for name, sha in sorted(first.items()):
        hints = DATE.findall(name)
        entry = {"name": name, "sha": sha,
                 "branch_date_hint": hints[-1].replace("_", "-") if hints else None,
                 "commit_date": None, "theme": "/".join(name.split("/")[:2]),
                 "url": f"https://github.com/{repo}/tree/{quote(name, safe='/')}",
                 "tree_indexed": False, "files_total": None,
                 "relevant_paths": [], "content_read": False}
        if with_dates:
            commit = fetch(f"/repos/{repo}/commits/{sha}")
            try:
                entry["commit_date"] = commit["commit"]["committer"]["date"]
            except (KeyError, TypeError):
                raise IncompleteInventory(f"missing verified date for {name}")
        if with_trees:
            tree = fetch(f"/repos/{repo}/git/trees/{sha}?recursive=1")
            if not isinstance(tree, dict) or tree.get("truncated") or not isinstance(tree.get("tree"), list):
                raise IncompleteInventory(f"incomplete tree for {name}")
            blobs = [x for x in tree["tree"] if x.get("type") == "blob"]
            if any(not isinstance(x.get("path"), str) for x in blobs):
                raise IncompleteInventory(f"invalid file path for {name}")
            entry["tree_indexed"] = True
            entry["files_total"] = len(blobs)
            entry["relevant_paths"] = [x["path"] for x in blobs if RELEVANT.search(x["path"])]
        entries.append(entry)
    if first != scan_branches(fetch, repo):
        raise IncompleteInventory("branch set or SHA changed during scan; discard output")
    return {"schema": "ronja-gtrcm-branch-coverage-v2",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "branch_count": len(entries),
            "tree_indexed": sum(e["tree_indexed"] for e in entries),
            "content_read": 0,
            "limitations": ["Current branch tips only; deleted refs and historical commits excluded.",
                            "Tree paths are not source-content review.",
                            "No Greg/Mac local files or prior conversation corpus inspected.",
                            "No novelty inferred from filenames."],
            "branches": entries}


def github_fetch(token=None, *, timeout=15):
    def fetch(path):
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "Baton-Ronja-ReadOnly-Coverage/1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=timeout) as response:
                return json.load(response)
        except (HTTPError, URLError, ValueError) as exc:
            raise IncompleteInventory(f"GitHub read failed at {path}: {type(exc).__name__}") from exc
    return fetch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-trees", action="store_true")
    parser.add_argument("--skip-dates", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = collect(github_fetch(os.getenv("GITHUB_TOKEN")),
                         with_trees=not args.skip_trees, with_dates=not args.skip_dates)
        if args.output.exists() or args.output.is_symlink():
            raise IncompleteInventory("refusing to overwrite existing output")
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        print(f"inventory: {result['branch_count']} branches, {result['tree_indexed']} trees, zero content-read")
        return 0
    except (IncompleteInventory, OSError) as exc:
        print(f"incomplete inventory: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
