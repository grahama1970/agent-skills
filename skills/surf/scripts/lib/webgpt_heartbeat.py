#!/usr/bin/env python3
"""Structured heartbeat/progress for long WebGPT submit runs (#36)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "surf.webgpt_heartbeat.v1"
HEARTBEAT_NAME = "webgpt_heartbeat.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_heartbeat(
    artifact_dir: Path,
    *,
    heartbeat_path: Path | None = None,
    phase: str,
    page_state: str,
    submitted_at: str | None = None,
    last_artifact: str | None = None,
    next_expected_artifact: str | None = None,
    timeout_remaining_s: int | None = None,
    sentinel: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    artifact_dir = artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = heartbeat_path.resolve() if heartbeat_path else artifact_dir / HEARTBEAT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    if sentinel and existing.get("sentinel") not in (None, sentinel):
        existing = {}
        events_path = artifact_dir / "webgpt_heartbeat.events.jsonl"
        events_path.unlink(missing_ok=True)
    payload = dict(existing)
    payload.update({
        "schema": SCHEMA,
        "updated_at": _now(),
        "submitted_at": submitted_at or existing.get("submitted_at"),
        "last_browser_observation_at": _now(),
        "phase": phase,
        "page_state": page_state,
        "last_artifact_written": last_artifact or existing.get("last_artifact_written"),
        "next_expected_artifact": next_expected_artifact,
        "timeout_remaining_seconds": timeout_remaining_s,
        "sentinel": sentinel or existing.get("sentinel"),
        "prepared_prompt_is_transport_proof": False,
    })
    if extra:
        payload.update(extra)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_heartbeat(artifact_dir: Path) -> dict[str, Any]:
    path = artifact_dir.resolve() / HEARTBEAT_NAME
    if not path.exists():
        return {"schema": SCHEMA, "status": "missing", "artifact_dir": str(artifact_dir.resolve())}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": SCHEMA, "status": "invalid", "error": str(exc)}
    data["status"] = "ok"
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WebGPT transport heartbeat")
    sub = parser.add_subparsers(dest="command", required=True)

    write_p = sub.add_parser("write")
    write_p.add_argument("--artifact-dir", required=True)
    write_p.add_argument("--heartbeat-path", default="")
    write_p.add_argument("--phase", required=True)
    write_p.add_argument("--page-state", required=True)
    write_p.add_argument("--submitted-at", default="")
    write_p.add_argument("--last-artifact", default="")
    write_p.add_argument("--next-expected-artifact", default="")
    write_p.add_argument("--timeout-remaining", type=int, default=-1)
    write_p.add_argument("--sentinel", default="")

    read_p = sub.add_parser("read")
    read_p.add_argument("--artifact-dir", required=True)
    read_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "write":
        write_heartbeat(
            Path(args.artifact_dir),
            heartbeat_path=Path(args.heartbeat_path) if args.heartbeat_path else None,
            phase=args.phase,
            page_state=args.page_state,
            submitted_at=args.submitted_at or None,
            last_artifact=args.last_artifact or None,
            next_expected_artifact=args.next_expected_artifact or None,
            timeout_remaining_s=None if args.timeout_remaining < 0 else args.timeout_remaining,
            sentinel=args.sentinel or None,
        )
        return 0
    payload = read_heartbeat(Path(args.artifact_dir))
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
