#!/usr/bin/env python3
"""Validate a Persona Dream multi-scene live smoke receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def validate_image_record(record: dict[str, Any], *, run_root: Path, blockers: list[dict[str, Any]], label: str) -> None:
    image_path = Path(str(record.get("image_path") or ""))
    receipt_path = Path(str(record.get("receipt_path") or ""))
    if not image_path.is_absolute():
        image_path = run_root / image_path
    if not receipt_path.is_absolute():
        receipt_path = run_root / receipt_path
    if not image_path.is_file():
        blockers.append({"label": label, "reason": "missing_image", "path": str(image_path)})
        return
    if not receipt_path.is_file():
        blockers.append({"label": label, "reason": "missing_receipt", "path": str(receipt_path)})
        return
    width, height = png_dimensions(image_path)
    if not width or not height:
        blockers.append({"label": label, "reason": "image_not_png", "path": str(image_path)})
    actual_sha = sha256_hex(image_path)
    receipt = load_json(receipt_path)
    if receipt.get("ok") is not True:
        blockers.append({"label": label, "reason": "receipt_not_ok", "path": str(receipt_path)})
    if str(receipt.get("sha256") or "") != actual_sha:
        blockers.append(
            {
                "label": label,
                "reason": "receipt_sha_mismatch",
                "path": str(receipt_path),
                "receipt_sha256": receipt.get("sha256"),
                "actual_sha256": actual_sha,
            }
        )
    if record.get("ok") is not True:
        blockers.append({"label": label, "reason": "record_not_ok"})
    if record.get("sha256") != actual_sha:
        blockers.append({"label": label, "reason": "aggregate_sha_mismatch", "actual_sha256": actual_sha})


def validate(receipt_path: Path) -> dict[str, Any]:
    receipt = load_json(receipt_path)
    run_root = Path(str(receipt.get("run_root") or receipt_path.parents[1]))
    blockers: list[dict[str, Any]] = []
    scenes = receipt.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        blockers.append({"reason": "no_scenes"})
        scenes = []
    scene_ids = [str(scene.get("scene_id") or "") for scene in scenes if isinstance(scene, dict)]
    if len(scene_ids) != len(set(scene_ids)):
        blockers.append({"reason": "duplicate_scene_ids", "scene_ids": scene_ids})
    if receipt.get("mocked") is not False or receipt.get("live") is not True:
        blockers.append({"reason": "receipt_not_live_unmocked"})
    if receipt.get("kling_called") is not False or receipt.get("paid_call_authorized") is not False:
        blockers.append({"reason": "kling_boundary_violated"})
    if receipt.get("forbidden_singleton_receipts"):
        blockers.append({"reason": "forbidden_singleton_receipts", "paths": receipt.get("forbidden_singleton_receipts")})

    for scene in scenes:
        if not isinstance(scene, dict):
            blockers.append({"reason": "scene_not_object"})
            continue
        scene_id = str(scene.get("scene_id") or "")
        scene_manifest = run_root / "scenes" / scene_id / "receipts" / "scene_manifest.json"
        if not scene_manifest.is_file():
            blockers.append({"scene_id": scene_id, "reason": "missing_scene_manifest", "path": str(scene_manifest)})
        elif load_json(scene_manifest).get("ok") is not True:
            blockers.append({"scene_id": scene_id, "reason": "scene_manifest_not_ok", "path": str(scene_manifest)})
        validate_image_record(scene.get("contact_sheet") or {}, run_root=run_root, blockers=blockers, label=f"{scene_id}:contact_sheet")
        validate_image_record(scene.get("panel") or {}, run_root=run_root, blockers=blockers, label=f"{scene_id}:panel")

    status = "PASS" if not blockers else "FAIL"
    return {
        "schema": "persona_dream.multiscene_live_smoke_validation.v1",
        "status": status,
        "reason": "ok" if status == "PASS" else "validation_blockers_present",
        "receipt": str(receipt_path),
        "run_root": str(run_root),
        "mocked": False,
        "live": True,
        "scene_count": len(scenes),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()
    result = validate(args.receipt)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True) if args.json_out else result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
