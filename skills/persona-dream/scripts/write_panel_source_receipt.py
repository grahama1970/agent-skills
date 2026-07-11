#!/usr/bin/env python3
"""Derive a panel_source_receipt from a panel repair gate receipt.

The output is intentionally conservative. It emits PASS_PANEL_SOURCE only when
the repair gate has a final reviewed panel, all panel subgates pass, the image
hash matches, the visual style is photoreal, and no forbidden fallback is used.
Otherwise it writes a BLOCKED receipt naming the unmet conditions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUBGATES = [
    "script_coverage_status",
    "post_generation_script_coverage_status",
    "reference_evidence_status",
    "visual_review_status",
    "no_overlay_status",
    "provider_media_status",
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _first_media_hash(receipt: dict[str, Any]) -> str | None:
    media_hashes = receipt.get("media_hashes")
    if not isinstance(media_hashes, dict):
        return None
    for value in media_hashes.values():
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


def derive_panel_source_receipt(
    panel_repair_gate_receipt: Path,
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    repair_path = panel_repair_gate_receipt.resolve()
    repair = _read_json(repair_path)
    if not isinstance(repair, dict):
        raise ValueError("panel repair gate receipt must be a JSON object")

    image_path_value = repair.get("generated_image_path") or repair.get("provider_media_asset_path")
    image_path = Path(image_path_value).resolve() if isinstance(image_path_value, str) else None
    actual_hash = _sha256(image_path) if image_path and image_path.exists() else None
    claimed_hash = repair.get("provider_media_sha256")
    if not isinstance(claimed_hash, str) or not claimed_hash.startswith("sha256:"):
        claimed_hash = _first_media_hash(repair)

    blockers: list[str] = []
    if repair.get("schema") != "persona_dream.panel_repair_gate_receipt.v1":
        blockers.append("repair_gate_schema_not_persona_dream_panel_repair_gate_receipt_v1")
    if repair.get("status") != "PASS_PANEL_REVIEWED":
        blockers.append(f"repair_gate_status_not_final_reviewed:{repair.get('status')}")
    for subgate in SUBGATES:
        if repair.get(subgate) != "PASS":
            blockers.append(f"{subgate}_not_pass:{repair.get(subgate)}")
    if repair.get("visual_style_status") != "PASS_PHOTOREAL_CINEMATIC":
        blockers.append(f"visual_style_not_photoreal:{repair.get('visual_style_status')}")
    if repair.get("provider_eligibility") is not True:
        blockers.append("provider_eligibility_not_true")
    if repair.get("nano_banana_fallback_used") is True:
        blockers.append("nano_banana_fallback_used")
    if not image_path:
        blockers.append("generated_image_path_missing")
    elif not image_path.exists():
        blockers.append(f"generated_image_path_not_found:{image_path}")
    if not claimed_hash:
        blockers.append("claimed_media_hash_missing")
    elif actual_hash and actual_hash != claimed_hash:
        blockers.append(f"claimed_media_hash_mismatch:{actual_hash}")
    if repair.get("live_call_performed") is True or repair.get("paid_call_performed") is True:
        blockers.append("unexpected_live_or_paid_call_in_panel_source_derivation")

    status = "PASS_PANEL_SOURCE" if not blockers else "BLOCKED"
    receipt = {
        "schema": "persona_dream.panel_source_receipt.v1",
        "run_id": str(repair.get("run_id") or "unknown"),
        "panel_id": str(repair.get("panel_id") or "unknown"),
        "status": status,
        "image_path": str(image_path) if image_path else "missing:generated_image_path",
        "sha256": actual_hash or claimed_hash or "sha256:" + ("0" * 64),
        "producer": {
            "kind": "subagent",
            "name": "persona-dream-panel-repair-gate",
            "receipt": str(repair_path),
        },
        "photoreal_status": repair.get("visual_style_status")
        if repair.get("visual_style_status") == "PASS_PHOTOREAL_CINEMATIC"
        else "UNKNOWN",
        "nano_banana_fallback_used": False,
        "final_panel_eligible": status == "PASS_PANEL_SOURCE",
        "blockers": blockers,
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel_repair_gate_receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = derive_panel_source_receipt(args.panel_repair_gate_receipt, output=args.output)
    except Exception as exc:
        receipt = {
            "schema": "persona_dream.panel_source_derivation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt.get("status") != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
