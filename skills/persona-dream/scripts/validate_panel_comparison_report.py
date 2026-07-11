#!/usr/bin/env python3
"""Validate the Panel 01 comparison report as a reality-check surface.

This is a deterministic report check. It verifies that the report references
real local PNG assets, that displayed dimensions/hashes match those assets, and
that the report preserves the fail-closed claim boundary: visual comparison is
not panel acceptance or Kling readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        attr_map = {key: value for key, value in attrs}
        src = attr_map.get("src")
        if src:
            self.images.append(src)

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.text_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


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
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", header[16:24])


def _block(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": "panel_comparison_report", "reason": reason}
    return result


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _resolve_status_artifact_path(path_value: Any, *, status_path: Path) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (status_path.parent / path).resolve()


def validate_panel_comparison_report(report_path: Path, *, status_path: Path | None = None) -> dict[str, Any]:
    report_path = report_path.resolve()
    report_dir = report_path.parent
    html = report_path.read_text(encoding="utf-8")
    parser = ReportParser()
    parser.feed(html)
    text = _normalize_text(parser.text)
    lower_text = text.lower()

    status_path = (status_path or report_dir / "status.json").resolve()
    status_doc = _read_json(status_path)
    if not isinstance(status_doc, dict):
        raise ValueError("status.json must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.panel_comparison_report_validation.v1",
        "status": "PASS_PANEL_COMPARISON_REPORT",
        "first_blocker": None,
        "report": str(report_path),
        "status_json": str(status_path),
        "candidate_count": 0,
        "assets": [],
        "mocked": "no",
        "live": "no",
        "exercised": "HTML parse, local PNG asset existence, displayed dimensions/hash parity, fail-closed report copy, status.json blocker alignment",
        "unverified": "visual semantic quality, live panel subagent generation/review, public media hosting, paid Kling submission",
    }

    if status_doc.get("schema") != "persona_dream.panel_comparison_status.v1":
        return _block(result, f"wrong_status_json_schema:{status_doc.get('schema')}")
    if status_doc.get("acceptance_state") != "Not asserted by this report.":
        return _block(result, "status_json_must_not_assert_acceptance")
    first_blocker = status_doc.get("first_blocker")
    if not isinstance(first_blocker, dict) or first_blocker.get("phase") not in {
        "provider_media_publication_authorization",
        "provider_media_public_probe",
    }:
        return _block(result, "status_json_first_blocker_must_be_provider_media_publication_authorization_or_probe")
    if status_doc.get("policy", {}).get("kling_call_allowed") is not False:
        return _block(result, "status_json_must_disallow_kling_call")
    if status_doc.get("policy", {}).get("nano_banana_final_panel_allowed") is not False:
        return _block(result, "status_json_must_disallow_nano_banana_final_panel")
    receipts = status_doc.get("receipts") if isinstance(status_doc.get("receipts"), dict) else {}
    evidence_bundle = receipts.get("pipeline_evidence_bundle") if isinstance(receipts.get("pipeline_evidence_bundle"), dict) else None
    if evidence_bundle is None:
        return _block(result, "status_json_missing_pipeline_evidence_bundle")
    if evidence_bundle.get("status") != "BLOCKED":
        return _block(result, f"status_json_pipeline_evidence_bundle_must_be_blocked:{evidence_bundle.get('status')}")
    evidence_blocker = evidence_bundle.get("first_blocker")
    if not isinstance(evidence_blocker, dict) or evidence_blocker.get("phase") not in {
        "provider_media_publication_authorization",
        "provider_media_public_probe",
    }:
        return _block(
            result,
            "status_json_pipeline_evidence_bundle_first_blocker_must_be_provider_media_publication_authorization_or_probe",
        )
    validation_statuses = evidence_bundle.get("validation_statuses")
    if not isinstance(validation_statuses, dict):
        return _block(result, "status_json_pipeline_evidence_bundle_missing_validation_statuses")
    if validation_statuses.get("panel_comparison_report") not in {"PASS_PANEL_COMPARISON_REPORT", None}:
        return _block(
            result,
            f"status_json_pipeline_evidence_bundle_report_status_bad:{validation_statuses.get('panel_comparison_report')}",
        )
    evidence_bundle_path = _resolve_status_artifact_path(evidence_bundle.get("path"), status_path=status_path)
    if evidence_bundle_path is None:
        return _block(result, "status_json_pipeline_evidence_bundle_missing_path")
    if not evidence_bundle_path.exists():
        return _block(result, f"status_json_pipeline_evidence_bundle_missing_file:{evidence_bundle_path}")
    bundle_doc = _read_json(evidence_bundle_path)
    if not isinstance(bundle_doc, dict):
        return _block(result, "pipeline_evidence_bundle_json_not_object")
    if bundle_doc.get("schema") != "persona_dream.pipeline_evidence_bundle_validation.v1":
        return _block(result, f"pipeline_evidence_bundle_wrong_schema:{bundle_doc.get('schema')}")
    if bundle_doc.get("status") != evidence_bundle.get("status"):
        return _block(
            result,
            f"pipeline_evidence_bundle_status_mismatch:status_json={evidence_bundle.get('status')}:bundle={bundle_doc.get('status')}",
        )
    bundle_blocker = bundle_doc.get("first_blocker")
    if not isinstance(bundle_blocker, dict) or bundle_blocker.get("phase") != evidence_blocker.get("phase"):
        return _block(result, "pipeline_evidence_bundle_first_blocker_mismatch")
    bundle_validations = bundle_doc.get("validations") if isinstance(bundle_doc.get("validations"), dict) else {}
    for key, summarized_status in validation_statuses.items():
        actual = bundle_validations.get(key)
        actual_status = actual.get("status") if isinstance(actual, dict) else None
        if actual_status != summarized_status:
            return _block(
                result,
                f"pipeline_evidence_bundle_validation_status_mismatch:{key}:status_json={summarized_status}:bundle={actual_status}",
            )
    result["pipeline_evidence_bundle"] = {
        "path": str(evidence_bundle_path),
        "status": bundle_doc.get("status"),
        "first_blocker": bundle_doc.get("first_blocker"),
    }

    required_phrases = [
        "does not assert final panel acceptance or kling readiness",
        "not asserted by this report",
        "nano banana fallback imagery is non-eligible for final panels",
        "do not call kling",
        "provider_media_publication_authorization",
        "pipeline_evidence_bundle_validation.json",
    ]
    for phrase in required_phrases:
        if phrase not in lower_text:
            return _block(result, f"missing_required_report_phrase:{phrase}")

    forbidden_claims = [
        "provider_ready",
        "kling ready",
        "ready for kling",
        "final panel accepted",
    ]
    for claim in forbidden_claims:
        if claim in lower_text:
            return _block(result, f"forbidden_report_claim:{claim}")

    if not parser.images:
        return _block(result, "missing_candidate_images")

    for src in parser.images:
        if "://" in src or src.startswith("/"):
            return _block(result, f"image_src_must_be_local_relative:{src}")
        image_path = (report_dir / src).resolve()
        if report_dir not in (image_path, *image_path.parents):
            return _block(result, f"image_src_escapes_report_dir:{src}")
        if not image_path.exists():
            return _block(result, f"missing_image_asset:{src}")
        try:
            width, height = _png_dimensions(image_path)
        except ValueError as exc:
            return _block(result, str(exc))
        sha256 = _sha256(image_path)
        if f"{width} x {height}" not in text:
            return _block(result, f"displayed_dimensions_missing_or_mismatch:{src}:{width}x{height}")
        if sha256 not in text:
            return _block(result, f"displayed_sha256_missing_or_mismatch:{src}:{sha256}")
        result["assets"].append(
            {
                "src": src,
                "path": str(image_path),
                "width": width,
                "height": height,
                "sha256": "sha256:" + sha256,
            }
        )

    result["candidate_count"] = len(parser.images)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--status-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_panel_comparison_report(args.report, status_path=args.status_json)
    except Exception as exc:
        result = {
            "schema": "persona_dream.panel_comparison_report_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "PASS_PANEL_COMPARISON_REPORT" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
