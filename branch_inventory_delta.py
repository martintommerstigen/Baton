"""Read-only comparison of a dated GitHub branch inventory with live GitHub.

No GitHub writes. Private repositories require GITHUB_TOKEN with read access.
Only branch names are fetched; this is NOT a source, priority or deployment audit.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def fetch_branches(repo, token=None, opener=urlopen):
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("repository must be owner/name")
    found = []
    page = 1
    while True:
        if page > 1000:
            raise ValueError("branch pagination exceeded safety limit")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "baton-branch-delta/1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        url = f"https://api.github.com/repos/{repo}/branches?per_page=100&page={page}"
        with opener(Request(url, headers=headers), timeout=20) as response:
            records = json.load(response)
        if not isinstance(records, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in records):
            raise ValueError("unexpected GitHub branch response")
        found.extend(item["name"] for item in records)
        if len(records) < 100:
            break
        page += 1
    if len(found) != len(set(found)):
        raise ValueError("duplicate branch names in live pagination")
    return sorted(found)


def compare(snapshot, live, repo):
    if snapshot.get("repository") != repo:
        raise ValueError("snapshot repository mismatch")
    old = snapshot.get("branches")
    if not isinstance(old, list) or not all(isinstance(b, str) for b in old):
        raise ValueError("invalid snapshot branches")
    if snapshot.get("branch_count") != len(old) or len(set(old)) != len(old):
        raise ValueError("snapshot count or uniqueness mismatch")
    return {
        "repository": repo,
        "snapshot_date_utc": snapshot.get("snapshot_date_utc"),
        "snapshot_count": len(old),
        "live_count": len(live),
        "added_since_snapshot": sorted(set(live) - set(old)),
        "missing_since_snapshot": sorted(set(old) - set(live)),
        "scope": "branch names only; not commit content, review, CI or deployment",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="dated BRANCH_NAME_INVENTORY.json")
    parser.add_argument("--repo", help="owner/name; defaults to snapshot.repository")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        repo = args.repo or snapshot["repository"]
        if snapshot.get("repository") != repo:
            raise ValueError("snapshot repository mismatch")
        result = compare(snapshot, fetch_branches(repo, os.environ.get("GITHUB_TOKEN")), repo)
    except (OSError, KeyError, ValueError, HTTPError, URLError) as exc:
        print(f"Branch comparison unavailable: {exc}. Private repos require a read-scoped GITHUB_TOKEN.", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
