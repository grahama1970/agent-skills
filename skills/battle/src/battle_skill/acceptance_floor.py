"""Acceptance-contract floor enforcement for Battle campaign arenas.

Battle may add fuzz and beyond-contract cases, but the frozen client contract is
non-optional: every acceptance case must map to at least one generator case that
is retained in the campaign profile's required_case_ids.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FLOOR_SCHEMA = "battle.acceptance_floor_receipt.v1"
BUNDLE_SCHEMA = "acceptance_contract.bundle.v1"
PROFILE_SCHEMA = "battle.campaign_profile.v1"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_acceptance_floor(
    *,
    bundle_path: str | Path,
    campaign_profile: dict[str, Any],
    case_map: dict[str, list[str]] | None,
) -> dict[str, Any]:
    """Return a fail-closed receipt proving the contract floor is in the arena."""
    problems: list[str] = []
    if not bundle_path:
        return {
            "schema": FLOOR_SCHEMA,
            "status": "BLOCKED",
            "bundle": None,
            "bundle_sha256": None,
            "profile_id": campaign_profile.get("profile_id"),
            "acceptance_cases": 0,
            "covered_acceptance_cases": 0,
            "required_campaign_cases": sorted(campaign_profile.get("required_case_ids") or []),
            "case_map": {},
            "problems": ["bundle-path-missing"],
        }
    bundle_path = Path(bundle_path)
    try:
        bundle = _load_json(bundle_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": FLOOR_SCHEMA,
            "status": "BLOCKED",
            "bundle": str(bundle_path),
            "bundle_sha256": None,
            "profile_id": campaign_profile.get("profile_id"),
            "acceptance_cases": 0,
            "covered_acceptance_cases": 0,
            "required_campaign_cases": sorted(campaign_profile.get("required_case_ids") or []),
            "case_map": {},
            "problems": [f"bundle-unreadable:{exc}"],
        }

    if bundle.get("schema") != BUNDLE_SCHEMA:
        problems.append(f"bundle-schema:{bundle.get('schema')!r}")
    if campaign_profile.get("schema") != PROFILE_SCHEMA:
        problems.append(f"profile-schema:{campaign_profile.get('schema')!r}")

    open_questions = bundle.get("open_questions") or []
    if open_questions:
        problems.append("bundle-open-questions")

    acceptance_cases = bundle.get("acceptance_cases") or []
    if not acceptance_cases:
        problems.append("bundle-has-no-acceptance-cases")

    required_case_ids = set(campaign_profile.get("required_case_ids") or [])
    if not isinstance(case_map, dict):
        problems.append("case-map-not-object")
        case_map = {}
    else:
        case_map = case_map or {}
    covered: dict[str, list[str]] = {}
    for case in acceptance_cases:
        ac_id = case.get("id")
        mapped = case_map.get(ac_id) if isinstance(ac_id, str) else None
        if not mapped:
            problems.append(f"acceptance-case-unmapped:{ac_id}")
            continue
        if not isinstance(mapped, list) or not all(isinstance(item, str) for item in mapped):
            problems.append(f"acceptance-case-map-invalid:{ac_id}")
            continue
        missing = [case_id for case_id in mapped if case_id not in required_case_ids]
        if missing:
            problems.append(f"acceptance-case-not-required:{ac_id}:{','.join(missing)}")
        covered[ac_id] = list(mapped)

    return {
        "schema": FLOOR_SCHEMA,
        "status": "PASS" if not problems else "BLOCKED",
        "bundle": str(bundle_path),
        "bundle_sha256": _sha256_file(bundle_path),
        "profile_id": campaign_profile.get("profile_id"),
        "acceptance_cases": len(acceptance_cases),
        "covered_acceptance_cases": len(covered),
        "required_campaign_cases": sorted(required_case_ids),
        "case_map": covered,
        "problems": problems,
    }
