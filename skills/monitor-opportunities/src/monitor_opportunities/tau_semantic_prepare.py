"""Materialize validated Tau semantic input artifacts from a completed run."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .contracts import (
    IMMUTABLE_GOAL,
    ResultStatus,
    TauSemanticRelationshipStatus,
    validate_manifest,
    validate_tau_semantic_input,
)
from .util import read_json, sha256_json, utc_now, write_json


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _goal_hash() -> str:
    return "sha256:" + hashlib.sha256(IMMUTABLE_GOAL.encode("utf-8")).hexdigest()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "opportunity"


def _claim_facts(claim_snapshot: dict[str, Any], claim_keys: list[str]) -> list[str]:
    claims = {row.get("claim_key"): row for row in claim_snapshot.get("claims", [])}
    facts: list[str] = []
    for claim_key in claim_keys:
        claim = claims.get(claim_key)
        if not claim:
            facts.append(claim_key)
            continue
        wordings = [
            row.get("text")
            for row in claim.get("wordings", [])
            if row.get("approved") is True and row.get("text")
        ]
        if wordings:
            facts.append(f"{claim_key}: {wordings[0]}")
        else:
            facts.append(claim_key)
    return facts or ["claim:unknown"]


def _source_receipt_hash(receipt: dict[str, Any]) -> str:
    return "sha256:" + sha256_json(receipt)


def _relationship_evidence(
    manifest: dict[str, Any],
    opportunity_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    for signal in manifest.get("relationship_signals", []):
        if signal.get("source_opportunity_id") != opportunity_id:
            continue
        evidence.append(
            {
                "signal_id": signal["signal_id"],
                "redacted_contact_ref": f"relationship_signal:{signal['signal_id']}",
                "relationship_type": signal.get("signal_type", "relationship_signal"),
                "strength_confidence": 0.7 if signal.get("memory_recall_found") else 0.5,
                "observed_at": manifest["generated_at"],
                "source_receipt_hash": _source_receipt_hash(signal),
                "permitted_fact": signal.get("provenance")
                or "Report-visible relationship signal exists for this opportunity.",
            }
        )
    status = (
        TauSemanticRelationshipStatus.HAS_RELATIONSHIP_EVIDENCE.value
        if evidence
        else TauSemanticRelationshipStatus.NO_RELATIONSHIP_EVIDENCE.value
    )
    return status, evidence


def _source_health(receipts: list[dict[str, Any]]) -> str:
    if all(row.get("result_status") == ResultStatus.MATCHES.value for row in receipts):
        return "OK"
    return "DEGRADED"


def prepare_tau_semantic_inputs(
    *,
    run_dir: Path,
    out_dir: Path,
    top_n: int = 3,
) -> dict[str, Any]:
    """Write validated provider-input JSON files without invoking any provider."""

    manifest_path = run_dir / "report-manifest.json"
    run_receipt_path = run_dir / "run-receipt.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing report manifest: {manifest_path}")
    if not run_receipt_path.exists():
        raise FileNotFoundError(f"missing run receipt: {run_receipt_path}")

    manifest_raw = read_json(manifest_path)
    validate_manifest(manifest_raw)
    run_receipt = read_json(run_receipt_path)
    claim_snapshot_path = run_dir / "claim-snapshot.json"
    claim_snapshot = read_json(claim_snapshot_path) if claim_snapshot_path.exists() else {}

    source_receipts_by_id = {
        receipt["receipt_id"]: receipt for receipt in manifest_raw.get("source_receipts", [])
    }
    source_run_sha256 = _sha256_file(run_receipt_path)
    manifest_sha256 = _sha256_file(manifest_path)
    profile_sha256 = _sha256_file(claim_snapshot_path) if claim_snapshot_path.exists() else manifest_sha256
    selected_at = utc_now()

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for rank, opportunity in enumerate(manifest_raw.get("opportunities", [])[:top_n], start=1):
        receipts = [
            source_receipts_by_id[receipt_id]
            for receipt_id in opportunity.get("source_receipt_ids", [])
            if receipt_id in source_receipts_by_id
        ]
        primary_receipts = [
            receipt
            for receipt in receipts
            if "meetup" not in " ".join(
                str(receipt.get(key) or "").lower()
                for key in ("provider", "source_class", "channel", "required_source_id")
            )
        ]
        if not primary_receipts:
            rejected.append(
                {
                    "opportunity_id": opportunity["opportunity_id"],
                    "reason": "NO_NON_MEETUP_PRIMARY_RECEIPT",
                }
            )
            continue

        relationship_status, relationship_evidence = _relationship_evidence(
            manifest_raw,
            opportunity["opportunity_id"],
        )
        primary_source_classes = sorted(
            {
                str(receipt.get("source_class") or receipt.get("provider") or "unknown")
                for receipt in primary_receipts
            }
        )
        payload = {
            "schema": "monitor_opportunities.tau_semantic_input.v1",
            "run_id": manifest_raw["run_id"],
            "source_run_receipt_ref": f"run-receipt:{run_receipt.get('run_id', manifest_raw['run_id'])}",
            "source_run_sha256": source_run_sha256,
            "opportunity_id": opportunity["opportunity_id"],
            "rank": rank,
            "selected_at": selected_at,
            "immutable_goal": {"text": IMMUTABLE_GOAL, "goal_hash": _goal_hash()},
            "goal_hash": _goal_hash(),
            "candidate_profile_version": str(
                claim_snapshot.get("candidate_profile_id")
                or claim_snapshot.get("schema")
                or "candidate-profile.unknown"
            ),
            "candidate_profile_sha256": profile_sha256,
            "allowed_fact_ledger": _claim_facts(claim_snapshot, opportunity.get("claim_keys", [])),
            "primary_opportunity_evidence_present": True,
            "primary_opportunity_evidence_ids": [receipt["receipt_id"] for receipt in primary_receipts],
            "primary_source_classes": primary_source_classes,
            "retained_artifact_hashes": [manifest_sha256, source_run_sha256],
            "source_receipt_hashes": [_source_receipt_hash(receipt) for receipt in primary_receipts],
            "fetched_at": max(receipt.get("observed_at") or manifest_raw["generated_at"] for receipt in primary_receipts),
            "source_health_state": _source_health(primary_receipts),
            "relationship_status": relationship_status,
            "relationship_evidence": relationship_evidence,
            "meetup_evidence_present": False,
            "meetup_policy": "SUPPLEMENTAL_ONLY",
            "policy": {
                "external_effects": False,
                "allowed_output_types": ["semantic_addendum", "interview_addendum"],
                "timeout_seconds": 600,
                "max_concurrency": 1,
                "max_attempts": 1,
                "max_cost_usd": 2.5,
            },
        }
        validate_tau_semantic_input(payload)
        path = out_dir / "semantic-inputs" / f"{rank:02d}-{_safe_filename(opportunity['opportunity_id'])}.json"
        write_json(path, payload)
        selected.append(
            {
                "rank": rank,
                "opportunity_id": opportunity["opportunity_id"],
                "artifact": str(path),
                "artifact_sha256": _sha256_file(path),
                "relationship_status": relationship_status,
                "source_health_state": payload["source_health_state"],
            }
        )

    receipt = {
        "schema": "monitor_opportunities.tau_semantic_prepare_receipt.v1",
        "status": "PASS" if selected else "FAIL",
        "run_id": manifest_raw["run_id"],
        "source_run_dir": str(run_dir),
        "source_run_sha256": source_run_sha256,
        "report_manifest_sha256": manifest_sha256,
        "selected_at": selected_at,
        "requested_top_n": top_n,
        "selected_count": len(selected),
        "rejected_count": len(rejected),
        "selected": selected,
        "rejected": rejected,
        "mocked": False,
        "live": bool(run_receipt.get("live")),
        "provider_live": False,
        "external_effects": False,
        "non_claims": [
            "This command materializes validated provider input only; it does not call Tau, WebGPT, scillm, LinkedIn, Gmail, ATS, or Meetup.",
            "Relationship evidence is included only when directly bound to the selected opportunity id.",
            "This command does not prove provider semantic quality or reviewer behavior.",
        ],
    }
    write_json(out_dir / "tau-semantic-prepare-receipt.json", receipt)
    return receipt
