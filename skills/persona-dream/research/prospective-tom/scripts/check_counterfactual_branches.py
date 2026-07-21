#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 3 counterfactual branch invariants."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_COUNTERFACTUAL_BRANCHES"
BLOCKED_STATUS = "BLOCKED_COUNTERFACTUAL_BRANCHES"
EPSILON = 1e-6
VISIBLE_EVIDENCE_SCOPES = {"social_episode_observation", "social_episode_access"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _episode_index(corpus: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(corpus, dict):
        errors.append("corpus_not_object")
        return {}
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list):
        errors.append("corpus_episodes_not_list")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            errors.append(f"episode_{idx}_missing_episode_id")
            continue
        index[episode_id] = episode
    return index


def _visible_evidence_ids(episode: dict[str, Any]) -> set[tuple[str, str]]:
    episode_id = str(episode.get("episode_id"))
    refs: set[tuple[str, str]] = {("social_episode_access", f"{episode_id}:information_access_by_agent")}
    history = episode.get("observable_history")
    if isinstance(history, list):
        for idx, item in enumerate(history):
            if isinstance(item, dict):
                refs.add(("social_episode_observation", f"{episode_id}:observable_history:{idx}"))
    return refs


def _distribution_sum(entries: Any, prefix: str, errors: list[str]) -> bool:
    if not isinstance(entries, list) or not entries:
        errors.append(f"{prefix}_distribution_not_nonempty_list")
        return False
    total = 0.0
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{prefix}_distribution_{idx}_not_object")
            continue
        value = entry.get("value")
        probability = entry.get("probability")
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix}_distribution_{idx}_missing_value")
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{prefix}_distribution_{idx}_invalid_probability:{probability}")
            continue
        if probability < 0 or probability > 1:
            errors.append(f"{prefix}_distribution_{idx}_probability_out_of_range:{probability}")
        total += float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"{prefix}_distribution_sum:{total:.6f}")
        return False
    return True


def _distribution_index(bundle: Any, errors: list[str]) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("distribution_bundle_not_object")
        return None, {}
    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("distribution_bundle_missing_episode_id")
        episode_id = None
    if bundle.get("schema") != "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1":
        errors.append(f"invalid_distribution_bundle_schema:{bundle.get('schema')}")
    if bundle.get("sealed") is not True:
        errors.append("distribution_bundle_not_sealed")
    if bundle.get("outcome_visible") is not False:
        errors.append("distribution_bundle_outcome_visible_not_false")
    if bundle.get("canonical_memory_write") is not False:
        errors.append("distribution_bundle_canonical_memory_write_not_false")
    distributions = bundle.get("distributions")
    if not isinstance(distributions, list):
        errors.append("distribution_bundle_distributions_not_list")
        return episode_id, {}
    index: dict[str, dict[str, Any]] = {}
    for idx, distribution in enumerate(distributions):
        if not isinstance(distribution, dict):
            errors.append(f"distribution_bundle_{idx}_not_object")
            continue
        hypothesis_id = distribution.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"distribution_bundle_{idx}_missing_hypothesis_id")
            continue
        if hypothesis_id in index:
            errors.append(f"duplicate_distribution_hypothesis_id:{hypothesis_id}")
        index[hypothesis_id] = distribution
    return episode_id, index


def _check_branch_bundle(corpus_path: Path, distributions_path: Path, branch_path: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    distribution_bundle = _load_json(distributions_path, errors, "distribution_bundle")
    branch_bundle = _load_json(branch_path, errors, "branch_bundle")
    episodes = _episode_index(corpus, errors)
    distribution_episode_id, distributions = _distribution_index(distribution_bundle, errors)

    counts = {
        "branches": 0,
        "factual_branches": 0,
        "counterfactual_branches": 0,
        "interventions": 0,
        "resolved_source_evidence_refs": 0,
        "distribution_refs": 0,
    }
    checks = {
        "has_factual_branch": False,
        "has_counterfactual_branch": False,
        "counterfactuals_are_synthetic": True,
        "one_intervention_variable": True,
        "held_fixed_excludes_intervened_variable": True,
        "evidence_refs_resolve_to_visible_episode_fields": True,
        "distribution_refs_resolve": True,
        "factual_branches_use_factual_distributions": True,
        "counterfactual_branches_use_counterfactual_distributions": True,
        "action_distributions_valid": True,
        "no_canonical_memory_write": False,
        "outcome_not_visible": False,
    }

    if not isinstance(branch_bundle, dict):
        errors.append("branch_bundle_not_object")
        return errors, {"counts": counts, "checks": checks, "branch_bundle_sha256": None}
    if branch_bundle.get("schema") != "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1":
        errors.append(f"invalid_branch_bundle_schema:{branch_bundle.get('schema')}")
    if branch_bundle.get("outcome_visible") is not False:
        errors.append("branch_bundle_outcome_visible_not_false")
    if branch_bundle.get("canonical_memory_write") is not False:
        errors.append("branch_bundle_canonical_memory_write_not_false")
    checks["outcome_not_visible"] = branch_bundle.get("outcome_visible") is False
    checks["no_canonical_memory_write"] = branch_bundle.get("canonical_memory_write") is False

    episode_id = branch_bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("branch_bundle_missing_episode_id")
        episode = None
    else:
        episode = episodes.get(episode_id)
        if episode is None:
            errors.append(f"branch_bundle_episode_not_in_corpus:{episode_id}")
    if distribution_episode_id and episode_id != distribution_episode_id:
        errors.append(f"distribution_bundle_episode_mismatch:{distribution_episode_id}:{episode_id}")
    visible_refs = _visible_evidence_ids(episode) if episode else set()
    allowed_actions = set(episode.get("allowed_next_actions") or []) if episode else set()

    branches = branch_bundle.get("branches")
    if not isinstance(branches, list) or not branches:
        errors.append("branch_bundle_branches_not_nonempty_list")
        branches = []
    seen_branch_ids: set[str] = set()
    factual_ids: set[str] = set()
    counterfactual_ids: set[str] = set()
    intervened_variables: set[str] = set()

    for idx, branch in enumerate(branches):
        prefix = f"branch_{idx}"
        counts["branches"] += 1
        if not isinstance(branch, dict):
            errors.append(f"{prefix}_not_object")
            continue
        branch_id = branch.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id:
            errors.append(f"{prefix}_missing_branch_id")
        elif branch_id in seen_branch_ids:
            errors.append(f"duplicate_branch_id:{branch_id}")
        else:
            seen_branch_ids.add(branch_id)
        if branch.get("episode_id") != episode_id:
            errors.append(f"{prefix}_episode_mismatch:{branch.get('episode_id')}:{episode_id}")

        branch_type = branch.get("branch_type")
        synthetic = branch.get("synthetic")
        intervention = branch.get("intervention")
        if branch_type == "factual":
            counts["factual_branches"] += 1
            if isinstance(branch_id, str):
                factual_ids.add(branch_id)
            if synthetic is not False:
                errors.append(f"{prefix}_factual_synthetic_not_false")
            if intervention is not None:
                errors.append(f"{prefix}_factual_has_intervention")
            checks["has_factual_branch"] = True
        elif branch_type == "counterfactual":
            counts["counterfactual_branches"] += 1
            if isinstance(branch_id, str):
                counterfactual_ids.add(branch_id)
            checks["has_counterfactual_branch"] = True
            if synthetic is not True:
                errors.append(f"{prefix}_counterfactual_synthetic_not_true")
                checks["counterfactuals_are_synthetic"] = False
            if not isinstance(intervention, dict):
                errors.append(f"{prefix}_counterfactual_missing_intervention")
                checks["one_intervention_variable"] = False
            else:
                counts["interventions"] += 1
                if intervention.get("episode_id") != episode_id:
                    errors.append(f"{prefix}_intervention_episode_mismatch:{intervention.get('episode_id')}:{episode_id}")
                if intervention.get("synthetic") is not True:
                    errors.append(f"{prefix}_intervention_not_synthetic")
                    checks["counterfactuals_are_synthetic"] = False
                intervened_variable = intervention.get("intervened_variable")
                if not isinstance(intervened_variable, str) or not intervened_variable:
                    errors.append(f"{prefix}_missing_intervened_variable")
                    checks["one_intervention_variable"] = False
                else:
                    if intervened_variable in intervened_variables:
                        errors.append(f"duplicate_intervened_variable:{intervened_variable}")
                    intervened_variables.add(intervened_variable)
                held_fixed = intervention.get("held_fixed")
                if not isinstance(held_fixed, list) or not held_fixed:
                    errors.append(f"{prefix}_intervention_held_fixed_empty")
                elif intervened_variable in held_fixed:
                    errors.append(f"{prefix}_held_fixed_includes_intervened_variable:{intervened_variable}")
                    checks["held_fixed_excludes_intervened_variable"] = False
        else:
            errors.append(f"{prefix}_invalid_branch_type:{branch_type}")

        branch_held_fixed = branch.get("held_fixed")
        if not isinstance(branch_held_fixed, list):
            errors.append(f"{prefix}_held_fixed_not_list")
            branch_held_fixed = []
        if branch_type == "counterfactual" and isinstance(intervention, dict):
            intervened_variable = intervention.get("intervened_variable")
            if intervened_variable in branch_held_fixed:
                errors.append(f"{prefix}_branch_held_fixed_includes_intervened_variable:{intervened_variable}")
                checks["held_fixed_excludes_intervened_variable"] = False

        refs = branch.get("source_evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}_source_evidence_refs_empty")
            refs = []
        for ref_idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                errors.append(f"{prefix}_source_ref_{ref_idx}_not_object")
                continue
            scope = ref.get("scope")
            source_id = ref.get("source_id")
            if scope not in VISIBLE_EVIDENCE_SCOPES or not isinstance(source_id, str) or not source_id:
                errors.append(f"{prefix}_source_ref_{ref_idx}_invalid:{scope}:{source_id}")
                checks["evidence_refs_resolve_to_visible_episode_fields"] = False
                continue
            if (scope, source_id) not in visible_refs:
                errors.append(f"{prefix}_unresolved_or_hidden_source_ref:{scope}:{source_id}")
                checks["evidence_refs_resolve_to_visible_episode_fields"] = False
                continue
            counts["resolved_source_evidence_refs"] += 1

        distribution_refs = branch.get("predicted_bdi_distribution_refs")
        if not isinstance(distribution_refs, list) or not distribution_refs:
            errors.append(f"{prefix}_predicted_bdi_distribution_refs_empty")
            distribution_refs = []
        for ref in distribution_refs:
            counts["distribution_refs"] += 1
            if not isinstance(ref, str) or not ref:
                errors.append(f"{prefix}_invalid_distribution_ref:{ref}")
                checks["distribution_refs_resolve"] = False
                continue
            distribution = distributions.get(ref)
            if not distribution:
                errors.append(f"{prefix}_unresolved_distribution_ref:{ref}")
                checks["distribution_refs_resolve"] = False
                continue
            if branch_type == "factual" and distribution.get("counterfactual") is not False:
                errors.append(f"{prefix}_factual_branch_uses_counterfactual_distribution:{ref}")
                checks["factual_branches_use_factual_distributions"] = False
            if branch_type == "counterfactual" and distribution.get("counterfactual") is not True:
                errors.append(f"{prefix}_counterfactual_branch_uses_factual_distribution:{ref}")
                checks["counterfactual_branches_use_counterfactual_distributions"] = False

        if not _distribution_sum(branch.get("predicted_action_distribution"), f"{prefix}_action", errors):
            checks["action_distributions_valid"] = False
        action_entries = branch.get("predicted_action_distribution") if isinstance(branch.get("predicted_action_distribution"), list) else []
        for action_idx, action in enumerate(action_entries):
            if not isinstance(action, dict):
                continue
            value = action.get("value")
            if isinstance(value, str) and allowed_actions and value not in allowed_actions and value != "UNKNOWN":
                errors.append(f"{prefix}_action_distribution_{action_idx}_action_not_allowed:{value}")
                checks["action_distributions_valid"] = False
        expected_observation = branch.get("expected_observation")
        if not isinstance(expected_observation, str) or not expected_observation.strip():
            errors.append(f"{prefix}_missing_expected_observation")
        uncertainty = branch.get("uncertainty")
        if not isinstance(uncertainty, (int, float)) or isinstance(uncertainty, bool) or uncertainty < 0 or uncertainty > 1:
            errors.append(f"{prefix}_invalid_uncertainty:{uncertainty}")

    if not factual_ids:
        errors.append("missing_factual_branch")
        checks["has_factual_branch"] = False
    if not counterfactual_ids:
        errors.append("missing_counterfactual_branch")
        checks["has_counterfactual_branch"] = False
    if len(intervened_variables) != counts["counterfactual_branches"]:
        errors.append(f"counterfactual_intervened_variable_count_mismatch:{len(intervened_variables)}:{counts['counterfactual_branches']}")
        checks["one_intervention_variable"] = False

    return errors, {
        "counts": counts,
        "checks": checks,
        "branch_bundle_sha256": _stable_json_sha256(branch_bundle),
        "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
    }


def build_receipt(corpus_path: Path, distributions_path: Path, branch_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors, derived = _check_branch_bundle(corpus_path, distributions_path, branch_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.gate3_counterfactual_branch_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "distribution_bundle_path": str(distributions_path.resolve()),
        "branch_bundle_path": str(branch_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "branch_bundle_sha256": derived["branch_bundle_sha256"],
        "distribution_bundle_sha256": derived["distribution_bundle_sha256"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied branch bundle has factual and counterfactual branches",
                "counterfactual branches are marked synthetic and have one intervention variable",
                "held-fixed variables exclude the intervened variable",
                "branch evidence resolves to agent-visible episode fields",
                "branch BDI refs resolve to matching factual/counterfactual ToM distributions",
                "predicted action distributions sum to one over allowed actions",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid counterfactual branch bundle",
            ],
            "does_not_prove": [
                "model prediction accuracy",
                "counterfactual causal correctness",
                "calibration quality",
                "Tau text-call execution",
                "live Memory recall",
                "outcome reveal or scoring",
                "belief revision",
                "fault-injection reliability",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--distributions", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.distributions, args.branches, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
