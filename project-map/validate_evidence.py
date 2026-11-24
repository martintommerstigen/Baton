"""Validate append-only evidence receipts in a project-map checkout."""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = {x["id"] for x in json.loads((ROOT / "project-map/tasks.json").read_text())["tasks"]}
ALLOWED = {"implemented-unverified", "tested-simulated", "tested-live", "negative", "blocked", "unverified"}
KINDS = {"commit", "pull_request", "issue", "workflow", "document", "test_report"}
OUTCOMES = {"passed", "failed", "not-run"}

def validate_receipt(p):
    data = json.loads(p.read_text())
    assert data["schema"] == "gtrcm-evidence/v1", p
    assert data["task_id"] in TASKS, p
    assert data["result"] in ALLOWED, p
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,120}", data["event_id"]), p
    assert data["event_id"].startswith(data["task_id"] + "-"), p
    assert isinstance(data["worker"], str) and data["worker"].strip(), p
    assert isinstance(data["summary"], str) and data["summary"].strip(), p
    assert isinstance(data["next_question"], str) and data["next_question"].strip(), p
    assert isinstance(data["limitations"], list), p
    datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00"))
    assert isinstance(data["sources"], list), p
    for source in data["sources"]:
        assert source["kind"] in KINDS, p
        assert source["url"].startswith("https://"), p
    assert isinstance(data["tests"], list), p
    for test in data["tests"]:
        assert test["outcome"] in OUTCOMES, p
        assert test["name"].strip() and test["environment"].strip(), p
    if data["result"] in {"tested-simulated", "tested-live"}:
        assert data["sources"] and data["tests"], p
        assert any(t["outcome"] == "passed" for t in data["tests"]), p
    assert data.get("supersedes") is None or data["supersedes"] != data["event_id"], p
    return data["event_id"]

def main():
    receipts = sorted((ROOT / "project-map/evidence").glob("**/*.json"))
    ids = [validate_receipt(p) for p in receipts]
    assert len(ids) == len(set(ids)), "duplicate event ID"
    print(f"Validated {len(receipts)} evidence receipts")

if __name__ == "__main__":
    main()
