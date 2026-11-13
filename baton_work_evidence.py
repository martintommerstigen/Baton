"""Read-only, provenance-labeled Baton participation evidence.

A local database post or idle-wake receipt is NOT a live ChatGPT model.
Do not confuse 'last contribution' with 'who is working now'. This observer
reads sources; it never wakes, authenticates, edits, or grants permission.
"""
import argparse
import json
import re
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote


def _readonly(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("source database missing or symlinked")
    # Open existing file only; never initialize absent tables or journals.
    c = sqlite3.connect("file:" + quote(str(path.resolve())) + "?mode=ro",
                        uri=True, timeout=2)
    c.row_factory = sqlite3.Row
    return c


def snapshot(topic_db, topic, *, wake_db=None, now=None):
    """Return bounded historical evidence, not a current-activity verdict."""
    if not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}",topic):
        raise ValueError("invalid topic ID")
    checked = time.time() if now is None else float(now)
    with _readonly(topic_db) as c:
        topic_row = c.execute(
            "SELECT topic_id,title,state FROM topics WHERE topic_id=?", (topic,)
        ).fetchone()
        if topic_row is None:
            raise ValueError("unknown Baton topic")
        rows = c.execute("""
            SELECT p.post_id,p.claimed_author,p.reply_post,
                   r.author_run,r.kind,r.created,r.revision,
                   r.transport_actor,r.verification_state
            FROM discussion_posts p
            JOIN discussion_revisions r USING(post_id)
            WHERE p.topic_id=?
              AND r.revision=(SELECT MAX(r2.revision)
                              FROM discussion_revisions r2
                              WHERE r2.post_id=p.post_id)
            ORDER BY r.created DESC,p.post_id DESC
            LIMIT 6
        """, (topic,)).fetchall()
    posts = [{
        "post_id": r["post_id"], "claimed_author": r["claimed_author"],
        "run_claim": r["author_run"], "kind": r["kind"],
        "revision": r["revision"], "created": r["created"],
        "seconds_since_post": max(0, checked - r["created"]),
        "transport_actor": r["transport_actor"],
        "verification_state": r["verification_state"],
        "model_author_authenticated": False
    } for r in rows]

    # Optional separately captured delivery traces; not topic-specific proof.
    wakes = None
    if wake_db is not None:
        with _readonly(wake_db) as c:
            records = c.execute("""
                SELECT id,target,title,state,created,updated,reply_id
                FROM wakes ORDER BY created DESC LIMIT 8
            """).fetchall()
        wakes = [{
            "wake_id": r["id"], "target_claim": r["target"],
            "last_observed_state": r["state"],
            "observed_at": r["updated"],
            "age_seconds": max(0, checked - r["updated"]),
            "reply_id": r["reply_id"],
            "historical_receipt_only": True
        } for r in records]

    return {
        "topic": dict(topic_row), "checked_at": checked,
        "recent_posts": posts,
        "wake_receipts": wakes,
        "model_active_now": "unknown",
        "currently_working_on": "not_proven_from_stored_evidence",
        "effect_authorization": "not_checked",
        "observation_note": "Post, OS process and wake receipt are not active-model proof"
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topic-db", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--wake-db")
    args = p.parse_args()
    print(json.dumps(snapshot(args.topic_db, args.topic, wake_db=args.wake_db),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
