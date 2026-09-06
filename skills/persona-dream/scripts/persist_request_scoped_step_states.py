#!/usr/bin/env python3
"""Update request-scoped pipeline step records for a repaired Phase 11 request.

After the zero-call Phase 11 preflight chain (payload binding, provider source
snapshot, public media evidence, canonical compile, adapter preflight) passes
for a new request hash, steps 21-29 gain fresh request-scoped evidence and
step 30 becomes the required BLOCKED_AWAITING_HUMAN_APPROVAL stop state. This
command updates those revision-bound Memory records with exact reread proof
and writes its receipt outside the frozen revision artifact set.
"""
from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

STEP_COLLECTION = "persona_dream_pipeline_steps"
PREFLIGHT = "phase_11_submit_return/preflight"
CANONICAL = "phase_11_submit_return/canonical"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve(strict=True)
    revision_root = run_root / ".persona-dream" / "revisions" / args.revision_id

    request = json.loads((revision_root / CANONICAL / "phase11_live_request.v1.json").read_text(encoding="utf-8"))
    request_hash = str(request["approval_bindings"]["request_body_sha256"])
    request_key = request_hash.removeprefix("sha256:")
    preflight_receipt_path = revision_root / PREFLIGHT / "phase11_adapter_preflight_receipt.v1.json"
    preflight = json.loads(preflight_receipt_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS_PHASE11_ADAPTER_PREFLIGHT" or preflight.get("technical_blockers"):
        raise SystemExit("adapter preflight not passing; refusing to update step records")
    if preflight.get("request_body_sha256") != request_hash:
        raise SystemExit("preflight/request hash mismatch")
    ledger_path = revision_root / f"phase_11_submit_return/attempts/{request_key}/attempt_ledger.v1.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("actual_provider_call_attempts") != 0 or ledger.get("submit_intent_count") != 0:
        raise SystemExit("attempt ledger is not unused; refusing to update step records")

    transition_path = revision_root / PREFLIGHT / "provider_media_transition_manifest.json"
    binding_path = revision_root / PREFLIGHT / "phase11_payload_binding.json"
    snapshot_path = revision_root / PREFLIGHT / "provider_source_snapshot.json"
    media_manifest_path = revision_root / CANONICAL / "phase11_media_binding_manifest.v2.json"
    pending_packet_path = revision_root / PREFLIGHT / "phase11_authorization_packet.v1.pending.json"

    updates_spec: dict[int, dict[str, Any]] = {
        21: {
            "status": "PASS_EXISTING_PUBLICATION_REUSED",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{PREFLIGHT}/provider_media_transition_manifest.json"],
        },
        22: {
            "status": "PASS_NOT_REQUIRED_ALREADY_PUBLISHED",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{PREFLIGHT}/provider_media_transition_manifest.json"],
        },
        23: {
            "status": "PASS",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [
                f"{PREFLIGHT}/phase11_adapter_preflight_receipt.v1.json",
                f"{PREFLIGHT}/provider_media_transition_manifest.json",
            ],
        },
        24: {
            "status": "BLOCKED_AWAITING_HUMAN_APPROVAL",
            "disposition": "blocked",
            "blocker": f"publication_authorization approval missing for request {request_hash}",
            "paths": [f"{PREFLIGHT}/phase11_authorization_packet.v1.pending.json"],
        },
        25: {
            "status": "PASS",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{PREFLIGHT}/provider_media_transition_manifest.json"],
        },
        26: {
            "status": "PASS",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{PREFLIGHT}/provider_media_transition_manifest.json", f"{PREFLIGHT}/phase11_payload_binding.json"],
        },
        27: {
            "status": "PASS",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{CANONICAL}/phase11_media_binding_manifest.v2.json"],
        },
        28: {
            "status": "PASS_COMPILED_ZERO_CALL",
            "disposition": "revalidated_current",
            "blocker": None,
            "paths": [f"{CANONICAL}/phase11_live_request.v1.json"],
        },
        29: {
            "status": "BLOCKED_AWAITING_HUMAN_APPROVAL",
            "disposition": "blocked",
            "blocker": "all technical provider gates pass; five hash-bound human approvals are missing",
            "paths": [
                f"{PREFLIGHT}/phase11_adapter_preflight_receipt.v1.json",
                f"phase_11_submit_return/attempts/{request_key}/attempt_ledger.v1.json",
            ],
        },
        30: {
            "status": "BLOCKED_AWAITING_HUMAN_APPROVAL",
            "disposition": "blocked",
            "blocker": (
                f"one paid Kling attempt for exact request {request_hash} requires explicit human "
                "hash-bound authorization; attempt ledger is unused with zero calls"
            ),
            "paths": [
                f"{PREFLIGHT}/phase11_authorization_packet.v1.pending.json",
                f"phase_11_submit_return/attempts/{request_key}/attempt_ledger.v1.json",
            ],
        },
        40: {
            "status": "BLOCKED_AWAITING_HUMAN_APPROVAL",
            "disposition": "blocked",
            "blocker": (
                "steps 05-29 pass, are revalidated, or are compiled zero-call; the critical path is the "
                f"five human approvals for repaired request {request_hash}, then one authorized submit"
            ),
            "paths": [f"{CANONICAL}/phase11_approval_requirements.v1.json"],
        },
    }

    for path in (transition_path, binding_path, snapshot_path, media_manifest_path, pending_packet_path):
        if not path.is_file():
            raise SystemExit(f"required evidence missing: {path}")

    filters = {"run_id": run_root.name, "revision_id": args.revision_id}
    timeout = httpx.Timeout(60.0, connect=5.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        listing = client.post("/list", json={"collection": STEP_COLLECTION, "limit": 100, "filters": filters})
        listing.raise_for_status()
        documents = validate_http_json("memory_list", listing.json()).get("documents") or listing.json().get("items") or []
        by_step = {int(document["step_no"]): document for document in documents if "step_no" in document}
        updates = []
        for step_no, spec in sorted(updates_spec.items()):
            document = dict(by_step[step_no])
            document.pop("_id", None)
            document.pop("_rev", None)
            document["status"] = spec["status"]
            document["disposition"] = spec["disposition"]
            document["blocker"] = spec["blocker"]
            document["request_hash"] = request_hash
            document["outputs"] = spec["paths"]
            document["receipt_paths"] = [path for path in spec["paths"] if path.endswith(".json")]
            document["artifact_hashes"] = {
                relative: sha256_file(revision_root / relative) for relative in spec["paths"]
            }
            document["retrieval_text"] = (
                f"Persona Dream {run_root.name} {args.revision_id} step {step_no:02d} "
                f"{document.get('step_name')} status {spec['status']} for repaired request {request_hash}"
            )
            document["tags"] = [
                tag for tag in document.get("tags", []) if not str(tag).startswith(("status:", "disposition:"))
            ] + [f"status:{spec['status'].lower()}", f"disposition:{spec['disposition']}", f"request:{request_key[:16]}"]
            updates.append(document)
        write = client.post("/upsert", json={"collection": STEP_COLLECTION, "documents": updates})
        write.raise_for_status()
        recheck = client.post("/list", json={"collection": STEP_COLLECTION, "limit": 100, "filters": filters})
        recheck.raise_for_status()
        rechecked = validate_http_json("memory_list", recheck.json()).get("documents") or recheck.json().get("items") or []

    reread_by_step = {int(document["step_no"]): document for document in rechecked if "step_no" in document}
    if len(rechecked) != 42:
        raise SystemExit(f"exact reread count changed: {len(rechecked)}")
    for step_no, spec in updates_spec.items():
        observed = reread_by_step[step_no].get("status")
        if observed != spec["status"]:
            raise SystemExit(f"exact reread status mismatch for step {step_no:02d}: {observed}")

    receipt = {
        "schema": "persona_dream.request_scoped_step_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_REQUEST_SCOPED_STEPS",
        "collection": STEP_COLLECTION,
        "run_id": run_root.name,
        "revision_id": args.revision_id,
        "request_body_sha256": request_hash,
        "updated_steps": sorted(updates_spec),
        "step_states": {f"{step_no:02d}": spec["status"] for step_no, spec in sorted(updates_spec.items())},
        "attempt_ledger": {
            "path": str(ledger_path.relative_to(run_root)),
            "state": ledger.get("state"),
            "actual_provider_call_attempts": ledger.get("actual_provider_call_attempts"),
            "submit_intent_count": ledger.get("submit_intent_count"),
        },
        "exact_reread_total": len(rechecked),
        "mocked": False,
        "live": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = run_root / ".persona-dream" / "state" / f"request_scoped_step_memory_receipt_{args.revision_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"],
        "updated_steps": receipt["updated_steps"],
        "request_body_sha256": request_hash,
        "receipt_path": str(receipt_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
