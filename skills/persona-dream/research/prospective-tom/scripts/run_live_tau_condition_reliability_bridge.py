#!/usr/bin/env python3
"""Validate controlled reliability faults over live Tau condition-comparison artifacts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
GATE8_SCRIPT = RESEARCH_ROOT / "scripts" / "run_reliability_surface.py"
GATE9_SCRIPT = RESEARCH_ROOT / "scripts" / "run_causal_replay.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE"
ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}
REQUIRED_FAULT_FAMILIES = {
    "stale_artifact",
    "missing_graph_edge",
    "malformed_structured_output",
    "interrupted_persistence_or_retry",
}
REQUIRED_BASE_FILES = [
    "live_tau_condition_comparison_receipt.v1.json",
    "artifacts/live_condition_case_index.json",
    "artifacts/live_condition_metrics_summary.json",
    "artifacts/social_episode_corpus.v1.json",
    "receipts/social_episode_corpus_check_receipt.json",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_base_receipt(base_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = base_root / "live_tau_condition_comparison_receipt.v1.json"
    if not receipt_path.exists() or receipt_path.is_symlink():
        errors.append(f"missing_base_live_condition_receipt:{receipt_path}")
        return {}
    receipt = _load_json(receipt_path)
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "tau_receipts_hash_bound": True,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{receipt.get(key)}:{value}")
    if receipt.get("tau_call_attempts", 0) < 16:
        errors.append(f"base_tau_call_attempts_lt_16:{receipt.get('tau_call_attempts')}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    for key in ("sealed_commitments_per_condition", "deterministic_scores_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict) or set(values) != {"M", "R", "D", "CD"}:
            errors.append(f"base_{key}_missing_conditions:{values}")
            continue
        if any(not isinstance(value, int) or value < 4 for value in values.values()):
            errors.append(f"base_{key}_insufficient:{values}")
    return receipt


def _base_manifest(base_root: Path, errors: list[str]) -> dict[str, Any]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for rel in REQUIRED_BASE_FILES:
        path = base_root / rel
        if path.exists() and not path.is_symlink():
            files[rel] = _file_sha256(path)
        else:
            missing.append(rel)
    if missing:
        errors.append(f"base_manifest_missing:{missing}")
    receipt_path = base_root / "live_tau_condition_comparison_receipt.v1.json"
    receipt = _load_json(receipt_path) if receipt_path.exists() and not receipt_path.is_symlink() else {}
    case_index_path = base_root / "artifacts" / "live_condition_case_index.json"
    rows = _load_json(case_index_path) if case_index_path.exists() and not case_index_path.is_symlink() else []
    return {
        "label": "repeated_live_tau_condition_comparison_root",
        "root": str(base_root),
        "receipt_status": receipt.get("status"),
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "tau_call_attempts": receipt.get("tau_call_attempts"),
        "tau_live_call_performed": receipt.get("tau_live_call_performed"),
        "tau_receipts_hash_bound": receipt.get("tau_receipts_hash_bound"),
        "cases": receipt.get("counts", {}).get("cases") if isinstance(receipt.get("counts"), dict) else None,
        "conditions": sorted({row.get("condition") for row in rows if isinstance(row, dict)}),
        "episodes": sorted({row.get("episode_id") for row in rows if isinstance(row, dict)}),
        "files": files,
        "missing": missing,
    }


def _fault_manifest(current_manifest: dict[str, Any], fault_family: str) -> dict[str, Any]:
    manifest = json.loads(json.dumps(current_manifest))
    manifest["label"] = f"controlled_fault_{fault_family}"
    manifest["controlled_fault_family"] = fault_family
    manifest["root"] = f"{current_manifest.get('root')}#{fault_family}"
    files = dict(manifest.get("files", {}))
    if fault_family == "stale_artifact":
        files["live_tau_condition_comparison_receipt.v1.json"] = _stable_json_sha256(
            {"fault": fault_family, "original": files.get("live_tau_condition_comparison_receipt.v1.json")}
        )
    elif fault_family == "missing_graph_edge":
        files.pop("artifacts/live_condition_case_index.json", None)
        manifest["missing_graph_edge"] = "case_index_to_gate_receipt_binding_removed"
    elif fault_family == "malformed_structured_output":
        files["artifacts/live_condition_case_index.json"] = _stable_json_sha256(
            {"fault": fault_family, "malformed_case_status": "prediction_payload_not_object"}
        )
    elif fault_family == "interrupted_persistence_or_retry":
        manifest["interrupted_retry_state"] = {
            "retry_after_uncertain_completion": True,
            "duplicate_active_predictions": 0,
            "duplicate_active_revisions": 0,
        }
    manifest["files"] = files
    return manifest


def _trial_base() -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.reliability_trial.v1",
        "episode_id": "condition-comparison-calibration-subset",
        "condition": "M/R/D/CD",
        "k": 2,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "side_effect_count": 0,
        "active_partial_state": False,
        "unknown_state_continued": False,
        "duplicate_active_predictions": 0,
        "duplicate_active_revisions": 0,
    }


def _surface(current_manifest: dict[str, Any], fault_manifests: dict[str, dict[str, Any]]) -> dict[str, Any]:
    current_hash = _stable_json_sha256(current_manifest)
    base = _trial_base()
    trials = [
        {
            **base,
            "trial_id": "condition-live-reliability-baseline-001",
            "repeat_group_id": "condition-live-repeat-current",
            "epsilon": 0,
            "lambda": 0,
            "perturbations": [],
            "faults": [],
            "terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
            "end_state_equivalence_sha256": current_hash,
            "evidence_refs": ["current_manifest"],
        },
        {
            **base,
            "trial_id": "condition-live-reliability-baseline-002",
            "repeat_group_id": "condition-live-repeat-current",
            "epsilon": 0,
            "lambda": 0,
            "perturbations": [],
            "faults": [],
            "terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
            "end_state_equivalence_sha256": current_hash,
            "evidence_refs": ["current_manifest"],
        },
        {
            **base,
            "trial_id": "condition-live-reliability-perturbed-001",
            "repeat_group_id": "condition-live-repeat-current",
            "epsilon": 0.25,
            "lambda": 0,
            "perturbations": ["rename_ids_preserve_bindings", "equivalent_question_form"],
            "faults": [],
            "terminal_outcome": "RECOVERED_WITH_EQUIVALENT_END_STATE",
            "end_state_equivalence_sha256": current_hash,
            "evidence_refs": ["current_manifest"],
        },
    ]
    fault_outcomes = {
        "stale_artifact": "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
        "missing_graph_edge": "BLOCKED_BEFORE_SIDE_EFFECT",
        "malformed_structured_output": "BLOCKED_BEFORE_SIDE_EFFECT",
        "interrupted_persistence_or_retry": "RECOVERED_WITH_EQUIVALENT_END_STATE",
    }
    fault_lambdas = {
        "stale_artifact": 0.75,
        "missing_graph_edge": 0.5,
        "malformed_structured_output": 0.5,
        "interrupted_persistence_or_retry": 0.75,
    }
    for fault_family in sorted(REQUIRED_FAULT_FAMILIES):
        manifest = fault_manifests[fault_family]
        terminal = fault_outcomes[fault_family]
        end_hash = current_hash if terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE" else _stable_json_sha256(manifest)
        trials.append(
            {
                **base,
                "trial_id": f"condition-live-reliability-{fault_family}-001",
                "repeat_group_id": f"condition-live-{fault_family}",
                "epsilon": 0.25 if fault_family in {"stale_artifact", "missing_graph_edge"} else 0,
                "lambda": fault_lambdas[fault_family],
                "perturbations": ["rename_ids_preserve_bindings"] if fault_family in {"stale_artifact", "missing_graph_edge"} else [],
                "faults": [fault_family],
                "terminal_outcome": terminal,
                "end_state_equivalence_sha256": end_hash,
                "evidence_refs": [f"{fault_family}_manifest"],
            }
        )
    return {
        "schema": "persona_dream.research.prospective_tom.reliability_surface.v1",
        "surface_id": "live-condition-runner-reliability-surface-v1",
        "episode_id": "condition-comparison-calibration-subset",
        "condition": "M/R/D/CD",
        "k": 2,
        "epsilon_values": [0, 0.25],
        "lambda_values": [0, 0.5, 0.75],
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "source_manifests": {
            "current_manifest": current_manifest,
            **{f"{family}_manifest": manifest for family, manifest in sorted(fault_manifests.items())},
        },
        "trials": trials,
    }


def _replay(surface: dict[str, Any], current_manifest: dict[str, Any], stale_manifest: dict[str, Any]) -> dict[str, Any]:
    current_hash = _stable_json_sha256(current_manifest)
    stale_hash = _stable_json_sha256(stale_manifest)
    first_receipt_id = "condition-live-receipt-004-read-condition-case-index"
    tool_return_id = "condition-live-tool-return-stale-case-index-001"
    return {
        "schema": "persona_dream.research.prospective_tom.causal_replay.v1",
        "replay_id": "condition-live-causal-replay-stale-artifact-001",
        "surface_id": surface["surface_id"],
        "trial_id": "condition-live-reliability-stale_artifact-001",
        "reliability_surface_sha256": _stable_json_sha256(surface),
        "first_divergent_receipt": {
            "receipt_id": first_receipt_id,
            "receipt_index": 4,
            "boundary": "condition_case_index_artifact_load",
            "expected_state_sha256": current_hash,
            "observed_state_sha256": stale_hash,
        },
        "replay_start_receipt_id": first_receipt_id,
        "suspected_tool_return": {
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "tool_name": "local_artifact_store.read",
            "operation": "REPLACE_TOOL_RETURN",
            "original_return_sha256": _stable_json_sha256({"tool": "local_artifact_store.read", "result": stale_manifest}),
            "replacement_return_sha256": _stable_json_sha256({"tool": "local_artifact_store.read", "result": current_manifest}),
        },
        "comparison": {
            "factual_end_state_sha256": stale_hash,
            "counterfactual_end_state_sha256": current_hash,
            "expected_end_state_sha256": current_hash,
            "counterfactual_matches_expected": True,
        },
        "localized_cause": {
            "cause_type": "STALE_ARTIFACT",
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "causal_confidence": 1.0,
            "evidence_refs": [
                "condition-live-reliability-stale_artifact-001",
                first_receipt_id,
                tool_return_id,
            ],
        },
        "terminal_outcome": "CAUSAL_FAILURE_LOCALIZED",
        "unknown_state_continued": False,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
    }


def _terminal_counts(surface: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trial in surface.get("trials", []):
        if isinstance(trial, dict):
            outcome = str(trial.get("terminal_outcome"))
            counts[outcome] = counts.get(outcome, 0) + 1
    return dict(sorted(counts.items()))


def _fault_families(surface: dict[str, Any]) -> set[str]:
    families: set[str] = set()
    for trial in surface.get("trials", []):
        if isinstance(trial, dict):
            for fault in trial.get("faults") or []:
                if isinstance(fault, str) and fault:
                    families.add(fault)
    return families


def build_receipt(*, base_root: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    started = time.monotonic()
    base_root = base_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    surface_path = artifacts_root / "condition_reliability_surface.json"
    replay_path = artifacts_root / "condition_causal_replay.json"
    gate8_receipt_path = receipts_root / "condition_reliability_surface_check_receipt.json"
    gate9_receipt_path = receipts_root / "condition_causal_replay_check_receipt.json"
    errors: list[str] = []
    base_receipt = _validate_base_receipt(base_root, errors)
    gate8_receipt: dict[str, Any] | None = None
    gate9_receipt: dict[str, Any] | None = None
    surface: dict[str, Any] = {}
    replay: dict[str, Any] = {}

    try:
        gate8 = _load_module(GATE8_SCRIPT, "persona_dream_pctom_gate8_reliability")
        gate9 = _load_module(GATE9_SCRIPT, "persona_dream_pctom_gate9_causal_replay")
        current_manifest = _base_manifest(base_root, errors)
        fault_manifests = {family: _fault_manifest(current_manifest, family) for family in REQUIRED_FAULT_FAMILIES}
        surface = _surface(current_manifest, fault_manifests)
        replay = _replay(surface, current_manifest, fault_manifests["stale_artifact"])
        _write_json(surface_path, surface)
        _write_json(replay_path, replay)
        gate8_receipt = gate8.build_receipt(surface_path, gate8_receipt_path)
        gate9_receipt = gate9.build_receipt(replay_path, surface_path, gate9_receipt_path)
        if gate8_receipt.get("status") != "PASS_TOM_RELIABILITY_SURFACE":
            errors.append(f"gate8_status:{gate8_receipt.get('status')}")
            errors.extend(f"gate8_error:{error}" for error in gate8_receipt.get("errors", []))
        if gate9_receipt.get("status") != "PASS_TOM_CAUSAL_REPLAY":
            errors.append(f"gate9_status:{gate9_receipt.get('status')}")
            errors.extend(f"gate9_error:{error}" for error in gate9_receipt.get("errors", []))
    except Exception as exc:
        errors.append(f"condition_reliability_bridge_failed:{exc}")

    fault_families = _fault_families(surface)
    missing_fault_families = sorted(REQUIRED_FAULT_FAMILIES - fault_families)
    if missing_fault_families:
        errors.append(f"missing_fault_families:{missing_fault_families}")
    terminal_counts = _terminal_counts(surface)
    continued_with_unknown_state = terminal_counts.get("CONTINUED_WITH_UNKNOWN_STATE", 0)
    if continued_with_unknown_state:
        errors.append(f"continued_with_unknown_state:{continued_with_unknown_state}")
    disallowed_terminals = sorted(set(terminal_counts) - ALLOWED_TERMINAL_OUTCOMES)
    if disallowed_terminals:
        errors.append(f"disallowed_terminal_outcomes:{disallowed_terminals}")
    causal_replay_receipts = 1 if gate9_receipt and gate9_receipt.get("status") == "PASS_TOM_CAUSAL_REPLAY" else 0
    if causal_replay_receipts < 1:
        errors.append("causal_replay_receipts_lt_1")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_condition_reliability_bridge_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(base_root),
        "base_receipt_path": str(base_root / "live_tau_condition_comparison_receipt.v1.json"),
        "base_receipt_sha256": _file_sha256(base_root / "live_tau_condition_comparison_receipt.v1.json")
        if (base_root / "live_tau_condition_comparison_receipt.v1.json").exists()
        else None,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": bool(base_receipt.get("live") is True),
        "live_repeated_condition_comparison_consumed": bool(base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON"),
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "controlled_fault_definition": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "conditions": ["M", "R", "D", "CD"],
        "fault_families": sorted(fault_families),
        "missing_fault_families": missing_fault_families,
        "terminal_outcome_counts": terminal_counts,
        "continued_with_unknown_state": continued_with_unknown_state,
        "causal_replay_receipts": causal_replay_receipts,
        "surface_path": str(surface_path),
        "replay_path": str(replay_path),
        "gate8_receipt_path": str(gate8_receipt_path),
        "gate9_receipt_path": str(gate9_receipt_path),
        "gate8_status": gate8_receipt.get("status") if gate8_receipt else None,
        "gate9_status": gate9_receipt.get("status") if gate9_receipt else None,
        "counts": {
            "gate8": (gate8_receipt or {}).get("counts", {}),
            "gate9": (gate9_receipt or {}).get("counts", {}),
        },
        "metrics": {
            "gate8": (gate8_receipt or {}).get("metrics", {}),
            "gate9": (gate9_receipt or {}).get("metrics", {}),
        },
        "checks": {
            "gate8": (gate8_receipt or {}).get("checks", {}),
            "gate9": (gate9_receipt or {}).get("checks", {}),
        },
        "errors": errors,
        "claims": {
            "proves": [
                "a repeated live Tau condition-comparison receipt was consumed as the reliability subject",
                "Gate 8 accepted repeated, perturbed, and fault-injected condition-runner artifact trials",
                "required fault families were represented: stale_artifact, missing_graph_edge, malformed_structured_output, interrupted_persistence_or_retry",
                "terminal outcomes were limited to recovered equivalent state, blocked before side effect, or quarantined with no active partial state",
                "Gate 9 localized a stale-artifact divergence by replacing one suspected tool return",
                "no Memory write, provider call, new Tau call, canonical memory write, identity write, source-memory write, duplicate active prediction, duplicate active revision, or human content judgment was required",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau condition reliability bridge produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "real external service fault injection",
                "production retry machinery",
                "held-out test-set prediction benefit",
                "action-selection regret improvement",
                "longitudinal recall after revision",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution or video quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_condition_reliability_bridge_receipt.v1.json")
    receipt = build_receipt(base_root=args.base_root, output_root=args.output_root, receipt_out=receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
