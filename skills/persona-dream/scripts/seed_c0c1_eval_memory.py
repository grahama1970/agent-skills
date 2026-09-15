#!/usr/bin/env python3
"""Seed literal-evaluation memory records for the preregistered C0/C1 experiment.

Memory is APPEND-ONLY (no delete route exists; destructive AQL is refused),
so `--reset` is NOT deletion: it deterministically re-upserts the arm's
records (upsert overwrites in place) so reseeding is idempotent and drift is
corrected. Arm isolation comes from deterministic arm-scoped `_key`s
(`c0c1_<arm>_<record>`) with CONSTANT canonical `event_id`s — identity is
event-level, so key/hash differences never change distinct-event counting.
Every record carries an `arm` field so admission can /list-filter by arm.

A successful /upsert is not accepted as proof: every written record is
reread by exact `_key` through /list and checked field-by-field.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

COLLECTION = "persona_memory"
SEED_SCHEMA = "persona_dream.c0c1_eval_seed.v1"
RECEIPT_SCHEMA = "persona_dream.c0c1_seed.v1"
DEFAULT_SEED_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "c0c1_eval_memory_seed.json"

# Fields that must survive the write/reread boundary byte-identically.
EXACT_FIELDS = (
    "_key",
    "schema",
    "event_id",
    "record_type",
    "persona_id",
    "user_id",
    "summary",
    "observed_at",
    "arm",
    "emotional_context",
    "intensity_value",
    "intensity_scale_max",
    "tags",
)


def _load_seed(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SEED_SCHEMA:
        raise SystemExit(f"seed fixture schema mismatch: {payload.get('schema')}")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise SystemExit("seed fixture has no records")
    by_key = {}
    for record in records:
        key = str(record.get("_key") or "")
        if not key or key in by_key:
            raise SystemExit(f"duplicate or missing _key in seed fixture: {key!r}")
        by_key[key] = record
    arms = payload.get("arms") or {}
    return {"payload": payload, "by_key": by_key, "arms": arms}


def _records_for_arm(seed: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    keys = seed["arms"].get(arm)
    if not keys:
        raise SystemExit(f"unknown arm {arm!r}; known: {sorted(seed['arms'])}")
    missing = [key for key in keys if key not in seed["by_key"]]
    if missing:
        raise SystemExit(f"arm {arm} references missing records: {missing}")
    return [seed["by_key"][key] for key in keys]


def _personas_tagged(client: httpx.Client, persona: str) -> int:
    """Count current persona_memory records carrying the persona tag."""
    resp = client.post(
        "/list",
        json={"collection": COLLECTION, "limit": 500, "filters": {"tags": f"persona:{persona}"}},
    )
    resp.raise_for_status()
    return len(resp.json().get("documents") or [])


def _seed(client: httpx.Client, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client.post("/upsert", json={"collection": COLLECTION, "documents": docs}).raise_for_status()
    results: list[dict[str, Any]] = []
    for doc in docs:
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": doc["_key"]}})
        resp.raise_for_status()
        reread = resp.json().get("documents") or []
        if len(reread) != 1:
            raise SystemExit(f"exact reread count mismatch for {doc['_key']}: {len(reread)}")
        got = reread[0]
        mismatches = [field for field in EXACT_FIELDS if got.get(field) != doc.get(field)]
        if mismatches:
            raise SystemExit(f"exact reread field mismatch for {doc['_key']}: {mismatches}")
        results.append({
            "_key": doc["_key"],
            "event_id": doc["event_id"],
            "exact_reread": True,
            "semantic_sync_state": got.get("semantic_sync_state"),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=["c0", "c1", "c1_null", "c1_inert", "full"])
    parser.add_argument("--reset", action="store_true",
                        help="Re-upsert the arm's records (memory is append-only; this is idempotent overwrite, not deletion).")
    parser.add_argument("--seed-file", default=str(DEFAULT_SEED_PATH))
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    seed = _load_seed(Path(args.seed_file))
    docs = _records_for_arm(seed, args.arm)
    payload = seed["payload"]
    before_count = None
    timeout = httpx.Timeout(30.0, connect=2.0)
    try:
        with httpx.Client(base_url=args.memory_base_url.rstrip("/"), timeout=timeout) as client:
            before_count = _personas_tagged(client, payload["persona"])
            rereads = _seed(client, docs)
            after_count = _personas_tagged(client, payload["persona"])
    except SystemExit:
        raise
    except Exception as exc:  # fail closed on any transport/service error
        raise SystemExit(f"BLOCKED_SEED_MEMORY_UNAVAILABLE: {exc}") from exc

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS_C0C1_EVAL_MEMORY_SEEDED",
        "arm": args.arm,
        "reset_requested": bool(args.reset),
        "reset_semantics": "upsert-overwrite idempotent (memory is append-only; no delete route)",
        "collection": COLLECTION,
        "persona_id": payload["persona"],
        "user_id": payload["user"],
        "seeded_keys": [d["_key"] for d in docs],
        "record_count": len(docs),
        "persona_tag_count_before": before_count,
        "persona_tag_count_after": after_count,
        "exact_rereads": rereads,
        "seed_file": str(Path(args.seed_file).resolve()),
        "mocked": False,
        "live": True,
        "failed_gates": [],
    }
    receipt_path = Path(args.receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"seeded {len(docs)} records for arm {args.arm}: {receipt['status']}")


if __name__ == "__main__":
    main()
