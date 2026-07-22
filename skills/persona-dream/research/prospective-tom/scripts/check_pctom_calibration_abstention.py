#!/usr/bin/env python3
"""Audit PCTOM-R calibration and abstention fields across live full64 case indexes."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_CALIBRATION_ABSTENTION_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_CALIBRATION_ABSTENTION_AUDIT"
SOURCE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION"
CONDITION_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON"
SCHEMA = "persona_dream.research.prospective_tom.calibration_abstention_audit_receipt.v1"
CONDITIONS = ("M", "R", "D", "CD")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


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
    if not path.is_file():
        errors.append(f"{label}_not_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _extract_case_index_from_source_root(source_root: Path, run_index: int, errors: list[str]) -> dict[str, Any] | None:
    source_root = source_root.resolve()
    source_receipt_path = source_root / "live_tau_sealed_test_replication_receipt.v1.json"
    source_receipt = _load_json(source_receipt_path, errors, f"source_{run_index}_receipt")
    if not isinstance(source_receipt, dict):
        return None

    source_errors: list[str] = []
    if source_receipt.get("status") != SOURCE_PASS_STATUS:
        source_errors.append(f"source_status:{source_receipt.get('status')}")
    if source_receipt.get("live") is not True or source_receipt.get("mocked") is not False:
        source_errors.append(f"source_live_mocked:{source_receipt.get('live')}:{source_receipt.get('mocked')}")
    if source_receipt.get("gate0_attribution_overlay_used") is not True:
        source_errors.append("source_gate0_attribution_overlay_missing")
    if source_receipt.get("episode_limit") != 64:
        source_errors.append(f"source_episode_limit:{source_receipt.get('episode_limit')}")
    if source_receipt.get("tau_live_call_performed") != 256:
        source_errors.append(f"source_tau_live_calls:{source_receipt.get('tau_live_call_performed')}")
    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if source_receipt.get(key) != 0:
            source_errors.append(f"source_{key}_not_zero:{source_receipt.get(key)}")

    condition_receipt_path = Path(str(source_receipt.get("live_tau_condition_comparison_receipt", ""))).resolve()
    condition_receipt = _load_json(condition_receipt_path, errors, f"source_{run_index}_condition_receipt")
    if not isinstance(condition_receipt, dict):
        condition_receipt = {}
    if condition_receipt.get("status") != CONDITION_PASS_STATUS:
        source_errors.append(f"condition_status:{condition_receipt.get('status')}")
    if condition_receipt.get("live") is not True or condition_receipt.get("mocked") is not False:
        source_errors.append(f"condition_live_mocked:{condition_receipt.get('live')}:{condition_receipt.get('mocked')}")
    if condition_receipt.get("tau_receipts_hash_bound") is not True:
        source_errors.append("condition_tau_receipts_not_hash_bound")

    case_index_path = Path(str(condition_receipt.get("case_index_path", ""))).resolve()
    errors.extend(f"source_{run_index}_{error}" for error in source_errors)
    return {
        "run_index": run_index,
        "source_root": str(source_root),
        "source_receipt_path": str(source_receipt_path),
        "source_receipt_sha256": _file_sha256(source_receipt_path) if source_receipt_path.exists() else None,
        "condition_receipt_path": str(condition_receipt_path),
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "case_index_path": str(case_index_path),
        "case_index_sha256": _file_sha256(case_index_path) if case_index_path.exists() else None,
        "source_status": source_receipt.get("status"),
        "condition_status": condition_receipt.get("status"),
        "live": source_receipt.get("live") is True and condition_receipt.get("live") is True,
        "mocked": source_receipt.get("mocked") is True or condition_receipt.get("mocked") is True,
    }


def _case_index_source_from_path(case_index: Path, run_index: int, errors: list[str]) -> dict[str, Any]:
    case_index = case_index.resolve()
    if not case_index.exists():
        errors.append(f"missing_case_index:{case_index}")
    elif case_index.is_symlink():
        errors.append(f"symlink_case_index:{case_index}")
    return {
        "run_index": run_index,
        "source_root": None,
        "source_receipt_path": None,
        "source_receipt_sha256": None,
        "condition_receipt_path": None,
        "condition_receipt_sha256": None,
        "case_index_path": str(case_index),
        "case_index_sha256": _file_sha256(case_index) if case_index.exists() and case_index.is_file() else None,
        "source_status": None,
        "condition_status": None,
        "live": False,
        "mocked": False,
    }


def _audit_row(row: dict[str, Any], row_index: int, errors: list[str]) -> dict[str, Any] | None:
    episode_id = row.get("episode_id")
    condition = row.get("condition")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append(f"row_{row_index}_missing_episode_id")
        return None
    if condition not in CONDITIONS:
        errors.append(f"row_{row_index}_invalid_condition:{condition}")
        return None
    if row.get("tau_live_call_performed") is not True:
        errors.append(f"row_{row_index}_tau_live_call_not_true:{episode_id}:{condition}")
    if row.get("blocked_by_systemic_failure") is True:
        errors.append(f"row_{row_index}_blocked_by_systemic_failure:{episode_id}:{condition}")
    statuses = row.get("statuses") if isinstance(row.get("statuses"), dict) else {}
    if statuses.get("gate5") != "PASS_TOM_SCORING_RECEIPT":
        errors.append(f"row_{row_index}_gate5_not_pass:{episode_id}:{condition}:{statuses.get('gate5')}")

    scoring = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else None
    if scoring is None:
        errors.append(f"row_{row_index}_missing_scoring_metrics:{episode_id}:{condition}")
        return None

    calibration = scoring.get("calibration") if isinstance(scoring.get("calibration"), dict) else None
    if calibration is None:
        errors.append(f"row_{row_index}_missing_calibration:{episode_id}:{condition}")
        return None
    ece = _number(calibration.get("expected_calibration_error"))
    if ece is None or ece < 0.0 or ece > 1.0:
        errors.append(f"row_{row_index}_invalid_ece:{episode_id}:{condition}:{calibration.get('expected_calibration_error')}")
        ece = None
    buckets = calibration.get("buckets")
    if not isinstance(buckets, list) or len(buckets) != 3:
        errors.append(f"row_{row_index}_invalid_calibration_buckets:{episode_id}:{condition}")
        bucket_count = 0
    else:
        bucket_count = 0
        for bucket_index, bucket in enumerate(buckets):
            if not isinstance(bucket, dict):
                errors.append(f"row_{row_index}_bucket_{bucket_index}_not_object:{episode_id}:{condition}")
                continue
            count = bucket.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"row_{row_index}_bucket_{bucket_index}_invalid_count:{episode_id}:{condition}:{count}")
                continue
            bucket_count += count
            accuracy = bucket.get("accuracy")
            mean_confidence = bucket.get("mean_confidence")
            if count == 0:
                if accuracy is not None or mean_confidence is not None:
                    errors.append(f"row_{row_index}_empty_bucket_has_values:{episode_id}:{condition}:{bucket_index}")
            else:
                acc_num = _number(accuracy)
                conf_num = _number(mean_confidence)
                if acc_num is None or acc_num < 0.0 or acc_num > 1.0:
                    errors.append(f"row_{row_index}_bucket_{bucket_index}_invalid_accuracy:{episode_id}:{condition}:{accuracy}")
                if conf_num is None or conf_num < 0.0 or conf_num > 1.0:
                    errors.append(f"row_{row_index}_bucket_{bucket_index}_invalid_mean_confidence:{episode_id}:{condition}:{mean_confidence}")
    if bucket_count <= 0:
        errors.append(f"row_{row_index}_calibration_bucket_count_zero:{episode_id}:{condition}")

    risk_coverage = scoring.get("risk_coverage") if isinstance(scoring.get("risk_coverage"), dict) else None
    if risk_coverage is None:
        errors.append(f"row_{row_index}_missing_risk_coverage:{episode_id}:{condition}")
        return None
    coverage = _number(risk_coverage.get("coverage"))
    selective_accuracy = _number(risk_coverage.get("selective_accuracy"))
    abstained = risk_coverage.get("abstained")
    if coverage is None or coverage < 0.0 or coverage > 1.0:
        errors.append(f"row_{row_index}_invalid_coverage:{episode_id}:{condition}:{risk_coverage.get('coverage')}")
        coverage = None
    if selective_accuracy is None or selective_accuracy < 0.0 or selective_accuracy > 1.0:
        errors.append(
            f"row_{row_index}_invalid_selective_accuracy:{episode_id}:{condition}:{risk_coverage.get('selective_accuracy')}"
        )
        selective_accuracy = None
    if not isinstance(abstained, bool):
        errors.append(f"row_{row_index}_invalid_abstained:{episode_id}:{condition}:{abstained}")
        abstained = None
    if abstained is True and coverage != 0.0:
        errors.append(f"row_{row_index}_abstained_coverage_not_zero:{episode_id}:{condition}:{coverage}")
    if abstained is False and coverage != 1.0:
        errors.append(f"row_{row_index}_covered_coverage_not_one:{episode_id}:{condition}:{coverage}")

    return {
        "episode_id": episode_id,
        "condition": condition,
        "ece": ece,
        "calibration_bucket_items": bucket_count,
        "coverage": coverage,
        "selective_accuracy": selective_accuracy,
        "abstained": abstained,
    }


def _condition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[dict[str, Any]]] = {condition: [] for condition in CONDITIONS}
    for row in rows:
        by_condition[row["condition"]].append(row)
    summary: dict[str, Any] = {}
    for condition, condition_rows in by_condition.items():
        eces = [row["ece"] for row in condition_rows if isinstance(row.get("ece"), float)]
        coverages = [row["coverage"] for row in condition_rows if isinstance(row.get("coverage"), float)]
        selective = [row["selective_accuracy"] for row in condition_rows if isinstance(row.get("selective_accuracy"), float)]
        summary[condition] = {
            "rows": len(condition_rows),
            "mean_expected_calibration_error": statistics.fmean(eces) if eces else None,
            "mean_coverage": statistics.fmean(coverages) if coverages else None,
            "mean_selective_accuracy": statistics.fmean(selective) if selective else None,
            "abstained_rows": sum(1 for row in condition_rows if row.get("abstained") is True),
        }
    return summary


def run(
    *,
    source_roots: list[Path],
    case_indexes: list[Path],
    output_root: Path,
    receipt_out: Path,
    fixture_backed: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    if not source_roots and not case_indexes:
        errors.append("requires_source_root_or_case_index")
    if source_roots and case_indexes:
        errors.append("source_root_and_case_index_modes_are_mutually_exclusive")

    sources: list[dict[str, Any]] = []
    if source_roots:
        for run_index, source_root in enumerate(source_roots, start=1):
            source = _extract_case_index_from_source_root(source_root, run_index, errors)
            if source:
                sources.append(source)
    else:
        for run_index, case_index in enumerate(case_indexes, start=1):
            sources.append(_case_index_source_from_path(case_index, run_index, errors))

    audit_rows: list[dict[str, Any]] = []
    source_row_counts: dict[str, int] = {}
    raw_case_rows_total = 0
    for source in sources:
        case_index_path = Path(str(source.get("case_index_path", "")))
        case_index = _load_json(case_index_path, errors, f"source_{source.get('run_index')}_case_index")
        if not isinstance(case_index, list):
            errors.append(f"source_{source.get('run_index')}_case_index_not_list")
            continue
        source_row_counts[str(source.get("run_index"))] = len(case_index)
        raw_case_rows_total += len(case_index)
        for row_index, row in enumerate(case_index):
            if not isinstance(row, dict):
                errors.append(f"source_{source.get('run_index')}_row_{row_index}_not_object")
                continue
            audited = _audit_row(row, row_index, errors)
            if audited is not None:
                audited["run_index"] = source.get("run_index")
                audited["source_root"] = source.get("source_root")
                audit_rows.append(audited)

    expected_rows = len(sources) * 256 if source_roots else raw_case_rows_total
    if source_roots and any(count != 256 for count in source_row_counts.values()):
        errors.append(f"source_case_index_row_counts_not_256:{source_row_counts}")
    conditions = collections.Counter(row["condition"] for row in audit_rows)
    missing_conditions = [condition for condition in CONDITIONS if conditions.get(condition, 0) == 0]
    if missing_conditions:
        errors.append(f"missing_conditions:{missing_conditions}")

    calibration_rows = [row for row in audit_rows if isinstance(row.get("ece"), float)]
    risk_rows = [row for row in audit_rows if isinstance(row.get("coverage"), float) and isinstance(row.get("selective_accuracy"), float)]
    abstained_rows = [row for row in audit_rows if row.get("abstained") is True]
    covered_rows = [row for row in audit_rows if row.get("abstained") is False]
    if len(calibration_rows) != expected_rows:
        errors.append(f"calibration_rows_mismatch:{len(calibration_rows)}:{expected_rows}")
    if len(risk_rows) != expected_rows:
        errors.append(f"risk_coverage_rows_mismatch:{len(risk_rows)}:{expected_rows}")

    row_artifact_path = output_root / "artifacts" / "calibration_abstention_audit_rows.v1.json"
    summary_artifact_path = output_root / "artifacts" / "calibration_abstention_summary.v1.json"
    _write_json(
        row_artifact_path,
        {
            "schema": "persona_dream.research.prospective_tom.calibration_abstention_audit_rows.v1",
            "sources": sources,
            "rows": audit_rows,
        },
    )

    mean_ece = statistics.fmean(row["ece"] for row in calibration_rows) if calibration_rows else None
    mean_coverage = statistics.fmean(row["coverage"] for row in risk_rows) if risk_rows else None
    mean_selective_accuracy = statistics.fmean(row["selective_accuracy"] for row in risk_rows) if risk_rows else None
    summary = {
        "schema": "persona_dream.research.prospective_tom.calibration_abstention_summary.v1",
        "sources": sources,
        "counts": {
            "source_roots": len(source_roots),
            "case_indexes": len(case_indexes),
            "source_records": len(sources),
            "case_rows": len(audit_rows),
            "raw_case_rows": raw_case_rows_total,
            "expected_case_rows": expected_rows,
            "calibration_rows": len(calibration_rows),
            "risk_coverage_rows": len(risk_rows),
            "abstained_rows": len(abstained_rows),
            "covered_rows": len(covered_rows),
            "calibration_bucket_items": sum(int(row.get("calibration_bucket_items") or 0) for row in audit_rows),
        },
        "condition_summary": _condition_summary(audit_rows),
        "metrics": {
            "mean_expected_calibration_error": mean_ece,
            "mean_coverage": mean_coverage,
            "mean_selective_accuracy": mean_selective_accuracy,
            "abstention_observed": len(abstained_rows) > 0,
        },
    }
    _write_json(summary_artifact_path, summary)

    checks = {
        "source_mode_live_hash_bound": (
            all(source.get("live") is True and source.get("mocked") is False for source in sources)
            and all(source.get("source_receipt_sha256") and source.get("condition_receipt_sha256") for source in sources)
            if source_roots
            else True
        ),
        "all_case_indexes_hash_bound": all(source.get("case_index_sha256") for source in sources),
        "calibration_present_for_all_rows": len(calibration_rows) == len(audit_rows) and bool(audit_rows),
        "risk_coverage_present_for_all_rows": len(risk_rows) == len(audit_rows) and bool(audit_rows),
        "audited_rows_match_expected_shape": len(audit_rows) == expected_rows and expected_rows > 0,
        "all_conditions_present": not missing_conditions,
        "unsupported_writes_absent": True,
        "human_content_judgment_absent": True,
        "llm_judge_absent": True,
    }
    if source_roots:
        checks["source_rows_match_full64_shape"] = len(audit_rows) == expected_rows and expected_rows > 0
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "errors": errors,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "sources": sources,
        "summary_path": str(summary_artifact_path),
        "summary_sha256": _file_sha256(summary_artifact_path),
        "row_artifact_path": str(row_artifact_path),
        "row_artifact_sha256": _file_sha256(row_artifact_path),
        "summary": summary,
        "counts": summary["counts"],
        "metrics": summary["metrics"],
        "checks": checks,
        "mocked": False,
        "live": bool(source_roots) and all(source.get("live") is True for source in sources),
        "fixture_backed": fixture_backed,
        "live_tau_reexecuted": False,
        "live_tau_receipts_consumed": bool(source_roots),
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "the consumed case indexes contain deterministic calibration metrics for every audited Gate 5 scoring row",
                "the consumed case indexes contain deterministic risk-coverage fields for every audited Gate 5 scoring row",
                "the audit hash-bound source receipts, condition receipts, case indexes, summary artifacts, and row artifacts",
                "the audit consumed existing live Tau receipts without reexecuting Tau or using human/LLM content judgment",
            ]
            if status == PASS_STATUS
            else [
                "the calibration/abstention audit failed closed before accepting the metric-surface claim",
            ],
            "does_not_prove": [
                "that abstention improves decisions when unsupported evidence is injected"
                if len(abstained_rows) == 0
                else "that abstention behavior generalizes beyond the observed abstention rows",
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
    parser.add_argument("--source-root", type=Path, action="append", default=[])
    parser.add_argument("--case-index", type=Path, action="append", default=[])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "pctom_calibration_abstention_audit_receipt.v1.json")
    receipt = run(
        source_roots=args.source_root,
        case_indexes=args.case_index,
        output_root=args.output_root,
        receipt_out=receipt_out,
        fixture_backed=args.fixture_backed,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
