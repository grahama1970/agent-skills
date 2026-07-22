"""Phase 7 sealed powered-trial protocol helpers for PCTOM-R2."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


SCHEMA_PREFIX = "persona_dream.research.prospective_tom"
PASS_STATUS = "PASS_PCTOM_POWERED_TRIAL_PROTOCOL"
BLOCKED_STATUS = "BLOCKED_PCTOM_POWERED_TRIAL_PROTOCOL"
PROTOCOL_STATUS = "SEALED_PCTOM_POWERED_TRIAL_PROTOCOL"
DEFAULT_PROTOCOL_PATH = Path("contracts/pctom-powered-trial-protocol.v1.json")
DEFAULT_CORPUS_PATH = Path("fixtures/phase6/compute_matched_corpora/pctom-compute-matched-corpus.v1.json")
ENDPOINT_CONDITIONS = ("M", "R", "D", "CD")
DETERMINISTIC_CORPUS_CONDITIONS = ("MEMORY", "FREE_CD", "STRUCTURED_CD", "FUNCTIONAL_TOM")
REQUIRED_ENDPOINTS = {
    "live_replication_runner": {
        "path": "scripts/run_live_tau_sealed_test_replication.py",
        "required_snippets": [
            'CONDITIONS = ("M", "R", "D", "CD")',
            'DEFAULT_SPLIT = "sealed_test"',
            "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION",
        ],
    },
    "live_condition_runner": {
        "path": "scripts/run_live_tau_condition_comparison.py",
        "required_snippets": [
            'CONDITIONS = ("M", "R", "D", "CD")',
            "SYSTEMIC_FAILURE_THRESHOLD = 3",
            "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
        ],
    },
    "live_action_selection_bridge": {
        "path": "scripts/run_live_tau_condition_action_selection.py",
        "required_snippets": [
            'CONDITIONS = ("M", "R", "D", "CD")',
            "ACTION_VOCABULARY",
            "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION",
        ],
    },
    "deterministic_statistical_preflight": {
        "path": "scripts/run_sealed_test_statistical_confidence.py",
        "required_snippets": [
            'CONDITIONS = ("M", "R", "D", "CD")',
            'PRIMARY_METRIC = "belief_brier"',
            'DEFAULT_SPLIT = "sealed_test"',
        ],
    },
    "live_fault_injection_surface": {
        "path": "scripts/run_live_fault_injection_surface.py",
        "required_snippets": [
            'CONDITIONS = {"M", "R", "D", "CD"}',
            "REQUIRED_FAULT_FAMILIES",
            "CONTINUED_WITH_UNKNOWN_STATE",
        ],
    },
}


def _endpoint_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for endpoint_id, spec in REQUIRED_ENDPOINTS.items():
        path = root / spec["path"]
        records.append(
            {
                "endpoint_id": endpoint_id,
                "path": spec["path"],
                "sha256": file_sha256(path) if path.exists() else "",
                "expected_conditions": list(ENDPOINT_CONDITIONS),
                "required_snippets": list(spec["required_snippets"]),
                "current_role": "protocol_bound_pre_execution_endpoint",
            }
        )
    return records


def build_protocol(root: Path, out: Path) -> dict[str, Any]:
    corpus_path = root / DEFAULT_CORPUS_PATH
    corpus_errors: list[str] = []
    corpus = load_json(corpus_path, corpus_errors, "compute_matched_corpus")
    corpus_counts = corpus.get("counts", {}) if isinstance(corpus, dict) else {}
    protocol = {
        "schema": f"{SCHEMA_PREFIX}.pctom_powered_trial_protocol.v1",
        "status": PROTOCOL_STATUS,
        "program": "PCTOM-R2",
        "protocol_id": "pctom-r2-powered-trial-endpoint-aligned-v1",
        "sealed_at": "2026-07-22T00:00:00Z",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "trial_execution_allowed": False,
        "powered_live_study_executed": False,
        "live_efficacy_claimed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "conditions": list(ENDPOINT_CONDITIONS),
        "deterministic_corpus_alignment": {
            "path": DEFAULT_CORPUS_PATH.as_posix(),
            "sha256": file_sha256(corpus_path) if corpus_path.exists() else "",
            "conditions": list(DETERMINISTIC_CORPUS_CONDITIONS),
            "rows": corpus_counts.get("rows"),
            "source_episodes": corpus_counts.get("episodes"),
            "endpoint_arm_mapping": {
                "MEMORY": "M",
                "FREE_CD": "D",
                "STRUCTURED_CD": "CD",
                "FUNCTIONAL_TOM": "diagnostic_not_current_live_endpoint_arm",
            },
            "functional_tom_live_endpoint_status": "EXPLICIT_PROTOCOL_EXTENSION_REQUIRED_BEFORE_POWERED_EXECUTION",
        },
        "endpoint_alignment": {
            "endpoint_condition_vocabulary": list(ENDPOINT_CONDITIONS),
            "endpoints": _endpoint_records(root),
            "live_execution_command_template": (
                "python3 scripts/run_live_tau_sealed_test_replication.py "
                "--output-root <run-root> --split sealed_test --episodes-per-family 16 "
                "--episode-limit 64 --timeout-s <bounded-timeout>"
            ),
            "deterministic_preflight_command_template": (
                "python3 scripts/run_sealed_test_statistical_confidence.py "
                "--output-root <run-root> --split sealed_test --episodes-per-family 16 "
                "--episode-limit 64 --bootstrap-samples 10000 --alpha 0.05"
            ),
            "fault_surface_command_template": (
                "python3 scripts/run_live_fault_injection_surface.py --root <sealed-test-run-root> "
                "--receipt-out <receipt>"
            ),
        },
        "powered_trial_design": {
            "split": "sealed_test",
            "episode_limit": 64,
            "episodes_per_family": 16,
            "conditions": list(ENDPOINT_CONDITIONS),
            "primary_metric": "belief_brier",
            "primary_hypothesis": "mean_belief_brier(CD) < mean_belief_brier(best_of_M_R_D)",
            "statistical_test": "paired_bootstrap_cd_minus_strongest_baseline",
            "alpha": 0.05,
            "bootstrap_samples": 10000,
            "secondary_metrics": [
                "action_brier",
                "planning_regret",
                "abstention_risk_coverage",
                "first_order_label_accuracy",
                "second_order_label_accuracy",
                "fault_containment_terminal_outcome",
            ],
            "minimum_execution_requirements_before_live_run": [
                "deterministic_statistical_preflight_receipt_pass",
                "live_memory_gate0_attribution_receipt_available",
                "tau_auth_and_model_endpoint_available",
                "three_case_systemic_failure_circuit_breaker_enabled",
                "receipt_discovery_zero_unrouted_after_dry_preflight",
                "functional_tom_endpoint_extension_either_implemented_or_excluded_from_primary_live_arms",
            ],
        },
        "pre_execution_gates": [
            {
                "gate_id": "seal_integrity",
                "required_status": "PASS_PCTOM_POWERED_TRIAL_PROTOCOL",
                "failure_status": "BLOCKED_PCTOM_POWERED_TRIAL_PROTOCOL",
            },
            {
                "gate_id": "deterministic_preflight",
                "required_status": "PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE",
                "failure_status": "BLOCKED_BEFORE_LIVE_TAU_EXECUTION",
            },
            {
                "gate_id": "live_endpoint_availability",
                "required_status": "PASS_LIVE_TAU_ENDPOINT_PREFLIGHT",
                "failure_status": "BLOCKED_BEFORE_SIDE_EFFECT",
            },
            {
                "gate_id": "fault_surface",
                "required_status": "PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE",
                "failure_status": "BLOCKED_OR_QUARANTINED_NO_ACTIVE_PARTIAL_STATE",
            },
        ],
        "forbidden_work": [
            "run_powered_live_efficacy_study_inside_protocol_seal",
            "claim_cd_prediction_or_planning_benefit_from_protocol_only",
            "use_human_or_llm_content_judgment",
            "perform_provider_video_voice_or_dashboard_work",
            "write_canonical_memory_identity_or_source_memory",
        ],
        "claims": {
            "proves": [
                "the future powered trial protocol is sealed as a local, non-executing artifact",
                "the protocol binds exact current PCTOM-R live endpoint scripts and their hashes",
                "the protocol preregisters the sealed-test split, primary metric, bootstrap method, and CD-vs-strongest-baseline hypothesis",
                "the protocol records the deterministic corpus to endpoint-arm mapping and explicitly gates functional-ToM live endpoint use",
            ],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "counterfactual-dream prediction benefit",
                "planning benefit",
                "provider execution",
                "semantic dream quality",
                "production Phase 01-16 execution",
            ],
        },
    }
    protocol["protocol_payload_sha256"] = stable_json_sha256(
        {key: value for key, value in protocol.items() if key != "protocol_payload_sha256"}
    )
    write_json(out, protocol)
    return protocol


def _protocol_errors(protocol: dict[str, Any], root: Path) -> tuple[list[str], dict[str, bool], dict[str, int]]:
    errors: list[str] = []
    checks: dict[str, bool] = {}
    counts: dict[str, int] = {
        "endpoint_records": 0,
        "endpoint_hash_mismatches": 0,
        "endpoint_snippet_misses": 0,
        "condition_mapping_missing": 0,
        "forbidden_side_effects": 0,
    }
    expected_scalars = {
        "schema": f"{SCHEMA_PREFIX}.pctom_powered_trial_protocol.v1",
        "status": PROTOCOL_STATUS,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "trial_execution_allowed": False,
        "powered_live_study_executed": False,
        "live_efficacy_claimed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, expected in expected_scalars.items():
        ok = protocol.get(key) == expected
        checks[f"{key}_matches"] = ok
        if not ok:
            errors.append(f"{key}_mismatch:{protocol.get(key)}:{expected}")
            if key.endswith("_attempts"):
                counts["forbidden_side_effects"] += 1
    if protocol.get("conditions") != list(ENDPOINT_CONDITIONS):
        errors.append(f"endpoint_conditions_mismatch:{protocol.get('conditions')}")
    checks["endpoint_conditions_match"] = protocol.get("conditions") == list(ENDPOINT_CONDITIONS)

    alignment = protocol.get("deterministic_corpus_alignment")
    if not isinstance(alignment, dict):
        errors.append("deterministic_corpus_alignment_missing")
        alignment = {}
    mapping = alignment.get("endpoint_arm_mapping") if isinstance(alignment.get("endpoint_arm_mapping"), dict) else {}
    for condition in DETERMINISTIC_CORPUS_CONDITIONS:
        if condition not in mapping:
            errors.append(f"condition_mapping_missing:{condition}")
            counts["condition_mapping_missing"] += 1
    if mapping.get("FUNCTIONAL_TOM") != "diagnostic_not_current_live_endpoint_arm":
        errors.append(f"functional_tom_mapping_not_gated:{mapping.get('FUNCTIONAL_TOM')}")
    corpus_path = root / str(alignment.get("path", ""))
    if not corpus_path.exists() or corpus_path.is_symlink():
        errors.append(f"corpus_missing_or_symlink:{corpus_path}")
    elif alignment.get("sha256") != file_sha256(corpus_path):
        errors.append("corpus_sha_mismatch")
    checks["corpus_hash_bound"] = corpus_path.exists() and alignment.get("sha256") == file_sha256(corpus_path)

    endpoints = protocol.get("endpoint_alignment", {}).get("endpoints") if isinstance(protocol.get("endpoint_alignment"), dict) else None
    if not isinstance(endpoints, list) or not endpoints:
        errors.append("endpoint_records_missing")
        endpoints = []
    counts["endpoint_records"] = len(endpoints)
    endpoint_by_id = {row.get("endpoint_id"): row for row in endpoints if isinstance(row, dict)}
    for endpoint_id, spec in REQUIRED_ENDPOINTS.items():
        row = endpoint_by_id.get(endpoint_id)
        if not isinstance(row, dict):
            errors.append(f"endpoint_missing:{endpoint_id}")
            continue
        path = root / spec["path"]
        if row.get("path") != spec["path"]:
            errors.append(f"endpoint_path_mismatch:{endpoint_id}:{row.get('path')}:{spec['path']}")
        if not path.exists() or path.is_symlink():
            errors.append(f"endpoint_file_missing_or_symlink:{endpoint_id}:{path}")
            continue
        actual_sha = file_sha256(path)
        if row.get("sha256") != actual_sha:
            errors.append(f"endpoint_hash_mismatch:{endpoint_id}")
            counts["endpoint_hash_mismatches"] += 1
        text = path.read_text(encoding="utf-8")
        for snippet in spec["required_snippets"]:
            if snippet not in text:
                errors.append(f"endpoint_required_snippet_missing:{endpoint_id}:{snippet}")
                counts["endpoint_snippet_misses"] += 1
    checks["endpoint_hashes_match"] = counts["endpoint_hash_mismatches"] == 0
    checks["endpoint_required_snippets_present"] = counts["endpoint_snippet_misses"] == 0

    design = protocol.get("powered_trial_design") if isinstance(protocol.get("powered_trial_design"), dict) else {}
    expected_design = {
        "split": "sealed_test",
        "episode_limit": 64,
        "episodes_per_family": 16,
        "primary_metric": "belief_brier",
        "alpha": 0.05,
        "bootstrap_samples": 10000,
    }
    for key, expected in expected_design.items():
        ok = design.get(key) == expected
        checks[f"design_{key}_matches"] = ok
        if not ok:
            errors.append(f"design_{key}_mismatch:{design.get(key)}:{expected}")
    if "CD" not in str(design.get("primary_hypothesis", "")) or "M_R_D" not in str(design.get("primary_hypothesis", "")):
        errors.append("primary_hypothesis_not_cd_vs_strongest_baseline")
    gates = protocol.get("pre_execution_gates")
    checks["pre_execution_gates_present"] = isinstance(gates, list) and len(gates) >= 4
    if not checks["pre_execution_gates_present"]:
        errors.append("pre_execution_gates_missing_or_insufficient")
    forbidden = protocol.get("forbidden_work")
    checks["forbidden_work_present"] = isinstance(forbidden, list) and len(forbidden) >= 5
    if not checks["forbidden_work_present"]:
        errors.append("forbidden_work_missing_or_insufficient")
    return errors, checks, counts


def negative_cases(protocol: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    mutated = copy.deepcopy(protocol)
    mutated["live_efficacy_claimed"] = True
    cases.append(("live-efficacy-claimed", BLOCKED_STATUS, mutated))
    mutated = copy.deepcopy(protocol)
    mutated["trial_execution_allowed"] = True
    cases.append(("trial-execution-allowed", BLOCKED_STATUS, mutated))
    mutated = copy.deepcopy(protocol)
    mutated["endpoint_alignment"]["endpoints"][0]["sha256"] = "sha256:" + "0" * 64
    cases.append(("endpoint-hash-mismatch", BLOCKED_STATUS, mutated))
    mutated = copy.deepcopy(protocol)
    del mutated["deterministic_corpus_alignment"]["endpoint_arm_mapping"]["STRUCTURED_CD"]
    cases.append(("condition-mapping-missing", BLOCKED_STATUS, mutated))
    mutated = copy.deepcopy(protocol)
    mutated["deterministic_corpus_alignment"]["endpoint_arm_mapping"]["FUNCTIONAL_TOM"] = "CD"
    cases.append(("functional-tom-promoted-to-current-live-arm", BLOCKED_STATUS, mutated))
    mutated = copy.deepcopy(protocol)
    mutated["human_content_judgment_required"] = True
    cases.append(("human-content-judgment-required", BLOCKED_STATUS, mutated))
    return cases


def audit_protocol(root: Path, protocol_path: Path, receipt_out: Path) -> dict[str, Any]:
    load_errors: list[str] = []
    protocol = load_json(protocol_path, load_errors, "powered_trial_protocol")
    protocol = protocol if isinstance(protocol, dict) else {}
    positive_errors, checks, counts = _protocol_errors(protocol, root)
    errors = load_errors + positive_errors
    negative_results: list[dict[str, Any]] = []
    for fixture, expected_status, mutated in negative_cases(protocol):
        mutation_errors, _, mutation_counts = _protocol_errors(mutated, root)
        observed_status = BLOCKED_STATUS if mutation_errors else PASS_STATUS
        negative_results.append(
            {
                "fixture": fixture,
                "expected_status": expected_status,
                "observed_status": observed_status,
                "blocked_as_expected": observed_status == expected_status,
                "counts": mutation_counts,
                "errors": mutation_errors,
            }
        )
    for result in negative_results:
        if not result["blocked_as_expected"]:
            errors.append(f"negative_fixture_not_blocked:{result['fixture']}")
    counts.update(
        {
            "negative_fixtures": len(negative_results),
            "negative_fixtures_blocked": sum(1 for result in negative_results if result["blocked_as_expected"]),
        }
    )
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_powered_trial_protocol_audit_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "trial_execution_allowed": False,
        "powered_live_study_executed": False,
        "live_efficacy_claimed": False,
        "protocol_path": rel(root, protocol_path),
        "protocol_sha256": file_sha256(protocol_path) if protocol_path.exists() else "",
        "counts": counts,
        "checks": checks,
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "the powered-trial protocol is sealed without executing the powered live efficacy study",
                "the protocol is bound to existing endpoint script paths, endpoint hashes, and M/R/D/CD condition vocabulary",
                "the protocol preregisters sealed_test, 64 episodes, belief_brier, alpha 0.05, 10000 bootstrap samples, and CD-vs-strongest-baseline comparison",
                "the protocol maps deterministic MEMORY, FREE_CD, STRUCTURED_CD, and FUNCTIONAL_TOM corpus rows to endpoint use while fail-closing functional-ToM live-arm promotion",
                "live-efficacy, execution-allowed, endpoint-hash, condition-mapping, functional-ToM-promotion, and human-judgment mutations fail closed",
            ]
            if status == PASS_STATUS
            else [
                "the powered-trial protocol audit failed closed before protocol acceptance",
            ],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "counterfactual-dream prediction benefit",
                "planning benefit",
                "provider execution",
                "semantic dream quality",
                "production Phase 01-16 execution",
            ],
        },
    }
    receipt["receipt_sha256"] = stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    write_json(receipt_out, receipt)
    return receipt
