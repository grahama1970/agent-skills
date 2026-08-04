"""Immutable local application packet binding and drift checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import sha256_bytes, sha256_json, stable_id, utc_now, write_json


def _artifact_digest(ref: str) -> dict[str, Any]:
    path = Path(ref)
    exists = path.exists()
    return {
        "path": ref,
        "exists": exists,
        "sha256": sha256_bytes(path.read_bytes()) if exists else None,
    }


def _digest_rows(rows: list[dict[str, Any]]) -> str:
    return sha256_json(rows)


def build_application_packets(
    *,
    run_dir: Path,
    opportunities: list[dict[str, Any]],
    resume_variants: list[dict[str, Any]],
    outreach_packets: list[dict[str, Any]],
    applications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write one packet per application with an available resume variant."""

    packet_dir = run_dir / "application-packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    opportunity_by_id = {row["opportunity_id"]: row for row in opportunities}
    resume_by_opportunity = {row["opportunity_id"]: row for row in resume_variants}
    outreach_by_opportunity: dict[str, list[dict[str, Any]]] = {}
    for packet in outreach_packets:
        outreach_by_opportunity.setdefault(packet["opportunity_id"], []).append(packet)

    packets: list[dict[str, Any]] = []
    for application in applications:
        opportunity_id = application["opportunity_id"]
        opportunity = opportunity_by_id.get(opportunity_id)
        resume = resume_by_opportunity.get(opportunity_id)
        if opportunity is None or resume is None:
            continue
        resume_artifacts = [_artifact_digest(ref) for ref in resume["artifact_refs"]]
        field_answers = application.get("fields", [])
        attachments = resume_artifacts
        outreach = outreach_by_opportunity.get(opportunity_id, [])
        policy_observations = [
            "Stage 0 packet is local and read-only.",
            "Every free-text and sensitive field remains human_required unless exact approved answer exists.",
            "Authorization binds this exact packet digest and is not reusable after drift.",
            "No application submit, Gmail send, or LinkedIn platform action is performed.",
        ]
        packet_basis = {
            "application_id": application["application_id"],
            "opportunity_id": opportunity_id,
            "posting_digest": sha256_json(
                {
                    "title": opportunity["title"],
                    "organization": opportunity["organization"],
                    "source_receipt_ids": opportunity["source_receipt_ids"],
                    "screening_interface_profile": opportunity["screening_interface_profile"],
                }
            ),
            "screening_interface_profile_digest": sha256_json(opportunity["screening_interface_profile"]),
            "resume_variant_id": resume["variant_id"],
            "resume_digest": _digest_rows(resume_artifacts),
            "claim_snapshot_digest": resume["claim_snapshot_sha256"],
            "field_answer_digest": sha256_json(field_answers),
            "attachment_digest": _digest_rows(attachments),
            "outreach_digest": sha256_json(outreach),
            "policy_observations_digest": sha256_json(policy_observations),
        }
        approval_payload = {
            **packet_basis,
            "artifact_paths": [row["path"] for row in resume_artifacts],
            "application_state": application["state"],
            "authorized": application["authorized"],
            "external_effects": False,
        }
        packet = {
            "schema": "monitor_opportunities.application_packet.v1",
            "packet_id": stable_id("application-packet", packet_basis),
            "created_at": utc_now(),
            "application_id": application["application_id"],
            "opportunity_id": opportunity_id,
            "posting_digest": packet_basis["posting_digest"],
            "screening_interface_profile_digest": packet_basis["screening_interface_profile_digest"],
            "resume_variant_id": resume["variant_id"],
            "resume_artifacts": resume_artifacts,
            "resume_digest": packet_basis["resume_digest"],
            "claim_snapshot_digest": packet_basis["claim_snapshot_digest"],
            "field_answer_digest": packet_basis["field_answer_digest"],
            "attachment_digest": packet_basis["attachment_digest"],
            "outreach_digest": packet_basis["outreach_digest"],
            "policy_observations": policy_observations,
            "policy_observations_digest": packet_basis["policy_observations_digest"],
            "approval_payload_digest": sha256_json(approval_payload),
            "approval_status": "NOT_AUTHORIZED",
            "visible_in_report": True,
            "action_worthy": True,
            "external_effects": False,
        }
        packet_path = packet_dir / f"{packet['packet_id'].replace(':', '-')}.json"
        packet["packet_ref"] = str(packet_path)
        write_json(packet_path, packet)
        packets.append(packet)
    return packets


def verify_application_packet(packet: dict[str, Any]) -> dict[str, Any]:
    current_artifacts = [_artifact_digest(row["path"]) for row in packet.get("resume_artifacts", [])]
    current_resume_digest = _digest_rows(current_artifacts)
    errors = []
    if current_resume_digest != packet.get("resume_digest"):
        errors.append("resume_digest drift")
    missing = [row["path"] for row in current_artifacts if not row["exists"]]
    if missing:
        errors.append("resume artifact missing: " + ", ".join(missing))
    return {
        "schema": "monitor_opportunities.application_packet_drift_check.v1",
        "packet_id": packet.get("packet_id"),
        "ok": not errors,
        "errors": errors,
        "expected_resume_digest": packet.get("resume_digest"),
        "current_resume_digest": current_resume_digest,
        "external_effects": False,
    }
