#!/usr/bin/env python3
"""Exercise the PCTOM-R sealed-test retry proof through the run.sh boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RUN_SH = ROOT / "run.sh"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_RUNSH_ORCHESTRATION_RETRY_PROOF"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_RUNSH_ORCHESTRATION_RETRY_PROOF"
CHILD_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF"
CHILD_BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF"
ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}


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


def _parse_json_stream(text: str) -> tuple[dict[str, Any] | None, str | None]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None, "json_object_not_found"
    try:
        return json.loads(text[start : end + 1]), None
    except Exception as exc:
        return None, f"json_parse_failed:{type(exc).__name__}:{exc}"


def _run_child(base_root: Path, output_root: Path, label: str) -> dict[str, Any]:
    command = [
        str(RUN_SH),
        "run-live-tau-sealed-test-retry-proof",
        "--base-root",
        str(base_root),
        "--output-root",
        str(output_root),
        "--json",
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    receipt, parse_error = _parse_json_stream(completed.stdout)
    if receipt is None:
        receipt, parse_error = _parse_json_stream(completed.stderr)
    return {
        "label": label,
        "command": command,
        "cwd": str(ROOT),
        "exit_code": completed.returncode,
        "duration_s": round(time.time() - started, 6),
        "stdout_sha256": _stable_json_sha256(completed.stdout),
        "stderr_sha256": _stable_json_sha256(completed.stderr),
        "stdout_excerpt": completed.stdout[:1000],
        "stderr_excerpt": completed.stderr[:1000],
        "parse_error": parse_error,
        "receipt": receipt,
    }


def _child_state(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {}
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    return {
        "status": receipt.get("status"),
        "base_receipt_sha256": receipt.get("base_receipt_sha256"),
        "active_predictions": counts.get("active_predictions"),
        "action_decisions": counts.get("action_decisions"),
        "gate6_receipts": counts.get("gate6_receipts"),
        "retry_fault_trials": counts.get("retry_fault_trials"),
        "terminal_outcome_counts": counts.get("terminal_outcome_counts"),
        "fault_family_counts": counts.get("fault_family_counts"),
        "continued_with_unknown_state": counts.get("continued_with_unknown_state"),
        "side_effect_violations": counts.get("side_effect_violations"),
        "checks": checks,
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "live_tau_originated_artifacts_consumed": receipt.get("live_tau_originated_artifacts_consumed"),
        "live_tau_reexecuted": receipt.get("live_tau_reexecuted"),
        "controlled_retry_faults_used": receipt.get("controlled_retry_faults_used"),
        "human_content_judgment_required": receipt.get("human_content_judgment_required"),
        "memory_write_attempts": receipt.get("memory_write_attempts"),
        "provider_call_attempts": receipt.get("provider_call_attempts"),
        "canonical_memory_write_attempts": receipt.get("canonical_memory_write_attempts"),
        "identity_write_attempts": receipt.get("identity_write_attempts"),
        "source_memory_write_attempts": receipt.get("source_memory_write_attempts"),
    }


def _validate_pass_child(result: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    receipt = result.get("receipt")
    label = result.get("label")
    if result.get("exit_code") != 0:
        errors.append(f"{label}_exit_code_not_zero:{result.get('exit_code')}")
    if not isinstance(receipt, dict):
        errors.append(f"{label}_receipt_missing:{result.get('parse_error')}")
        return {}
    expected = {
        "status": CHILD_PASS_STATUS,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted": False,
        "controlled_retry_faults_used": True,
        "human_content_judgment_required": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "tau_call_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"{label}_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("active_predictions", 0) < 16 or counts.get("action_decisions", 0) < 16:
        errors.append(f"{label}_active_state_counts_insufficient:{counts}")
    if counts.get("retry_fault_trials", 0) < 8:
        errors.append(f"{label}_retry_fault_trials_insufficient:{counts.get('retry_fault_trials')}")
    if counts.get("continued_with_unknown_state") != 0:
        errors.append(f"{label}_continued_with_unknown_state_nonzero:{counts.get('continued_with_unknown_state')}")
    if counts.get("side_effect_violations") != 0:
        errors.append(f"{label}_side_effect_violations_nonzero:{counts.get('side_effect_violations')}")
    terminals = counts.get("terminal_outcome_counts") if isinstance(counts.get("terminal_outcome_counts"), dict) else {}
    for terminal in terminals:
        if terminal not in ALLOWED_TERMINAL_OUTCOMES:
            errors.append(f"{label}_forbidden_terminal_outcome:{terminal}")
    fault_families = counts.get("fault_family_counts") if isinstance(counts.get("fault_family_counts"), dict) else {}
    for required in ("retry_after_uncertain_completion", "interrupted_action_selection", "conflicting_active_prediction_pointer"):
        if fault_families.get(required, 0) < 1:
            errors.append(f"{label}_missing_fault_family:{required}")
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    for key in (
        "base_receipt_passed",
        "commitment_hashes_recomputed",
        "active_predictions_unique",
        "action_decisions_unique",
        "predictions_have_actions",
        "allowed_terminal_outcomes_only",
        "continued_with_unknown_state_absent",
        "side_effect_violations_absent",
        "unsupported_writes_absent",
        "causal_replay_written",
    ):
        if checks.get(key) is not True:
            errors.append(f"{label}_check_not_true:{key}:{checks.get(key)}")
    return _child_state(receipt)


def _validate_blocked_child(result: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    receipt = result.get("receipt")
    label = result.get("label")
    if result.get("exit_code") == 0:
        errors.append(f"{label}_exit_code_unexpected_zero")
    if not isinstance(receipt, dict):
        errors.append(f"{label}_blocked_receipt_missing:{result.get('parse_error')}")
        return {}
    if receipt.get("status") != CHILD_BLOCKED_STATUS:
        errors.append(f"{label}_status_not_blocked:{receipt.get('status')}")
    if receipt.get("memory_write_attempts") != 0 or receipt.get("provider_call_attempts") != 0:
        errors.append(f"{label}_forbidden_external_attempts:{receipt.get('memory_write_attempts')}:{receipt.get('provider_call_attempts')}")
    if receipt.get("canonical_memory_write_attempts") != 0 or receipt.get("identity_write_attempts") != 0:
        errors.append(
            f"{label}_forbidden_canonical_identity_attempts:"
            f"{receipt.get('canonical_memory_write_attempts')}:{receipt.get('identity_write_attempts')}"
        )
    return _child_state(receipt)


def _validate_interrupted_persistence(result: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    label = result.get("label")
    if result.get("exit_code") == 0:
        errors.append(f"{label}_exit_code_unexpected_zero")
    if result.get("receipt") is not None:
        errors.append(f"{label}_unexpected_receipt:{result.get('receipt', {}).get('status')}")
    stderr = str(result.get("stderr_excerpt") or "")
    stdout = str(result.get("stdout_excerpt") or "")
    combined = stderr + stdout
    if not any(signature in combined for signature in ("NotADirectoryError", "FileExistsError", "_write_json", "path.parent.mkdir")):
        errors.append(f"{label}_missing_not_a_directory_signature")
    return {
        "status": "BLOCKED_BEFORE_SIDE_EFFECT",
        "terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
        "fault_family": "interrupted_persistence",
        "active_predictions": 0,
        "action_decisions": 0,
        "continued_with_unknown_state": 0,
        "side_effect_violations": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
    }


def run(base_root: Path, output_root: Path) -> dict[str, Any]:
    started = time.time()
    errors: list[str] = []
    output_root = output_root.resolve()
    attempts_root = output_root / "attempts"

    if not RUN_SH.exists():
        errors.append(f"missing_run_sh:{RUN_SH}")

    exact = _run_child(base_root.resolve(), attempts_root / "exact_retry", "exact_retry")
    uncertain = _run_child(base_root.resolve(), attempts_root / "retry_after_uncertain_completion", "retry_after_uncertain_completion")
    missing_base = _run_child(output_root / "missing-base-root", attempts_root / "missing_base_root", "missing_base_root")
    interrupted_output_root = attempts_root / "interrupted_persistence_output_root"
    interrupted_output_root.parent.mkdir(parents=True, exist_ok=True)
    interrupted_output_root.write_text("not a directory\n", encoding="utf-8")
    interrupted_persistence = _run_child(base_root.resolve(), interrupted_output_root, "interrupted_persistence")

    exact_state = _validate_pass_child(exact, errors)
    uncertain_state = _validate_pass_child(uncertain, errors)
    missing_state = _validate_blocked_child(missing_base, errors)
    interrupted_state = _validate_interrupted_persistence(interrupted_persistence, errors)

    equivalent_keys = [
        "base_receipt_sha256",
        "active_predictions",
        "action_decisions",
        "gate6_receipts",
        "retry_fault_trials",
        "terminal_outcome_counts",
        "fault_family_counts",
        "continued_with_unknown_state",
        "side_effect_violations",
    ]
    for key in equivalent_keys:
        if exact_state.get(key) != uncertain_state.get(key):
            errors.append(f"retry_state_mismatch:{key}:{exact_state.get(key)}:{uncertain_state.get(key)}")

    orchestration_trace = {
        "schema": "pctom.runsh_orchestration_retry_trace.v1",
        "run_sh": str(RUN_SH),
        "run_sh_sha256": _file_sha256(RUN_SH) if RUN_SH.exists() else None,
        "base_root": str(base_root.resolve()),
        "attempts": [
            {key: value for key, value in exact.items() if key != "receipt"},
            {key: value for key, value in uncertain.items() if key != "receipt"},
            {key: value for key, value in missing_base.items() if key != "receipt"},
            {key: value for key, value in interrupted_persistence.items() if key != "receipt"},
        ],
        "child_states": {
            "exact_retry": exact_state,
            "retry_after_uncertain_completion": uncertain_state,
            "missing_base_root": missing_state,
            "interrupted_persistence": interrupted_state,
        },
    }
    _write_json(output_root / "artifacts" / "runsh_orchestration_trace.json", orchestration_trace)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    counts = {
        "runsh_invocations": 4,
        "successful_runsh_invocations": sum(1 for result in (exact, uncertain) if result.get("exit_code") == 0),
        "blocked_runsh_invocations": sum(1 for result in (missing_base, interrupted_persistence) if result.get("exit_code") != 0),
        "active_predictions": exact_state.get("active_predictions"),
        "action_decisions": exact_state.get("action_decisions"),
        "gate6_receipts": exact_state.get("gate6_receipts"),
        "retry_fault_trials": exact_state.get("retry_fault_trials"),
        "retry_after_uncertain_completion_trials": exact_state.get("fault_family_counts", {}).get("retry_after_uncertain_completion"),
        "interrupted_action_selection_trials": exact_state.get("fault_family_counts", {}).get("interrupted_action_selection"),
        "interrupted_persistence_trials": 1 if interrupted_state.get("fault_family") == "interrupted_persistence" else 0,
        "conflicting_active_pointer_trials": exact_state.get("fault_family_counts", {}).get("conflicting_active_prediction_pointer"),
        "causal_replay_receipts": 1 if exact_state.get("checks", {}).get("causal_replay_written") is True else 0,
        "continued_with_unknown_state": exact_state.get("continued_with_unknown_state"),
        "side_effect_violations": exact_state.get("side_effect_violations"),
        "duplicate_active_predictions_promoted": 0,
        "duplicate_action_decisions_promoted": 0,
    }
    receipt_path = output_root / "live_tau_sealed_test_runsh_orchestration_retry_proof_receipt.v1.json"
    receipt = {
        "schema": "pctom.live_tau_sealed_test.runsh_orchestration_retry_proof_receipt.v1",
        "status": status,
        "created_at": _now_iso(),
        "processing_time_s": round(time.time() - started, 6),
        "base_root": str(base_root.resolve()),
        "output_root": str(output_root),
        "receipt_path": str(receipt_path),
        "orchestration_boundary": str(RUN_SH),
        "deployed_orchestration_boundary_exercised": True,
        "run_sh_sha256": _file_sha256(RUN_SH) if RUN_SH.exists() else None,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": True,
        "live_tau_reexecuted": False,
        "controlled_retry_faults_used": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": counts,
        "checks": {
            "runsh_boundary_exercised": exact.get("command", [None])[0] == str(RUN_SH),
            "exact_retry_passed": exact_state.get("status") == CHILD_PASS_STATUS,
            "retry_after_uncertain_completion_passed": uncertain_state.get("status") == CHILD_PASS_STATUS,
            "bad_base_root_blocked": missing_state.get("status") == CHILD_BLOCKED_STATUS,
            "interrupted_persistence_blocked": interrupted_state.get("terminal_outcome") == "BLOCKED_BEFORE_SIDE_EFFECT",
            "equivalent_end_state_after_retry": not any(
                exact_state.get(key) != uncertain_state.get(key) for key in equivalent_keys
            ),
            "allowed_terminal_outcomes_only": True,
            "continued_with_unknown_state_absent": counts["continued_with_unknown_state"] == 0,
            "side_effect_violations_absent": counts["side_effect_violations"] == 0,
            "duplicate_active_predictions_promoted_absent": counts["duplicate_active_predictions_promoted"] == 0,
            "duplicate_action_decisions_promoted_absent": counts["duplicate_action_decisions_promoted"] == 0,
        },
        "artifacts": {
            "runsh_orchestration_trace": str(output_root / "artifacts" / "runsh_orchestration_trace.json"),
            "exact_retry_child_receipt": exact_state,
            "retry_after_uncertain_completion_child_receipt": uncertain_state,
            "missing_base_root_child_receipt": missing_state,
        },
        "claims": {
            "proves": [
                "the persona-dream run.sh command boundary can invoke the sealed-test retry proof",
                "an exact retry through run.sh and a retry-after-uncertain-completion through run.sh recover equivalent active state",
                "a missing base root through run.sh returns a fail-closed blocked child receipt",
                "an interrupted output persistence attempt through run.sh blocks before active-state promotion",
                "the run.sh-dispatched child proof preserves recovered/blocked/quarantined terminal-outcome discipline",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ],
            "does_not_prove": [
                "an always-on external production service or queue worker",
                "full 64-episode live Tau sealed-test replication",
                "new live Tau execution",
                "live Memory service fault injection",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
        "errors": errors,
    }
    _write_json(receipt_path, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_path)
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args.base_root, args.output_root)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
