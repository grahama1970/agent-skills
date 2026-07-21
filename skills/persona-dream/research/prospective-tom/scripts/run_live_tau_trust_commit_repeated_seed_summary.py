#!/usr/bin/env python3
"""Aggregate repeated live Tau trust/commitment replication receipts."""
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


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY"
EXPECTED_SOURCE_STATUS = "PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION"
TRUST_FAMILY = "trust_commitment_relationship"
CONDITIONS = ("M", "R", "D", "CD")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
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


def _load_planning_rows(receipt: dict[str, Any], errors: list[str], seed_index: int) -> list[dict[str, Any]]:
    path_value = receipt.get("planning_rows_path")
    if not isinstance(path_value, str):
        errors.append(f"seed_{seed_index}_missing_planning_rows_path")
        return []
    payload = _load_json(Path(path_value), errors, f"seed_{seed_index}_planning_rows")
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        errors.append(f"seed_{seed_index}_planning_rows_not_list")
        return []
    loaded: list[dict[str, Any]] = []
    for row_idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"seed_{seed_index}_planning_row_{row_idx}_not_object")
            continue
        delta = row.get("cd_minus_baseline")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            errors.append(f"seed_{seed_index}_planning_row_{row_idx}_delta_not_numeric:{delta}")
            continue
        episode_id = row.get("episode_id")
        if not isinstance(episode_id, str) or "trust-commit" not in episode_id:
            errors.append(f"seed_{seed_index}_planning_row_{row_idx}_non_trust_episode:{episode_id}")
            continue
        copy = dict(row)
        copy["seed_index"] = seed_index
        copy["seed_episode_key"] = f"seed-{seed_index}:{episode_id}"
        loaded.append(copy)
    return loaded


def _source_summary(receipt: dict[str, Any], path: Path, seed_index: int, errors: list[str]) -> dict[str, Any]:
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    planning = metrics.get("planning_summary") if isinstance(metrics.get("planning_summary"), dict) else {}
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), dict) else {}
    source_errors: list[str] = []

    if receipt.get("status") != EXPECTED_SOURCE_STATUS:
        source_errors.append(f"status:{receipt.get('status')}")
    if receipt.get("scenario_family") != TRUST_FAMILY:
        source_errors.append(f"scenario_family:{receipt.get('scenario_family')}")
    if receipt.get("trust_episode_limit") != 4:
        source_errors.append(f"trust_episode_limit:{receipt.get('trust_episode_limit')}")
    if receipt.get("mocked") is not False:
        source_errors.append(f"mocked:{receipt.get('mocked')}")
    if receipt.get("live") is not True:
        source_errors.append(f"live:{receipt.get('live')}")
    if receipt.get("live_tau_reexecuted") is not True:
        source_errors.append(f"live_tau_reexecuted:{receipt.get('live_tau_reexecuted')}")
    if receipt.get("tau_call_attempts") != 16:
        source_errors.append(f"tau_call_attempts:{receipt.get('tau_call_attempts')}")
    if receipt.get("tau_live_call_performed") != 16:
        source_errors.append(f"tau_live_call_performed:{receipt.get('tau_live_call_performed')}")
    if counts.get("episodes") != 4:
        source_errors.append(f"episodes:{counts.get('episodes')}")
    if counts.get("cases") != 16:
        source_errors.append(f"cases:{counts.get('cases')}")
    for condition in CONDITIONS:
        action_counts = counts.get("action_decisions_per_condition")
        regret_counts = counts.get("planning_regret_scores_per_condition")
        if not isinstance(action_counts, dict) or action_counts.get(condition) != 4:
            source_errors.append(f"action_decisions_{condition}:{action_counts}")
        if not isinstance(regret_counts, dict) or regret_counts.get(condition) != 4:
            source_errors.append(f"planning_regret_scores_{condition}:{regret_counts}")
    for key in (
        "condition_receipt_passed",
        "action_selection_receipt_passed",
        "only_trust_commit_episodes_selected",
        "tau_receipts_hash_bound",
        "all_conditions_have_expected_action_counts",
        "planning_rows_cover_expected_episodes",
    ):
        if checks.get(key) is not True:
            source_errors.append(f"check_{key}:{checks.get(key)}")
    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if receipt.get(key) != 0:
            source_errors.append(f"{key}:{receipt.get(key)}")
    if source_errors:
        errors.extend(f"seed_{seed_index}_{error}" for error in source_errors)

    return {
        "seed_index": seed_index,
        "receipt_path": str(path),
        "receipt_sha256": _file_sha256(path),
        "declared_receipt_sha256": receipt.get("receipt_sha256"),
        "status": receipt.get("status"),
        "output_root": receipt.get("output_root"),
        "tau_call_attempts": receipt.get("tau_call_attempts"),
        "cases": counts.get("cases"),
        "episodes": counts.get("episodes"),
        "action_switch_count": counts.get("action_switch_count"),
        "nonzero_delta_count": counts.get("nonzero_delta_count"),
        "oracle_match_transitions": counts.get("oracle_match_transitions"),
        "planning_mean_cd_minus_baseline": planning.get("mean_cd_minus_baseline"),
        "planning_regret_ci": planning.get("planning_regret_ci"),
        "planning_benefit_with_confidence": planning.get("planning_benefit_with_confidence"),
        "source_errors": source_errors,
    }


def summarize_repeated_seeds(
    *,
    receipt_paths: list[Path],
    output_root: Path,
    receipt_out: Path,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    started = time.monotonic()
    errors: list[str] = []
    if len(receipt_paths) < 2:
        errors.append(f"requires_at_least_two_seed_receipts:{len(receipt_paths)}")

    source_summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    receipt_hashes: list[str] = []
    for seed_index, path in enumerate(receipt_paths, start=1):
        receipt = _load_json(path, errors, f"seed_{seed_index}_receipt")
        if not isinstance(receipt, dict):
            errors.append(f"seed_{seed_index}_receipt_not_object")
            continue
        source_summaries.append(_source_summary(receipt, path, seed_index, errors))
        receipt_hashes.append(_file_sha256(path))
        all_rows.extend(_load_planning_rows(receipt, errors, seed_index))

    deltas = [float(row["cd_minus_baseline"]) for row in all_rows]
    ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
    direction_counts = collections.Counter(row.get("direction") for row in all_rows)
    transition_counts = collections.Counter(row.get("oracle_match_transition") for row in all_rows)
    action_switch_count = sum(1 for row in all_rows if row.get("action_switched") is True)
    nonzero_rows = [row for row in all_rows if float(row["cd_minus_baseline"]) != 0.0]

    repeated_rows_path = output_root / "artifacts" / "repeated_seed_trust_commit_planning_rows.json"
    summary_path = output_root / "artifacts" / "repeated_seed_trust_commit_summary.json"
    _write_json(
        repeated_rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_repeated_seed_rows.v1",
            "source_receipts": [str(path) for path in receipt_paths],
            "rows": all_rows,
        },
    )
    summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_repeated_seed_summary.v1",
        "source_receipts": source_summaries,
        "source_receipt_hashes_sha256": _stable_json_sha256(receipt_hashes),
        "counts": {
            "seed_receipts": len(source_summaries),
            "passed_seed_receipts": sum(1 for row in source_summaries if row.get("status") == EXPECTED_SOURCE_STATUS),
            "total_tau_call_attempts": sum(
                int(row["tau_call_attempts"]) for row in source_summaries if isinstance(row.get("tau_call_attempts"), int)
            ),
            "total_cases": sum(int(row["cases"]) for row in source_summaries if isinstance(row.get("cases"), int)),
            "total_planning_rows": len(all_rows),
            "action_switch_count": action_switch_count,
            "nonzero_delta_count": len(nonzero_rows),
            "nonzero_action_switch_count": sum(1 for row in nonzero_rows if row.get("action_switched") is True),
            "oracle_match_transitions": dict(transition_counts),
            "direction_counts": dict(direction_counts),
        },
        "planning": {
            "mean_cd_minus_baseline": _mean(deltas),
            "planning_regret_ci": ci,
            "planning_benefit_with_confidence": bool(ci and isinstance(ci.get("upper"), (int, float)) and ci["upper"] < 0),
        },
        "mocked": False,
        "live": all(row.get("status") == EXPECTED_SOURCE_STATUS for row in source_summaries),
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
        "at_least_two_seed_receipts": len(source_summaries) >= 2,
        "all_seed_receipts_passed": all(row.get("status") == EXPECTED_SOURCE_STATUS for row in source_summaries),
        "all_seed_receipts_live": all(row.get("tau_call_attempts") == 16 for row in source_summaries),
        "all_seed_receipts_have_four_episodes": all(row.get("episodes") == 4 for row in source_summaries),
        "all_seed_receipts_have_sixteen_cases": all(row.get("cases") == 16 for row in source_summaries),
        "planning_rows_cover_all_seed_episodes": len(all_rows) == 4 * len(source_summaries),
        "source_receipts_hash_bound": len(receipt_hashes) == len(source_summaries),
        "llm_judge_absent": True,
        "human_content_judgment_absent": True,
        "unsupported_writes_absent": True,
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_repeated_seed_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "source_receipts": [str(path) for path in receipt_paths],
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path),
        "planning_rows_path": str(repeated_rows_path),
        "planning_rows_sha256": _file_sha256(repeated_rows_path),
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
        "counts": summary["counts"],
        "checks": checks,
        "metrics": summary,
        "planning_benefit_with_confidence": summary["planning"]["planning_benefit_with_confidence"],
        "errors": errors,
        "claims": {
            "proves": [
                "multiple accepted floor4 trust/commitment live Tau replication receipts were hash-bound and aggregated",
                "repeated live Tau trust/commitment planning rows were recomputed without human content judgment or an LLM judge",
                "aggregate CD-minus-baseline planning-regret deltas were recomputed across repeated live Tau receipts",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the repeated-seed trust/commitment aggregation failed closed before accepting a repeated-seed planning claim",
            ],
            "does_not_prove": [
                "new live Tau execution inside this aggregate command",
                "planning benefit if the aggregate confidence interval crosses zero",
                "planning benefit on an expanded trust/commitment corpus beyond the consumed source receipts",
                "production retry machinery",
                "live Memory recall in the sealed-test loop",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
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
    parser.add_argument("--source-receipt", type=Path, action="append", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260725)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_trust_commit_repeated_seed_receipt.v1.json")
    receipt = summarize_repeated_seeds(
        receipt_paths=args.source_receipt,
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
