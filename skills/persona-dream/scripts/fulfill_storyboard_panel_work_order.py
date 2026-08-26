#!/usr/bin/env python3
"""Fulfill a validated storyboard-panel work order from run-root artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_storyboard_panel_receipt import validate_storyboard_panel_receipt
from validate_storyboard_panel_work_order import validate_storyboard_panel_work_order


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def rel_or_abs(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", header[16:24])
    return (1, 1)


def path_from_work_order(work_order: dict[str, Any], key: str) -> Path:
    raw = (work_order.get("source_paths") or {}).get(key)
    if not isinstance(raw, str) or raw.startswith("missing:"):
        raise ValueError(f"missing source path: {key}")
    return Path(raw).expanduser().resolve()


def source_ref(path: Path, *, base: Path) -> dict[str, Any]:
    return {
        "path": rel_or_abs(path, base),
        "absolute_path": str(path.resolve()),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def panel_image_path(run_root: Path, dream_packet: dict[str, Any]) -> Path:
    raw = dream_packet.get("contact_sheet") or "contact_sheet.png"
    path = Path(str(raw))
    if not path.is_absolute():
        path = run_root / path
    return path.resolve()


def fulfill(
    work_order_path: Path,
    *,
    run_root: Path | None,
    output: Path | None,
    created_at: str | None,
) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    work_order = read_json(work_order_path)
    root = (run_root or path_from_work_order(work_order, "run_root")).resolve()
    created = created_at or datetime.now(timezone.utc).isoformat()
    mocked = "yes" if "fixtures" in root.parts else "no"
    receipt_path = (output or (root / "receipts/storyboard_panel_fulfillment.json")).resolve()

    validation = validate_storyboard_panel_work_order(work_order_path)
    if validation.get("status") != "PASS_STORYBOARD_PANEL_WORK_ORDER":
        receipt = {
            "schema": "persona_dream.storyboard_panel_fulfillment.v1",
            "status": "BLOCKED_STORYBOARD_PANEL_WORK_ORDER_INVALID",
            "created_at": created,
            "run_root": str(root),
            "input_work_order": str(work_order_path),
            "work_order_validation": validation,
            "mocked": mocked,
            "live": "no",
            "paid_provider_call_attempted": False,
            "kling_call_attempted": False,
        }
        write_json(receipt_path, receipt)
        return receipt

    dream_packet_path = path_from_work_order(work_order, "dream_packet")
    story_contract_path = path_from_work_order(work_order, "story_contract")
    dream_packet = read_json(dream_packet_path)
    story_contract = read_json(story_contract_path)
    image_path = panel_image_path(root, dream_packet)
    if not image_path.exists():
        receipt = {
            "schema": "persona_dream.storyboard_panel_fulfillment.v1",
            "status": "BLOCKED_PANEL_IMAGE_MISSING",
            "created_at": created,
            "run_root": str(root),
            "input_work_order": str(work_order_path),
            "panel_image": str(image_path),
            "mocked": mocked,
            "live": "no",
            "paid_provider_call_attempted": False,
            "kling_call_attempted": False,
        }
        write_json(receipt_path, receipt)
        return receipt

    artifacts_dir = root / "artifacts"
    receipts_dir = root / "receipts"
    panel_work_order_path = artifacts_dir / "panel_001_work_order.json"
    continuity_path = artifacts_dir / "panel_continuity_and_repair_ledger.json"
    panel_receipt_path = receipts_dir / "storyboard_panel_receipt.json"
    width, height = png_dimensions(image_path)
    duration = min(2.5, float(story_contract.get("target_duration_s") or 10.0))

    panel_work_order = {
        "schema": "persona_dream.storyboard_panel_generation_work_order.v1",
        "status": "PANEL_WORK_ORDER_READY",
        "created_at": created,
        "panel_id": "panel_001",
        "source_story_contract": source_ref(story_contract_path, base=root),
        "source_dream_packet": source_ref(dream_packet_path, base=root),
        "source_storyboard_panel_work_order": source_ref(work_order_path, base=root),
        "timing": {"start_s": 0.0, "end_s": duration},
        "beat": str(story_contract.get("story") or "")[:600],
        "required_visible_entities": [str(value) for value in (story_contract.get("speaking_characters") or ["Embry", "Horus"])],
        "required_props": ["dream residue", "journal tension"],
        "required_environment": ["synthetic dream space"],
        "required_dynamic_behaviors": ["mood shifts without changing answer content"],
        "forbidden_actions": work_order.get("forbidden_actions"),
    }
    write_json(panel_work_order_path, panel_work_order)

    continuity_ledger = {
        "schema": "persona_dream.panel_continuity_ledger.v1",
        "status": "PASS_CONTINUITY_LINKED",
        "created_at": created,
        "panel_id": "panel_001",
        "checks": [
            {"name": "story_contract_present", "status": "PASS", "artifact": rel_or_abs(story_contract_path, root)},
            {"name": "dream_packet_present", "status": "PASS", "artifact": rel_or_abs(dream_packet_path, root)},
            {"name": "source_image_hash_bound", "status": "PASS", "artifact": rel_or_abs(image_path, root)},
            {"name": "provider_readiness_not_claimed", "status": "PASS"},
        ],
        "unverified": "visual semantics, identity continuity, provider eligibility, live Kling generation",
    }
    write_json(continuity_path, continuity_ledger)

    panel_receipt = {
        "schema": "persona_dream.storyboard_panel_receipt.v1",
        "run_id": root.name,
        "panel_id": "panel_001",
        "status": "PANEL_READY_FOR_SOURCE_REVIEW",
        "timing": panel_work_order["timing"],
        "beat": panel_work_order["beat"],
        "image": {
            "path": rel_or_abs(image_path, root),
            "sha256": sha256_file(image_path),
            "width": int(width),
            "height": int(height),
        },
        "required_visible_entities": panel_work_order["required_visible_entities"],
        "required_props": panel_work_order["required_props"],
        "required_environment": panel_work_order["required_environment"],
        "required_dynamic_behaviors": panel_work_order["required_dynamic_behaviors"],
        "continuity_ledger": rel_or_abs(continuity_path, root),
        "work_order": rel_or_abs(panel_work_order_path, root),
    }
    write_json(panel_receipt_path, panel_receipt)
    panel_validation = validate_storyboard_panel_receipt(panel_receipt_path, run_root=root)

    status = "PASS_STORYBOARD_PANEL_FULFILLED" if panel_validation.get("status") == "PASS_STORYBOARD_PANEL" else "BLOCKED_STORYBOARD_PANEL_VALIDATION"
    receipt = {
        "schema": "persona_dream.storyboard_panel_fulfillment.v1",
        "status": status,
        "created_at": created,
        "run_root": str(root),
        "owner_subagent": "dreamer",
        "input_work_order": str(work_order_path),
        "work_order_validation": validation,
        "storyboard_panel_receipt": str(panel_receipt_path),
        "storyboard_panel_validation": panel_validation,
        "continuity_ledger": str(continuity_path),
        "panel_work_order": str(panel_work_order_path),
        "panel_image": str(image_path),
        "panel_image_sha256": sha256_file(image_path),
        "paid_provider_call_attempted": False,
        "kling_call_attempted": False,
        "nano_banana_or_gemini_final_image_used": False,
        "storyboard_packet_written": False,
        "mocked": mocked,
        "live": "no",
        "exercised": "validated storyboard-panel work-order consumption, continuity ledger emission, panel receipt validation",
        "unverified": "visual review semantics, panel source eligibility, provider media publication, live Kling generation",
    }
    write_json(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    receipt = fulfill(args.work_order, run_root=args.run_root, output=args.output, created_at=args.created_at)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if str(receipt.get("status", "")).startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
