"""Append-only local decision ledger and replay projection."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import time
from typing import Any

from .application_packets import verify_application_packet
from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json, write_jsonl

ALLOWED_ACTIONS = {
    "KEEP",
    "REJECT",
    "DEFER",
    "ATTEND_MEETUP",
    "WATCH_MEETUP",
    "SKIP_MEETUP",
    "RECONNECT_CONTACT",
    "DEFER_CONTACT",
    "ACCEPT_RESUME_VARIANT",
    "PROPOSE_CLAIM_AMENDMENT",
    "WITHHOLD_APPLICATION",
    "AUTHORIZE_APPLICATION_PAYLOAD",
    "MARK_HUMAN_SENT_GMAIL",
    "MARK_HUMAN_SENT_LINKEDIN",
}


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "decision-ledger.jsonl"


@contextmanager
def _ledger_lock(run_dir: Path):
    lock_path = run_dir / "decision-ledger.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _decision_append_delay_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("MONITOR_OPPORTUNITIES_DECISION_APPEND_DELAY_SECONDS", "0") or "0"))
    except ValueError:
        return 0.0


def _manifest(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "report-manifest.json"
    if not path.exists():
        return None
    return read_json(path)


def _manifest_item(manifest: dict[str, Any] | None, item_id: str) -> dict[str, Any] | None:
    if manifest is None:
        return None
    id_fields = {
        "opportunities": "opportunity_id",
        "resume_variants": "variant_id",
        "outreach_packets": "packet_id",
        "applications": "application_id",
        "application_packets": "packet_id",
        "relationship_signals": "signal_id",
    }
    for collection, id_field in id_fields.items():
        for row in manifest.get(collection, []):
            if row.get(id_field) == item_id:
                return row
    return None


def _application_payload(manifest: dict[str, Any] | None, item_id: str) -> dict[str, Any] | None:
    if manifest is None:
        return None
    application = next(
        (row for row in manifest.get("applications", []) if row.get("application_id") == item_id),
        None,
    )
    if application is None:
        return None
    opportunity_id = application["opportunity_id"]
    opportunity = next(
        (row for row in manifest.get("opportunities", []) if row.get("opportunity_id") == opportunity_id),
        None,
    )
    resume = next(
        (row for row in manifest.get("resume_variants", []) if row.get("opportunity_id") == opportunity_id),
        None,
    )
    packet = next(
        (row for row in manifest.get("application_packets", []) if row.get("application_id") == item_id),
        None,
    )
    fields = application.get("fields", [])
    unresolved = [
        field["name"]
        for field in fields
        if field.get("required") is True and field.get("disposition") == "human_required"
    ]
    payload = {
        "schema": "monitor_opportunities.application_payload.v1",
        "application_id": item_id,
        "opportunity_id": opportunity_id,
        "posting": {
            "title": opportunity.get("title") if opportunity else None,
            "organization": opportunity.get("organization") if opportunity else None,
        },
        "resume_variant_id": resume.get("variant_id") if resume else None,
        "resume_artifact_refs": resume.get("artifact_refs", []) if resume else [],
        "application_packet_id": packet.get("packet_id") if packet else None,
        "application_packet_ref": packet.get("packet_ref") if packet else None,
        "application_packet_digest": sha256_json(packet) if packet else None,
        "approval_payload_digest": packet.get("approval_payload_digest") if packet else None,
        "attachment_set": resume.get("artifact_refs", []) if resume else [],
        "answer_set_digest": sha256_json(fields),
        "form_schema_digest": application.get("form_schema_digest"),
        "unresolved_required_fields": unresolved,
        "stage": manifest.get("stage"),
        "does_not_execute_submit": True,
    }
    return {**payload, "payload_digest": sha256_json(payload)}


def _artifact_hashes(manifest: dict[str, Any] | None, item_id: str, action: str) -> dict[str, Any]:
    item = _manifest_item(manifest, item_id)
    hashes: dict[str, Any] = {"item_digest": sha256_json(item) if item is not None else None}
    if action == "AUTHORIZE_APPLICATION_PAYLOAD":
        payload = _application_payload(manifest, item_id)
        hashes["application_payload_digest"] = payload["payload_digest"] if payload else None
        hashes["form_schema_digest"] = payload.get("form_schema_digest") if payload else None
        hashes["resume_variant_id"] = payload.get("resume_variant_id") if payload else None
        hashes["application_packet_digest"] = payload.get("application_packet_digest") if payload else None
        hashes["approval_payload_digest"] = payload.get("approval_payload_digest") if payload else None
    return hashes


def _resulting_state(action: str) -> str:
    return {
        "KEEP": "KEPT",
        "REJECT": "REJECTED",
        "DEFER": "DEFERRED",
        "ATTEND_MEETUP": "MEETUP_ATTEND_SELECTED_LOCAL_ONLY",
        "WATCH_MEETUP": "MEETUP_WATCH_SELECTED_LOCAL_ONLY",
        "SKIP_MEETUP": "MEETUP_SKIPPED_LOCAL_ONLY",
        "RECONNECT_CONTACT": "CONTACT_RECONNECT_SELECTED_LOCAL_ONLY",
        "DEFER_CONTACT": "CONTACT_DEFERRED_LOCAL_ONLY",
        "ACCEPT_RESUME_VARIANT": "RESUME_VARIANT_ACCEPTED",
        "PROPOSE_CLAIM_AMENDMENT": "CLAIM_AMENDMENT_PENDING",
        "WITHHOLD_APPLICATION": "APPLICATION_WITHHELD",
        "AUTHORIZE_APPLICATION_PAYLOAD": "APPLICATION_PAYLOAD_AUTHORIZED_LOCAL_ONLY",
        "MARK_HUMAN_SENT_GMAIL": "HUMAN_SENT_GMAIL_ATTESTED",
        "MARK_HUMAN_SENT_LINKEDIN": "HUMAN_SENT_LINKEDIN_ATTESTED",
    }[action]


def _append_claim_amendment(run_dir: Path, manifest: dict[str, Any] | None, item_id: str, reason: str | None) -> dict[str, Any]:
    item = _manifest_item(manifest, item_id)
    claim_keys = item.get("claim_keys", []) if item else []
    proposal = {
        "schema": "monitor_opportunities.claim_amendment.v1",
        "proposal_id": stable_id("claim-amendment", {"run": str(run_dir), "item": item_id, "reason": reason}),
        "claim_keys": claim_keys,
        "status": "AMENDMENT_PROPOSED",
        "human_review_required": True,
        "evidence_refs": [item_id],
        "reason": reason,
        "canonical_mutation": False,
    }
    rows = read_jsonl(run_dir / "claim-amendments.jsonl")
    if not any(row.get("proposal_id") == proposal["proposal_id"] for row in rows):
        rows.append(proposal)
        write_jsonl(run_dir / "claim-amendments.jsonl", rows)
    return proposal


def append_decision(
    *,
    run_dir: Path,
    item_id: str,
    action: str,
    actor: str,
    idempotency_key: str,
    reason: str | None,
) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"unsupported decision action: {action}")
    if action in {"MARK_HUMAN_SENT_GMAIL", "MARK_HUMAN_SENT_LINKEDIN"} and actor != "human":
        raise ValueError(f"{action} requires explicit human actor")
    run_dir.mkdir(parents=True, exist_ok=True)
    with _ledger_lock(run_dir):
        path = _ledger_path(run_dir)
        rows = read_jsonl(path)
        delay = _decision_append_delay_seconds()
        if delay > 0:
            time.sleep(delay)
        for row in rows:
            if row["idempotency_key"] == idempotency_key:
                return row
        manifest = _manifest(run_dir)
        if action == "AUTHORIZE_APPLICATION_PAYLOAD":
            packet = next(
                (row for row in (manifest or {}).get("application_packets", []) if row.get("application_id") == item_id),
                None,
            )
            if packet is None:
                raise ValueError("APPLICATION_PACKET_MISSING")
            drift = verify_application_packet(packet)
            if not drift["ok"]:
                raise ValueError("APPLICATION_PACKET_DRIFT: " + "; ".join(drift["errors"]))
        application_payload = _application_payload(manifest, item_id) if action == "AUTHORIZE_APPLICATION_PAYLOAD" else None
        amendment = _append_claim_amendment(run_dir, manifest, item_id, reason) if action == "PROPOSE_CLAIM_AMENDMENT" else None
        artifact_hashes = _artifact_hashes(manifest, item_id, action)
        event = {
            "schema": "monitor_opportunities.decision_event.v1",
            "event_id": stable_id("decision", {"run": str(run_dir), "item": item_id, "key": idempotency_key}),
            "run_id": manifest.get("run_id") if manifest else str(run_dir),
            "run_dir": str(run_dir),
            "item_id": item_id,
            "action": action,
            "actor": actor,
            "created_at": utc_now(),
            "prior_report_digest": sha256_json(manifest) if manifest else None,
            "artifact_hashes": artifact_hashes,
            "idempotency_key": idempotency_key,
            "reason": reason,
            "notes": reason,
            "resulting_state": _resulting_state(action),
            "external_effects": False,
            "application_payload": application_payload,
            "claim_amendment": amendment,
            "payload_digest": sha256_json(
                {
                    "run_id": manifest.get("run_id") if manifest else str(run_dir),
                    "item_id": item_id,
                    "action": action,
                    "reason": reason,
                    "artifact_hashes": artifact_hashes,
                    "application_payload": application_payload,
                    "claim_amendment": amendment,
                }
            ),
        }
        rows.append(event)
        write_jsonl(path, rows)
        return event


def replay(run_dir: Path) -> dict[str, Any]:
    rows = read_jsonl(_ledger_path(run_dir))
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        state[row["item_id"]] = {
            "last_action": row["action"],
            "resulting_state": row.get("resulting_state", _resulting_state(row["action"])),
            "event_id": row["event_id"],
            "actor": row["actor"],
            "updated_at": row["created_at"],
            "payload_digest": row["payload_digest"],
        }
    projection = {
        "schema": "monitor_opportunities.decision_projection.v1",
        "run_dir": str(run_dir),
        "event_count": len(rows),
        "external_effects": False,
        "items": state,
        "projection_digest": sha256_json(state),
    }
    write_json(run_dir / "decision-projection.json", projection)
    return projection
