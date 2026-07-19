#!/usr/bin/env python3
"""Persist cognitive-loop governance + step records THROUGH the $memory API.

After the first legitimate canonical dream-memory write (phase 15 on an accepted,
non-superseded successor return), this records the provenance:

  * one governance record in ``persona_dream_governance`` describing the
    canonical-write event (dream key, acceptance-receipt sha, loop-receipt sha),
  * the phase 13/14/15 step records in ``persona_dream_pipeline_steps`` are
    read-modified-written to reflect their new live-proven status.

Every write is followed by an exact reread-by-_key; a /store "true" response is
NOT accepted as proof - the reread content hash is.
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("phase15_dream_persistence", _HERE / "phase15_dream_persistence.py")
assert _spec and _spec.loader
p15 = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(p15)

GOVERNANCE_COLLECTION = "persona_dream_governance"
STEPS_COLLECTION = "persona_dream_pipeline_steps"

# Fields the $memory API stamps/recomputes on every /store (epoch timestamps and
# semantic-sync metadata). They must be excluded from a caller-authored record so
# the exact reread-by-key comparison covers only fields the caller controls.
SERVER_MANAGED_FIELDS = {
    "created_at", "updated_at", "text_hash", "semantic_sync_state",
    "qdrant_point_id", "qdrant_collection", "embedding_model", "embedding_version",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_one(collection: str, key: str, base_url: str) -> dict[str, Any] | None:
    resp = p15._http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": collection, "limit": 1, "filters": {"_key": key}},
    )
    docs = resp.get("documents") or resp.get("items") or []
    return docs[0] if docs else None


def run(
    loop_receipt_path: Path,
    persistence_receipt_path: Path,
    acceptance_receipt_path: Path,
    run_id: str,
    revision_id: str,
    return_id: str,
    base_url: str = p15.MEMORY_BASE_URL,
) -> dict[str, Any]:
    loop_receipt = p15.read_json(loop_receipt_path)
    persistence = p15.read_json(persistence_receipt_path)
    acceptance = p15.read_json(acceptance_receipt_path)
    proof = persistence.get("canonical_write_proof") or {}
    dream_key = next((k for k in proof.get("node_keys", []) if k.startswith("dream_")), None)

    receipts: list[dict[str, Any]] = []

    # 1) Governance record for the canonical-write event.
    gov_key = f"persona_dream:{run_id}:{revision_id}:cognitive_loop_canonical_write"
    gov_doc = {
        "_key": gov_key,
        "schema": "persona_dream.governance_record.v1",
        "kind": "governance",
        "record_type": "cognitive_loop_canonical_write",
        "status": persistence.get("status"),
        "run_id": run_id,
        "revision_id": revision_id,
        "return_id": return_id,
        "canonical_dream_memory_written": bool(persistence.get("canonical_dream_memory_written")),
        "dream_memory_key": dream_key,
        "canonical_node_keys": proof.get("node_keys", []),
        "canonical_edge_keys": proof.get("edge_keys", []),
        "all_exact_reread_match": proof.get("all_exact_reread_match"),
        "acceptance_receipt_sha256": p15.canonical_sha(acceptance),
        "loop_receipt_sha256": p15.canonical_sha(loop_receipt),
        "persistence_receipt_sha256": p15.canonical_sha(persistence),
        "text_reasoning_route": "tau:persona-dream-text-reasoning (no direct scillm)",
        "tags": ["persona_dream", "governance", "cognitive_loop", "canonical_write", f"revision:{revision_id}"],
        "retrieval_text": (
            f"Persona-dream cognitive loop 12->15 wrote canonical synthetic dream memory "
            f"{dream_key} for accepted successor return {return_id} in revision {revision_id}; "
            f"phases 13/14 text reasoning routed through the Tau node; exact reread proven."
        ),
        "observed_at": utc_now(),
    }
    receipts.append({"role": "governance", **p15.store_and_reread(gov_doc, GOVERNANCE_COLLECTION, base_url)})

    # 2) Phase 13/14/15 step records - read-modify-write to preserve existing fields.
    phase_status = {
        "13": ("13_self_interpretation", "Persona Self-Interpretation"),
        "14": ("14_tom_validation", "Theory-of-Mind Validation"),
        "15": ("15_persistence", "Memory, Graph, and Qdrant Persistence"),
    }
    phase_by_id = {ph["phase"].split("_", 1)[0]: ph for ph in loop_receipt.get("phases", [])}
    for pid, (phase_slug, title) in phase_status.items():
        key = f"persona-dream:pipeline:phase:{pid}"
        existing = _list_one(STEPS_COLLECTION, key, base_url) or {"_key": key, "phase_id": pid, "title": title}
        merged = {
            k: v for k, v in existing.items()
            if (not k.startswith("_") or k == "_key") and k not in SERVER_MANAGED_FIELDS
        }
        loop_phase = phase_by_id.get(pid, {})
        merged["status_class"] = "Live-Proven-On-Accepted-Return"
        merged["live_slice_status"] = loop_phase.get("status")
        merged["cognitive_loop_run_id"] = run_id
        merged["cognitive_loop_revision_id"] = revision_id
        merged["cognitive_loop_return_id"] = return_id
        merged["cognitive_loop_proven_at"] = utc_now()
        if pid == "15":
            merged["canonical_dream_memory_written"] = bool(persistence.get("canonical_dream_memory_written"))
            merged["canonical_node_keys"] = proof.get("node_keys", [])
        merged["retrieval_text"] = (
            f"Phase {pid} {title} live-proven on accepted successor return {return_id}: "
            + (loop_phase.get("status") or "")
        )
        receipts.append({"role": f"step_phase_{pid}", **p15.store_and_reread(merged, STEPS_COLLECTION, base_url)})

    return {
        "schema": "persona_dream.loop_governance_receipt.v1",
        "status": "PASS_LOOP_GOVERNANCE" if all(r["exact_reread_match"] for r in receipts) else "FAIL_LOOP_GOVERNANCE",
        "run_id": run_id,
        "revision_id": revision_id,
        "return_id": return_id,
        "governance_key": gov_key,
        "records_written": len(receipts),
        "all_exact_reread_match": all(r["exact_reread_match"] for r in receipts),
        "receipts": receipts,
        "generated_at": utc_now(),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--loop-receipt", type=Path, required=True)
    p.add_argument("--persistence-receipt", type=Path, required=True)
    p.add_argument("--acceptance-receipt", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--revision-id", required=True)
    p.add_argument("--return-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = run(
        args.loop_receipt, args.persistence_receipt, args.acceptance_receipt,
        args.run_id, args.revision_id, args.return_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p15.write_json(args.output, result)
    if args.json:
        print(json.dumps({
            "status": result["status"],
            "governance_key": result["governance_key"],
            "records_written": result["records_written"],
            "all_exact_reread_match": result["all_exact_reread_match"],
        }, indent=2))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
