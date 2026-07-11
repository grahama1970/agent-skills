#!/usr/bin/env python3
"""Validate a Persona Dream visual review receipt.

This is a deterministic local gate for receipt evidence. It does not perform a
new vision review. PASS means the receipt carries the panel-reviewer fields
needed to prove the review happened and covered all required check categories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_CHECKS = [
    "characters",
    "props",
    "environment",
    "creatures",
    "effects",
    "script_dialogue",
    "scale",
    "motion_cues",
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _block(result: dict[str, Any], phase: str, reason: str, path: Path) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


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


def validate_visual_review_receipt(receipt_path: Path, *, run_root: Path | None = None) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    base = run_root.resolve() if run_root else receipt_path.parent.parent
    receipt = _read_json(receipt_path)
    if not isinstance(receipt, dict):
        raise ValueError("visual review receipt must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.visual_review_validation.v1",
        "receipt": str(receipt_path),
        "run_root": str(base),
        "status": "PASS_VISUAL_REVIEW",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in base.parts else "no",
        "live": "no",
        "exercised": "local visual review receipt fields, reviewed image hash parity, reviewer source, eight-check coverage, blocker list discipline",
        "unverified": "new live VLM/WebGPT review, actual image semantics, provider readiness, Kling submission",
    }

    status = receipt.get("status") or receipt.get("verdict")
    if status == "ACCEPTED_MANUAL":
        if receipt.get("schema") != "persona_dream.manual_review_receipt.v1":
            return _block(result, "visual_review_receipt", "manual_acceptance_wrong_schema", receipt_path)
        if not _non_empty_string(receipt.get("decision")):
            return _block(result, "visual_review_receipt", "manual_acceptance_missing_decision", receipt_path)
        reviewed_artifacts = receipt.get("reviewed_artifacts")
        if not isinstance(reviewed_artifacts, list) or not reviewed_artifacts:
            return _block(result, "visual_review_receipt", "manual_acceptance_missing_reviewed_artifacts", receipt_path)
        return result

    if status != "PASS":
        return _block(result, "visual_review_receipt", f"visual_review_not_accepted:{status}", receipt_path)

    panel_id = receipt.get("panel_id") or receipt.get("panel")
    if not _non_empty_string(panel_id):
        return _block(result, "visual_review_receipt", "missing_panel_id", receipt_path)
    if not _non_empty_string(receipt.get("reviewer_source")):
        return _block(result, "visual_review_receipt", "missing_reviewer_source", receipt_path)

    blocking_findings = receipt.get("blocking_findings")
    if not isinstance(blocking_findings, list):
        return _block(result, "visual_review_receipt", "blocking_findings_not_list", receipt_path)
    if blocking_findings:
        return _block(result, "visual_review_receipt", "blocking_findings_present", receipt_path)

    passed_entities = receipt.get("passed_entities")
    if not isinstance(passed_entities, list) or not passed_entities:
        return _block(result, "visual_review_receipt", "missing_passed_entities", receipt_path)

    checks = receipt.get("checks")
    if not isinstance(checks, dict):
        return _block(result, "visual_review_receipt", "missing_checks", receipt_path)
    for check in REQUIRED_CHECKS:
        if checks.get(check) != "PASS":
            return _block(result, "visual_review_receipt", f"check_not_pass:{check}:{checks.get(check)}", receipt_path)

    if not _non_empty_string(receipt.get("hash")):
        return _block(result, "visual_review_receipt", "missing_reviewed_image_hash", receipt_path)
    if not _non_empty_string(receipt.get("reviewed_image_path")):
        return _block(result, "visual_review_receipt", "missing_reviewed_image_path", receipt_path)
    reviewed_image_path = _resolve_path(base, receipt["reviewed_image_path"])
    if not reviewed_image_path.exists():
        return _block(result, "visual_review_image", "reviewed_image_path_missing", reviewed_image_path)
    actual_hash = _sha256(reviewed_image_path)
    if actual_hash != receipt["hash"]:
        return _block(result, "visual_review_image", f"reviewed_image_hash_mismatch:{actual_hash}", reviewed_image_path)
    dimensions = receipt.get("dimensions")
    if not (
        isinstance(dimensions, dict)
        and isinstance(dimensions.get("width"), int)
        and isinstance(dimensions.get("height"), int)
        and dimensions["width"] > 0
        and dimensions["height"] > 0
    ):
        return _block(result, "visual_review_receipt", "missing_dimensions", receipt_path)
    if not _non_empty_string(receipt.get("timestamp")):
        return _block(result, "visual_review_receipt", "missing_timestamp", receipt_path)
    if any(key in receipt for key in ("generated_image_path", "image_generation", "provider_packet_status")):
        return _block(result, "visual_review_receipt", "reviewer_receipt_contains_forbidden_owner_fields", receipt_path)

    result["reviewed_image_path"] = str(reviewed_image_path)
    result["sha256"] = actual_hash
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_visual_review_receipt(args.receipt, run_root=args.run_root)
    except Exception as exc:
        result = {
            "schema": "persona_dream.visual_review_validation.v1",
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
