#!/usr/bin/env python3
"""Validate a provider-neutral bespoke-design reviewer transport receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
SECRETISH_RE = re.compile(r"(?:rn-secret-nonce-|access_nonce=|/__review/[A-Za-z0-9_-]{16,}/)")
REPO = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", type=Path)
    return parser.parse_args()


def read_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"file not found: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
    return {}


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_artifact(record: dict[str, Any], path_field: str, sha_field: str, label: str, errors: list[str]) -> None:
    path_value = record.get(path_field)
    digest = record.get(sha_field)
    if not path_value or not valid_sha(digest):
        errors.append(f"{label} requires {path_field} and {sha_field}")
        return
    path = repo_path(str(path_value))
    if not path.is_file():
        errors.append(f"{label} missing artifact: {path_value}")
    elif sha256(path) != digest:
        errors.append(f"{label} sha256 mismatch: {path_value}")


def walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(walk_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for item in value.values():
            strings.extend(walk_strings(item))
        return strings
    return []


def validate(root: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(root, dict):
        return ["root must be an object"]
    if root.get("schema_version") != "bespoke-review-transport.v1":
        errors.append("schema_version must be bespoke-review-transport.v1")
    attempt_kind = root.get("attempt_kind")
    if attempt_kind not in {"preflight", "rater", "attachment_fallback"}:
        errors.append("attempt_kind is invalid")
    delivery_mode = root.get("delivery_mode")
    if delivery_mode not in {"url", "attachment"}:
        errors.append("delivery_mode is invalid")
    expected_fp = root.get("expected_candidate_fingerprint")
    observed_fp = root.get("observed_candidate_fingerprint")
    if not valid_sha(expected_fp):
        errors.append("expected_candidate_fingerprint must be sha256")
    if not valid_sha(observed_fp):
        errors.append("observed_candidate_fingerprint must be sha256")
    expected_units = root.get("expected_unit_ids")
    observed_units = root.get("observed_unit_ids")
    if not isinstance(expected_units, list) or not expected_units:
        errors.append("expected_unit_ids must be non-empty")
        expected_units = []
    if not isinstance(observed_units, list):
        errors.append("observed_unit_ids must be an array")
        observed_units = []

    transport = root.get("transport") if isinstance(root.get("transport"), dict) else {}
    inspection = root.get("inspection") if isinstance(root.get("inspection"), dict) else {}
    rater = root.get("rater") if isinstance(root.get("rater"), dict) else {}
    redaction = root.get("access_token_redaction") if isinstance(root.get("access_token_redaction"), dict) else {}

    transport_status = transport.get("status")
    if transport_status not in {"PASS", "BLOCKED"}:
        errors.append("transport.status must be PASS or BLOCKED")
    if transport_status == "BLOCKED" and root.get("design_gate_status") != "UNCHANGED":
        errors.append("reviewer transport BLOCKED must leave design_gate_status UNCHANGED")
    if transport_status == "BLOCKED" and not transport.get("blocked_reason"):
        errors.append("transport BLOCKED requires blocked_reason")

    inspection_status = inspection.get("status")
    if inspection_status not in {"PROVEN", "NOT_PROVEN"}:
        errors.append("inspection.status is invalid")
    inspection_flags = (
        "review_marker_seen",
        "candidate_fingerprint_seen",
        "unit_ids_seen",
        "canonical_render_loaded",
    )
    if inspection_status == "PROVEN":
        for flag in inspection_flags:
            if inspection.get(flag) is not True:
                errors.append(f"inspection PROVEN requires {flag}=true")

    rater_status = rater.get("status")
    counted = rater.get("counted_as_rater")
    if rater_status not in {"USABLE", "UNUSABLE", "NOT_RUN"}:
        errors.append("rater.status is invalid")
    if not isinstance(counted, bool):
        errors.append("rater.counted_as_rater must be boolean")
        counted = False
    if attempt_kind == "preflight" and counted:
        errors.append("preflight acknowledgement cannot be counted as a rater")
    if attempt_kind == "preflight" and rater_status == "USABLE":
        errors.append("preflight cannot be USABLE rater evidence")
    if counted and rater_status != "USABLE":
        errors.append("only USABLE rater responses may be counted")
    if rater_status == "USABLE":
        if transport_status != "PASS" or inspection_status != "PROVEN":
            errors.append("USABLE rater requires transport PASS and inspection PROVEN")
        if expected_fp != observed_fp:
            errors.append("USABLE rater observed wrong candidate fingerprint")
        if set(expected_units) != set(observed_units):
            errors.append("USABLE rater observed stale or incomplete unit ids")
        check_artifact(rater, "raw_output_path", "raw_output_sha256", "rater raw output", errors)
        check_artifact(rater, "parsed_output_path", "parsed_output_sha256", "rater parsed output", errors)
        prompt = root.get("prompt") if isinstance(root.get("prompt"), dict) else {}
        check_artifact(prompt, "path", "sha256", "prompt", errors)
    if rater_status == "UNUSABLE" and not rater.get("exclusion_reason"):
        errors.append("UNUSABLE rater requires exclusion_reason")

    if redaction.get("status") != "PASS":
        errors.append("access_token_redaction.status must be PASS")
    if not valid_sha(redaction.get("review_url_hash_sha256")):
        errors.append("access_token_redaction.review_url_hash_sha256 must be sha256")
    if delivery_mode == "url" and "<redacted>" not in str(redaction.get("redacted_url") or ""):
        errors.append("URL transport must preserve only a redacted URL")
    for text in walk_strings(root):
        if SECRETISH_RE.search(text) and "<redacted>" not in text:
            errors.append("transport receipt leaks an access nonce or unredacted review URL")
            break
    return errors


def main() -> int:
    args = parse_args()
    read_errors: list[str] = []
    root = read_json(args.transport, read_errors)
    errors = read_errors + validate(root)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "transport": str(args.transport)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
