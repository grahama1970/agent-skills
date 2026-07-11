#!/usr/bin/env python3
"""Validate provider-media publication preflight without publishing.

This is the last local-only check before an authorized public upload or git
push. It proves the work order and staged bytes agree and records that public
availability is still unverified until a live URL probe passes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_provider_media_local_staging import validate_provider_media_local_staging
from validate_provider_media_publication_work_order import validate_provider_media_publication_work_order


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], reason: str, *, phase: str = "provider_media_publication_preflight") -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason}
    return result


def validate_provider_media_publication_preflight(
    *,
    work_order_path: Path,
    local_staging_receipt_path: Path,
) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    local_staging_receipt_path = local_staging_receipt_path.resolve()

    result: dict[str, Any] = {
        "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
        "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
        "first_blocker": {
            "phase": "provider_media_publication_authorization",
            "reason": "public_upload_or_git_push_authorization_required",
        },
        "work_order": str(work_order_path),
        "local_staging_receipt": str(local_staging_receipt_path),
        "mocked": "yes" if "fixtures" in (*work_order_path.parts, *local_staging_receipt_path.parts) else "no",
        "live": "no",
        "exercised": "publication work-order validation, local staging byte/hash validation, proposed URL/hash parity, authorization boundary",
        "unverified": "public upload authorization, git push/public asset publication, public URL fetch, Kling provider fetch behavior, paid-call approval, Kling submission",
        "does_not_authorize": [
            "git_push",
            "public_upload",
            "provider_readiness",
            "direct_kling_submit",
            "paid_provider_call",
        ],
    }

    work_order_validation = validate_provider_media_publication_work_order(work_order_path)
    staging_validation = validate_provider_media_local_staging(local_staging_receipt_path)
    result["work_order_validation_status"] = work_order_validation.get("status")
    result["local_staging_validation_status"] = staging_validation.get("status")
    if work_order_validation.get("status") != "PASS_PROVIDER_MEDIA_PUBLICATION_WORK_ORDER":
        blocker = work_order_validation.get("first_blocker") or {}
        return _block(result, f"work_order_not_pass:{blocker.get('reason')}", phase="provider_media_publication_work_order")
    if staging_validation.get("status") != "PASS_PROVIDER_MEDIA_LOCAL_STAGING":
        blocker = staging_validation.get("first_blocker") or {}
        return _block(result, f"local_staging_not_pass:{blocker.get('reason')}", phase="provider_media_local_staging")

    work_order = _read_json(work_order_path)
    staging = _read_json(local_staging_receipt_path)
    if not isinstance(work_order, dict) or not isinstance(staging, dict):
        raise ValueError("preflight inputs must be JSON objects")

    publication = work_order.get("proposed_publication") if isinstance(work_order.get("proposed_publication"), dict) else {}
    locked = work_order.get("locked_media") if isinstance(work_order.get("locked_media"), dict) else {}
    proposed_url = publication.get("proposed_url")
    target_repo_path = publication.get("target_repo_path")
    locked_sha256 = locked.get("sha256")
    staged_url = staging.get("proposed_url")
    staged_sha256 = staging.get("staged_sha256")
    staged_target_repo_path = staging.get("target_repo_path")

    result["proposed_url"] = proposed_url
    result["target_repo_path"] = target_repo_path
    result["locked_sha256"] = locked_sha256
    result["staged_sha256"] = staged_sha256
    result["staged_asset_path"] = staging.get("staged_asset_path")
    result["authorization_required"] = work_order.get("authorization_required", [])
    result["next_required_probe_command"] = staging.get("next_required_probe_command")

    if staged_url != proposed_url:
        return _block(result, f"staged_url_mismatch:work_order={proposed_url}:staging={staged_url}")
    if staged_target_repo_path != target_repo_path:
        return _block(
            result,
            f"staged_target_repo_path_mismatch:work_order={target_repo_path}:staging={staged_target_repo_path}",
        )
    if staged_sha256 != locked_sha256:
        return _block(result, f"staged_sha256_mismatch:work_order={locked_sha256}:staging={staged_sha256}")

    result["preflight_ready"] = True
    result["next_action"] = (
        "After explicit authorization, publish the staged asset at target_repo_path, "
        "then run next_required_probe_command and validate-provider-media-public-handoff."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--local-staging-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_provider_media_publication_preflight(
            work_order_path=args.work_order,
            local_staging_receipt_path=args.local_staging_receipt,
        )
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
            "status": "BLOCKED",
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
    return 0 if result["status"] == "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION" and result.get("preflight_ready") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
