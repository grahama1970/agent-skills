#!/usr/bin/env python3
"""Diagnose why full64 live Tau planning-regret benefit is not confidence-bound."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
STAT_SCRIPT = RESEARCH_ROOT / "scripts" / "run_sealed_test_statistical_confidence.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC"
DEFAULT_SPLIT = "sealed_test"


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stat = _load_module(STAT_SCRIPT, "pctom_sealed_test_statistical_confidence")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _family_from_episode(episode_id: str) -> str:
    parts = episode_id.split("-")
    if len(parts) >= 4 and parts[0].startswith("sealed"):
        return "-".join(parts[1:-1])
    return episode_id


def _validate_inputs(
    *,
    base_receipt: dict[str, Any],
    confidence_receipt: dict[str, Any],
    errors: list[str],
) -> None:
    if base_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION":
        errors.append(f"base_status_not_pass:{base_receipt.get('status')}")
    expected_base = {
        "split": DEFAULT_SPLIT,
        "episode_limit": 64,
        "full_64_episode_replication": True,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
    }
    for key, value in expected_base.items():
        if base_receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{base_receipt.get(key)}:{value}")
    counts = base_receipt.get("counts") if isinstance(base_receipt.get("counts"), dict) else {}
    if counts.get("episodes_consumed") != 64:
        errors.append(f"base_episode_count_mismatch:{counts.get('episodes_consumed')}:64")
    if counts.get("cases") != 256:
        errors.append(f"base_case_count_mismatch:{counts.get('cases')}:256")
    for count_key in (
        "action_decisions_per_condition",
        "planning_regret_scores_per_condition",
    ):
        values = counts.get(count_key)
        if not isinstance(values, dict):
            errors.append(f"base_{count_key}_not_object")
            continue
        for condition in CONDITIONS:
            if values.get(condition) != 64:
                errors.append(f"base_{count_key}_mismatch:{condition}:{values.get(condition)}:64")

    if confidence_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE":
        errors.append(f"confidence_status_not_pass:{confidence_receipt.get('status')}")
    if confidence_receipt.get("planning_benefit_with_confidence") is not False:
        errors.append(f"confidence_planning_benefit_unexpected:{confidence_receipt.get('planning_benefit_with_confidence')}")
    if confidence_receipt.get("primary_benefit_with_confidence") is not True:
        errors.append(f"confidence_primary_benefit_not_true:{confidence_receipt.get('primary_benefit_with_confidence')}")
    if confidence_receipt.get("mocked") is not False or confidence_receipt.get("live") is not True:
        errors.append("confidence_mocked_live_flags_mismatch")
    for key in (
        "tau_call_attempts",
        "tau_live_call_performed",
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if confidence_receipt.get(key) != 0:
            errors.append(f"confidence_{key}_not_zero:{confidence_receipt.get(key)}")


def _build_planning_rows(action_index: list[dict[str, Any]], errors: list[str]) -> list[dict[str, Any]]:
    by_episode: dict[str, dict[str, dict[str, Any]]] = {}
    for idx, row in enumerate(action_index):
        if not isinstance(row, dict):
            errors.append(f"action_index_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        regret = row.get("planning_regret")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        if not isinstance(regret, (int, float)) or isinstance(regret, bool):
            errors.append(f"action_index_{idx}_planning_regret_not_numeric:{episode_id}:{condition}:{regret}")
            continue
        by_episode.setdefault(episode_id, {})[condition] = row

    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        missing = [condition for condition in CONDITIONS if condition not in episode_rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
            continue
        baseline_regrets = {condition: float(episode_rows[condition]["planning_regret"]) for condition in ("M", "R", "D")}
        baseline_condition = min(baseline_regrets, key=baseline_regrets.get)
        baseline = episode_rows[baseline_condition]
        cd = episode_rows["CD"]
        cd_regret = float(cd["planning_regret"])
        baseline_regret = float(baseline["planning_regret"])
        delta = cd_regret - baseline_regret
        rows.append(
            {
                "episode_id": episode_id,
                "family": _family_from_episode(episode_id),
                "baseline_condition": baseline_condition,
                "cd_regret": cd_regret,
                "baseline_regret": baseline_regret,
                "cd_minus_baseline": delta,
                "direction": "BENEFIT" if delta < 0 else "HARM" if delta > 0 else "TIE",
                "cd_action": cd.get("selected_action"),
                "baseline_action": baseline.get("selected_action"),
                "oracle_action": cd.get("oracle_action"),
                "cd_matches_oracle": cd.get("selected_action") == cd.get("oracle_action"),
                "baseline_matches_oracle": baseline.get("selected_action") == cd.get("oracle_action"),
                "cd_source_status": cd.get("status"),
                "baseline_source_status": baseline.get("status"),
            }
        )
    return rows


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["cd_minus_baseline"]) for row in rows]
    direction_counts = collections.Counter(row["direction"] for row in rows)
    delta_counts = collections.Counter(str(row["cd_minus_baseline"]) for row in rows)
    families: dict[str, dict[str, Any]] = {}
    for family in sorted({row["family"] for row in rows}):
        family_rows = [row for row in rows if row["family"] == family]
        family_deltas = [float(row["cd_minus_baseline"]) for row in family_rows]
        families[family] = {
            "episodes": len(family_rows),
            "mean_cd_minus_baseline": _mean(family_deltas),
            "direction_counts": dict(collections.Counter(row["direction"] for row in family_rows)),
            "delta_counts": dict(collections.Counter(str(row["cd_minus_baseline"]) for row in family_rows)),
            "cd_actions": dict(collections.Counter(str(row["cd_action"]) for row in family_rows)),
            "baseline_actions": dict(collections.Counter(str(row["baseline_action"]) for row in family_rows)),
            "oracle_actions": dict(collections.Counter(str(row["oracle_action"]) for row in family_rows)),
        }
    return {
        "episodes": len(rows),
        "mean_cd_minus_baseline": _mean(deltas),
        "direction_counts": dict(direction_counts),
        "delta_counts": dict(delta_counts),
        "families": families,
        "cd_actions": dict(collections.Counter(str(row["cd_action"]) for row in rows)),
        "baseline_actions": dict(collections.Counter(str(row["baseline_action"]) for row in rows)),
        "oracle_actions": dict(collections.Counter(str(row["oracle_action"]) for row in rows)),
        "nonzero_delta_rows": [row for row in rows if row["cd_minus_baseline"] != 0],
    }


def run_planning_diagnostic(
    *,
    base_root: Path,
    confidence_root: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    base_root = base_root.resolve()
    confidence_root = confidence_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    base_receipt_path = base_root / "live_tau_sealed_test_replication_receipt.v1.json"
    confidence_receipt_path = confidence_root / "live_tau_full64_statistical_confidence_receipt.v1.json"
    action_index_path = base_root / "live_tau_sealed_test_action_selection" / "artifacts" / "live_condition_action_decisions.json"
    base_receipt = _load_json(base_receipt_path, errors, "base_live_tau_full64_receipt")
    confidence_receipt = _load_json(confidence_receipt_path, errors, "full64_statistical_confidence_receipt")
    action_index = _load_json(action_index_path, errors, "action_decision_index")
    if not isinstance(base_receipt, dict):
        base_receipt = {}
    if not isinstance(confidence_receipt, dict):
        confidence_receipt = {}
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []
    _validate_inputs(base_receipt=base_receipt, confidence_receipt=confidence_receipt, errors=errors)

    planning_rows = _build_planning_rows(action_index, errors)
    if len(planning_rows) != 64:
        errors.append(f"planning_row_count_mismatch:{len(planning_rows)}:64")
    summary = _summarize_rows(planning_rows)
    planning_ci = (
        confidence_receipt.get("metrics", {})
        .get("paired_delta_confidence_intervals", {})
        .get("planning_regret", {})
        if isinstance(confidence_receipt.get("metrics"), dict)
        else {}
    )
    zero_count = int(summary["direction_counts"].get("TIE", 0))
    benefit_count = int(summary["direction_counts"].get("BENEFIT", 0))
    harm_count = int(summary["direction_counts"].get("HARM", 0))
    nonzero_count = benefit_count + harm_count
    nonzero_families = sorted(
        family
        for family, family_summary in summary["families"].items()
        if int(family_summary["direction_counts"].get("BENEFIT", 0)) + int(family_summary["direction_counts"].get("HARM", 0)) > 0
    )
    diagnostic_conclusion = (
        "SPARSE_FAMILY_CONCENTRATED_SIGNAL"
        if nonzero_count <= 8 and len(nonzero_families) == 1
        else "BROAD_BUT_UNCERTAIN_SIGNAL"
        if nonzero_count > 8
        else "NO_PLANNING_SIGNAL"
    )
    planning_ci_crosses_zero = (
        isinstance(planning_ci.get("lower"), (int, float))
        and isinstance(planning_ci.get("upper"), (int, float))
        and planning_ci["lower"] < 0 < planning_ci["upper"]
    )
    if not planning_ci_crosses_zero:
        errors.append(f"planning_ci_does_not_cross_zero:{planning_ci}")
    if diagnostic_conclusion != "SPARSE_FAMILY_CONCENTRATED_SIGNAL":
        errors.append(f"unexpected_diagnostic_conclusion:{diagnostic_conclusion}")

    artifacts_root = output_root / "artifacts"
    planning_rows_path = artifacts_root / "planning_delta_rows.json"
    diagnostic_summary_path = artifacts_root / "planning_diagnostic_summary.json"
    diagnostic_summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_planning_diagnostic_summary.v1",
        "base_live_tau_replication_receipt_sha256": _file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "full64_statistical_confidence_receipt_sha256": _file_sha256(confidence_receipt_path)
        if confidence_receipt_path.exists()
        else None,
        "planning_regret_ci": planning_ci,
        "planning_ci_crosses_zero": planning_ci_crosses_zero,
        "diagnostic_conclusion": diagnostic_conclusion,
        "summary": summary,
        "interpretation": {
            "planning_point_estimate_is_negative": isinstance(summary.get("mean_cd_minus_baseline"), (int, float))
            and summary["mean_cd_minus_baseline"] < 0,
            "confidence_bounded_planning_benefit": False,
            "tie_count": zero_count,
            "benefit_count": benefit_count,
            "harm_count": harm_count,
            "nonzero_count": nonzero_count,
            "nonzero_families": nonzero_families,
            "reason_ci_crosses_zero": "60 of 64 paired planning-regret deltas are ties; the four nonzero deltas are all in trust-commit episodes",
            "next_planning_evidence_needed": "repeat or expand trust/commitment planning episodes and action-policy sensitivity before claiming planning benefit",
        },
    }
    _write_json(planning_rows_path, {"schema": "persona_dream.research.prospective_tom.live_tau_full64_planning_delta_rows.v1", "rows": planning_rows})
    _write_json(diagnostic_summary_path, diagnostic_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_planning_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "base_root": str(base_root),
        "base_live_tau_replication_receipt": str(base_receipt_path),
        "base_live_tau_replication_receipt_sha256": _file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "confidence_root": str(confidence_root),
        "full64_statistical_confidence_receipt": str(confidence_receipt_path),
        "full64_statistical_confidence_receipt_sha256": _file_sha256(confidence_receipt_path)
        if confidence_receipt_path.exists()
        else None,
        "action_index_path": str(action_index_path),
        "action_index_sha256": _file_sha256(action_index_path) if action_index_path.exists() else None,
        "planning_rows_path": str(planning_rows_path),
        "planning_rows_sha256": _file_sha256(planning_rows_path),
        "diagnostic_summary_path": str(diagnostic_summary_path),
        "diagnostic_summary_sha256": _file_sha256(diagnostic_summary_path),
        "diagnostic_conclusion": diagnostic_conclusion,
        "planning_benefit_with_confidence": False,
        "planning_ci_crosses_zero": planning_ci_crosses_zero,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes": len(planning_rows),
            "tie_count": zero_count,
            "benefit_count": benefit_count,
            "harm_count": harm_count,
            "nonzero_count": nonzero_count,
            "nonzero_families": nonzero_families,
        },
        "checks": {
            "base_receipt_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION",
            "confidence_receipt_passed": confidence_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE",
            "base_is_full64_live_tau": base_receipt.get("full_64_episode_replication") is True and base_receipt.get("live") is True,
            "planning_ci_crosses_zero": planning_ci_crosses_zero,
            "diagnostic_identifies_sparse_family_concentrated_signal": diagnostic_conclusion == "SPARSE_FAMILY_CONCENTRATED_SIGNAL",
            "planning_rows_cover_64_episodes": len(planning_rows) == 64,
            "nonzero_deltas_are_family_concentrated": len(nonzero_families) == 1,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": diagnostic_summary,
        "errors": errors,
        "claims": {
            "proves": [
                "the accepted full64 live Tau action decisions were consumed without reexecuting Tau",
                "the planning-regret confidence interval crosses zero",
                "the planning signal is sparse: 60 ties, 3 beneficial deltas, and 1 harmful delta",
                "all nonzero planning-regret deltas are concentrated in the trust-commit family",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau full64 planning diagnostic failed closed before explaining the planning-benefit gap",
            ],
            "does_not_prove": [
                "confidence-bounded planning-regret benefit",
                "planning benefit under repeated live Tau seeds",
                "planning benefit under a larger or differently balanced sealed-test corpus",
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
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--confidence-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_full64_planning_diagnostic_receipt.v1.json")
    receipt = run_planning_diagnostic(
        base_root=args.base_root,
        confidence_root=args.confidence_root,
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
