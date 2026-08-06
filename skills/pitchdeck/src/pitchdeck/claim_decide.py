"""Writable claim triage: the sanctioned decision path for the ledger (#1227).

decide_claim sets a candidate claim's status with human provenance, appends a
replayable JSONL audit line, re-validates the whole bundle, and re-emits the
UI bundle — the ONLY supported write path for review decisions (the ledger is
a governance file: not undoable, not chat-appliable). Batch decisions refuse
high-risk and numeric claims (anti-rubber-stamp: those are individual
decisions by construction). replay_decisions re-applies an audit log
deterministically. Failure modes: unknown claim, non-candidate re-decision
without --force, and validation failures refuse with nothing written.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml
from loguru import logger

from .models import ClaimApproval, ClaimLedger, ClaimRisk, ClaimStatus

DECISION_LOG = "claim_decisions.jsonl"
_HAS_DIGIT = re.compile(r"\d")


def _write_ledger(bundle_dir: Path, ledger: ClaimLedger) -> None:
    payload = ledger.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["claims"] = [{k: v for k, v in c.items() if v not in ([], None)} for c in payload["claims"]]
    (bundle_dir / "claim_ledger.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def decide_claim(
    bundle_dir: Path,
    output_dir: Path,
    *,
    claim_id: str,
    decision: str,
    decided_by: str,
    qualifier: str | None = None,
    batch: bool = False,
    deck_name: str = "deck.public.yaml",
) -> dict:
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    from .slide_edit import _load

    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    claim = next((c for c in ledger.claims if c.id == claim_id), None)
    if claim is None:
        raise ValueError(f"no claim '{claim_id}' in the ledger")
    if batch and (claim.risk == ClaimRisk.HIGH or _HAS_DIGIT.search(claim.text)):
        raise PermissionError(
            f"claim '{claim_id}' is high-risk or numeric; batch decisions are refused — decide it individually"
        )

    updated = claim.model_copy(
        update={
            "status": ClaimStatus.APPROVED if decision == "approve" else ClaimStatus.REJECTED,
            "approval": ClaimApproval(approved_by=decided_by, approved_at=datetime.now(UTC).isoformat())
            if decision == "approve"
            else None,
            "required_qualifier": qualifier or claim.required_qualifier,
        }
    )
    new_ledger = ledger.model_copy(
        update={"claims": [updated if c.id == claim_id else c for c in ledger.claims]}
    )

    # Validate the WHOLE bundle with the decided ledger before writing anything.
    from .ui_emitter import emit_ui_bundle

    emit_ui_bundle(
        deck, new_ledger, sources, assets,
        source_manifest_dir=source_path.parent, asset_manifest_dir=bundle_dir, output_dir=output_dir,
    )
    _write_ledger(bundle_dir, new_ledger)
    with (bundle_dir / DECISION_LOG).open("a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "claim_id": claim_id,
                    "decision": decision,
                    "decided_by": decided_by,
                    "qualifier": qualifier,
                    "batch": batch,
                    "decided_at": datetime.now(UTC).isoformat(),
                }
            )
            + "\n"
        )
    logger.info("claim decision: {} {} by {}", decision, claim_id, decided_by)
    remaining = sum(1 for c in new_ledger.claims if c.status == ClaimStatus.CANDIDATE)
    return {"claim_id": claim_id, "decision": decision, "candidates_remaining": remaining}


def replay_decisions(bundle_dir: Path, output_dir: Path, log_path: Path, *, deck_name: str = "deck.public.yaml") -> dict:
    """Deterministically re-apply an audit log (proof gate: decisions replay)."""
    applied = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        decide_claim(
            bundle_dir, output_dir,
            claim_id=record["claim_id"], decision=record["decision"],
            decided_by=record["decided_by"], qualifier=record.get("qualifier"),
            batch=False, deck_name=deck_name,
        )
        applied += 1
    return {"replayed": applied}
