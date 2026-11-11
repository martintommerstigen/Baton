"""B1 source observer via restricted Unix snapshot relay, WITHOUT CDP access.

A recorded R22 witness is not a ChatGPT wake or authorship proof. No UI Send.
No automatic retry if a witness may have been committed.
"""
import argparse
import json
import os

from b1_snapshot_relay import observe_via_snapshots
from chatgpt_ui_driver import PAUSE_FILE, pause_active


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "source-turn-id", "target", "id", "payload-sha256",
                "snapshot-socket", "collector-uid", "broker-socket", "broker-uid"):
        p.add_argument("--" + arg, required=True)
    a = p.parse_args(argv)
    try:
        collector_uid, broker_uid = int(a.collector_uid), int(a.broker_uid)
    except ValueError:
        p.error("peer UIDs must be integers")
    if (min(collector_uid, broker_uid) <= 0 or collector_uid == broker_uid
            or os.geteuid() in (0, collector_uid, broker_uid)):
        p.error("observer, collector and broker must use three distinct non-root UIDs")
    from remote_security.broker_peer import query_verified_broker
    def snapshot_query(req):
        return query_verified_broker(a.snapshot_socket, collector_uid, req,
                                     require_distinct_uid=True)
    def witness_query(req):
        return query_verified_broker(a.broker_socket, broker_uid, req,
                                     require_distinct_uid=True)
    result = observe_via_snapshots(
        source=a.source, source_turn_id=a.source_turn_id,
        target=a.target, message_id=a.id, payload_sha256=a.payload_sha256,
        snapshot_query=snapshot_query, witness_query=witness_query,
        pause_checker=lambda: pause_active(PAUSE_FILE))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
