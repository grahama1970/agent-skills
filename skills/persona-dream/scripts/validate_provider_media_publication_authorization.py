#!/usr/bin/env python3
"""Validate explicit authorization for provider-media publication.

This is a fail-closed gate between local preflight and any public upload or git
push. Without an authorization receipt, it emits a concrete approval request and
keeps publication blocked. With a receipt, it verifies the authorized URL/hash
match the preflight-locked media before allowing the next publication step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AUTH_SCHEMA = "persona_dream.provider_media_publication_authorization.v1"
VALIDATION_SCHEMA = "persona_dream.provider_media_publication_authorization_validation.v1"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], reason: str, *, phase: str = "provider_media_publication_authorization") -> dict[str, Any]:
    result["status"] = "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION"
    result["first_blocker"] = {"phase": phase, "reason": reason}
    return result


def _approval_request(preflight: dict[str, Any]) -> dict[str, Any]:
    staged_asset_path = preflight.get("staged_asset_path")
    target_repo_path = preflight.get("target_repo_path")
    proposed_url = preflight.get("proposed_url")
    locked_sha256 = preflight.get("locked_sha256")
    return {
        "human_role": "Approve, reject, or provide an equivalent stable public media URL for the exact locked asset.",
        "agent_default_after_approval": [
            f"Publish the exact staged asset {staged_asset_path} to {target_repo_path}.",
            "Do not alter image bytes, provider packet status, or panel review status during publication.",
            "Run next_required_probe_command and require PASS_PROVIDER_MEDIA_URL_PROBE before patching provider media receipts.",
            "If the URL probe fails, keep provider readiness blocked and record the failed probe receipt.",
        ],
        "target_record": {
            "staged_asset_path": staged_asset_path,
            "target_repo_path": target_repo_path,
            "proposed_url": proposed_url,
            "locked_sha256": locked_sha256,
        },
        "authorization_receipt_template": {
            "schema": AUTH_SCHEMA,
            "status": "AUTHORIZED_PUBLICATION",
            "approved_by": "<human-or-authority>",
            "approved_at": "<ISO-8601 timestamp>",
            "approved_action": "publish_exact_locked_provider_media",
            "authorized_url": proposed_url,
            "authorized_sha256": locked_sha256,
            "authorized_target_repo_path": target_repo_path,
            "notes": "No Kling call or provider readiness approval is implied.",
        },
    }


def validate_provider_media_publication_authorization(
    *,
    preflight_receipt_path: Path,
    authorization_receipt_path: Path | None = None,
) -> dict[str, Any]:
    preflight_receipt_path = preflight_receipt_path.resolve()
    preflight = _read_json(preflight_receipt_path)
    if not isinstance(preflight, dict):
        raise ValueError("preflight receipt must be a JSON object")

    result: dict[str, Any] = {
        "schema": VALIDATION_SCHEMA,
        "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
        "first_blocker": {
            "phase": "provider_media_publication_authorization",
            "reason": "authorization_receipt_required",
        },
        "preflight_receipt": str(preflight_receipt_path),
        "authorization_receipt": str(authorization_receipt_path.resolve()) if authorization_receipt_path else None,
        "mocked": "yes" if "fixtures" in preflight_receipt_path.parts else "no",
        "live": "no",
        "exercised": "preflight receipt parse, authorization boundary, locked URL/hash comparison when an authorization receipt is supplied",
        "unverified": "public upload execution, public URL fetch, Kling provider fetch behavior, paid-call approval, Kling submission",
        "does_not_authorize": [
            "git_push_without_authorization_receipt",
            "public_upload_without_authorization_receipt",
            "provider_readiness",
            "direct_kling_submit",
            "paid_provider_call",
        ],
        "approval_request": _approval_request(preflight),
    }

    if preflight.get("status") != "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION" or preflight.get("preflight_ready") is not True:
        return _block(
            result,
            f"preflight_not_ready:{preflight.get('status')}:{preflight.get('preflight_ready')}",
            phase="provider_media_publication_preflight",
        )

    proposed_url = preflight.get("proposed_url")
    locked_sha256 = preflight.get("locked_sha256")
    target_repo_path = preflight.get("target_repo_path")
    result["proposed_url"] = proposed_url
    result["locked_sha256"] = locked_sha256
    result["target_repo_path"] = target_repo_path
    result["next_required_probe_command"] = preflight.get("next_required_probe_command")

    if not authorization_receipt_path:
        return result

    auth_path = authorization_receipt_path.resolve()
    auth = _read_json(auth_path)
    if not isinstance(auth, dict):
        raise ValueError("authorization receipt must be a JSON object")
    result["authorization_receipt"] = str(auth_path)

    if auth.get("schema") != AUTH_SCHEMA:
        return _block(result, f"wrong_authorization_schema:{auth.get('schema')}")
    if auth.get("status") != "AUTHORIZED_PUBLICATION":
        return _block(result, f"authorization_not_granted:{auth.get('status')}")
    if auth.get("approved_action") != "publish_exact_locked_provider_media":
        return _block(result, f"wrong_approved_action:{auth.get('approved_action')}")
    if auth.get("authorized_url") != proposed_url:
        return _block(result, f"authorized_url_mismatch:preflight={proposed_url}:auth={auth.get('authorized_url')}")
    if auth.get("authorized_sha256") != locked_sha256:
        return _block(
            result,
            f"authorized_sha256_mismatch:preflight={locked_sha256}:auth={auth.get('authorized_sha256')}",
        )
    if auth.get("authorized_target_repo_path") != target_repo_path:
        return _block(
            result,
            f"authorized_target_repo_path_mismatch:preflight={target_repo_path}:auth={auth.get('authorized_target_repo_path')}",
        )
    if not auth.get("approved_by"):
        return _block(result, "missing_approved_by")
    if not auth.get("approved_at"):
        return _block(result, "missing_approved_at")

    result["status"] = "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION"
    result["first_blocker"] = None
    result["authorized_by"] = auth.get("approved_by")
    result["authorized_at"] = auth.get("approved_at")
    result["next_action"] = (
        "Publish the exact locked staged asset to the authorized URL, then run "
        "next_required_probe_command and require PASS_PROVIDER_MEDIA_URL_PROBE."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_provider_media_publication_authorization(
            preflight_receipt_path=args.preflight_receipt,
            authorization_receipt_path=args.authorization_receipt,
        )
    except Exception as exc:
        result = {
            "schema": VALIDATION_SCHEMA,
            "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']} {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
