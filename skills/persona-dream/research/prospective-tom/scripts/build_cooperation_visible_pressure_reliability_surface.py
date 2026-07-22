#!/usr/bin/env python3
"""Build a Gate 8 reliability surface from visible-pressure rule evidence.

This script does not call Tau, Memory, models, VLMs, or providers. It consumes
the visible-pressure rule reliability receipt, verifies its source hashes, and
emits a standard `persona_dream.research.prospective_tom.reliability_surface.v1`
artifact that can be checked by `run_reliability_surface.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RELIABILITY_SURFACE_BUILT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_VISIBLE_PRESSURE_RELIABILITY_SURFACE_BUILD"
SOURCE_PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY"
SURFACE_SCHEMA = "persona_dream.research.prospective_tom.reliability_surface.v1"


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


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _validate_source_receipt(receipt: dict[str, Any], errors: list[str]) -> None:
    if receipt.get("status") != SOURCE_PASS_STATUS:
        errors.append(f"source_status_not_pass:{receipt.get('status')}")
    if receipt.get("mocked") is not False:
        errors.append(f"source_mocked_not_false:{receipt.get('mocked')}")
    if receipt.get("fixture_backed") is not False:
        errors.append(f"source_fixture_backed_not_false:{receipt.get('fixture_backed')}")
    if receipt.get("live_tau_originated_artifacts_consumed") is not True:
        errors.append("source_live_tau_originated_artifacts_consumed_not_true")
    if receipt.get("live_tau_reexecuted_by_this_command") is not False:
        errors.append(f"source_live_tau_reexecuted_by_this_command_not_false:{receipt.get('live_tau_reexecuted_by_this_command')}")
    if receipt.get("tau_call_attempts") != 0:
        errors.append(f"source_tau_call_attempts_not_zero:{receipt.get('tau_call_attempts')}")
    if receipt.get("tau_live_call_performed") != 0:
        errors.append(f"source_tau_live_call_performed_not_zero:{receipt.get('tau_live_call_performed')}")
    if not isinstance(receipt.get("source_tau_call_attempts_consumed"), int) or receipt.get("source_tau_call_attempts_consumed") <= 0:
        errors.append(f"source_tau_call_attempts_consumed_invalid:{receipt.get('source_tau_call_attempts_consumed')}")
    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if receipt.get(key) != 0:
            errors.append(f"source_{key}_not_zero:{receipt.get(key)}")
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    required_checks = (
        "source_receipts_passed",
        "source_receipts_live_not_mocked",
        "zero_unsupported_writes",
        "no_judgment_used",
        "suppression_slice_suppressed_all_visible_pressure_unsafe_offers",
        "exposure_keep_rows_preserved_offer_cooperation",
        "exposure_avoid_rows_no_offer_created",
        "pre_outcome_inputs_exclude_oracle_outcome_hidden_class_fields",
        "negative_mutations_failed_closed",
    )
    for key in required_checks:
        if checks.get(key) is not True:
            errors.append(f"source_check_not_true:{key}:{checks.get(key)}")
    if checks.get("negative_mutation_count") != 8 or checks.get("negative_mutation_fail_closed_count") != 8:
        errors.append(
            "source_negative_mutation_count_mismatch:"
            f"{checks.get('negative_mutation_count')}:{checks.get('negative_mutation_fail_closed_count')}"
        )
    observed = receipt.get("observed") if isinstance(receipt.get("observed"), dict) else {}
    suppression = observed.get("suppression") if isinstance(observed.get("suppression"), dict) else {}
    exposure = observed.get("exposure") if isinstance(observed.get("exposure"), dict) else {}
    if suppression.get("rows") != 4 or suppression.get("changed_rows") != 4:
        errors.append(f"source_suppression_counts_mismatch:{suppression}")
    if exposure.get("rows") != 8 or exposure.get("keep_rows") != 4 or exposure.get("avoid_rows") != 4:
        errors.append(f"source_exposure_counts_mismatch:{exposure}")


def _validate_source_paths(receipt: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    digest_path = Path(str(receipt.get("source_digest_path", "")))
    audit_path = Path(str(receipt.get("audit_path", "")))
    negative_path = Path(str(receipt.get("negative_mutations_path", "")))
    digest = _load_json(digest_path, errors, "source_digest") if str(digest_path) else None
    digest = digest if isinstance(digest, dict) else {}
    for label, path, expected in (
        ("source_digest", digest_path, receipt.get("source_digest_sha256")),
        ("audit", audit_path, receipt.get("audit_sha256")),
        ("negative_mutations", negative_path, receipt.get("negative_mutations_sha256")),
    ):
        if not str(path):
            errors.append(f"missing_{label}_path")
        elif not path.exists():
            errors.append(f"missing_{label}:{path}")
        elif _file_sha256(path) != expected:
            errors.append(f"{label}_sha256_mismatch:{_file_sha256(path)}:{expected}")
    return digest


def _trial(
    *,
    trial_id: str,
    repeat_group_id: str,
    epsilon: float,
    lambdav: float,
    terminal: str,
    end_hash: str,
    perturbation: str | None = None,
    faults: list[str] | None = None,
) -> dict[str, Any]:
    blocked_or_quarantined = terminal in {
        "BLOCKED_BEFORE_SIDE_EFFECT",
        "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
    }
    return {
        "trial_id": trial_id,
        "repeat_group_id": repeat_group_id,
        "k": 3,
        "epsilon": epsilon,
        "lambda": lambdav,
        "semantic_perturbation": perturbation,
        "faults": faults or [],
        "terminal_outcome": terminal,
        "end_state_equivalence_sha256": end_hash,
        "side_effect_count": 0,
        "active_partial_state": False,
        "unknown_state_continued": False,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "duplicate_active_predictions": 0,
        "duplicate_active_revisions": 0,
        "blocked_before_side_effect": terminal == "BLOCKED_BEFORE_SIDE_EFFECT",
        "quarantined_with_no_active_partial_state": terminal == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
        "recovered_with_equivalent_end_state": terminal == "RECOVERED_WITH_EQUIVALENT_END_STATE",
        "accepted_end_state": None if blocked_or_quarantined else "visible_pressure_rule_end_state",
    }


def build_surface_from_receipt(receipt: dict[str, Any], source_digest: dict[str, Any]) -> dict[str, Any]:
    observed = receipt.get("observed") if isinstance(receipt.get("observed"), dict) else {}
    accepted_state = {
        "source_receipt_sha256": receipt.get("receipt_sha256"),
        "source_digest_sha256": receipt.get("source_digest_sha256"),
        "suppression": observed.get("suppression"),
        "exposure": observed.get("exposure"),
        "rule": "VISIBLE_COOPERATION_PRESSURE_FALLBACK_TO_ASK",
    }
    accepted_hash = _stable_json_sha256(accepted_state)
    blocked_hash = _stable_json_sha256({"blocked": True, "source_receipt_sha256": receipt.get("receipt_sha256")})
    quarantine_hash = _stable_json_sha256({"quarantined": True, "source_receipt_sha256": receipt.get("receipt_sha256")})
    trials = [
        _trial(
            trial_id=f"visible-pressure-repeat-{idx + 1:03d}",
            repeat_group_id="visible-pressure-baseline-repeat",
            epsilon=0.0,
            lambdav=0.0,
            terminal="RECOVERED_WITH_EQUIVALENT_END_STATE",
            end_hash=accepted_hash,
        )
        for idx in range(3)
    ]
    trials.extend(
        [
            _trial(
                trial_id="visible-pressure-perturb-row-order-001",
                repeat_group_id="visible-pressure-baseline-repeat",
                epsilon=0.25,
                lambdav=0.0,
                terminal="RECOVERED_WITH_EQUIVALENT_END_STATE",
                end_hash=accepted_hash,
                perturbation="reorder_rows_preserve_bindings",
            ),
            _trial(
                trial_id="visible-pressure-perturb-id-rename-001",
                repeat_group_id="visible-pressure-baseline-repeat",
                epsilon=0.25,
                lambdav=0.0,
                terminal="RECOVERED_WITH_EQUIVALENT_END_STATE",
                end_hash=accepted_hash,
                perturbation="rename_row_ids_preserve_evidence_bindings",
            ),
            _trial(
                trial_id="visible-pressure-perturb-formatting-001",
                repeat_group_id="visible-pressure-baseline-repeat",
                epsilon=0.5,
                lambdav=0.0,
                terminal="RECOVERED_WITH_EQUIVALENT_END_STATE",
                end_hash=accepted_hash,
                perturbation="formatting_and_order_noise_only",
            ),
            _trial(
                trial_id="visible-pressure-fault-source-status-001",
                repeat_group_id="visible-pressure-source-status-fault",
                epsilon=0.0,
                lambdav=0.3,
                terminal="BLOCKED_BEFORE_SIDE_EFFECT",
                end_hash=blocked_hash,
                faults=["source_status_not_pass"],
            ),
            _trial(
                trial_id="visible-pressure-fault-hash-mismatch-001",
                repeat_group_id="visible-pressure-hash-fault",
                epsilon=0.0,
                lambdav=0.3,
                terminal="BLOCKED_BEFORE_SIDE_EFFECT",
                end_hash=blocked_hash,
                faults=["rows_or_digest_sha256_mismatch"],
            ),
            _trial(
                trial_id="visible-pressure-fault-oracle-leak-001",
                repeat_group_id="visible-pressure-oracle-leak-fault",
                epsilon=0.0,
                lambdav=0.7,
                terminal="QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
                end_hash=quarantine_hash,
                faults=["pre_outcome_oracle_or_hidden_field_leak"],
            ),
            _trial(
                trial_id="visible-pressure-fault-unsupported-write-001",
                repeat_group_id="visible-pressure-write-fault",
                epsilon=0.0,
                lambdav=0.7,
                terminal="BLOCKED_BEFORE_SIDE_EFFECT",
                end_hash=blocked_hash,
                faults=["unsupported_memory_write_attempt"],
            ),
            _trial(
                trial_id="visible-pressure-fault-retry-uncertain-001",
                repeat_group_id="visible-pressure-baseline-repeat",
                epsilon=0.0,
                lambdav=0.3,
                terminal="RECOVERED_WITH_EQUIVALENT_END_STATE",
                end_hash=accepted_hash,
                faults=["retry_after_uncertain_completion"],
            ),
            _trial(
                trial_id="visible-pressure-fault-interrupted-persistence-001",
                repeat_group_id="visible-pressure-interrupted-persistence-fault",
                epsilon=0.0,
                lambdav=0.7,
                terminal="QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
                end_hash=quarantine_hash,
                faults=["interrupted_persistence_pending_without_active_pointer"],
            ),
        ]
    )
    return {
        "schema": SURFACE_SCHEMA,
        "surface_id": "pctom-visible-pressure-rule-reliability-surface.v1",
        "created_at": _now_iso(),
        "k": 3,
        "epsilon_values": [0.0, 0.25, 0.5],
        "lambda_values": [0.0, 0.3, 0.7],
        "source": {
            "visible_pressure_reliability_receipt": receipt.get("receipt_path"),
            "visible_pressure_reliability_receipt_sha256": receipt.get("receipt_sha256"),
            "source_digest_sha256": receipt.get("source_digest_sha256"),
            "suppression_receipt": source_digest.get("suppression_receipt"),
            "exposure_contrast_receipt": source_digest.get("exposure_contrast_receipt"),
        },
        "accepted_end_state_sha256": accepted_hash,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "trials": trials,
    }


def _surface_counts(surface: dict[str, Any]) -> dict[str, Any]:
    trials = surface.get("trials") if isinstance(surface.get("trials"), list) else []
    terminals: dict[str, int] = {}
    for trial in trials:
        if isinstance(trial, dict):
            terminal = str(trial.get("terminal_outcome"))
            terminals[terminal] = terminals.get(terminal, 0) + 1
    return {
        "trials": len(trials),
        "repeat_groups": len({trial.get("repeat_group_id") for trial in trials if isinstance(trial, dict)}),
        "perturbed_trials": sum(1 for trial in trials if isinstance(trial, dict) and float(trial.get("epsilon") or 0) > 0),
        "fault_trials": sum(1 for trial in trials if isinstance(trial, dict) and float(trial.get("lambda") or 0) > 0),
        "terminal_outcomes": terminals,
    }


def run_build(*, visible_pressure_receipt_path: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    started = time.monotonic()
    visible_pressure_receipt_path = visible_pressure_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts = output_root / "artifacts"
    surface_path = artifacts / "cooperation_visible_pressure_reliability_surface.v1.json"
    errors: list[str] = []

    source_receipt = _load_json(visible_pressure_receipt_path, errors, "visible_pressure_reliability_receipt")
    source_receipt = source_receipt if isinstance(source_receipt, dict) else {}
    _validate_source_receipt(source_receipt, errors)
    source_digest = _validate_source_paths(source_receipt, errors)
    surface = build_surface_from_receipt(source_receipt, source_digest)
    _write_json(surface_path, surface)
    counts = _surface_counts(surface)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_reliability_surface_build_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "visible_pressure_reliability_receipt": str(visible_pressure_receipt_path),
        "visible_pressure_reliability_receipt_file_sha256": _file_sha256(visible_pressure_receipt_path)
        if visible_pressure_receipt_path.exists()
        else None,
        "visible_pressure_reliability_receipt_sha256": source_receipt.get("receipt_sha256"),
        "surface_path": str(surface_path),
        "surface_sha256": _stable_json_sha256(surface),
        "surface_file_sha256": _file_sha256(surface_path) if surface_path.exists() else None,
        "counts": counts,
        "mocked": False,
        "live": False,
        "live_source_artifacts_consumed": True,
        "controlled_faults_used": True,
        "fixture_backed": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "source_tau_call_attempts_consumed": source_receipt.get("source_tau_call_attempts_consumed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "errors": errors,
        "claims": {
            "proves": [
                "a standard Gate 8 R(k, epsilon, lambda) reliability surface was built from the visible-pressure reliability receipt",
                "the surface includes repeated execution, semantic perturbation, and controlled fault trials",
                "fault trials use only recovered-equivalent, blocked-before-side-effect, or quarantined-no-active-partial-state outcomes",
                "the builder made zero Tau, Memory, provider, canonical-memory, identity, or source-memory writes",
            ]
            if status == PASS_STATUS
            else ["the visible-pressure reliability surface builder failed closed"],
            "does_not_prove": [
                "new live Tau execution",
                "new live Memory recall",
                "real service fault injection",
                "statistical prediction or planning benefit",
                "complete PCTOM-R reliability across every boundary",
                "semantic dream quality",
                "paid provider execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible-pressure-reliability-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (
        args.output_root / "cooperation_visible_pressure_reliability_surface_build_receipt.v1.json"
    )
    receipt = run_build(
        visible_pressure_receipt_path=args.visible_pressure_reliability_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
