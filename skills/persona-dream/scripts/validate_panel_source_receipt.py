#!/usr/bin/env python3
"""Validate a Persona Dream panel source receipt.

This is a local deterministic gate. It verifies receipt shape, final-panel
eligibility fields, image existence, image hash, and producer receipt presence.
It does not perform visual review and does not call image or video providers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/panel_source_receipt.schema.json"


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


def _block(
    result: dict[str, Any],
    *,
    phase: str,
    reason: str,
    path: Path,
) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


def _validate_producer_receipt(
    producer_doc: dict[str, Any],
    *,
    producer_name: str,
    panel_id: str,
) -> str | None:
    if producer_name == "persona-dream-panel-repair-gate":
        if producer_doc.get("schema") != "persona_dream.panel_repair_gate_receipt.v1":
            return f"producer_schema_mismatch:{producer_doc.get('schema')}"
        if producer_doc.get("panel_id") != panel_id:
            return f"producer_panel_id_mismatch:{producer_doc.get('panel_id')}"
        if producer_doc.get("status") != "PASS_PANEL_REVIEWED":
            return f"producer_status_not_final_reviewed:{producer_doc.get('status')}"
        if producer_doc.get("provider_eligibility") is not True:
            return "producer_provider_eligibility_not_true"
        if producer_doc.get("nano_banana_fallback_used") is True or producer_doc.get("gemini_fallback_used") is True:
            return "producer_forbidden_fallback_used"
        return None

    if producer_name == "panel-creator":
        status = producer_doc.get("status")
        if status not in {"PASS", "PASS_PANEL_CREATED", "PASS_PANEL_REVIEWED"}:
            return f"producer_status_not_pass:{status}"
        producer_identity = producer_doc.get("producer") or producer_doc.get("name")
        if producer_identity not in {None, "panel-creator"}:
            return f"producer_identity_mismatch:{producer_identity}"
        producer_panel_id = producer_doc.get("panel_id")
        if producer_panel_id is not None and producer_panel_id != panel_id:
            return f"producer_panel_id_mismatch:{producer_panel_id}"
        if producer_doc.get("nano_banana_fallback_used") is True or producer_doc.get("gemini_fallback_used") is True:
            return "producer_forbidden_fallback_used"
        return None

    return f"unsupported_producer_name:{producer_name}"


def validate_panel_source_receipt(receipt_path: Path, *, run_root: Path | None = None) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    base = run_root.resolve() if run_root else receipt_path.parent.parent
    schema = _read_json(SCHEMA)
    receipt = _read_json(receipt_path)
    jsonschema.Draft202012Validator(schema).validate(receipt)

    result: dict[str, Any] = {
        "schema": "persona_dream.panel_source_validation.v1",
        "receipt": str(receipt_path),
        "run_root": str(base),
        "status": "PASS_PANEL_SOURCE",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in base.parts else "no",
        "live": "no",
        "exercised": "local receipt schema, image existence, image hash, subagent producer receipt presence, Nano Banana exclusion fields",
        "unverified": "visual semantics, live image generation, panel-reviewer VLM verdict, provider media hosting, Kling submission",
    }

    if receipt.get("status") != "PASS_PANEL_SOURCE":
        blockers = receipt.get("blockers")
        blocker_suffix = ""
        if isinstance(blockers, list) and all(isinstance(item, str) and item.strip() for item in blockers):
            blocker_suffix = ":" + ";".join(blockers)
        return _block(
            result,
            phase="panel_source_receipt",
            reason=f"panel_source_not_pass:{receipt.get('status')}{blocker_suffix}",
            path=receipt_path,
        )

    field_checks = [
        ("final_panel_eligible", receipt.get("final_panel_eligible") is True, "final_panel_eligible_not_true"),
        (
            "photoreal_status",
            receipt.get("photoreal_status") == "PASS_PHOTOREAL_CINEMATIC",
            f"photoreal_status_not_pass:{receipt.get('photoreal_status')}",
        ),
        ("nano_banana_fallback_used", receipt.get("nano_banana_fallback_used") is False, "nano_banana_fallback_used"),
    ]
    for phase, ok, reason in field_checks:
        if not ok:
            return _block(result, phase=phase, reason=reason, path=receipt_path)

    image_path = _resolve_path(base, receipt["image_path"])
    if not image_path.exists():
        return _block(result, phase="panel_image", reason="missing_image_path", path=image_path)

    actual_hash = _sha256(image_path)
    if actual_hash != receipt["sha256"]:
        return _block(result, phase="panel_image", reason=f"sha256_mismatch:{actual_hash}", path=image_path)

    producer = receipt.get("producer", {})
    producer_name = producer.get("name")
    producer_receipt = producer.get("receipt")
    if not isinstance(producer_receipt, str) or producer_receipt.startswith("missing:"):
        return _block(
            result,
            phase="producer_receipt",
            reason="missing_producer_receipt_reference",
            path=receipt_path,
        )

    producer_receipt_path = _resolve_path(base, producer_receipt)
    if not producer_receipt_path.exists():
        return _block(
            result,
            phase="producer_receipt",
            reason="producer_receipt_file_missing",
            path=producer_receipt_path,
        )

    producer_doc = _read_json(producer_receipt_path)
    if not isinstance(producer_doc, dict):
        return _block(
            result,
            phase="producer_receipt",
            reason="producer_receipt_not_json_object",
            path=producer_receipt_path,
        )
    producer_error = _validate_producer_receipt(
        producer_doc,
        producer_name=str(producer_name),
        panel_id=str(receipt.get("panel_id")),
    )
    if producer_error:
        return _block(
            result,
            phase="producer_receipt",
            reason=producer_error,
            path=producer_receipt_path,
        )

    result["image_path"] = str(image_path)
    result["producer_receipt"] = str(producer_receipt_path)
    result["producer_name"] = producer_name
    result["sha256"] = actual_hash
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_panel_source_receipt(args.receipt, run_root=args.run_root)
    except Exception as exc:
        result = {
            "schema": "persona_dream.panel_source_validation.v1",
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
