"""Receipt-backed human interjection contract for Battle."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any


INTERJECTION_SCHEMA = "battle.human_interjection.v1"
APPLICATION_SCHEMA = "battle.human_interjection_application.v1"
CONTROL_SCAN_SCHEMA = "battle.human_interjection_control_scan.v1"
SUPPORTED_ACTION = "pause_after_round"
VALID_BOUNDARIES = {"round_running"}


def submit_pause_after_round(
    *,
    out_dir: Path,
    active_run_id: str,
    request_run_id: str,
    request_id: str,
    auth_token: str,
    expected_auth_token: str,
    boundary: str,
    judge_receipt: Path,
) -> dict[str, Any]:
    """Record one pause_after_round request and fail closed on invalid input."""

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = _safe_request_id(request_id)
    receipt_path = out_dir / f"{safe_request_id}.json"
    existing = _read_json(receipt_path)
    judge_before = _sha256(judge_receipt)
    accepted = False
    reason = ""
    status = "REJECTED"

    if existing:
        status = "DUPLICATE_ACCEPTED" if existing.get("status") == "ACCEPTED" else "DUPLICATE_REJECTED"
        reason = "duplicate_request_id"
        accepted = existing.get("status") == "ACCEPTED"
    elif safe_request_id != request_id:
        reason = "invalid_request_id"
    elif not hmac.compare_digest(auth_token, expected_auth_token):
        reason = "invalid_auth"
    elif request_run_id != active_run_id:
        reason = "wrong_run"
    elif boundary not in VALID_BOUNDARIES:
        reason = "invalid_timing"
    else:
        status = "ACCEPTED"
        reason = "pause_after_round_recorded"
        accepted = True

    receipt = {
        "schema": INTERJECTION_SCHEMA,
        "status": status,
        "action": SUPPORTED_ACTION,
        "mocked": False,
        "live": True,
        "request_id": request_id,
        "safe_request_id": safe_request_id,
        "active_run_id": active_run_id,
        "request_run_id": request_run_id,
        "boundary": boundary,
        "accepted": accepted,
        "applies_at": "after_current_round" if accepted else None,
        "reason": reason,
        "auth": {
            "method": "shared_secret_sha256",
            "token_sha256": hashlib.sha256(auth_token.encode()).hexdigest(),
        },
        "immutability": {
            "judge_receipt": str(judge_receipt),
            "judge_receipt_sha256_before": judge_before,
            "judge_receipt_sha256_after": _sha256(judge_receipt),
            "judge_receipt_unchanged": judge_before == _sha256(judge_receipt),
        },
        "created_at": _utc(),
    }
    if not existing:
        _write_json(receipt_path, receipt)
    else:
        duplicate_path = out_dir / f"{safe_request_id}.duplicate.{int(time.time())}.json"
        receipt["original_receipt"] = str(receipt_path)
        _write_json(duplicate_path, receipt)
    return receipt


def apply_after_round(
    *,
    out_dir: Path,
    interjection_receipt: Path,
    round_receipt: Path,
) -> dict[str, Any]:
    """Apply an accepted pause request at the after-round boundary."""

    out_dir.mkdir(parents=True, exist_ok=True)
    interjection = _read_required_json(interjection_receipt)
    round_sha = _sha256(round_receipt)
    request_id = str(interjection.get("request_id") or "missing-request-id")
    safe_request_id = _safe_request_id(request_id)
    application_path = out_dir / f"{safe_request_id}.application.json"
    existing = _read_json(application_path)
    if existing is not None:
        return existing

    status = "APPLIED" if interjection.get("status") == "ACCEPTED" else "REJECTED"
    receipt = {
        "schema": APPLICATION_SCHEMA,
        "status": status,
        "mocked": False,
        "live": True,
        "action": interjection.get("action"),
        "request_id": request_id,
        "safe_request_id": safe_request_id,
        "run_id": interjection.get("active_run_id"),
        "boundary": "after_current_round",
        "pause_next_round": status == "APPLIED",
        "source_interjection_receipt": str(interjection_receipt),
        "source_interjection_receipt_sha256": _sha256(interjection_receipt),
        "round_receipt": str(round_receipt),
        "round_receipt_sha256_before": round_sha,
        "round_receipt_sha256_after": _sha256(round_receipt),
        "round_receipt_unchanged": round_sha == _sha256(round_receipt),
        "created_at": _utc(),
    }
    _write_json(application_path, receipt)
    return receipt


def apply_pending_pause_after_round(
    *,
    control_dir: Path,
    active_run_id: str,
    round_receipt: Path,
) -> dict[str, Any]:
    """Apply the first eligible request in one documented per-run control tree.

    Requests live in ``<control_dir>/requests`` and applications in
    ``<control_dir>/applications``. Existing applications are never rewritten,
    which makes restart scans exactly-once for a request id.
    """

    control_dir = control_dir.resolve()
    request_dir = control_dir / "requests"
    application_dir = control_dir / "applications"
    scan_dir = control_dir / "scans"
    application_dir.mkdir(parents=True, exist_ok=True)
    scan_dir.mkdir(parents=True, exist_ok=True)

    round_payload = _read_required_json(round_receipt)
    round_number = int(round_payload.get("round_number", 0) or 0)
    scanned: list[dict[str, Any]] = []
    selected: Path | None = None

    if request_dir.exists():
        for request_path in sorted(request_dir.glob("*.json")):
            entry: dict[str, Any] = {"path": str(request_path), "eligible": False}
            try:
                request = _read_required_json(request_path)
            except Exception as exc:
                entry["reason"] = "malformed_request"
                entry["error"] = str(exc)
                scanned.append(entry)
                continue

            request_id = str(request.get("request_id") or "")
            safe_request_id = _safe_request_id(request_id)
            entry["request_id"] = request_id
            if request.get("schema") != INTERJECTION_SCHEMA:
                entry["reason"] = "unsupported_schema"
            elif request.get("status") != "ACCEPTED":
                entry["reason"] = "request_not_accepted"
            elif request.get("action") != SUPPORTED_ACTION:
                entry["reason"] = "unsupported_action"
            elif request.get("active_run_id") != active_run_id:
                entry["reason"] = "wrong_run"
            elif not request_id or safe_request_id != request_id:
                entry["reason"] = "invalid_request_id"
            elif (application_dir / f"{safe_request_id}.application.json").exists():
                entry["reason"] = "already_applied"
            else:
                entry["eligible"] = True
                entry["reason"] = "eligible"
                if selected is None:
                    selected = request_path
            scanned.append(entry)

    application: dict[str, Any] | None = None
    status = "NO_REQUEST"
    if selected is not None:
        application = apply_after_round(
            out_dir=application_dir,
            interjection_receipt=selected,
            round_receipt=round_receipt,
        )
        status = "APPLIED" if application.get("status") == "APPLIED" else "BLOCKED"
    elif scanned:
        status = "NO_ELIGIBLE_REQUEST"

    receipt = {
        "schema": CONTROL_SCAN_SCHEMA,
        "status": status,
        "mocked": False,
        "live": True,
        "active_run_id": active_run_id,
        "round_number": round_number,
        "control_dir": str(control_dir),
        "round_receipt": str(round_receipt),
        "round_receipt_sha256": _sha256(round_receipt),
        "selected_request": str(selected) if selected else None,
        "application": application,
        "scanned": scanned,
        "created_at": _utc(),
    }
    scan_path = scan_dir / f"round-{round_number:04d}.json"
    _write_json(scan_path, receipt)
    receipt["scan_receipt"] = str(scan_path)
    return receipt


def _safe_request_id(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if value and len(value) <= 128 and all(char in allowed for char in value):
        return value
    digest = hashlib.sha256(value.encode()).hexdigest()[:16]
    return f"invalid-{digest}"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _read_required_json(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if value is None:
        raise ValueError(f"missing JSON object: {path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
