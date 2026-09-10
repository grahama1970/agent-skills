"""Execution provenance and immutable oracle identity for eval evidence.

Fixtures enter as ordinary JSON, but evidence qualification needs a stricter
closed model: exploration, fixed replay, and test repair mean different things.
This module computes stable test/oracle hashes, validates closed mutation flags,
and decides whether an executed case may satisfy an existing evidence slot.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any


class ExecutionMode(StrEnum):
    EXPLORATION = "exploration"
    REGRESSION_REPLAY = "regression_replay"
    TEST_REPAIR = "test_repair"


MUTATION_FLAGS = frozenset(
    {
        "test_mutated",
        "locator_healed",
        "locator_changed",
        "step_changed",
        "assertion_changed",
        "fixture_input_changed",
        "exclusion_changed",
        "evidence_requirement_changed",
        "expected_output_changed",
        "oracle_changed",
        "fixture_changed",
        "case_ownership_changed",
        "category_map_changed",
        "proof_command_changed",
        "readiness_logic_changed",
        "test_exclusion_changed",
        "protected_surface_changed",
    }
)

TEST_MUTATION_FLAGS = frozenset(
    {"test_mutated", "locator_healed", "locator_changed", "step_changed", "fixture_input_changed"}
)
ORACLE_MUTATION_FLAGS = frozenset(
    {
        "assertion_changed",
        "exclusion_changed",
        "evidence_requirement_changed",
        "expected_output_changed",
        "oracle_changed",
        "test_exclusion_changed",
    }
)
PROTECTED_SURFACE_FLAGS = frozenset(
    {
        "assertion_changed",
        "exclusion_changed",
        "evidence_requirement_changed",
        "expected_output_changed",
        "oracle_changed",
        "fixture_changed",
        "case_ownership_changed",
        "category_map_changed",
        "proof_command_changed",
        "readiness_logic_changed",
        "test_exclusion_changed",
        "protected_surface_changed",
    }
)

TEST_HASH_EXCLUDE = frozenset(
    {
        "expected",
        "execution_mode",
        "generated_test",
        "generated_test_lineage",
        "provenance",
        "mutation_provenance",
        "repair",
        "external_result",
        "provider_result",
        "application_identity",
    }
)


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_source_hash(case: dict[str, Any]) -> str:
    """Hash the executable test source without the oracle or provenance wrapper."""
    source = {k: v for k, v in case.items() if k not in TEST_HASH_EXCLUDE}
    return _sha256_json(source)


def oracle_hash(case: dict[str, Any]) -> str:
    """Hash the expectation/oracle block that decides PASS/FAIL."""
    return _sha256_json(case.get("expected") or {})


def validate_manifest_provenance(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Validate closed mode and mutation vocabularies at fixture load time."""
    problems: list[str] = []
    for case in cases:
        name = case.get("name", "<unnamed>")
        mode = case.get("execution_mode", ExecutionMode.REGRESSION_REPLAY.value)
        if mode not in {m.value for m in ExecutionMode}:
            problems.append(
                f"case {name!r} execution_mode {mode!r} invalid; "
                f"valid: {[m.value for m in ExecutionMode]}"
            )
        for where, flags in _mutation_sources(case):
            if not isinstance(flags, dict):
                problems.append(f"case {name!r} {where} must be an object")
                continue
            unknown = sorted(set(flags) - MUTATION_FLAGS)
            if unknown:
                problems.append(f"case {name!r} {where} has unknown mutation flags: {unknown}")
            non_bool = sorted(k for k, v in flags.items() if k in MUTATION_FLAGS and not isinstance(v, bool))
            if non_bool:
                problems.append(f"case {name!r} {where} flags must be booleans: {non_bool}")
        for field in ("external_result", "provider_result"):
            if field in case and not isinstance(case[field], dict):
                problems.append(f"case {name!r} {field} must be an object")

    for claim in manifest.get("capability_claims") or []:
        records = claim.get("admitted_evidence") or claim.get("admitted_generations")
        if records is None:
            continue
        if not isinstance(records, list):
            problems.append(f"claim {claim.get('id')!r} admitted_evidence must be a list")
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                problems.append(f"claim {claim.get('id')!r} admitted_evidence[{index}] must be an object")
                continue
            if not any(record.get(k) for k in ("case", "generation_id", "test_source_sha256", "oracle_sha256")):
                problems.append(
                    f"claim {claim.get('id')!r} admitted_evidence[{index}] must pin a case, "
                    "generation_id, test_source_sha256, or oracle_sha256"
                )
    return problems


def case_provenance(
    manifest: dict[str, Any],
    case: dict[str, Any],
    *,
    fixture_sha256: str | None,
    repo: dict[str, Any],
) -> dict[str, Any]:
    """Build the report provenance block and its evidence-eligibility decision."""
    mode = ExecutionMode(case.get("execution_mode", ExecutionMode.REGRESSION_REPLAY.value))
    current_test_hash = test_source_hash(case)
    current_oracle_hash = oracle_hash(case)
    provenance = case.get("provenance") or {}
    repair = case.get("repair") or {}
    external = case.get("external_result") or case.get("provider_result") or {}
    flags = _merged_mutation_flags(case)

    prior_test_hash = (
        provenance.get("prior_test_source_sha256")
        or repair.get("prior_test_source_sha256")
        or external.get("prior_test_source_sha256")
    )
    prior_oracle_hash = (
        provenance.get("prior_oracle_sha256")
        or repair.get("prior_oracle_sha256")
        or external.get("prior_oracle_sha256")
    )
    external_test_hash = external.get("test_source_sha256")
    external_oracle_hash = external.get("oracle_sha256")
    test_hash_changed = _hash_changed(prior_test_hash, current_test_hash) or _hash_changed(
        external_test_hash, current_test_hash
    )
    oracle_hash_changed = _hash_changed(prior_oracle_hash, current_oracle_hash) or _hash_changed(
        external_oracle_hash, current_oracle_hash
    )

    declared_mutation = any(flags.values())
    errors: list[str] = []
    reasons: list[str] = []
    if mode == ExecutionMode.TEST_REPAIR and (not prior_test_hash or not prior_oracle_hash):
        errors.append("test_repair_requires_prior_test_and_oracle_hashes")
    if test_hash_changed and not any(flags[f] for f in TEST_MUTATION_FLAGS):
        errors.append("undeclared_test_mutation")
    if oracle_hash_changed and not any(flags[f] for f in ORACLE_MUTATION_FLAGS):
        errors.append("undeclared_oracle_mutation")
    if mode == ExecutionMode.REGRESSION_REPLAY and declared_mutation:
        reasons.append("regression_replay_declared_mutation_requires_test_repair")
    if mode == ExecutionMode.EXPLORATION:
        reasons.append("exploration_candidate_not_admitted")
    if mode == ExecutionMode.TEST_REPAIR:
        reasons.append("test_repair_candidate_requires_requalification")
    protected = any(flags[f] for f in PROTECTED_SURFACE_FLAGS)
    if protected:
        reasons.append("protected_surface_changed")
    if external.get("passed") is True or external.get("status") == "passed":
        if declared_mutation:
            reasons.append("external_pass_after_mutation_requires_requalification")

    changed = declared_mutation or test_hash_changed or oracle_hash_changed
    eligible = mode == ExecutionMode.REGRESSION_REPLAY and not changed and not errors and not protected
    if errors:
        reasons.extend(errors)
    if not eligible and not reasons:
        reasons.append("evidence_identity_not_admissible")

    generation_id = _generation_id(case, current_test_hash, current_oracle_hash)
    lineage = case.get("generated_test_lineage") or case.get("generated_test")
    return {
        "execution_mode": mode.value,
        "fixture_sha256": fixture_sha256,
        "test_source_sha256": current_test_hash,
        "oracle_sha256": current_oracle_hash,
        "generated_test_lineage": lineage,
        "generation_id": generation_id,
        "prior_test_source_sha256": prior_test_hash,
        "prior_oracle_sha256": prior_oracle_hash,
        "application_identity": case.get("application_identity")
        or manifest.get("application_identity")
        or {"repo": repo},
        "mutation_provenance": {
            "flags": flags,
            "declared": declared_mutation,
            "test_hash_changed": test_hash_changed,
            "oracle_hash_changed": oracle_hash_changed,
            "changed_between_failure_and_observed_pass": changed,
            "protected_surface_changed": protected,
            "external_result": {
                "provider": external.get("provider"),
                "status": external.get("status"),
                "passed": external.get("passed"),
                "test_source_sha256": external_test_hash,
                "oracle_sha256": external_oracle_hash,
            }
            if external
            else None,
        },
        "evidence_eligibility": {
            "eligible": eligible,
            "eligible_for_existing_claim": eligible,
            "requires_requalification": mode != ExecutionMode.REGRESSION_REPLAY or changed,
            "reason_codes": sorted(set(reasons)),
            "integrity_errors": sorted(set(errors)),
        },
    }


def _mutation_sources(case: dict[str, Any]) -> list[tuple[str, Any]]:
    sources: list[tuple[str, Any]] = []
    if "mutation_provenance" in case:
        sources.append(("mutation_provenance", case["mutation_provenance"]))
    provenance = case.get("provenance") or {}
    if "mutations" in provenance:
        sources.append(("provenance.mutations", provenance["mutations"]))
    for field in ("external_result", "provider_result"):
        external = case.get(field) or {}
        if "mutation_provenance" in external:
            sources.append((f"{field}.mutation_provenance", external["mutation_provenance"]))
        if "mutations" in external:
            sources.append((f"{field}.mutations", external["mutations"]))
    return sources


def _merged_mutation_flags(case: dict[str, Any]) -> dict[str, bool]:
    merged = {flag: False for flag in sorted(MUTATION_FLAGS)}
    for _where, flags in _mutation_sources(case):
        if not isinstance(flags, dict):
            continue
        for key, value in flags.items():
            if key in merged:
                merged[key] = bool(value) or merged[key]
    return merged


def _hash_changed(prior: Any, current: str) -> bool:
    return isinstance(prior, str) and bool(prior) and prior != current


def _generation_id(case: dict[str, Any], test_hash: str, oracle_hash_value: str) -> str:
    lineage = case.get("generated_test_lineage") or case.get("generated_test") or {}
    if isinstance(lineage, dict) and lineage.get("generation_id"):
        return str(lineage["generation_id"])
    return _sha256_json({"test_source_sha256": test_hash, "oracle_sha256": oracle_hash_value})[:32]
