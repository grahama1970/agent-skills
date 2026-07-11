#!/usr/bin/env python3
"""Validate a Persona Dream storyboard panel receipt.

This gate proves the storyboard panel contract exists and points to concrete
local artifacts. It does not perform visual review and does not generate images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/storyboard_panel_receipt.schema.json"


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _block(result: dict[str, Any], phase: str, reason: str, path: Path) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


def validate_storyboard_panel_receipt(receipt_path: Path, *, run_root: Path | None = None) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    base = run_root.resolve() if run_root else receipt_path.parent.parent
    schema = _read_json(SCHEMA)
    receipt = _read_json(receipt_path)
    jsonschema.Draft202012Validator(schema).validate(receipt)

    result: dict[str, Any] = {
        "schema": "persona_dream.storyboard_panel_validation.v1",
        "receipt": str(receipt_path),
        "run_root": str(base),
        "status": "PASS_STORYBOARD_PANEL",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in base.parts else "no",
        "live": "no",
        "exercised": "local storyboard panel schema, image existence/hash, timing bounds, continuity ledger path, work order path",
        "unverified": "live panel generation, visual review semantics, panel source eligibility, provider/Kling execution",
    }

    if receipt.get("status") != "PANEL_READY_FOR_SOURCE_REVIEW":
        return _block(
            result,
            "storyboard_panel",
            f"storyboard_panel_not_ready:{receipt.get('status')}",
            receipt_path,
        )

    timing = receipt["timing"]
    if timing["end_s"] <= timing["start_s"]:
        return _block(result, "storyboard_panel", "timing_end_not_after_start", receipt_path)

    image_path = _resolve_path(base, receipt["image"]["path"])
    if not image_path.exists():
        return _block(result, "storyboard_panel_image", "missing_image_path", image_path)
    actual_hash = _sha256(image_path)
    if actual_hash != receipt["image"]["sha256"]:
        return _block(result, "storyboard_panel_image", f"sha256_mismatch:{actual_hash}", image_path)

    for field in ("continuity_ledger", "work_order"):
        artifact_path = _resolve_path(base, receipt[field])
        if not artifact_path.exists():
            return _block(result, field, "missing_artifact", artifact_path)
        loaded = _read_json(artifact_path)
        if not isinstance(loaded, (dict, list)):
            return _block(result, field, "artifact_json_not_object_or_list", artifact_path)

    result["image_path"] = str(image_path)
    result["sha256"] = actual_hash
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_storyboard_panel_receipt(args.receipt, run_root=args.run_root)
    except Exception as exc:
        result = {
            "schema": "persona_dream.storyboard_panel_validation.v1",
            "receipt": str(args.receipt),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc), "path": str(args.receipt)},
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
