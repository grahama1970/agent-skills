#!/usr/bin/env python3
"""Write atomic Surf tab recovery receipts.

The receipt is intentionally small and fail-closed: only completed repair
statuses can be encoded as success, and any skipped/unknown guard value forces
``success`` to false.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUSES = frozenset(
    {"scanned", "skipped_guarded", "rebound", "reloaded", "failed"}
)
SUCCESS_STATUSES = frozenset({"rebound", "reloaded"})
UNKNOWN_GUARD_VALUES = frozenset({"unknown", "skipped", "skip", "not_checked", "n/a", "na"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _read_json_arg(value: str | None, *, default: Any) -> Any:
    if value is None:
        return default
    parsed = json.loads(value)
    return parsed


def _guard_is_known_success(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        if value.get("skipped") is True:
            return False
        if str(value.get("status", "")).lower() in UNKNOWN_GUARD_VALUES:
            return False
        if str(value.get("value", "")).lower() in UNKNOWN_GUARD_VALUES:
            return False
        if "passed" in value:
            return value.get("passed") is True
        if "ok" in value:
            return value.get("ok") is True
        if "allowed" in value:
            return value.get("allowed") is True
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"true", "passed", "pass", "ok", "allowed"}
    return False


def _guards_allow_success(guard_values: dict[str, Any]) -> bool:
    if not guard_values:
        return False
    return all(_guard_is_known_success(value) for value in guard_values.values())


def build_tab_recovery_receipt(
    *,
    status: str,
    project: str,
    requested_tab_id: str | int | None,
    resolved_tab_id: str | int | None,
    url_evidence: dict[str, Any] | list[Any] | str | None,
    guard_values: dict[str, Any] | None,
    repair_trigger: str | None,
    action_started_at: str | None = None,
    action_finished_at: str | None = None,
    before_observation: dict[str, Any] | str | None = None,
    after_observation: dict[str, Any] | str | None = None,
    written_at: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed Surf tab recovery receipt payload."""

    if status not in VALID_STATUSES:
        raise ValueError(f"invalid tab recovery status: {status!r}")

    guards = dict(guard_values or {})
    guard_success = _guards_allow_success(guards)
    success = status in SUCCESS_STATUSES and guard_success
    if status == "skipped_guarded":
        success = False

    now = written_at or _utc_now()
    return {
        "schema": "surf.tab_recovery_receipt.v1",
        "status": status,
        "success": success,
        "project": project,
        "requested_tab_id": requested_tab_id,
        "resolved_tab_id": resolved_tab_id,
        "url_evidence": url_evidence,
        "guard_values": guards,
        "guard_success": guard_success,
        "repair_trigger": repair_trigger,
        "action_started_at": action_started_at or now,
        "action_finished_at": action_finished_at or now,
        "written_at": now,
        "before_observation": before_observation,
        "after_observation": after_observation,
    }


def write_tab_recovery_receipt(path: Path, **kwargs: Any) -> Path:
    payload = build_tab_recovery_receipt(**kwargs)
    _write_json_atomic(path, payload)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--requested-tab-id", default=None)
    parser.add_argument("--resolved-tab-id", default=None)
    parser.add_argument("--url-evidence", default=None, help="JSON value or string URL")
    parser.add_argument("--guard-values", default="{}", help="JSON object of every guard value")
    parser.add_argument("--repair-trigger", default=None)
    parser.add_argument("--action-started-at", default=None)
    parser.add_argument("--action-finished-at", default=None)
    parser.add_argument("--before-observation", default=None, help="JSON value or text")
    parser.add_argument("--after-observation", default=None, help="JSON value or text")
    args = parser.parse_args()

    def json_or_text(value: str | None) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    guard_values = _read_json_arg(args.guard_values, default={})
    if not isinstance(guard_values, dict):
        raise SystemExit("--guard-values must be a JSON object")

    write_tab_recovery_receipt(
        args.output,
        status=args.status,
        project=args.project,
        requested_tab_id=args.requested_tab_id,
        resolved_tab_id=args.resolved_tab_id,
        url_evidence=json_or_text(args.url_evidence),
        guard_values=guard_values,
        repair_trigger=args.repair_trigger,
        action_started_at=args.action_started_at,
        action_finished_at=args.action_finished_at,
        before_observation=json_or_text(args.before_observation),
        after_observation=json_or_text(args.after_observation),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
