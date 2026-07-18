#!/usr/bin/env python3
"""Replay a Watch source-session journal into isolated sinks (gate P0B).

Read-only consumer of the immutable journal written by the tracker adapter.
Order of operations is fail-closed: the journal is fully validated and the
deterministic observation plan is built BEFORE any embedding, Qdrant, or
Memory client call. A tampered or truncated journal exits with
``JOURNAL_REJECTED`` and zero side effects.

Persistence is idempotent by construction: observation documents contain no
volatile fields (no wall-clock timestamps), keys and Qdrant point ids are the
deterministic observation ids, and re-running against the unchanged journal
converges to the identical canonical observation set. Killing this process at
any point and restarting it is therefore a supported recovery path.

Targets default to ISOLATED test collections — never the production
watch_content / crop-embedding collections.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from watch_source_session_journal import (  # noqa: E402
    JournalValidationError,
    build_observation_plan,
    canonical_json,
    read_journal,
    sha256_hex,
)

DEFAULT_QDRANT_COLLECTION = "watch_p0b_replay_observations_test"
DEFAULT_MEMORY_COLLECTION = "watch_p0b_replay_observations_test"


def observation_document(plan: dict[str, Any], obs: dict[str, Any], journal_path: str) -> dict[str, Any]:
    return {
        "_key": obs["observation_id"],
        "schema": "watch.source_session_observation.v1",
        "record_kind": "watch_source_session_observation",
        "source_session_id": obs["source_session_id"],
        "source_sha256": plan["source_sha256"],
        "journal_path": journal_path,
        "track_id": obs["track_id"],
        "first_event_sequence": obs["first_event_sequence"],
        "last_event_sequence": obs["last_event_sequence"],
        "event_ids": obs["event_ids"],
        "event_count": obs["event_count"],
        "window_start_seconds": obs["window_start_seconds"],
        "window_end_seconds": obs["window_end_seconds"],
        "clock_mode": obs["clock_mode"],
        "evidence_digest": obs["evidence_digest"],
        "asset_uid": obs["asset_uid"],
        "stream_id": obs["stream_id"],
        "segment_id": obs["segment_id"],
        "identity_status": "IDENTITY_INCONCLUSIVE",
        "promotion_blockers": ["SOURCE_SESSION_REPLAY_CANARY_ONLY"],
        "retrieval_text": (
            f"Watch source-session replay observation {obs['observation_id']} for "
            f"{obs['track_id']} in session {obs['source_session_id']}, window "
            f"{obs['window_start_seconds']:.2f}-{obs['window_end_seconds']:.2f}s, "
            f"{obs['event_count']} journal events, evidence digest {obs['evidence_digest'][:16]}."
        ),
    }


def canonical_set_from_documents(documents: list[dict[str, Any]]) -> str:
    pairs = sorted((d["_key"], d["evidence_digest"]) for d in documents)
    return sha256_hex(canonical_json([[k, v] for k, v in pairs]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:8603")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--qdrant-collection", default=DEFAULT_QDRANT_COLLECTION)
    parser.add_argument("--memory-collection", default=DEFAULT_MEMORY_COLLECTION)
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--receipt-out", type=Path, help="Write a completion receipt JSON here")
    parser.add_argument(
        "--per-observation-delay",
        type=float,
        default=0.0,
        help="Test hook: sleep this many seconds after each observation write",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate + plan, no side effects (P0A preflight behavior)",
    )
    args = parser.parse_args()

    for name in ("watch_content", "watch_track_crop_embeddings_jina_v5_1024",
                 "watch_reference_image_embeddings_jina_v5_1024", "watch_keyframe_annotations"):
        if name in (args.qdrant_collection, args.memory_collection):
            print(f"REFUSED_PRODUCTION_COLLECTION: {name}")
            return 3

    # Fail-closed boundary: everything below must succeed before any client
    # is constructed or any network call is made.
    try:
        header, events, _finalize = read_journal(args.journal)
    except JournalValidationError as exc:
        print(f"JOURNAL_REJECTED: {exc}")
        return 2
    plan = build_observation_plan(header, events)
    documents = [
        observation_document(plan, obs, str(args.journal)) for obs in plan["observations"]
    ]
    planned_canonical = canonical_set_from_documents(documents)
    if planned_canonical != sha256_hex(
        canonical_json(
            sorted([[o["observation_id"], o["evidence_digest"]] for o in plan["observations"]])
        )
    ):
        print("PLAN_CANONICAL_MISMATCH")
        return 2

    if args.plan_only:
        print(
            f"PLAN_OK session={plan['source_session_id']} "
            f"observations={plan['observation_count']} canonical={planned_canonical[:16]}"
        )
        return 0

    import httpx

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0), headers={"X-Caller-Skill": "watch"}) as client:
        collections = client.get(f"{args.qdrant_url}/collections").json()
        names = {c["name"] for c in collections.get("result", {}).get("collections", [])}
        if args.qdrant_collection not in names:
            client.put(
                f"{args.qdrant_url}/collections/{args.qdrant_collection}",
                json={"vectors": {"size": args.dimensions, "distance": "Cosine"}},
            ).raise_for_status()

        written = 0
        for document in documents:
            embedding = client.post(
                f"{args.embedding_url}/embed/batch",
                json={"texts": [document["retrieval_text"]], "task": "retrieval", "dimensions": args.dimensions},
            )
            embedding.raise_for_status()
            vector = (embedding.json().get("embeddings") or [[]])[0]
            client.put(
                f"{args.qdrant_url}/collections/{args.qdrant_collection}/points",
                params={"wait": "true"},
                json={
                    "points": [
                        {
                            "id": document["_key"],
                            "vector": vector,
                            "payload": {
                                "source_session_id": document["source_session_id"],
                                "track_id": document["track_id"],
                                "evidence_digest": document["evidence_digest"],
                                "window_start_seconds": document["window_start_seconds"],
                                "window_end_seconds": document["window_end_seconds"],
                            },
                        }
                    ]
                },
            ).raise_for_status()
            client.post(
                f"{args.memory_url}/upsert",
                json={"collection": args.memory_collection, "documents": [document]},
            ).raise_for_status()
            written += 1
            print(f"observation_written {written}/{len(documents)} {document['_key']}", flush=True)
            if args.per_observation_delay > 0:
                time.sleep(args.per_observation_delay)

    receipt = {
        "schema_version": "watch.source_session_replay_receipt.v1",
        "status": "REPLAY_COMPLETE",
        "journal": str(args.journal),
        "source_session_id": plan["source_session_id"],
        "qdrant_collection": args.qdrant_collection,
        "memory_collection": args.memory_collection,
        "observation_count": len(documents),
        "canonical_set_sha256": planned_canonical,
        "observation_ids": [d["_key"] for d in documents],
    }
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"REPLAY_COMPLETE observations={len(documents)} canonical={planned_canonical[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
