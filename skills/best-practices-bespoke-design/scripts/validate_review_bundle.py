#!/usr/bin/env python3
"""Validate a provider-neutral bespoke-design review bundle."""

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
    parser.add_argument("bundle", type=Path)
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


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
    if root.get("schema_version") != "bespoke-review-bundle.v1":
        errors.append("schema_version must be bespoke-review-bundle.v1")
    if not valid_sha(root.get("candidate_fingerprint")):
        errors.append("candidate_fingerprint must be a lowercase sha256")
    if root.get("candidate_fingerprint_usage") != "integrity_only":
        errors.append("candidate_fingerprint_usage must be integrity_only")
    if root.get("candidate_fingerprint_is_secret") is True:
        errors.append("candidate_fingerprint must not be treated as a secret")
    if root.get("access_credential_source") == "candidate_fingerprint":
        errors.append("candidate_fingerprint must not be used as an access credential")
    candidate_inputs = root.get("candidate_inputs")
    if not isinstance(candidate_inputs, list) or len(set(candidate_inputs or [])) < 3:
        errors.append("candidate_inputs must contain at least three unique inputs")

    delivery = root.get("delivery") if isinstance(root.get("delivery"), dict) else {}
    mode = delivery.get("mode")
    if mode not in {"url", "attachment"}:
        errors.append("delivery.mode must be url or attachment")
    if "access_nonce" in delivery:
        errors.append("durable bundle must not contain plaintext access_nonce")
    if mode == "url":
        redacted = str(delivery.get("review_index_url_redacted") or "")
        if "<redacted>" not in redacted:
            errors.append("URL delivery must store only a redacted review URL")
        for field in ("review_url_hash_sha256", "access_nonce_sha256"):
            if not valid_sha(delivery.get(field)):
                errors.append(f"delivery.{field} must be a sha256")
        if delivery.get("attachment_manifest_path"):
            errors.append("URL delivery must not be expressed as attachment-first")
    if mode == "attachment":
        if not delivery.get("attachment_manifest_path") or not valid_sha(delivery.get("attachment_manifest_sha256")):
            errors.append("attachment delivery requires attachment manifest path and sha256")

    safety = root.get("public_safety") if isinstance(root.get("public_safety"), dict) else {}
    classification = safety.get("classification")
    if classification not in {"public_safe", "private_client", "confidential", "regulated", "itar"}:
        errors.append("public_safety.classification is invalid")
    if safety.get("publish_allowed") is True and classification != "public_safe":
        errors.append("capability URL publication is forbidden for non-public-safe content")
    if safety.get("sensitive_material") is True and safety.get("publish_allowed") is True:
        errors.append("sensitive material cannot be published by opaque URL")

    blind = root.get("blind_mode") if isinstance(root.get("blind_mode"), dict) else {}
    if blind.get("enabled") is True and blind.get("leakage_scan_status") != "PASS":
        errors.append("blind mode requires leakage_scan_status PASS")

    units = root.get("review_units")
    if not isinstance(units, list) or not units:
        errors.append("review_units must be a non-empty array")
        units = []
    unit_ids: list[str] = []
    for index, unit in enumerate(units):
        label = f"review_units[{index}]"
        if not isinstance(unit, dict):
            errors.append(f"{label} must be an object")
            continue
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            errors.append(f"{label}.unit_id missing")
        else:
            unit_ids.append(unit_id)
        for field in ("route", "selector", "viewport", "page_state", "intended_proof"):
            if not isinstance(unit.get(field), str) or not unit.get(field).strip():
                errors.append(f"{label}.{field} missing")
        render = unit.get("canonical_render") if isinstance(unit.get("canonical_render"), dict) else {}
        path_value = render.get("path")
        digest = render.get("sha256")
        if not path_value or not valid_sha(digest):
            errors.append(f"{label}.canonical_render requires path and sha256")
        else:
            path = repo_path(str(path_value))
            if not path.is_file():
                errors.append(f"{label}.canonical_render path missing: {path_value}")
            elif sha256(path) != digest:
                errors.append(f"{label}.canonical_render sha256 mismatch: {path_value}")
        boundaries = unit.get("does_not_prove")
        if not isinstance(boundaries, list) or not boundaries:
            errors.append(f"{label}.does_not_prove must be non-empty")
    if len(set(unit_ids)) != len(unit_ids):
        errors.append("review unit ids must be unique")
    if not isinstance(root.get("does_not_prove"), list) or not root.get("does_not_prove"):
        errors.append("bundle does_not_prove must be non-empty")

    for text in walk_strings(root):
        if SECRETISH_RE.search(text) and "<redacted>" not in text:
            errors.append("durable bundle leaks an access nonce or unredacted review URL")
            break
    return errors


def main() -> int:
    args = parse_args()
    read_errors: list[str] = []
    root = read_json(args.bundle, read_errors)
    errors = read_errors + validate(root)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "bundle": str(args.bundle)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
