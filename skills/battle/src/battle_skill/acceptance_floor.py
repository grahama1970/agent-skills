"""Acceptance-contract floor enforcement for Battle campaign arenas.

Battle may add fuzz and beyond-contract cases, but the frozen client contract is
non-optional for enrolled projects: every acceptance case must map to at least
one generator case retained in the campaign profile's required_case_ids. The
project enrollment record, not a campaign request flag, decides whether that
contract floor is required and which bundle digest is approved.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from .strict_json import finite_json_values, load_path

FLOOR_SCHEMA = "battle.acceptance_floor_receipt.v1"
BUNDLE_SCHEMA = "acceptance_contract.bundle.v1"
PROFILE_SCHEMA = "battle.campaign_profile.v1"
ENROLLMENT_SCHEMA = "battle.project_contract_enrollment.v1"


def _load_json(path: Path) -> dict[str, Any]:
    data = load_path(path)
    if not isinstance(data, dict):
        raise ValueError("JSON document must be an object")
    return data


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _blocked_enrollment(path: str | Path | None, problems: list[str]) -> dict[str, Any]:
    return {
        "schema": ENROLLMENT_SCHEMA + ".receipt",
        "status": "BLOCKED",
        "path": str(path) if path else None,
        "acceptance_contract_required": None,
        "approved_bundle_sha256": None,
        "bundle_path": None,
        "problems": problems,
    }


def validate_project_contract_enrollment(
    enrollment_path: str | Path | None,
    *,
    expected_target: str,
) -> dict[str, Any]:
    """Read the trusted project enrollment record that controls floor admission."""
    if not enrollment_path:
        return _blocked_enrollment(enrollment_path, ["project-enrollment-missing"])
    path = Path(enrollment_path)
    try:
        enrollment = _load_json(path)
    except (OSError, ValueError) as exc:
        return _blocked_enrollment(path, [f"project-enrollment-unreadable:{exc}"])

    problems: list[str] = []
    extra = sorted(set(enrollment) - {"schema", "target_identity", "acceptance_contract"})
    if extra:
        problems.append(f"project-enrollment-extra-fields:{','.join(extra)}")
    if not finite_json_values(enrollment):
        problems.append("project-enrollment-non-finite-number")
    if enrollment.get("schema") != ENROLLMENT_SCHEMA:
        problems.append(f"project-enrollment-schema:{enrollment.get('schema')!r}")
    if enrollment.get("target_identity") != expected_target:
        problems.append("project-enrollment-target-mismatch")

    contract = enrollment.get("acceptance_contract")
    if not isinstance(contract, dict):
        problems.append("acceptance-contract-enrollment-missing")
        contract = {}
    contract_extra = sorted(set(contract) - {"required", "bundle_path", "sha256"})
    if contract_extra:
        problems.append(f"acceptance-contract-enrollment-extra-fields:{','.join(contract_extra)}")
    required = contract.get("required")
    if required not in {True, False}:
        problems.append("acceptance-contract-required-not-boolean")
        required = None

    bundle_path = contract.get("bundle_path")
    approved_digest = contract.get("sha256")
    if required is True:
        if not bundle_path:
            problems.append("acceptance-contract-bundle-path-missing")
        if not approved_digest:
            problems.append("acceptance-contract-approved-digest-missing")
        if bundle_path and approved_digest:
            bundle = Path(bundle_path)
            if not bundle.is_absolute():
                bundle = path.parent / bundle
            try:
                actual = _sha256_file(bundle)
            except OSError as exc:
                problems.append(f"acceptance-contract-bundle-unreadable:{exc}")
            else:
                if actual != approved_digest:
                    problems.append("acceptance-contract-bundle-digest-mismatch")
    elif required is False and (bundle_path or approved_digest):
        problems.append("acceptance-contract-disabled-with-bundle-fields")

    return {
        "schema": ENROLLMENT_SCHEMA + ".receipt",
        "status": "PASS" if not problems else "BLOCKED",
        "path": str(path),
        "acceptance_contract_required": required,
        "approved_bundle_sha256": approved_digest,
        "bundle_path": str((path.parent / bundle_path).resolve()) if bundle_path and not Path(bundle_path).is_absolute() else bundle_path,
        "problems": problems,
    }


def retain_approved_bundle(
    *,
    enrollment_receipt: dict[str, Any],
    retained_path: Path,
) -> dict[str, Any]:
    """Copy the approved bundle bytes into the campaign work area and verify them."""
    source = enrollment_receipt.get("bundle_path")
    approved = enrollment_receipt.get("approved_bundle_sha256")
    if not source or not approved:
        return {"status": "BLOCKED", "path": None, "sha256": None, "problems": ["approved-bundle-missing"]}
    retained_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(source, retained_path)
        digest = _sha256_file(retained_path)
    except OSError as exc:
        return {"status": "BLOCKED", "path": str(retained_path), "sha256": None, "problems": [f"approved-bundle-retain-failed:{exc}"]}
    problems = [] if digest == approved else ["approved-bundle-retained-digest-mismatch"]
    return {
        "status": "PASS" if not problems else "BLOCKED",
        "path": str(retained_path),
        "sha256": digest,
        "problems": problems,
    }


def validate_acceptance_floor(
    *,
    bundle_path: str | Path,
    campaign_profile: dict[str, Any],
    case_map: dict[str, Any] | None,
    approved_bundle_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a fail-closed receipt proving the contract floor is in the arena."""
    problems: list[str] = []
    if not bundle_path:
        return {
            "schema": FLOOR_SCHEMA,
            "status": "BLOCKED",
            "bundle": None,
            "bundle_sha256": None,
            "approved_bundle_sha256": approved_bundle_sha256,
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
    except (OSError, ValueError) as exc:
        return {
            "schema": FLOOR_SCHEMA,
            "status": "BLOCKED",
            "bundle": str(bundle_path),
            "bundle_sha256": None,
            "approved_bundle_sha256": approved_bundle_sha256,
            "profile_id": campaign_profile.get("profile_id"),
            "acceptance_cases": 0,
            "covered_acceptance_cases": 0,
            "required_campaign_cases": sorted(campaign_profile.get("required_case_ids") or []),
            "case_map": {},
            "problems": [f"bundle-unreadable:{exc}"],
        }

    bundle_sha256 = _sha256_file(bundle_path)
    if approved_bundle_sha256 and bundle_sha256 != approved_bundle_sha256:
        problems.append("bundle-digest-not-approved")
    bundle_allowed = {"schema", "project_name", "source", "requirements", "acceptance_cases", "open_questions", "immutable_goal", "non_claims"}
    bundle_extra = sorted(set(bundle) - bundle_allowed)
    if bundle_extra:
        problems.append(f"bundle-extra-fields:{','.join(bundle_extra)}")
    if not finite_json_values(bundle):
        problems.append("bundle-non-finite-number")
    if bundle.get("schema") != BUNDLE_SCHEMA:
        problems.append(f"bundle-schema:{bundle.get('schema')!r}")
    if campaign_profile.get("schema") != PROFILE_SCHEMA:
        problems.append(f"profile-schema:{campaign_profile.get('schema')!r}")

    open_questions = bundle.get("open_questions") or []
    if not isinstance(open_questions, list):
        problems.append("bundle-open-questions-not-list")
        open_questions = []
    elif open_questions:
        problems.append("bundle-open-questions")

    acceptance_cases = bundle.get("acceptance_cases") or []
    if not isinstance(acceptance_cases, list):
        problems.append("acceptance-cases-not-list")
        acceptance_cases = []
    if not acceptance_cases:
        problems.append("bundle-has-no-acceptance-cases")

    required_case_ids = set(campaign_profile.get("required_case_ids") or [])
    if not isinstance(case_map, dict):
        problems.append("case-map-not-object")
        case_map = {}
    else:
        case_map = case_map or {}
    covered: dict[str, list[str]] = {}
    seen_acceptance_ids: set[str] = set()
    for case in acceptance_cases:
        if not isinstance(case, dict):
            problems.append("acceptance-case-not-object")
            continue
        ac_extra = sorted(set(case) - {"id", "requirement_id", "kind", "predicate", "deterministic_check", "proof_artifacts", "source_path", "source_line", "evidence_text"})
        if ac_extra:
            problems.append(f"acceptance-case-extra-fields:{case.get('id')}:{','.join(ac_extra)}")
        ac_id = case.get("id")
        if not isinstance(ac_id, str) or not ac_id.strip():
            problems.append("acceptance-case-id-invalid")
            continue
        if ac_id in seen_acceptance_ids:
            problems.append(f"acceptance-case-duplicate:{ac_id}")
            continue
        seen_acceptance_ids.add(ac_id)
        mapped = case_map.get(ac_id)
        if not mapped:
            problems.append(f"acceptance-case-unmapped:{ac_id}")
            continue
        if not isinstance(mapped, dict):
            problems.append(f"acceptance-case-map-invalid:{ac_id}")
            continue
        mapped_extra = sorted(set(mapped) - {"case_ids", "assertion", "evidence_extractors"})
        if mapped_extra:
            problems.append(f"acceptance-case-map-extra-fields:{ac_id}:{','.join(mapped_extra)}")
        case_ids = mapped.get("case_ids")
        assertion = mapped.get("assertion")
        extractors = mapped.get("evidence_extractors")
        if (not isinstance(case_ids, list) or not case_ids
                or not all(isinstance(item, str) and item.strip() for item in case_ids)
                or len(set(case_ids)) != len(case_ids)):
            problems.append(f"acceptance-case-map-invalid:{ac_id}")
            continue
        if not isinstance(assertion, str) or not assertion.strip():
            problems.append(f"acceptance-case-assertion-missing:{ac_id}")
        if (not isinstance(extractors, list) or not extractors
                or not all(isinstance(item, str) and item.strip() for item in extractors)):
            problems.append(f"acceptance-case-evidence-extractors-missing:{ac_id}")
        missing = [case_id for case_id in case_ids if case_id not in required_case_ids]
        if missing:
            problems.append(f"acceptance-case-not-required:{ac_id}:{','.join(missing)}")
        covered[ac_id] = {"case_ids": list(case_ids), "assertion": assertion, "evidence_extractors": list(extractors or [])}

    return {
        "schema": FLOOR_SCHEMA,
        "status": "PASS" if not problems else "BLOCKED",
        "bundle": str(bundle_path),
        "bundle_sha256": bundle_sha256,
        "approved_bundle_sha256": approved_bundle_sha256,
        "profile_id": campaign_profile.get("profile_id"),
        "acceptance_cases": len(acceptance_cases),
        "covered_acceptance_cases": len(covered),
        "required_campaign_cases": sorted(required_case_ids),
        "case_map": covered,
        "problems": problems,
    }


def validate_executed_acceptance_floor(
    *,
    floor_receipt: dict[str, Any],
    campaign_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Require retained passing predicate evidence for every acceptance mapping."""
    problems: list[str] = []
    case_results = {item.get("case"): item for item in campaign_receipt.get("case_results") or [] if isinstance(item, dict)}
    evidence: dict[str, Any] = {}
    for ac_id, mapping in (floor_receipt.get("case_map") or {}).items():
        assertions = []
        for case_id in mapping.get("case_ids", []):
            result = case_results.get(case_id)
            if not result:
                problems.append(f"acceptance-case-not-executed:{ac_id}:{case_id}")
                continue
            if result.get("passed") is not True:
                problems.append(f"acceptance-case-not-passing:{ac_id}:{case_id}")
                continue
            assertions.append({
                "case_id": case_id,
                "assertion": mapping.get("assertion"),
                "evidence_extractors": mapping.get("evidence_extractors") or [],
                "execution": result.get("execution"),
                "functional": result.get("functional"),
                "violations": result.get("violations", []),
            })
        evidence[ac_id] = assertions
        if len(assertions) != len(mapping.get("case_ids", [])):
            problems.append(f"acceptance-case-evidence-incomplete:{ac_id}")
    plan = campaign_receipt.get("plan") or {}
    binding = {
        "target_run_cmd_sha256": "sha256:" + hashlib.sha256(str((campaign_receipt.get("request") or {}).get("target_run_cmd", "")).encode()).hexdigest(),
        "bundle_sha256": floor_receipt.get("bundle_sha256"),
        "profile_sha256": plan.get("profile_sha256"),
        "lock_sha256": plan.get("lock_sha256"),
        "evaluator_lock_receipt_sha256": "sha256:" + hashlib.sha256(repr((campaign_receipt.get("request") or {}).get("evaluator_lock_receipt")).encode()).hexdigest(),
        "floor_receipt_sha256": "sha256:" + hashlib.sha256(repr(floor_receipt).encode()).hexdigest(),
    }
    if floor_receipt.get("status") != "PASS":
        problems.append("acceptance-floor-not-passing")
    if campaign_receipt.get("verdict") != "PASS":
        problems.append("campaign-not-passing")
    return {
        "schema": "battle.executed_acceptance_floor_receipt.v1",
        "status": "PASS" if not problems else "BLOCKED",
        "binding": binding,
        "acceptance_evidence": evidence,
        "problems": problems,
    }
