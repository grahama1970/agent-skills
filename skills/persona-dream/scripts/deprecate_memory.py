#!/usr/bin/env python3
"""Mark a memory deprecated, since memory cannot be deleted.

The store is append-only on purpose: destructive AQL is refused and there is no
delete route. That is the right design — a memory a system can quietly rewrite
is not a memory, and a record that can vanish cannot anchor a claim.

But records do go bad. A writer keyed on the wrong thing and wrote duplicates; a
document was stored with a defect; an interpretation was superseded. The
append-only answer is a tombstone, not a deletion: rewrite the record with
``deprecated: true``, why, when, and what supersedes it. The history stays
intact and auditable, and readers skip it.

This is deliberately not a delete dressed up in different words. The original
text is preserved verbatim; only the deprecation fields are added. Anyone
auditing the store can still see exactly what was written, when, and on what
grounds it stopped counting.
"""
from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "persona_memory"


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _client():
    import httpx
    return httpx.Client(transport=httpx.HTTPTransport(uds=MEMORY_SOCKET),
                        base_url="http://localhost", timeout=30.0)


def fetch(client, key: str, collection: str) -> dict[str, Any] | None:
    resp = client.post("/query", json={
        "aql": "FOR d IN @@col FILTER d._key == @k RETURN d",
        "bind_vars": {"@col": collection, "k": key},
    })
    docs = (validate_http_json("memory_query", resp.json() or {})).get("documents") or []
    return docs[0] if docs else None


def deprecate(keys: list[str], reason: str, superseded_by: str | None,
              collection: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failed: list[str] = []
    with _client() as client:
        for key in keys:
            doc = fetch(client, key, collection)
            if doc is None:
                failed.append(f"not_found:{key}")
                results.append({"key": key, "status": "not_found"})
                continue
            if doc.get("deprecated"):
                results.append({"key": key, "status": "already_deprecated"})
                continue

            # Preserve the record exactly; add the tombstone alongside it.
            doc.pop("_id", None)
            doc.pop("_rev", None)
            doc["deprecated"] = True
            doc["deprecated_at"] = utc_now()
            doc["deprecated_reason"] = reason
            if superseded_by:
                doc["superseded_by"] = superseded_by

            resp = client.post("/store", json={"document": doc, "collection": collection})
            ok = resp.status_code < 400
            if not ok:
                failed.append(f"store_failed:{key}:{resp.status_code}")
            results.append({"key": key, "status": "deprecated" if ok else "error",
                            "http_status": resp.status_code})

        # Read back: the tombstone is only real if it is visible.
        for row in results:
            if row["status"] != "deprecated":
                continue
            doc = fetch(client, row["key"], collection)
            row["read_back_deprecated"] = bool(doc and doc.get("deprecated"))
            row["text_preserved"] = bool(doc and doc.get("solution"))
            if not row["read_back_deprecated"]:
                failed.append(f"deprecation_not_visible:{row['key']}")

    return {
        "schema": "persona_dream.memory_deprecation_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_MEMORY_DEPRECATED" if not failed else "BLOCKED_MEMORY_DEPRECATION",
        "mocked": False, "live": True,
        "collection": collection,
        "reason": reason,
        "superseded_by": superseded_by,
        "records": results,
        "rule": (
            "memory is append-only: destructive AQL is refused and no delete route "
            "exists. A bad record is tombstoned, never removed -- the original text "
            "is preserved verbatim and only deprecation fields are added, so an "
            "auditor can still see what was written and why it stopped counting."
        ),
        "failed_gates": failed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", action="append", required=True, help="document key; repeatable")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--superseded-by", help="the key that replaces these")
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = deprecate(args.key, args.reason, args.superseded_by, args.collection)
    if args.out:
        Path(args.out).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  records={len(r['records'])}"
          + (f"  failed={r['failed_gates']}" if r["failed_gates"] else ""))
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
