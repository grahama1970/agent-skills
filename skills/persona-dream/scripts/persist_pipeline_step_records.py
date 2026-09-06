#!/usr/bin/env python3
"""Persist one revision's staged 42-step pipeline record bundle through Memory.

The bundle (`pipeline_step_records.v1.json`) is staged inside the frozen
revision before index/manifest/activation, so the documents are part of the
qualified artifact set. This command upserts those documents, exactly rereads
them by run/revision filters, refreshes server-owned semantic sync fields, and
writes the write/reread receipt OUTSIDE the frozen revision under
`.persona-dream/state/` so the revision's bound artifact index stays intact.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from pydantic_step_gate import validate_http_json
SERVER_OWNED_FIELDS = (
    "semantic_sync_state",
    "qdrant_collection",
    "qdrant_point_id",
)


def response_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    validate_http_json("memory_store", payload)
    return payload.get("documents") or payload.get("items") or []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve(strict=True)
    revision_root = run_root / ".persona-dream" / "revisions" / args.revision_id
    bundle_path = revision_root / "pipeline_step_records.v1.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("schema") != "persona_dream.pipeline_step_memory_bundle.v1":
        raise SystemExit(f"unexpected bundle schema: {bundle.get('schema')}")
    if bundle.get("revision_id") != args.revision_id:
        raise SystemExit("bundle revision mismatch")
    documents = [dict(document) for document in bundle["documents"]]
    expected_count = int(bundle["count"])
    if len(documents) != expected_count:
        raise SystemExit(f"bundle count mismatch: declared {expected_count}, observed {len(documents)}")
    collection = str(bundle["collection"])
    run_id = str(bundle["run_id"])
    expected_keys = {document["_key"] for document in documents}
    if len(expected_keys) != expected_count:
        raise SystemExit("duplicate step keys in bundle")

    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "document_count": expected_count, "collection": collection}, indent=2))
        return 0

    filters = {"run_id": run_id, "revision_id": args.revision_id}
    timeout = httpx.Timeout(60.0, connect=5.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        write = client.post("/upsert", json={"collection": collection, "documents": documents})
        write.raise_for_status()
        first = client.post("/list", json={"collection": collection, "limit": 100, "filters": filters})
        first.raise_for_status()
        first_docs = response_documents(validate_http_json("memory_list", first.json()))
        by_key = {document.get("_key"): document for document in first_docs}
        if set(by_key) != expected_keys:
            raise SystemExit(
                f"first exact reread key mismatch: expected {expected_count}, got {len(by_key)}"
            )
        for document in documents:
            stored = by_key[document["_key"]]
            for field in SERVER_OWNED_FIELDS:
                document[field] = stored.get(field)
        refresh = client.post("/upsert", json={"collection": collection, "documents": documents})
        refresh.raise_for_status()
        final = client.post("/list", json={"collection": collection, "limit": 100, "filters": filters})
        final.raise_for_status()
        final_docs = response_documents(validate_http_json("memory_list", final.json()))

    final_keys = {document.get("_key") for document in final_docs}
    if final_keys != expected_keys or len(final_docs) != expected_count:
        raise SystemExit(f"final exact reread mismatch: expected {expected_count}, got {len(final_docs)}")

    for document in documents:
        stored = next(item for item in final_docs if item.get("_key") == document["_key"])
        for field in ("status", "step_no", "step_slug", "disposition"):
            if stored.get(field) != document.get(field):
                raise SystemExit(f"exact reread field mismatch on {document['_key']}: {field}")

    receipt = {
        "schema": "persona_dream.pipeline_step_memory_write_receipt.v1",
        "status": f"PASS_EXACT_REREAD_{expected_count}_OF_{expected_count}",
        "collection": collection,
        "run_id": run_id,
        "revision_id": args.revision_id,
        "bundle_path": str(bundle_path),
        "upsert_response": validate_http_json("memory_store", write.json()),
        "semantic_refresh_response": validate_http_json("memory_store", refresh.json()),
        "exact_reread_count": len(final_docs),
        "expected_count": expected_count,
        "exact_reread_keys": sorted(final_keys),
        "semantic_synced_count": sum(document.get("semantic_sync_state") == "synced" for document in final_docs),
        "qdrant_pointer_count": sum(bool(document.get("qdrant_point_id")) for document in final_docs),
        "exact_reread_filters": filters,
        "mocked": False,
        "live": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = run_root / ".persona-dream" / "state" / f"pipeline_step_memory_receipt_{args.revision_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"],
        "exact_reread_count": receipt["exact_reread_count"],
        "semantic_synced_count": receipt["semantic_synced_count"],
        "qdrant_pointer_count": receipt["qdrant_pointer_count"],
        "receipt_path": str(receipt_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
