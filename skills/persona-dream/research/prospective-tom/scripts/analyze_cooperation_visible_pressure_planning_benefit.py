#!/usr/bin/env python3
"""Analyze planning benefit from visible-pressure cooperation rule artifacts.

This diagnostic consumes the visible-pressure rule reliability receipt and its
live-originated source row artifacts. It computes slice-level planning-regret
changes without calling Tau, Memory, models, VLMs, providers, or judges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_PLANNING_BENEFIT_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_VISIBLE_PRESSURE_PLANNING_BENEFIT_DIAGNOSTIC"
SOURCE_PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY"
OFFER_ACTION = "OFFER_COOPERATION"
ASK_ACTION = "ASK_CLARIFYING_QUESTION"
KEEP_CLASS = "KEEP_COOPERATION_POSITIVE"
AVOID_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)


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


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any]:
    if not values:
        return {"mean": None, "lower": None, "upper": None, "samples": samples, "alpha": alpha}
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(draw))
    means.sort()
    lower_idx = max(0, min(len(means) - 1, int((alpha / 2.0) * len(means))))
    upper_idx = max(0, min(len(means) - 1, int((1.0 - alpha / 2.0) * len(means)) - 1))
    return {
        "mean": statistics.fmean(values),
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "samples": samples,
        "alpha": alpha,
    }


def _direction(value: float) -> str:
    if value > 1e-9:
        return "BENEFIT"
    if value < -1e-9:
        return "HARM"
    return "TIE"


def _rows_from_doc(doc: Any, errors: list[str], label: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
        errors.append(f"{label}_rows_not_list")
        return []
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(doc["rows"]):
        if isinstance(row, dict):
            rows.append(row)
        else:
            errors.append(f"{label}_row_{idx}_not_object")
    return rows


def _source_receipt_sha_valid(receipt: dict[str, Any]) -> bool:
    expected = receipt.get("receipt_sha256")
    actual = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    return expected == actual


def _validate_rule_reliability_receipt(receipt: dict[str, Any], errors: list[str]) -> None:
    if receipt.get("status") != SOURCE_PASS_STATUS:
        errors.append(f"source_status_not_pass:{receipt.get('status')}")
    if not _source_receipt_sha_valid(receipt):
        errors.append("source_receipt_sha256_mismatch")
    if receipt.get("mocked") is not False:
        errors.append(f"source_mocked_not_false:{receipt.get('mocked')}")
    if receipt.get("fixture_backed") is not False:
        errors.append(f"source_fixture_backed_not_false:{receipt.get('fixture_backed')}")
    if receipt.get("live_tau_originated_artifacts_consumed") is not True:
        errors.append("source_live_tau_originated_artifacts_consumed_not_true")
    if receipt.get("tau_call_attempts") != 0 or receipt.get("tau_live_call_performed") != 0:
        errors.append(f"source_reexecuted_tau_calls:{receipt.get('tau_call_attempts')}:{receipt.get('tau_live_call_performed')}")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"source_{key}_not_zero:{receipt.get(key)}")
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    for key in (
        "suppression_slice_suppressed_all_visible_pressure_unsafe_offers",
        "exposure_keep_rows_preserved_offer_cooperation",
        "exposure_avoid_rows_no_offer_created",
        "negative_mutations_failed_closed",
        "zero_unsupported_writes",
    ):
        if checks.get(key) is not True:
            errors.append(f"source_check_not_true:{key}:{checks.get(key)}")


def _load_source_rows(source_receipt: dict[str, Any], errors: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    suppression_receipt_path = Path(str(source_receipt.get("suppression_receipt", "")))
    exposure_receipt_path = Path(str(source_receipt.get("exposure_contrast_receipt", "")))
    suppression_receipt = _load_json(suppression_receipt_path, errors, "suppression_source_receipt")
    exposure_receipt = _load_json(exposure_receipt_path, errors, "exposure_source_receipt")
    suppression_receipt = suppression_receipt if isinstance(suppression_receipt, dict) else {}
    exposure_receipt = exposure_receipt if isinstance(exposure_receipt, dict) else {}
    for label, receipt, path in (
        ("suppression", suppression_receipt, suppression_receipt_path),
        ("exposure", exposure_receipt, exposure_receipt_path),
    ):
        if not path.exists():
            errors.append(f"{label}_source_receipt_missing:{path}")
        elif not _source_receipt_sha_valid(receipt):
            errors.append(f"{label}_source_receipt_sha256_mismatch")
        rows_path = Path(str(receipt.get("rows_path", "")))
        if not rows_path.exists():
            errors.append(f"{label}_rows_path_missing:{rows_path}")
            continue
        if receipt.get("rows_sha256") != _file_sha256(rows_path):
            errors.append(f"{label}_rows_sha256_mismatch:{receipt.get('rows_sha256')}:{_file_sha256(rows_path)}")
    suppression_rows_doc = _load_json(Path(str(suppression_receipt.get("rows_path", ""))), errors, "suppression_rows")
    exposure_rows_doc = _load_json(Path(str(exposure_receipt.get("rows_path", ""))), errors, "exposure_rows")
    metadata = {
        "suppression_receipt": str(suppression_receipt_path),
        "suppression_receipt_sha256": suppression_receipt.get("receipt_sha256"),
        "suppression_rows_sha256": suppression_receipt.get("rows_sha256"),
        "exposure_receipt": str(exposure_receipt_path),
        "exposure_receipt_sha256": exposure_receipt.get("receipt_sha256"),
        "exposure_rows_sha256": exposure_receipt.get("rows_sha256"),
    }
    return (
        _rows_from_doc(suppression_rows_doc, errors, "suppression_rows"),
        _rows_from_doc(exposure_rows_doc, errors, "exposure_rows"),
        metadata,
    )


def _row_delta(row: dict[str, Any], errors: list[str], label: str, idx: int) -> float | None:
    original = row.get("original_cd_minus_baseline_planning_regret")
    intervened = row.get("intervened_cd_minus_baseline_planning_regret")
    if not isinstance(original, (int, float)) or isinstance(original, bool):
        errors.append(f"{label}_row_{idx}_original_regret_not_number:{original}")
        return None
    if not isinstance(intervened, (int, float)) or isinstance(intervened, bool):
        errors.append(f"{label}_row_{idx}_intervened_regret_not_number:{intervened}")
        return None
    return float(original) - float(intervened)


def _analyze_rows(
    rows: list[dict[str, Any]],
    *,
    label: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    errors: list[str],
) -> dict[str, Any]:
    deltas: list[float] = []
    original_values: list[float] = []
    intervened_values: list[float] = []
    action_changes = 0
    direction_counts: dict[str, int] = {}
    classes: dict[str, int] = {}
    for idx, row in enumerate(rows):
        delta = _row_delta(row, errors, label, idx)
        if delta is None:
            continue
        deltas.append(delta)
        original_values.append(float(row["original_cd_minus_baseline_planning_regret"]))
        intervened_values.append(float(row["intervened_cd_minus_baseline_planning_regret"]))
        direction = _direction(delta)
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
        contrast_class = str(row.get("contrast_class"))
        classes[contrast_class] = classes.get(contrast_class, 0) + 1
        if row.get("cd_action_changed_by_rule") is True:
            action_changes += 1
    ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
    return {
        "rows": len(rows),
        "contrast_classes": classes,
        "action_changes": action_changes,
        "cd_original_actions": _count_actions(rows, "cd_original_action"),
        "cd_intervened_actions": _count_actions(rows, "cd_intervened_action"),
        "original_mean_cd_minus_baseline_planning_regret": _mean(original_values),
        "intervened_mean_cd_minus_baseline_planning_regret": _mean(intervened_values),
        "mean_improvement_vs_original": _mean(deltas),
        "improvement_direction_counts": direction_counts,
        "improvement_ci": ci,
        "planning_benefit_with_confidence": isinstance(ci.get("lower"), (int, float)) and ci["lower"] > 0,
    }


def _count_actions(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = row.get(field)
        if isinstance(action, str):
            counts[action] = counts.get(action, 0) + 1
    return counts


def _validate_expected_rows(
    suppression_rows: list[dict[str, Any]], exposure_rows: list[dict[str, Any]], errors: list[str]
) -> None:
    if len(suppression_rows) != 4:
        errors.append(f"suppression_row_count_not_4:{len(suppression_rows)}")
    if len(exposure_rows) != 8:
        errors.append(f"exposure_row_count_not_8:{len(exposure_rows)}")
    for idx, row in enumerate(suppression_rows):
        if row.get("contrast_class") != AVOID_CLASS:
            errors.append(f"suppression_row_{idx}_class_mismatch:{row.get('contrast_class')}")
        if row.get("cd_original_action") != OFFER_ACTION or row.get("cd_intervened_action") != ASK_ACTION:
            errors.append(f"suppression_row_{idx}_action_mismatch:{row.get('cd_original_action')}:{row.get('cd_intervened_action')}")
        if row.get("cd_action_changed_by_rule") is not True:
            errors.append(f"suppression_row_{idx}_not_changed")
    keep_rows = [row for row in exposure_rows if row.get("contrast_class") == KEEP_CLASS]
    avoid_rows = [row for row in exposure_rows if row.get("contrast_class") == AVOID_CLASS]
    if len(keep_rows) != 4 or len(avoid_rows) != 4:
        errors.append(f"exposure_class_counts_mismatch:{len(keep_rows)}:{len(avoid_rows)}")
    if any(row.get("cd_intervened_action") != OFFER_ACTION for row in keep_rows):
        errors.append("exposure_keep_rows_not_preserved_offer")
    if any(row.get("cd_intervened_action") == OFFER_ACTION for row in avoid_rows):
        errors.append("exposure_avoid_rows_created_offer")


def run_diagnostic(
    *,
    rule_reliability_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    rule_reliability_receipt_path = rule_reliability_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts = output_root / "artifacts"
    diagnostic_path = artifacts / "cooperation_visible_pressure_planning_benefit_diagnostic.json"
    errors: list[str] = []

    source_receipt = _load_json(rule_reliability_receipt_path, errors, "rule_reliability_receipt")
    source_receipt = source_receipt if isinstance(source_receipt, dict) else {}
    _validate_rule_reliability_receipt(source_receipt, errors)
    suppression_rows, exposure_rows, source_metadata = _load_source_rows(source_receipt, errors)
    _validate_expected_rows(suppression_rows, exposure_rows, errors)

    suppression = _analyze_rows(
        suppression_rows,
        label="suppression",
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
        errors=errors,
    )
    exposure = _analyze_rows(
        exposure_rows,
        label="exposure",
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed + 1,
        alpha=alpha,
        errors=errors,
    )
    combined = _analyze_rows(
        suppression_rows + exposure_rows,
        label="combined",
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed + 2,
        alpha=alpha,
        errors=errors,
    )
    diagnostic = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_planning_benefit_diagnostic.v1",
        "source": source_metadata,
        "suppression_slice": suppression,
        "exposure_contrast_slice": exposure,
        "combined_slice": combined,
        "planning_benefit_scope": "slice_local_visible_pressure_artifacts",
        "broad_planning_benefit_claimed": False,
        "statistical_generalization_claimed": False,
        "checks": {
            "suppression_slice_planning_benefit_with_confidence": suppression["planning_benefit_with_confidence"] is True,
            "exposure_contrast_no_regression": exposure["mean_improvement_vs_original"] == 0.0
            and exposure["action_changes"] == 0,
            "combined_slice_planning_benefit_with_confidence": combined["planning_benefit_with_confidence"] is True,
            "broad_planning_benefit_not_claimed": True,
            "statistical_generalization_not_claimed": True,
        },
    }
    for key, value in diagnostic["checks"].items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")
    _write_json(diagnostic_path, diagnostic)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_planning_benefit_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "rule_reliability_receipt": str(rule_reliability_receipt_path),
        "rule_reliability_receipt_file_sha256": _file_sha256(rule_reliability_receipt_path)
        if rule_reliability_receipt_path.exists()
        else None,
        "rule_reliability_receipt_sha256": source_receipt.get("receipt_sha256"),
        "diagnostic_path": str(diagnostic_path),
        "diagnostic_sha256": _stable_json_sha256(diagnostic),
        "diagnostic_file_sha256": _file_sha256(diagnostic_path) if diagnostic_path.exists() else None,
        "counts": {
            "suppression_rows": len(suppression_rows),
            "exposure_rows": len(exposure_rows),
            "combined_rows": len(suppression_rows) + len(exposure_rows),
            "suppression_action_changes": suppression["action_changes"],
            "exposure_action_changes": exposure["action_changes"],
        },
        "metrics": {
            "suppression_mean_improvement_vs_original": suppression["mean_improvement_vs_original"],
            "suppression_improvement_ci": suppression["improvement_ci"],
            "exposure_mean_improvement_vs_original": exposure["mean_improvement_vs_original"],
            "exposure_improvement_ci": exposure["improvement_ci"],
            "combined_mean_improvement_vs_original": combined["mean_improvement_vs_original"],
            "combined_improvement_ci": combined["improvement_ci"],
        },
        "checks": diagnostic["checks"],
        "mocked": False,
        "live": False,
        "live_source_artifacts_consumed": True,
        "fixture_backed": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "planning_benefit_scope": diagnostic["planning_benefit_scope"],
        "broad_planning_benefit_claimed": False,
        "statistical_generalization_claimed": False,
        "errors": errors,
        "claims": {
            "proves": [
                "the visible-pressure suppression rows have slice-local planning-regret improvement with bootstrap confidence",
                "the exposure/contrast rows show no action-change regression in the same diagnostic",
                "the combined supplied visible-pressure artifacts show slice-local planning-regret improvement with bootstrap confidence",
                "the diagnostic consumed live-originated hash-bound row artifacts without new Tau, Memory, provider, canonical, identity, or source-memory writes",
            ]
            if status == PASS_STATUS
            else ["the visible-pressure planning-benefit diagnostic failed closed"],
            "does_not_prove": [
                "broad held-out PCTOM-R planning benefit",
                "statistical generalization beyond the supplied visible-pressure artifacts",
                "real service fault injection",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-reliability-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=41729)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (
        args.output_root / "cooperation_visible_pressure_planning_benefit_diagnostic_receipt.v1.json"
    )
    receipt = run_diagnostic(
        rule_reliability_receipt_path=args.rule_reliability_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
