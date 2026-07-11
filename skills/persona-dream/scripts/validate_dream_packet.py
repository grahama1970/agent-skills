#!/usr/bin/env python3
"""Validate a Persona Dream packet.

This gate proves the beginning-of-pipeline dream packet exists and has the
minimum local artifacts needed to feed story planning. It does not prove live
memory recall, creative quality, or downstream storyboard/provider readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base / path


def _block(result: dict[str, Any], phase: str, reason: str, path: Path) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


def validate_dream_packet(packet_path: Path, *, run_root: Path | None = None) -> dict[str, Any]:
    packet_path = packet_path.resolve()
    base = run_root.resolve() if run_root else packet_path.parent
    packet = _read_json(packet_path)

    result: dict[str, Any] = {
        "schema": "persona_dream.dream_packet_validation.v1",
        "packet": str(packet_path),
        "run_root": str(base),
        "status": "PASS_DREAM_PACKET",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in base.parts else "no",
        "live": "no",
        "exercised": "local dream packet shape, residue list, prompt list, contact sheet path and PNG signature",
        "unverified": "live memory recall, residue semantic grounding, story acceptance, panel generation, provider/Kling execution",
    }

    if not isinstance(packet, dict):
        return _block(result, "dream_packet", "packet_json_not_object", packet_path)
    if packet.get("schema") != "persona_dream.packet.v1":
        return _block(result, "dream_packet", f"wrong_schema:{packet.get('schema')}", packet_path)
    if not str(packet.get("run_id", "")).strip():
        return _block(result, "dream_packet", "missing_run_id", packet_path)
    if packet.get("mode") not in {"static_dream", "video_plan"}:
        return _block(result, "dream_packet", f"invalid_mode:{packet.get('mode')}", packet_path)

    persona = packet.get("persona")
    if not isinstance(persona, dict) or not str(persona.get("id", "")).strip():
        return _block(result, "dream_packet", "missing_persona_id", packet_path)

    residue_items = packet.get("residue_items")
    if not isinstance(residue_items, list) or not residue_items:
        return _block(result, "dream_packet", "missing_residue_items", packet_path)
    for item in residue_items:
        if not isinstance(item, dict) or not str(item.get("source_id", "")).strip():
            return _block(result, "dream_packet", "invalid_residue_item_source_id", packet_path)

    if not str(packet.get("dream_prompt", "")).strip():
        return _block(result, "dream_packet", "missing_dream_prompt", packet_path)

    frame_prompts = packet.get("frame_prompts")
    if not isinstance(frame_prompts, list) or not frame_prompts:
        return _block(result, "dream_packet", "missing_frame_prompts", packet_path)
    for frame in frame_prompts:
        if not isinstance(frame, dict) or not str(frame.get("frame_id", "")).strip() or not str(frame.get("prompt", "")).strip():
            return _block(result, "dream_packet", "invalid_frame_prompt", packet_path)

    contact_sheet_value = packet.get("contact_sheet")
    if not isinstance(contact_sheet_value, str) or not contact_sheet_value.strip():
        return _block(result, "dream_packet", "missing_contact_sheet", packet_path)
    contact_sheet = _resolve_path(base, contact_sheet_value)
    if not contact_sheet.exists():
        return _block(result, "dream_packet_contact_sheet", "missing_contact_sheet_file", contact_sheet)
    with contact_sheet.open("rb") as handle:
        signature = handle.read(8)
    if signature != b"\x89PNG\r\n\x1a\n":
        return _block(result, "dream_packet_contact_sheet", "contact_sheet_not_png", contact_sheet)

    if not str(packet.get("reflection", "")).strip():
        return _block(result, "dream_packet", "missing_reflection", packet_path)

    result["run_id"] = packet["run_id"]
    result["persona_id"] = persona["id"]
    result["frame_prompt_count"] = len(frame_prompts)
    result["contact_sheet"] = str(contact_sheet)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_dream_packet(args.packet, run_root=args.run_root)
    except Exception as exc:
        result = {
            "schema": "persona_dream.dream_packet_validation.v1",
            "packet": str(args.packet),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc), "path": str(args.packet)},
            "mocked": "unknown",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
