"""Append-only local decision ledger and replay projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import read_jsonl, sha256_json, stable_id, utc_now, write_json, write_jsonl

ALLOWED_ACTIONS = {
    "KEEP",
    "REJECT",
    "DEFER",
    "ACCEPT_RESUME_VARIANT",
    "PROPOSE_CLAIM_AMENDMENT",
    "WITHHOLD_APPLICATION",
    "AUTHORIZE_APPLICATION_PAYLOAD",
    "MARK_HUMAN_SENT_GMAIL",
    "MARK_HUMAN_SENT_LINKEDIN",
}


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "decision-ledger.jsonl"


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
    run_dir.mkdir(parents=True, exist_ok=True)
    path = _ledger_path(run_dir)
    rows = read_jsonl(path)
    for row in rows:
        if row["idempotency_key"] == idempotency_key:
            return row
    event = {
        "schema": "monitor_opportunities.decision_event.v1",
        "event_id": stable_id("decision", {"run": str(run_dir), "item": item_id, "key": idempotency_key}),
        "run_dir": str(run_dir),
        "item_id": item_id,
        "action": action,
        "actor": actor,
        "created_at": utc_now(),
        "idempotency_key": idempotency_key,
        "reason": reason,
        "external_effects": False,
        "payload_digest": sha256_json({"item_id": item_id, "action": action, "reason": reason}),
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
            "event_id": row["event_id"],
            "actor": row["actor"],
            "updated_at": row["created_at"],
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
