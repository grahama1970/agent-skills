#!/usr/bin/env python3
"""Persist the state-clearing deviation audit + supersession mechanism to Memory.

Writes one durable governance record through ``$memory`` and proves an exact
reread by ``_key`` (GOAL.md Memory Persistence Contract: exact reread, not only
semantic recall). Reuses the deterministic hash + httpx pattern already used by
the other persona-dream memory writers. No provider or paid work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SKILL_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "project_knowledge"
RUN_ID = "pipeline-complete"
REVISION_ID = "rev_successor_943b01ecd9a3"
AUDIT_RECEIPT_RELPATH = (
    f"reports/pipeline-complete/.persona-dream/revisions/{REVISION_ID}/"
    "state_clearing_audit_receipt.v1.json"
)
MEMORY_KEY = f"persona_dream:{RUN_ID}:{REVISION_ID}:state_clearing_audit_and_supersession"


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def build_document(audit_receipt: dict[str, Any], *, audit_sha: str, observed_at: str) -> dict[str, Any]:
    supersede_sha = sha256_file(SKILL_ROOT / "scripts" / "revision_supersession.py")
    activate_sha = sha256_file(SKILL_ROOT / "scripts" / "activate_revision_qualification.py")
    verdict = audit_receipt["verdict"]["code"]
    retrieval_text = (
        "Persona Dream Phase D state-deletion deviation audit and sanctioned supersession "
        f"mechanism for run {RUN_ID} revision {REVISION_ID}. Five derived/mutable items were "
        "hand-cleared to re-qualify a rebuilt artifact index (old sha256:fbeedef1 -> new "
        "sha256:06496a6a): one ArangoDB active-revision pointer, one immutable queue terminal "
        "event, and three immutable qualification receipts (prepare/verify/activation). Audit "
        f"verdict {verdict}: all four file items are recoverable byte-for-byte from git commit "
        "a97c734e and the ArangoDB pointer is deterministically re-derivable from the committed "
        "old activation receipt; no evidentiary content is unrecoverable; the frozen revision "
        "rev_upstream_bf3b05d47fb8 was untouched. Codified fix: revision_supersession.py plus "
        "activate --supersede replace ad hoc deletion with a retain-and-mark supersession that "
        "archives predecessors under superseded/, snapshots the old pointer as SUPERSEDED in "
        "Memory, and records an old->new artifact-index entry in an append-only ledger; every "
        "other pointer mismatch stays fail-closed."
    )
    return {
        "_key": MEMORY_KEY,
        "schema": "persona_dream.state_clearing_audit_memory.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": "state_clearing_audit",
        "project": "persona-dream",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "source_revision_id": audit_receipt.get("source_revision_id"),
        "status": verdict,
        "audit_receipt_relative_path": AUDIT_RECEIPT_RELPATH,
        "audit_receipt_sha256": audit_sha,
        "old_artifact_index_sha256": audit_receipt["index_change"]["old_artifact_index_sha256"],
        "new_artifact_index_sha256": audit_receipt["index_change"]["new_artifact_index_sha256"],
        "deleted_item_count": len(audit_receipt["deleted_items"]),
        "deleted_items": [
            {
                "item": item["item"],
                "kind": item["kind"],
                "blocked_guard": item["blocked_guard"],
                "recoverable": item["recoverable"],
                "recoverable_from": item["recoverable_from"],
            }
            for item in audit_receipt["deleted_items"]
        ],
        "evidence_loss": audit_receipt["verdict"]["evidence_loss"],
        "git_recovery_commit": audit_receipt["git_recovery_anchor"]["old_state_commit"],
        "supersession_mechanism": {
            "supersede_script": "scripts/revision_supersession.py",
            "supersede_script_sha256": supersede_sha,
            "activate_script": "scripts/activate_revision_qualification.py",
            "activate_script_sha256": activate_sha,
            "activate_flag": "--supersede",
            "ledger": "revision_requalification_supersession_ledger.v1.json",
            "rule": "retain-and-mark, never delete; fail-closed for every non index-rebuild mismatch",
        },
        "memory_write_method": "/upsert",
        "claims": {
            "proves": [
                "the Phase D ad hoc state deletion was audited item-by-item with a recorded verdict",
                "a sanctioned supersession mechanism now exists so rebuilt-index re-qualification never requires hand-deleting DB state",
            ],
            "does_not_prove": [
                "provider readiness, publication, payment, or submission",
                "correctness of the rebuilt index or regenerated storyboard frames",
            ],
        },
        "tags": [
            "persona-dream",
            "governance",
            "state-clearing-audit",
            "supersession",
            f"run:{RUN_ID}",
            f"revision:{REVISION_ID}",
            f"verdict:{verdict.lower()}",
        ],
        "retrieval_text": retrieval_text,
        "observed_at": observed_at,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = parser.parse_args()

    audit_path = SKILL_ROOT / AUDIT_RECEIPT_RELPATH
    if not audit_path.is_file():
        raise SystemExit(f"audit receipt missing: {audit_path}")
    audit_receipt = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_sha = sha256_file(audit_path)
    observed_at = datetime.now(timezone.utc).isoformat()
    document = build_document(audit_receipt, audit_sha=audit_sha, observed_at=observed_at)

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        write = client.post("/upsert", json={"collection": COLLECTION, "documents": [document]})
        write.raise_for_status()

        reread = client.post(
            "/list",
            json={"collection": COLLECTION, "limit": 2, "filters": {"_key": MEMORY_KEY}},
        )
        reread.raise_for_status()
        observed = reread.json().get("documents") or []
        if len(observed) != 1:
            raise SystemExit(f"exact reread count mismatch for {MEMORY_KEY}: {len(observed)}")
        got = observed[0]
        for field in ("_key", "status", "old_artifact_index_sha256", "new_artifact_index_sha256", "audit_receipt_sha256", "deleted_item_count"):
            if got.get(field) != document.get(field):
                raise SystemExit(f"exact reread field mismatch for {field}: {got.get(field)!r} != {document.get(field)!r}")

    receipt = {
        "schema": "persona_dream.state_clearing_audit_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_STATE_CLEARING_AUDIT",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "memory_key": MEMORY_KEY,
        "audit_receipt_sha256": audit_sha,
        "exact_reread_count": 1,
        "semantic_sync_state": got.get("semantic_sync_state"),
        "qdrant_collection": got.get("qdrant_collection"),
        "qdrant_point_id": got.get("qdrant_point_id"),
        "memory_write_method": "/upsert",
        "observed_at": observed_at,
        "mocked": False,
        "live": True,
    }
    receipt_path = (
        SKILL_ROOT
        / "reports"
        / "pipeline-complete"
        / ".persona-dream"
        / "state"
        / f"state_clearing_audit_memory_receipt_{REVISION_ID}.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt_path": str(receipt_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
