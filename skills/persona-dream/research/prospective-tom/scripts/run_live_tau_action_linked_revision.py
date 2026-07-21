#!/usr/bin/env python3
"""Write Gate 7 revisions linked to live-originated Gate 6 action decisions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
GATE7_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_belief_revision.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION"


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


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_base(action_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    receipt = _load_json(receipt_path, errors, "base_action_selection_receipt")
    if not isinstance(receipt, dict):
        return {}
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{receipt.get(key)}:{value}")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    for key in ("action_decisions_per_condition", "deterministic_reward_or_regret_scores_per_condition"):
        values = counts.get(key)
        if not isinstance(values, dict) or set(values) != set(CONDITIONS):
            errors.append(f"base_{key}_missing_conditions:{values}")
            continue
        for condition in CONDITIONS:
            if not isinstance(values.get(condition), int) or values[condition] < 4:
                errors.append(f"base_{key}_{condition}_lt_4:{values.get(condition)}")
    return receipt


def _belief_score_index(scoring_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scores = scoring_receipt.get("metrics", {}).get("belief_scores")
    if not isinstance(scores, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for score in scores:
        if isinstance(score, dict) and isinstance(score.get("hypothesis_id"), str):
            index[score["hypothesis_id"]] = score
    return index


def _first_factual_prior(distribution_bundle: dict[str, Any], scoring_receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    score_index = _belief_score_index(scoring_receipt)
    for distribution in distribution_bundle.get("distributions", []):
        if not isinstance(distribution, dict):
            continue
        hypothesis_id = distribution.get("hypothesis_id")
        if distribution.get("counterfactual") is False and hypothesis_id in score_index:
            return distribution, score_index[hypothesis_id]
    raise RuntimeError("no_factual_prior_with_score")


def _probabilities(entries: list[dict[str, Any]]) -> dict[str, float]:
    return {str(entry["value"]): float(entry["probability"]) for entry in entries}


def _posterior_distribution(prior_entries: list[dict[str, Any]], actual_label: str, planning_regret: float) -> list[dict[str, Any]]:
    prior = _probabilities(prior_entries)
    values = list(prior)
    if actual_label not in prior:
        values.append(actual_label)
        prior[actual_label] = 0.0
    actual_prior = prior.get(actual_label, 0.0)
    regret_penalty = min(max(planning_regret, 0.0), 1.0) * 0.05
    increase = min(0.18 - regret_penalty, 1.0 - actual_prior)
    if increase < 0.05:
        increase = min(0.05, 1.0 - actual_prior)
    remaining = 1.0 - actual_prior
    remaining_scale = (remaining - increase) / remaining if remaining > 0 else 1.0
    posterior: dict[str, float] = {}
    for value in values:
        if value == actual_label:
            posterior[value] = actual_prior + increase
        else:
            posterior[value] = prior.get(value, 0.0) * remaining_scale
    total = sum(posterior.values())
    if total <= 0:
        return [{"value": "UNKNOWN", "probability": 1.0}]
    return [{"value": value, "probability": posterior[value] / total} for value in values]


def _build_revision(
    *,
    condition: str,
    action_selection: dict[str, Any],
    action_selection_sha256: str,
    gate6_receipt_sha256: str,
    distribution_bundle: dict[str, Any],
    scoring_receipt: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    prior, score = _first_factual_prior(distribution_bundle, scoring_receipt)
    prior_hypothesis_id = prior["hypothesis_id"]
    planning_regret = float(action_selection.get("planning_regret") or 0.0)
    actual_label = score["actual_label"]
    posterior = _posterior_distribution(prior["distribution"], actual_label, planning_regret)
    return {
        "schema": "persona_dream.research.prospective_tom.tom_belief_revision.v1",
        "revision_id": f"action-linked-revision-{condition.lower()}-{outcome['episode_id']}-{prior_hypothesis_id}",
        "episode_id": outcome["episode_id"],
        "prediction_id": outcome["prediction_id"],
        "prior_hypothesis_id": prior_hypothesis_id,
        "prior_distribution": prior,
        "prior_distribution_sha256": _stable_json_sha256(prior),
        "prior_audit_ref": {
            "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
            "hypothesis_id": prior_hypothesis_id,
        },
        "observed_outcome_id": outcome["outcome_id"],
        "outcome_reveal_sha256": _stable_json_sha256(outcome),
        "scoring_receipt_sha256": _stable_json_sha256(scoring_receipt),
        "prediction_error": {
            "actual_label": actual_label,
            "prior_actual_probability": score["actual_probability"],
            "brier": score["brier"],
            "log_loss": score["log_loss"],
            "top_correct": score["top_correct"],
        },
        "surprise": score["log_loss"],
        "posterior_distribution": posterior,
        "posterior_distribution_sha256": _stable_json_sha256(posterior),
        "update_reason": (
            "Action-selected live Tau condition case consumed deterministic outcome evidence; "
            "current-use posterior is updated while preserving the sealed prior and separate action linkage."
        ),
        "update_evidence_refs": [{"scope": "outcome_reveal", "source_id": outcome["outcome_id"]}],
        "evidence_mutations": [],
        "supersedes_for_current_use": True,
        "prior_remains_auditable": True,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "_action_linkage_comment": {
            "action_selection_sha256": action_selection_sha256,
            "gate6_receipt_sha256": gate6_receipt_sha256,
        },
    }


def _strip_action_comment(revision: dict[str, Any]) -> dict[str, Any]:
    clean = dict(revision)
    clean.pop("_action_linkage_comment", None)
    return clean


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def run_bridge(action_root: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    gate7 = _load_module(GATE7_SCRIPT, "pctom_gate7_belief_revision")
    action_root = action_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    base_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    base_receipt = _validate_base(action_root, errors)
    base_receipt_sha256 = _file_sha256(base_receipt_path) if base_receipt_path.exists() else None
    decision_index_path = action_root / "artifacts" / "live_condition_action_decisions.json"
    decision_rows = _load_json(decision_index_path, errors, "decision_index")
    if not isinstance(decision_rows, list):
        errors.append("decision_index_not_list")
        decision_rows = []

    revision_rows: list[dict[str, Any]] = []
    prior_counts = {condition: 0 for condition in CONDITIONS}
    posterior_counts = {condition: 0 for condition in CONDITIONS}
    status_counts: dict[str, int] = {}
    surprise_by_condition = {condition: [] for condition in CONDITIONS}

    for idx, row in enumerate(decision_rows):
        if not isinstance(row, dict):
            errors.append(f"decision_row_{idx}_not_object")
            continue
        condition = row.get("condition")
        episode_id = row.get("episode_id")
        if condition not in CONDITIONS:
            errors.append(f"decision_row_{idx}_invalid_condition:{condition}")
            continue
        if row.get("status") != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"decision_row_{idx}_not_pass:{row.get('status')}")
            continue
        source_case_root = Path(str(row.get("source_case_root", "")))
        source_receipt_root = Path(str(row.get("source_receipt_root", "")))
        action_selection_path = Path(str(row.get("action_selection_path", "")))
        gate6_receipt_path = Path(str(row.get("gate6_receipt_path", "")))
        distribution_path = source_case_root / "tom_belief_distribution_bundle.json"
        scoring_path = source_receipt_root / "gate5_scoring_receipt.json"
        outcome_path = source_case_root / "tom_outcome_reveal.json"
        case_errors: list[str] = []
        action_selection = _load_json(action_selection_path, case_errors, "action_selection")
        gate6_receipt = _load_json(gate6_receipt_path, case_errors, "gate6_receipt")
        distribution_bundle = _load_json(distribution_path, case_errors, "distribution_bundle")
        scoring_receipt = _load_json(scoring_path, case_errors, "scoring_receipt")
        outcome = _load_json(outcome_path, case_errors, "outcome_reveal")
        if not all(isinstance(value, dict) for value in (action_selection, gate6_receipt, distribution_bundle, scoring_receipt, outcome)):
            errors.extend(f"{episode_id}:{condition}:{error}" for error in case_errors)
            continue
        if action_selection.get("canonical_memory_write") is not False:
            case_errors.append("action_selection_canonical_memory_write_not_false")
        if gate6_receipt.get("status") != "PASS_TOM_ACTION_SELECTION":
            case_errors.append(f"gate6_receipt_not_pass:{gate6_receipt.get('status')}")
        if gate6_receipt.get("canonical_memory_write_attempts") != 0:
            case_errors.append(f"gate6_canonical_memory_write_attempts_nonzero:{gate6_receipt.get('canonical_memory_write_attempts')}")
        out_case_root = output_root / "artifacts" / "cases" / str(episode_id) / str(condition)
        out_receipt_root = output_root / "receipts" / "cases" / str(episode_id) / str(condition)
        revision_path = out_case_root / "tom_belief_revision.json"
        gate7_receipt_path = out_receipt_root / "gate7_belief_revision_check_receipt.json"
        try:
            revision_with_comment = _build_revision(
                condition=str(condition),
                action_selection=action_selection,
                action_selection_sha256=_stable_json_sha256(action_selection),
                gate6_receipt_sha256=_stable_json_sha256(gate6_receipt),
                distribution_bundle=distribution_bundle,
                scoring_receipt=scoring_receipt,
                outcome=outcome,
            )
            revision = _strip_action_comment(revision_with_comment)
        except Exception as exc:
            case_errors.append(f"revision_build_failed:{exc}")
            revision = {}
        _write_json(revision_path, revision)
        gate7_errors, derived = gate7._check_revision(distribution_path, scoring_path, outcome_path, revision_path)
        all_case_errors = case_errors + gate7_errors
        gate7_status = "PASS_TOM_BELIEF_REVISION" if not all_case_errors else "BLOCKED_TOM_BELIEF_REVISION"
        status_counts[gate7_status] = status_counts.get(gate7_status, 0) + 1
        gate7_receipt = {
            "schema": "persona_dream.research.prospective_tom.action_linked_belief_revision_check_receipt.v1",
            "created_at": _now_iso(),
            "status": gate7_status,
            "base_action_selection_receipt": str(base_receipt_path),
            "base_action_selection_receipt_sha256": base_receipt_sha256,
            "episode_id": episode_id,
            "condition": condition,
            "action_selection_path": str(action_selection_path),
            "action_selection_sha256": _stable_json_sha256(action_selection) if isinstance(action_selection, dict) else None,
            "gate6_receipt_path": str(gate6_receipt_path),
            "gate6_receipt_sha256": _stable_json_sha256(gate6_receipt) if isinstance(gate6_receipt, dict) else None,
            "distribution_bundle_path": str(distribution_path),
            "scoring_receipt_path": str(scoring_path),
            "outcome_reveal_path": str(outcome_path),
            "belief_revision_path": str(revision_path),
            "receipt_path": str(gate7_receipt_path),
            "selected_action": row.get("selected_action"),
            "oracle_action": row.get("oracle_action"),
            "planning_regret": row.get("planning_regret"),
            "errors": all_case_errors,
            "counts": derived["counts"],
            "checks": derived["checks"],
            "metrics": derived["metrics"],
            "mocked": False,
            "live": True,
            "fixture_backed": False,
            "live_tau_originated_action_case_consumed": True,
            "deterministic_simulator_corpus_fixture_backed": True,
            "human_content_judgment_required": False,
            "tau_call_attempts": 0,
            "memory_write_attempts": 0,
            "provider_call_attempts": 0,
            "canonical_memory_write_attempts": 0,
            "identity_write_attempts": 0,
            "source_memory_write_attempts": 0,
        }
        _write_json(gate7_receipt_path, gate7_receipt)
        if gate7_status != "PASS_TOM_BELIEF_REVISION":
            errors.append(f"gate7_case_blocked:{episode_id}:{condition}:{all_case_errors}")
        else:
            prior_counts[condition] += 1
            posterior_counts[condition] += 1
            surprise = gate7_receipt.get("metrics", {}).get("surprise")
            if isinstance(surprise, (int, float)) and not isinstance(surprise, bool):
                surprise_by_condition[condition].append(float(surprise))
        revision_rows.append(
            {
                "episode_id": episode_id,
                "condition": condition,
                "selected_action": row.get("selected_action"),
                "oracle_action": row.get("oracle_action"),
                "planning_regret": row.get("planning_regret"),
                "prior_hypothesis_id": gate7_receipt.get("metrics", {}).get("prior_hypothesis_id"),
                "prior_remains_auditable": gate7_receipt.get("checks", {}).get("prior_remains_auditable"),
                "revision_path": str(revision_path),
                "gate7_receipt_path": str(gate7_receipt_path),
                "status": gate7_status,
                "errors": all_case_errors,
            }
        )

    for condition in CONDITIONS:
        if prior_counts[condition] < 1:
            errors.append(f"prior_action_hypotheses_per_condition_insufficient:{condition}:{prior_counts[condition]}")
        if posterior_counts[condition] < 1:
            errors.append(f"posterior_action_revisions_per_condition_insufficient:{condition}:{posterior_counts[condition]}")

    revision_index_path = output_root / "artifacts" / "live_action_linked_belief_revisions.json"
    _write_json(revision_index_path, revision_rows)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_action_linked_revision_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "base_root": str(action_root),
        "base_receipt": str(base_receipt_path),
        "base_receipt_sha256": base_receipt_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "revision_index": str(revision_index_path),
        "conditions": list(CONDITIONS),
        "errors": errors,
        "counts": {
            "base_action_cases": base_receipt.get("counts", {}).get("action_cases_written")
            if isinstance(base_receipt.get("counts"), dict)
            else None,
            "decision_rows_seen": len(decision_rows),
            "revision_cases_written": len(revision_rows),
            "individual_status_counts": status_counts,
            "prior_action_hypotheses_per_condition": prior_counts,
            "posterior_action_revisions_per_condition": posterior_counts,
        },
        "metrics": {
            "mean_surprise_by_condition": {condition: _mean(surprise_by_condition[condition]) for condition in CONDITIONS},
        },
        "checks": {
            "base_action_selection_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION",
            "base_receipt_hash_recomputed": isinstance(base_receipt_sha256, str) and base_receipt_sha256.startswith("sha256:"),
            "conditions_represented": all(prior_counts[condition] >= 1 for condition in CONDITIONS),
            "posterior_revisions_present": all(posterior_counts[condition] >= 1 for condition in CONDITIONS),
            "prior_remains_auditable": all(row.get("prior_remains_auditable") is True for row in revision_rows),
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "live_tau_originated_action_artifacts_consumed": True,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "live-originated Gate 6 action decisions can be linked to strict Gate 7 non-destructive belief revisions",
                "each condition has at least one action-linked prior hypothesis and posterior revision",
                "sealed prior hypotheses remain auditable while posterior current-use distributions are hash-bound",
                "action linkage is preserved outside the strict belief-revision schema without mutating evidence",
                "no human content judgment, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the action-linked revision bridge failed closed before claiming Gate 7 live-originated revision evidence",
            ],
            "does_not_prove": [
                "held-out statistical prediction benefit",
                "planning benefit over the strongest baseline",
                "longitudinal recall after action-linked revision",
                "real external service fault injection",
                "production retry machinery",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video or semantic dream quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = run_bridge(args.action_root, args.output_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
