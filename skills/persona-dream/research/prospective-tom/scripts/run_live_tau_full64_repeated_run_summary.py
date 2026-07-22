#!/usr/bin/env python3
"""Aggregate repeated full64 live Tau sealed-test replications."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_FULL64_REPEATED_RUN_SUMMARY"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_FULL64_REPEATED_RUN_SUMMARY"
SOURCE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION"
CONDITIONS = ("M", "R", "D", "CD")
METRICS = ("belief_brier", "action_brier", "planning_regret")


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


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(sample))
    means.sort()
    lower_idx = max(0, int((alpha / 2) * samples) - 1)
    upper_idx = min(samples - 1, int((1 - alpha / 2) * samples) - 1)
    return {
        "alpha": alpha,
        "samples": samples,
        "seed": seed,
        "mean": statistics.fmean(values),
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "bootstrap_distribution_sha256": _stable_json_sha256(means),
    }


def _belief_brier(row: dict[str, Any]) -> float | None:
    metrics = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else {}
    scores = metrics.get("belief_scores") if isinstance(metrics.get("belief_scores"), list) else []
    values = [
        float(score["brier"])
        for score in scores
        if isinstance(score, dict)
        and isinstance(score.get("brier"), (int, float))
        and not isinstance(score.get("brier"), bool)
    ]
    return statistics.fmean(values) if values else None


def _action_brier(row: dict[str, Any]) -> float | None:
    metrics = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else {}
    action = metrics.get("action") if isinstance(metrics.get("action"), dict) else {}
    value = action.get("brier")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _index_by_episode_condition(rows: list[dict[str, Any]], errors: list[str], label: str) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{label}_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"{label}_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        indexed.setdefault(episode_id, {})[condition] = row
    return indexed


def _metric_values(
    case_index: dict[str, dict[str, dict[str, Any]]],
    action_index: dict[str, dict[str, dict[str, Any]]],
    errors: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    episode_ids = sorted(set(case_index) | set(action_index))
    for episode_id in episode_ids:
        case_rows = case_index.get(episode_id, {})
        action_rows = action_index.get(episode_id, {})
        missing = [condition for condition in CONDITIONS if condition not in case_rows or condition not in action_rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
            continue
        values: dict[str, dict[str, float]] = {metric: {} for metric in METRICS}
        for condition in CONDITIONS:
            belief = _belief_brier(case_rows[condition])
            action = _action_brier(case_rows[condition])
            regret = action_rows[condition].get("planning_regret")
            if belief is None or action is None or not isinstance(regret, (int, float)) or isinstance(regret, bool):
                errors.append(f"episode_metric_missing:{episode_id}:{condition}")
                continue
            values["belief_brier"][condition] = belief
            values["action_brier"][condition] = action
            values["planning_regret"][condition] = float(regret)
        if any(set(metric_values) != set(CONDITIONS) for metric_values in values.values()):
            continue
        metric_deltas: dict[str, Any] = {}
        for metric in METRICS:
            baseline_condition = min(("M", "R", "D"), key=lambda condition: values[metric][condition])
            delta = values[metric]["CD"] - values[metric][baseline_condition]
            metric_deltas[metric] = {
                "strongest_baseline_condition": baseline_condition,
                "strongest_baseline_value": values[metric][baseline_condition],
                "cd_value": values[metric]["CD"],
                "cd_minus_strongest_baseline": delta,
                "direction": "BENEFIT" if delta < 0 else "HARM" if delta > 0 else "TIE",
            }
        rows.append({"episode_id": episode_id, "metrics": metric_deltas})
    return rows


def _load_source(source_root: Path, run_index: int, errors: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_root = source_root.resolve()
    receipt_path = source_root / "live_tau_sealed_test_replication_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, f"source_{run_index}_replication_receipt")
    if not isinstance(receipt, dict):
        return {}, []

    source_errors: list[str] = []
    if receipt.get("status") != SOURCE_PASS_STATUS:
        source_errors.append(f"status:{receipt.get('status')}")
    if receipt.get("full_64_episode_replication") is not True:
        source_errors.append(f"full_64_episode_replication:{receipt.get('full_64_episode_replication')}")
    if receipt.get("episode_limit") != 64 or receipt.get("episodes_per_family") != 16:
        source_errors.append(f"episode_shape:{receipt.get('episode_limit')}:{receipt.get('episodes_per_family')}")
    if receipt.get("live") is not True or receipt.get("mocked") is not False:
        source_errors.append(f"live_mocked:{receipt.get('live')}:{receipt.get('mocked')}")
    if receipt.get("gate0_attribution_overlay_used") is not True:
        source_errors.append("gate0_attribution_overlay_missing")
    if receipt.get("tau_call_attempts") != 256 or receipt.get("tau_live_call_performed") != 256:
        source_errors.append(f"tau_count:{receipt.get('tau_call_attempts')}:{receipt.get('tau_live_call_performed')}")
    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if receipt.get(key) != 0:
            source_errors.append(f"{key}:{receipt.get(key)}")

    condition_receipt_path = Path(str(receipt.get("live_tau_condition_comparison_receipt", "")))
    action_receipt_path = Path(str(receipt.get("live_tau_action_selection_receipt", "")))
    condition_receipt = _load_json(condition_receipt_path, errors, f"source_{run_index}_condition_receipt")
    action_receipt = _load_json(action_receipt_path, errors, f"source_{run_index}_action_receipt")
    if not isinstance(condition_receipt, dict):
        condition_receipt = {}
    if not isinstance(action_receipt, dict):
        action_receipt = {}
    if condition_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON":
        source_errors.append(f"condition_status:{condition_receipt.get('status')}")
    if action_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION":
        source_errors.append(f"action_status:{action_receipt.get('status')}")

    case_rows = _load_json(Path(str(condition_receipt.get("case_index_path", ""))), errors, f"source_{run_index}_case_index")
    action_rows = _load_json(Path(str(action_receipt.get("decision_index", ""))), errors, f"source_{run_index}_decision_index")
    if not isinstance(case_rows, list):
        source_errors.append("case_index_not_list")
        case_rows = []
    if not isinstance(action_rows, list):
        source_errors.append("decision_index_not_list")
        action_rows = []
    if len(case_rows) != 256 or len(action_rows) != 256:
        source_errors.append(f"index_size:{len(case_rows)}:{len(action_rows)}")

    metric_rows = _metric_values(
        _index_by_episode_condition(case_rows, source_errors, f"source_{run_index}_case"),
        _index_by_episode_condition(action_rows, source_errors, f"source_{run_index}_action"),
        source_errors,
    )
    if len(metric_rows) != 64:
        source_errors.append(f"metric_rows:{len(metric_rows)}")

    errors.extend(f"source_{run_index}_{error}" for error in source_errors)
    summary = {
        "run_index": run_index,
        "source_root": str(source_root),
        "receipt_path": str(receipt_path),
        "receipt_sha256": _file_sha256(receipt_path) if receipt_path.exists() else None,
        "declared_receipt_sha256": receipt.get("receipt_sha256"),
        "condition_receipt_path": str(condition_receipt_path),
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt_path": str(action_receipt_path),
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
        "status": receipt.get("status"),
        "gate0_case_root": receipt.get("gate0_case_root"),
        "gate0_attribution_record_count": receipt.get("gate0_attribution_record_count"),
        "tau_call_attempts": receipt.get("tau_call_attempts"),
        "tau_live_call_performed": receipt.get("tau_live_call_performed"),
        "metric_rows": len(metric_rows),
        "source_errors": source_errors,
    }
    tagged_rows = [dict(row, run_index=run_index, source_root=str(source_root)) for row in metric_rows]
    return summary, tagged_rows


def summarize(
    *,
    source_roots: list[Path],
    output_root: Path,
    receipt_out: Path,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []
    if len(source_roots) < 2:
        errors.append(f"requires_at_least_two_full64_roots:{len(source_roots)}")

    source_summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for run_index, source_root in enumerate(source_roots, start=1):
        summary, rows = _load_source(source_root, run_index, errors)
        if summary:
            source_summaries.append(summary)
        all_rows.extend(rows)

    metric_summary: dict[str, Any] = {}
    for offset, metric in enumerate(METRICS):
        deltas = [float(row["metrics"][metric]["cd_minus_strongest_baseline"]) for row in all_rows]
        directions = collections.Counter(row["metrics"][metric]["direction"] for row in all_rows)
        ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed + offset, alpha=alpha)
        metric_summary[metric] = {
            "paired_rows": len(deltas),
            "direction_counts": dict(directions),
            "cd_minus_strongest_baseline_ci": ci,
            "benefit_with_confidence": bool(ci and isinstance(ci.get("upper"), (int, float)) and ci["upper"] < 0),
        }

    rows_path = output_root / "artifacts" / "full64_repeated_run_episode_metric_rows.json"
    summary_path = output_root / "artifacts" / "full64_repeated_run_summary.json"
    _write_json(
        rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.live_tau_full64_repeated_run_episode_metric_rows.v1",
            "source_roots": [str(path.resolve()) for path in source_roots],
            "rows": all_rows,
        },
    )
    summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_repeated_run_summary.v1",
        "source_runs": source_summaries,
        "source_receipts_sha256": _stable_json_sha256([row.get("receipt_sha256") for row in source_summaries]),
        "counts": {
            "source_roots": len(source_roots),
            "accepted_source_runs": len([row for row in source_summaries if row.get("status") == SOURCE_PASS_STATUS]),
            "episode_metric_rows": len(all_rows),
            "tau_call_attempts_consumed": sum(int(row["tau_call_attempts"]) for row in source_summaries if isinstance(row.get("tau_call_attempts"), int)),
            "tau_live_calls_consumed": sum(int(row["tau_live_call_performed"]) for row in source_summaries if isinstance(row.get("tau_live_call_performed"), int)),
        },
        "metrics": metric_summary,
        "mocked": False,
        "live": all(row.get("status") == SOURCE_PASS_STATUS for row in source_summaries),
        "fixture_backed": False,
        "live_tau_reexecuted": False,
        "live_tau_receipts_consumed": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    _write_json(summary_path, summary)

    checks = {
        "at_least_two_full64_roots": len(source_roots) >= 2,
        "all_source_runs_passed": all(row.get("status") == SOURCE_PASS_STATUS for row in source_summaries),
        "all_source_runs_gate0_attributed": all(row.get("gate0_attribution_record_count") for row in source_summaries),
        "all_source_runs_have_64_metric_rows": all(row.get("metric_rows") == 64 for row in source_summaries),
        "episode_metric_rows_cover_all_runs": len(all_rows) == len(source_roots) * 64,
        "llm_judge_absent": True,
        "human_content_judgment_absent": True,
        "unsupported_writes_absent": True,
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_repeated_run_summary_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "source_roots": [str(path.resolve()) for path in source_roots],
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path),
        "episode_metric_rows_path": str(rows_path),
        "episode_metric_rows_sha256": _file_sha256(rows_path),
        "counts": summary["counts"],
        "checks": checks,
        "metrics": metric_summary,
        "mocked": False,
        "live": summary["live"],
        "fixture_backed": False,
        "live_tau_reexecuted": False,
        "live_tau_receipts_consumed": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "errors": errors,
        "claims": {
            "proves": [
                "multiple full64 Gate 0-attributed live Tau sealed-test replication roots were hash-bound and aggregated",
                "CD-minus-strongest-baseline belief, action, and planning deltas were recomputed from case/action indices across repeated full64 runs",
                "the aggregate command consumed existing live Tau receipts without reexecuting Tau or using an LLM judge",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the repeated full64 summary failed closed before accepting a repeated-run claim",
            ],
            "does_not_prove": [
                "new live Tau execution inside this aggregate command",
                "independent scenario-corpus generalization beyond the sealed-test split",
                "planning benefit if the planning confidence interval crosses zero",
                "production retry machinery",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, action="append", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260722)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_full64_repeated_run_summary_receipt.v1.json")
    receipt = summarize(
        source_roots=args.source_root,
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
