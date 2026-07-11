#!/usr/bin/env python3
"""Validate the provider-media public handoff boundary.

This command ties together the authorization work order, local staging receipt,
and public URL probe. It does not publish media, push git changes, patch panel
receipts, call Kling, or authorize paid provider work.
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


def _block(result: dict[str, Any], reason: str, *, phase: str = "provider_media_public_handoff") -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason}
    return result


def validate_provider_media_public_handoff(
    *,
    work_order_path: Path,
    local_staging_receipt_path: Path,
    public_probe_receipt_path: Path,
) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    local_staging_receipt_path = local_staging_receipt_path.resolve()
    public_probe_receipt_path = public_probe_receipt_path.resolve()

    result: dict[str, Any] = {
        "schema": "persona_dream.provider_media_public_handoff_validation.v1",
        "status": "PASS_PROVIDER_MEDIA_PUBLIC_HANDOFF_READY",
        "first_blocker": None,
        "work_order": str(work_order_path),
        "local_staging_receipt": str(local_staging_receipt_path),
        "public_probe_receipt": str(public_probe_receipt_path),
        "mocked": "yes"
        if any("fixtures" in path.parts for path in (work_order_path, local_staging_receipt_path, public_probe_receipt_path))
        else "no",
        "live": "no",
        "exercised": "publication work-order validation, local staging validation, URL/hash agreement, public probe receipt status",
        "unverified": "public upload authorization, Kling provider fetch behavior, paid-call approval, Kling submission",
        "does_not_authorize": [
            "git_push",
            "public_upload",
            "provider_readiness_without_passed_probe",
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
    probe = _read_json(public_probe_receipt_path)
    if not isinstance(work_order, dict) or not isinstance(staging, dict) or not isinstance(probe, dict):
        raise ValueError("handoff inputs must be JSON objects")

    publication = work_order.get("proposed_publication") if isinstance(work_order.get("proposed_publication"), dict) else {}
    locked = work_order.get("locked_media") if isinstance(work_order.get("locked_media"), dict) else {}
    proposed_url = publication.get("proposed_url")
    target_repo_path = publication.get("target_repo_path")
    locked_sha256 = locked.get("sha256")
    staged_url = staging.get("proposed_url")
    staged_sha256 = staging.get("staged_sha256")
    staged_target_repo_path = staging.get("target_repo_path")
    probe_url = probe.get("url")
    probe_expected_sha256 = probe.get("expected_sha256")
    probe_observed_sha256 = probe.get("observed_sha256")

    result["proposed_url"] = proposed_url
    result["target_repo_path"] = target_repo_path
    result["locked_sha256"] = locked_sha256
    result["staged_sha256"] = staged_sha256
    result["probe_status"] = probe.get("status")
    result["probe_http_status"] = probe.get("http_status")
    result["probe_blockers"] = probe.get("blockers", [])
    result["live"] = probe.get("live") if probe.get("live") in {"yes", "no"} else "no"

    if staged_url != proposed_url:
        return _block(result, f"staged_url_mismatch:work_order={proposed_url}:staging={staged_url}")
    if staged_target_repo_path != target_repo_path:
        return _block(
            result,
            f"staged_target_repo_path_mismatch:work_order={target_repo_path}:staging={staged_target_repo_path}",
        )
    if staged_sha256 != locked_sha256:
        return _block(result, f"staged_sha256_mismatch:work_order={locked_sha256}:staging={staged_sha256}")
    if probe_url != proposed_url:
        return _block(result, f"probe_url_mismatch:work_order={proposed_url}:probe={probe_url}")
    if probe_expected_sha256 != locked_sha256:
        return _block(result, f"probe_expected_sha256_mismatch:work_order={locked_sha256}:probe={probe_expected_sha256}")
    if probe.get("status") != "PASS_PROVIDER_MEDIA_URL_PROBE":
        blockers = probe.get("blockers") if isinstance(probe.get("blockers"), list) else []
        reason = "public_probe_not_pass"
        if blockers:
            reason += ":" + ";".join(str(blocker) for blocker in blockers)
        return _block(result, reason, phase="provider_media_public_probe")
    if probe_observed_sha256 != locked_sha256:
        return _block(result, f"probe_observed_sha256_mismatch:work_order={locked_sha256}:probe={probe_observed_sha256}")

    result["next_action"] = (
        "Apply the passing provider media probe to the panel repair gate, then rerun "
        "validate-panel-repair-gate --require-provider-eligible."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--local-staging-receipt", type=Path, required=True)
    parser.add_argument("--public-probe-receipt", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_provider_media_public_handoff(
            work_order_path=args.work_order,
            local_staging_receipt_path=args.local_staging_receipt,
            public_probe_receipt_path=args.public_probe_receipt,
        )
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_public_handoff_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']} {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "PASS_PROVIDER_MEDIA_PUBLIC_HANDOFF_READY" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
