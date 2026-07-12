#!/usr/bin/env python3
"""Emit a fail-closed Surf Doctor work order from terminal WebGPT metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _artifact(path: Path, kind: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "kind": kind,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def emit_incident(
    *,
    meta_path: Path,
    receipt_path: Path,
    submitted_path: Path,
    raw_path: Path,
    clean_path: Path,
    heartbeat_path: Path,
) -> Path | None:
    meta = _read_json(meta_path)
    if not meta or meta.get("proof_status") == "response_proven":
        return None

    receipt = _read_json(receipt_path)
    output_path = meta_path.with_suffix(".surf-doctor-request.json")
    candidates = [
        (meta_path, "response_meta"),
        (receipt_path, "submit_receipt"),
        (submitted_path, "submitted_prompt"),
        (raw_path, "raw_response"),
        (clean_path, "clean_response"),
        (heartbeat_path, "heartbeat"),
        (Path(str(meta.get("stderr_log") or "")), "stderr"),
    ]
    artifacts = [artifact for path, kind in candidates if (artifact := _artifact(path, kind))]
    incident = {
        "schema": "surf_doctor.incident_request.v1",
        "status": "PENDING_DIAGNOSIS",
        "agent_id": "surf-doctor",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "failure_class": meta.get("failure") or meta.get("status") or "unknown_failure",
        "proof_status": meta.get("proof_status"),
        "requested_tab_id": meta.get("requested_tab_id"),
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "requested_url": meta.get("requested_url"),
        "conversation_url": meta.get("conversation_url"),
        "sentinel": meta.get("sentinel") or receipt.get("sentinel"),
        "submitted_to_chatgpt": meta.get("submitted_to_chatgpt")
        if "submitted_to_chatgpt" in meta
        else receipt.get("submitted_to_chatgpt"),
        "active_submission_state": "terminal_finalization",
        "browser_mutation_authorized": False,
        "allowed_actions": [
            "preserve_incident",
            "classify_failure",
            "read_only_reproduction",
            "prepare_repair_packet",
        ],
        "forbidden_actions": [
            "webgpt_resubmit",
            "tab_activate",
            "tab_close",
            "tab_navigate",
            "page_refresh",
            "extension_reload",
        ],
        "source_artifacts": artifacts,
        "dag_spec": {
            "schema": "subagent_dag.v1",
            "mode": "bounded_dag",
            "nodes": [
                "preserve_incident",
                "classify_failure",
                "reproduce_or_bound",
                "prepare_repair",
            ],
            "max_attempts": 3,
            "stop_conditions": [
                "diagnosis_and_repair_packet_written",
                "same_failure_repeated_twice",
                "architectural_change_required",
                "browser_mutation_required",
            ],
        },
    }
    _write_json_atomic(output_path, incident)
    meta["surf_doctor_request_path"] = str(output_path.resolve())
    _write_json_atomic(meta_path, meta)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--submitted", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--heartbeat", type=Path, required=True)
    args = parser.parse_args()
    emit_incident(
        meta_path=args.meta,
        receipt_path=args.receipt,
        submitted_path=args.submitted,
        raw_path=args.raw,
        clean_path=args.clean,
        heartbeat_path=args.heartbeat,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
