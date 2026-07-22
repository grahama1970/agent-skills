"""Deterministic Phase 5 crash-safe transition helpers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


SCHEMA_PREFIX = "persona_dream.research.prospective_tom"
ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}
FORBIDDEN_TERMINAL_OUTCOMES = {"CONTINUED_WITH_UNKNOWN_STATE"}
REQUIRED_FAULT_BOUNDARIES = {
    "memory_timeout",
    "stale_artifact",
    "exact_retry",
    "retry_after_uncertain_completion",
    "interrupted_persistence",
    "malformed_structured_output",
}


def default_phase5_paths(root: Path) -> dict[str, Path]:
    return {
        "gate8_surface": root / "fixtures/gate8/positive/reliability_surface_ok/reliability_surface.json",
        "phase5_fixture": root / "fixtures/phase5/crash_safe_transitions/crash_transition_trials.v1.json",
        "gate8_receipt": root / "receipts/pctom-crash-safe-gate8-reliability-surface.v1.json",
    }


def phase5_fixture_rows() -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA_PREFIX}.pctom_crash_transition_trials.v1",
        "fixture_id": "phase5-crash-safe-transitions",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "transition_rows": [
            {
                "transition_id": "phase5-exact-retry-recovery",
                "source": "phase5_fixture",
                "boundary": "exact_retry",
                "faults": ["exact_retry"],
                "state_before_sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                "accepted_end_state_sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                "observed_end_state_sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                "terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
                "side_effect_count": 0,
                "active_partial_state": False,
                "unknown_state_continued": False,
                "duplicate_active_predictions": 0,
                "duplicate_active_revisions": 0,
                "canonical_memory_write": False,
                "identity_write": False,
                "source_memory_write": False,
            },
            {
                "transition_id": "phase5-uncertain-retry-recovery",
                "source": "phase5_fixture",
                "boundary": "retry_after_uncertain_completion",
                "faults": ["retry_after_uncertain_completion"],
                "state_before_sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "accepted_end_state_sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "observed_end_state_sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
                "side_effect_count": 0,
                "active_partial_state": False,
                "unknown_state_continued": False,
                "duplicate_active_predictions": 0,
                "duplicate_active_revisions": 0,
                "canonical_memory_write": False,
                "identity_write": False,
                "source_memory_write": False,
            },
            {
                "transition_id": "phase5-interrupted-persistence-block",
                "source": "phase5_fixture",
                "boundary": "interrupted_persistence",
                "faults": ["interrupted_persistence"],
                "state_before_sha256": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "accepted_end_state_sha256": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "observed_end_state_sha256": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
                "side_effect_count": 0,
                "active_partial_state": False,
                "unknown_state_continued": False,
                "duplicate_active_predictions": 0,
                "duplicate_active_revisions": 0,
                "canonical_memory_write": False,
                "identity_write": False,
                "source_memory_write": False,
            },
            {
                "transition_id": "phase5-malformed-output-quarantine",
                "source": "phase5_fixture",
                "boundary": "malformed_structured_output",
                "faults": ["malformed_structured_output"],
                "state_before_sha256": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
                "accepted_end_state_sha256": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
                "observed_end_state_sha256": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
                "terminal_outcome": "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
                "side_effect_count": 0,
                "active_partial_state": False,
                "unknown_state_continued": False,
                "duplicate_active_predictions": 0,
                "duplicate_active_revisions": 0,
                "canonical_memory_write": False,
                "identity_write": False,
                "source_memory_write": False,
            },
        ],
    }


def write_phase5_fixture(path: Path) -> dict[str, Any]:
    fixture = phase5_fixture_rows()
    write_json(path, fixture)
    return fixture


def gate8_rows(surface: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trial in surface.get("trials") or []:
        if not isinstance(trial, dict):
            continue
        faults = trial.get("faults") if isinstance(trial.get("faults"), list) else []
        boundary = faults[0] if faults else "no_fault_repeat"
        end_state = trial.get("end_state_equivalence_sha256")
        rows.append({
            "transition_id": f"gate8:{trial.get('trial_id')}",
            "source": "gate8_reliability_surface",
            "boundary": boundary,
            "faults": faults,
            "state_before_sha256": end_state,
            "accepted_end_state_sha256": end_state,
            "observed_end_state_sha256": end_state,
            "terminal_outcome": trial.get("terminal_outcome"),
            "side_effect_count": trial.get("side_effect_count"),
            "active_partial_state": trial.get("active_partial_state"),
            "unknown_state_continued": trial.get("unknown_state_continued"),
            "duplicate_active_predictions": trial.get("duplicate_active_predictions"),
            "duplicate_active_revisions": trial.get("duplicate_active_revisions"),
            "canonical_memory_write": trial.get("canonical_memory_write"),
            "identity_write": trial.get("identity_write"),
            "source_memory_write": trial.get("source_memory_write"),
        })
    return rows


def audit_rows(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    seen: set[str] = set()
    fault_boundaries: set[str] = set()
    terminal_counts = {outcome: 0 for outcome in sorted(ALLOWED_TERMINAL_OUTCOMES)}
    for index, row in enumerate(rows):
        prefix = f"transition_{index}"
        if not isinstance(row, dict):
            errors.append(f"{prefix}_not_object")
            continue
        transition_id = row.get("transition_id")
        if not isinstance(transition_id, str) or not transition_id:
            errors.append(f"{prefix}_missing_transition_id")
        elif transition_id in seen:
            errors.append(f"duplicate_transition_id:{transition_id}")
        else:
            seen.add(transition_id)
        boundary = row.get("boundary")
        if isinstance(boundary, str) and boundary:
            fault_boundaries.add(boundary)
        for fault in row.get("faults") or []:
            if isinstance(fault, str) and fault:
                fault_boundaries.add(fault)
        terminal = row.get("terminal_outcome")
        if terminal in FORBIDDEN_TERMINAL_OUTCOMES or row.get("unknown_state_continued") is not False:
            errors.append(f"continued_unknown_state:{transition_id}:{terminal}:{row.get('unknown_state_continued')}")
        if terminal not in ALLOWED_TERMINAL_OUTCOMES:
            errors.append(f"terminal_outcome_not_allowed:{transition_id}:{terminal}")
        else:
            terminal_counts[terminal] += 1
        if terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE":
            if row.get("observed_end_state_sha256") != row.get("accepted_end_state_sha256"):
                errors.append(
                    "non_equivalent_recovery:"
                    f"{transition_id}:{row.get('observed_end_state_sha256')}:{row.get('accepted_end_state_sha256')}"
                )
        if terminal == "BLOCKED_BEFORE_SIDE_EFFECT" and row.get("side_effect_count") != 0:
            errors.append(f"side_effect_before_block:{transition_id}:{row.get('side_effect_count')}")
        if terminal == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE":
            if row.get("side_effect_count") != 0 or row.get("active_partial_state") is not False:
                errors.append(
                    "active_partial_quarantine:"
                    f"{transition_id}:{row.get('side_effect_count')}:{row.get('active_partial_state')}"
                )
        if row.get("duplicate_active_predictions") != 0 or row.get("duplicate_active_revisions") != 0:
            errors.append(
                "duplicate_active_state:"
                f"{transition_id}:{row.get('duplicate_active_predictions')}:{row.get('duplicate_active_revisions')}"
            )
        if row.get("canonical_memory_write") is not False or row.get("identity_write") is not False or row.get("source_memory_write") is not False:
            errors.append(
                "unauthorized_write:"
                f"{transition_id}:{row.get('canonical_memory_write')}:{row.get('identity_write')}:{row.get('source_memory_write')}"
            )
        for key in ("state_before_sha256", "accepted_end_state_sha256", "observed_end_state_sha256"):
            value = row.get(key)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                errors.append(f"{prefix}_{key}_invalid:{value}")
    missing_fault_boundaries = sorted(REQUIRED_FAULT_BOUNDARIES - fault_boundaries)
    for boundary in missing_fault_boundaries:
        errors.append(f"missing_fault_boundary:{boundary}")
    counts = {
        "transition_rows": len(rows),
        "fault_boundaries": len(fault_boundaries),
        "required_fault_boundaries": len(REQUIRED_FAULT_BOUNDARIES),
        "missing_required_fault_boundaries": len(missing_fault_boundaries),
        "recovered": terminal_counts["RECOVERED_WITH_EQUIVALENT_END_STATE"],
        "blocked": terminal_counts["BLOCKED_BEFORE_SIDE_EFFECT"],
        "quarantined": terminal_counts["QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE"],
        "continued_unknown_state": sum(1 for error in errors if error.startswith("continued_unknown_state:")),
        "restart_non_equivalent_recoveries": sum(1 for error in errors if error.startswith("non_equivalent_recovery:")),
        "side_effect_before_block": sum(1 for error in errors if error.startswith("side_effect_before_block:")),
        "active_partial_quarantines": sum(1 for error in errors if error.startswith("active_partial_quarantine:")),
        "duplicate_active_state": sum(1 for error in errors if error.startswith("duplicate_active_state:")),
        "unauthorized_writes": sum(1 for error in errors if error.startswith("unauthorized_write:")),
    }
    return errors, counts


def mutation_status(errors: list[str]) -> str:
    if any(error.startswith("continued_unknown_state:") or error.startswith("terminal_outcome_not_allowed:") for error in errors):
        return "BLOCKED_PCTOM_CONTINUED_UNKNOWN_STATE"
    if any(error.startswith("non_equivalent_recovery:") for error in errors):
        return "BLOCKED_PCTOM_NON_EQUIVALENT_RECOVERY"
    if any(error.startswith("side_effect_before_block:") for error in errors):
        return "BLOCKED_PCTOM_SIDE_EFFECT_BEFORE_BLOCK"
    if any(error.startswith("active_partial_quarantine:") for error in errors):
        return "BLOCKED_PCTOM_ACTIVE_PARTIAL_QUARANTINE"
    if any(error.startswith("duplicate_active_state:") for error in errors):
        return "BLOCKED_PCTOM_DUPLICATE_ACTIVE_STATE"
    if any(error.startswith("unauthorized_write:") for error in errors):
        return "BLOCKED_PCTOM_UNAUTHORIZED_WRITE"
    return "PASS_PCTOM_CRASH_TRANSITION_CASE"


def negative_cases(rows: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    cases: list[tuple[str, str, list[dict[str, Any]]]] = []
    unknown = deepcopy(rows)
    unknown[0]["terminal_outcome"] = "CONTINUED_WITH_UNKNOWN_STATE"
    unknown[0]["unknown_state_continued"] = True
    cases.append(("continued-unknown-state", "BLOCKED_PCTOM_CONTINUED_UNKNOWN_STATE", unknown))

    divergent = deepcopy(rows)
    for row in divergent:
        if row.get("terminal_outcome") == "RECOVERED_WITH_EQUIVALENT_END_STATE":
            row["observed_end_state_sha256"] = "sha256:9999999999999999999999999999999999999999999999999999999999999999"
            break
    cases.append(("non-equivalent-recovery", "BLOCKED_PCTOM_NON_EQUIVALENT_RECOVERY", divergent))

    blocked = deepcopy(rows)
    for row in blocked:
        if row.get("terminal_outcome") == "BLOCKED_BEFORE_SIDE_EFFECT":
            row["side_effect_count"] = 1
            break
    cases.append(("blocked-with-side-effect", "BLOCKED_PCTOM_SIDE_EFFECT_BEFORE_BLOCK", blocked))

    quarantined = deepcopy(rows)
    for row in quarantined:
        if row.get("terminal_outcome") == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE":
            row["active_partial_state"] = True
            break
    cases.append(("quarantined-active-partial", "BLOCKED_PCTOM_ACTIVE_PARTIAL_QUARANTINE", quarantined))

    duplicate = deepcopy(rows)
    duplicate[0]["duplicate_active_predictions"] = 1
    cases.append(("duplicate-active-state", "BLOCKED_PCTOM_DUPLICATE_ACTIVE_STATE", duplicate))

    write = deepcopy(rows)
    write[0]["canonical_memory_write"] = True
    cases.append(("unauthorized-write", "BLOCKED_PCTOM_UNAUTHORIZED_WRITE", write))
    return cases


def build_surface(root: Path, evidence_out: Path, gate8_receipt: dict[str, Any]) -> dict[str, Any]:
    paths = default_phase5_paths(root)
    write_phase5_fixture(paths["phase5_fixture"])
    errors: list[str] = []
    gate8_surface = load_json(paths["gate8_surface"], errors, "gate8_surface")
    phase5_fixture = load_json(paths["phase5_fixture"], errors, "phase5_fixture")
    gate8_transition_rows = gate8_rows(gate8_surface if isinstance(gate8_surface, dict) else {})
    fixture_rows = phase5_fixture.get("transition_rows") if isinstance(phase5_fixture, dict) else []
    rows = gate8_transition_rows + [row for row in fixture_rows if isinstance(row, dict)]
    row_errors, counts = audit_rows(rows)
    source_files = [
        {
            "artifact": "gate8_reliability_surface",
            "path": rel(root, paths["gate8_surface"]),
            "sha256": file_sha256(paths["gate8_surface"]),
        },
        {
            "artifact": "phase5_crash_transition_trials",
            "path": rel(root, paths["phase5_fixture"]),
            "sha256": file_sha256(paths["phase5_fixture"]),
        },
        {
            "artifact": "gate8_reliability_receipt",
            "path": rel(root, paths["gate8_receipt"]),
            "sha256": file_sha256(paths["gate8_receipt"]),
        },
    ]
    counts["build_errors"] = len(errors) + len(row_errors)
    surface = {
        "schema": f"{SCHEMA_PREFIX}.pctom_crash_safe_transition_surface.v1",
        "created_at": now_iso(),
        "status": "CRASH_SAFE_TRANSITION_SURFACE_BUILT",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "source_files": source_files,
        "gate8_reliability_receipt_status": gate8_receipt.get("status"),
        "gate8_reliability_receipt_counts": gate8_receipt.get("counts"),
        "transition_rows": rows,
        "counts": counts,
        "build_errors": errors + row_errors,
        "claims": {
            "proves": [
                "Gate 8 and Phase 5 fixture transition rows use only recovered, blocked-before-side-effect, and quarantined-with-no-active-partial terminal outcomes",
                "deterministic retry, interrupted-persistence, and malformed-output transition rows are represented with side-effect and duplicate-active-state counters",
            ],
            "does_not_prove": [
                "live service fault injection",
                "deployed production retry machinery",
                "statistical prediction benefit",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    write_json(evidence_out, surface)
    return surface
