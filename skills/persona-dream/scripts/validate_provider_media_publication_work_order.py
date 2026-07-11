#!/usr/bin/env python3
"""Validate a provider-media publication work order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_AUTH = {
    "public_upload_of_panel_image",
    "git_commit_and_push_or_equivalent_public_asset_publish",
}
REQUIRED_FORBIDDEN = {
    "direct_kling_submit",
    "paid_provider_call",
    "nano_banana_final_panel_generation",
    "gemini_final_panel_generation",
    "provider_readiness_without_live_url_probe",
    "hash_or_receipt_rewrite_without_matching_public_fetch",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": "provider_media_publication_work_order", "reason": reason}
    return result


def validate_provider_media_publication_work_order(path: Path) -> dict[str, Any]:
    path = path.resolve()
    doc = _read_json(path)
    if not isinstance(doc, dict):
        raise ValueError("work order must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.provider_media_publication_work_order_validation.v1",
        "status": "PASS_PROVIDER_MEDIA_PUBLICATION_WORK_ORDER",
        "work_order": str(path),
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in path.parts else "no",
        "live": "no",
        "exercised": "local work-order schema, authorization gate, source paths, URL/hash verification plan, forbidden action policy",
        "unverified": "public upload authorization, public URL fetch, Kling provider fetch behavior, paid-call approval, Kling submission",
    }

    if doc.get("schema") != "persona_dream.provider_media_publication_work_order.v1":
        return _block(result, f"wrong_schema:{doc.get('schema')}")
    if doc.get("status") != "WORK_ORDER_READY_PUBLIC_UPLOAD_AUTH_REQUIRED":
        return _block(result, f"wrong_status:{doc.get('status')}")

    auth = set(doc.get("authorization_required", []))
    missing_auth = sorted(REQUIRED_AUTH - auth)
    if missing_auth:
        return _block(result, "missing_authorization_required:" + ",".join(missing_auth))

    forbidden = set(doc.get("forbidden_actions", []))
    missing_forbidden = sorted(REQUIRED_FORBIDDEN - forbidden)
    if missing_forbidden:
        return _block(result, "missing_forbidden_actions:" + ",".join(missing_forbidden))

    source_paths = doc.get("source_paths")
    if not isinstance(source_paths, dict):
        return _block(result, "missing_source_paths")
    for field in ("run_root", "panel_repair_gate_receipt", "provider_media_probe_receipt", "panel_image"):
        value = source_paths.get(field)
        if not isinstance(value, str) or not Path(value).exists():
            return _block(result, f"missing_source_path:{field}")

    locked = doc.get("locked_media")
    if not isinstance(locked, dict):
        return _block(result, "missing_locked_media")
    if not isinstance(locked.get("sha256"), str) or not locked["sha256"].startswith("sha256:"):
        return _block(result, "missing_locked_media_sha256")

    publication = doc.get("proposed_publication")
    if not isinstance(publication, dict):
        return _block(result, "missing_proposed_publication")
    proposed_url = publication.get("proposed_url")
    if not isinstance(proposed_url, str) or not proposed_url.startswith("https://raw.githubusercontent.com/"):
        return _block(result, "proposed_url_must_be_github_raw_https")

    commands = doc.get("verification_commands")
    if not isinstance(commands, list) or not any("validate-provider-media-url" in str(command) for command in commands):
        return _block(result, "missing_validate_provider_media_url_command")
    if not any("validate-panel-repair-gate" in str(command) and "--require-provider-eligible" in str(command) for command in commands):
        return _block(result, "missing_final_panel_repair_gate_command")

    current = doc.get("current_state")
    if isinstance(current, dict):
        result["current_probe_status"] = current.get("probe_status")
        result["current_provider_media_status"] = current.get("provider_media_status")
    result["proposed_url"] = proposed_url
    result["locked_sha256"] = locked["sha256"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_provider_media_publication_work_order(args.work_order)
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_publication_work_order_validation.v1",
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
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
