#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 4 sealed prediction commitments."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_PREDICTION_COMMITMENTS"
BLOCKED_STATUS = "BLOCKED_TOM_PREDICTION_COMMITMENTS"
EPSILON = 1e-6
CONDITIONS = {"M", "R", "D", "CD", "ORACLE_DIAGNOSTIC"}
VISIBLE_EVIDENCE_SCOPES = {"social_episode_observation", "social_episode_access"}
FORBIDDEN_OUTCOME_KEYS = {
    "actual_next_action",
    "hidden_world_state",
    "ground_truth_tom_labels",
    "outcome",
    "outcome_reveal",
    "observed_outcome",
    "revealed_outcome",
    "score",
    "scoring_receipt",
}


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
        if episode_id in index:
            errors.append(f"duplicate_episode_id:{episode_id}")
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
    index: dict[str, dict[str, Any]] = {}
    distributions = bundle.get("distributions")
    if not isinstance(distributions, list):
        errors.append("distribution_bundle_distributions_not_list")
        return episode_id, index
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


def _branch_index(bundle: Any, errors: list[str]) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("branch_bundle_not_object")
        return None, {}
    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("branch_bundle_missing_episode_id")
        episode_id = None
    if bundle.get("schema") != "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1":
        errors.append(f"invalid_branch_bundle_schema:{bundle.get('schema')}")
    if bundle.get("outcome_visible") is not False:
        errors.append("branch_bundle_outcome_visible_not_false")
    if bundle.get("canonical_memory_write") is not False:
        errors.append("branch_bundle_canonical_memory_write_not_false")
    index: dict[str, dict[str, Any]] = {}
    branches = bundle.get("branches")
    if not isinstance(branches, list):
        errors.append("branch_bundle_branches_not_list")
        return episode_id, index
    for idx, branch in enumerate(branches):
        if not isinstance(branch, dict):
            errors.append(f"branch_bundle_{idx}_not_object")
            continue
        branch_id = branch.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id:
            errors.append(f"branch_bundle_{idx}_missing_branch_id")
            continue
        if branch_id in index:
            errors.append(f"duplicate_branch_id:{branch_id}")
        index[branch_id] = branch
    return episode_id, index


def _collect_forbidden_paths(value: Any, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_OUTCOME_KEYS:
                paths.append(child_path)
            paths.extend(_collect_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            paths.extend(_collect_forbidden_paths(child, f"{prefix}[{idx}]"))
    return paths


def _check_distribution(entries: Any, prefix: str, errors: list[str]) -> bool:
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


def _refs_from(value: Any, key: str) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return value[key]
    return []


def _check_source_refs(refs: list[Any], visible_refs: set[tuple[str, str]], prefix: str, errors: list[str]) -> int:
    resolved = 0
    for idx, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"{prefix}_source_ref_{idx}_not_object")
            continue
        scope = ref.get("scope")
        source_id = ref.get("source_id")
        if scope not in VISIBLE_EVIDENCE_SCOPES or not isinstance(source_id, str) or not source_id:
            errors.append(f"{prefix}_source_ref_{idx}_invalid:{scope}:{source_id}")
            continue
        if (scope, source_id) not in visible_refs:
            errors.append(f"{prefix}_unresolved_or_hidden_source_ref:{scope}:{source_id}")
            continue
        resolved += 1
    return resolved


def _check_commitment_bundle(
    corpus_path: Path,
    distributions_path: Path,
    branches_path: Path,
    commitments_path: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    distribution_bundle = _load_json(distributions_path, errors, "distribution_bundle")
    branch_bundle = _load_json(branches_path, errors, "branch_bundle")
    commitment_bundle = _load_json(commitments_path, errors, "commitment_bundle")
    episodes = _episode_index(corpus, errors)
    distribution_episode_id, distributions = _distribution_index(distribution_bundle, errors)
    branch_episode_id, branches = _branch_index(branch_bundle, errors)

    counts = {
        "commitments": 0,
        "conditions": 0,
        "branch_refs": 0,
        "distribution_refs": 0,
        "resolved_source_evidence_refs": 0,
        "hashes_checked": 0,
        "forbidden_outcome_paths": 0,
    }
    checks = {
        "bundle_sealed_before_reveal": False,
        "no_canonical_memory_write": False,
        "payload_hashes_match": True,
        "model_receipt_hashes_match": True,
        "evidence_bundle_hashes_match": True,
        "upstream_bundle_hashes_match": True,
        "branch_refs_resolve": True,
        "distribution_refs_resolve": True,
        "evidence_refs_resolve": True,
        "prediction_distributions_sum_to_one": True,
        "outcome_absent_from_commitment": True,
        "no_prediction_edits_after_reveal": True,
    }

    branch_bundle_sha256 = _stable_json_sha256(branch_bundle) if isinstance(branch_bundle, dict) else None
    distribution_bundle_sha256 = _stable_json_sha256(distribution_bundle) if isinstance(distribution_bundle, dict) else None

    if not isinstance(commitment_bundle, dict):
        errors.append("commitment_bundle_not_object")
        return errors, {
            "counts": counts,
            "checks": checks,
            "commitment_bundle_sha256": None,
            "branch_bundle_sha256": branch_bundle_sha256,
            "distribution_bundle_sha256": distribution_bundle_sha256,
        }

    if commitment_bundle.get("schema") != "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1":
        errors.append(f"invalid_commitment_bundle_schema:{commitment_bundle.get('schema')}")
    if commitment_bundle.get("sealed") is not True:
        errors.append("commitment_bundle_not_sealed")
    if commitment_bundle.get("outcome_visible") is not False:
        errors.append("commitment_bundle_outcome_visible_not_false")
    if commitment_bundle.get("canonical_memory_write") is not False:
        errors.append("commitment_bundle_canonical_memory_write_not_false")
    checks["bundle_sealed_before_reveal"] = (
        commitment_bundle.get("sealed") is True and commitment_bundle.get("outcome_visible") is False
    )
    checks["no_canonical_memory_write"] = commitment_bundle.get("canonical_memory_write") is False

    episode_id = commitment_bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("commitment_bundle_missing_episode_id")
        episode = None
    else:
        episode = episodes.get(episode_id)
        if episode is None:
            errors.append(f"commitment_bundle_episode_not_in_corpus:{episode_id}")
    if distribution_episode_id and episode_id != distribution_episode_id:
        errors.append(f"distribution_bundle_episode_mismatch:{distribution_episode_id}:{episode_id}")
    if branch_episode_id and episode_id != branch_episode_id:
        errors.append(f"branch_bundle_episode_mismatch:{branch_episode_id}:{episode_id}")
    visible_refs = _visible_evidence_ids(episode) if episode else set()

    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or not commitments:
        errors.append("commitment_bundle_commitments_not_nonempty_list")
        commitments = []
    seen_prediction_ids: set[str] = set()
    seen_conditions: set[str] = set()
    for idx, commitment in enumerate(commitments):
        prefix = f"commitment_{idx}"
        counts["commitments"] += 1
        if not isinstance(commitment, dict):
            errors.append(f"{prefix}_not_object")
            continue
        prediction_id = commitment.get("prediction_id")
        if not isinstance(prediction_id, str) or not prediction_id:
            errors.append(f"{prefix}_missing_prediction_id")
        elif prediction_id in seen_prediction_ids:
            errors.append(f"duplicate_prediction_id:{prediction_id}")
        else:
            seen_prediction_ids.add(prediction_id)
        if commitment.get("episode_id") != episode_id:
            errors.append(f"{prefix}_episode_mismatch:{commitment.get('episode_id')}:{episode_id}")
        condition = commitment.get("condition")
        if condition not in CONDITIONS:
            errors.append(f"{prefix}_invalid_condition:{condition}")
        elif condition not in seen_conditions:
            seen_conditions.add(str(condition))
            counts["conditions"] += 1
        if not isinstance(commitment.get("sealed_at"), str) or not commitment.get("sealed_at"):
            errors.append(f"{prefix}_missing_sealed_at")
        if commitment.get("outcome_visible") is not False:
            errors.append(f"{prefix}_outcome_visible_not_false")
            checks["no_prediction_edits_after_reveal"] = False
        if commitment.get("canonical_memory_write") not in (None, False):
            errors.append(f"{prefix}_canonical_memory_write_not_false")
            checks["no_canonical_memory_write"] = False
        if commitment.get("revision_of") not in (None, ""):
            errors.append(f"{prefix}_revision_of_not_allowed_before_reveal")
            checks["no_prediction_edits_after_reveal"] = False
        if commitment.get("edited_after_reveal") not in (None, False):
            errors.append(f"{prefix}_edited_after_reveal_not_false")
            checks["no_prediction_edits_after_reveal"] = False

        payload = commitment.get("prediction_payload")
        model_receipts = commitment.get("model_receipts")
        evidence_bundle = commitment.get("evidence_bundle")
        if not isinstance(payload, dict):
            errors.append(f"{prefix}_prediction_payload_not_object")
            payload = {}
        if not isinstance(model_receipts, list):
            errors.append(f"{prefix}_model_receipts_not_list")
            model_receipts = []
        if not isinstance(evidence_bundle, dict):
            errors.append(f"{prefix}_evidence_bundle_not_object")
            evidence_bundle = {}

        expected_payload_hash = _stable_json_sha256(payload)
        expected_model_hash = _stable_json_sha256(model_receipts)
        expected_evidence_hash = _stable_json_sha256(evidence_bundle)
        counts["hashes_checked"] += 3
        if commitment.get("prediction_payload_sha256") != expected_payload_hash:
            errors.append(f"{prefix}_prediction_payload_sha256_mismatch:{commitment.get('prediction_payload_sha256')}:{expected_payload_hash}")
            checks["payload_hashes_match"] = False
        if commitment.get("model_receipts_sha256") != expected_model_hash:
            errors.append(f"{prefix}_model_receipts_sha256_mismatch:{commitment.get('model_receipts_sha256')}:{expected_model_hash}")
            checks["model_receipt_hashes_match"] = False
        if commitment.get("evidence_bundle_sha256") != expected_evidence_hash:
            errors.append(f"{prefix}_evidence_bundle_sha256_mismatch:{commitment.get('evidence_bundle_sha256')}:{expected_evidence_hash}")
            checks["evidence_bundle_hashes_match"] = False

        if evidence_bundle.get("branch_bundle_sha256") != branch_bundle_sha256:
            errors.append(f"{prefix}_branch_bundle_sha256_mismatch:{evidence_bundle.get('branch_bundle_sha256')}:{branch_bundle_sha256}")
            checks["upstream_bundle_hashes_match"] = False
        if evidence_bundle.get("distribution_bundle_sha256") != distribution_bundle_sha256:
            errors.append(f"{prefix}_distribution_bundle_sha256_mismatch:{evidence_bundle.get('distribution_bundle_sha256')}:{distribution_bundle_sha256}")
            checks["upstream_bundle_hashes_match"] = False

        forbidden_paths = (
            _collect_forbidden_paths(payload, f"{prefix}.prediction_payload")
            + _collect_forbidden_paths(evidence_bundle, f"{prefix}.evidence_bundle")
        )
        if forbidden_paths:
            errors.extend(f"{prefix}_forbidden_outcome_field:{path}" for path in forbidden_paths)
            counts["forbidden_outcome_paths"] += len(forbidden_paths)
            checks["outcome_absent_from_commitment"] = False
        if payload.get("outcome_visible") is not False:
            errors.append(f"{prefix}_payload_outcome_visible_not_false")
            checks["no_prediction_edits_after_reveal"] = False

        branch_refs = _refs_from(payload, "branch_refs") + _refs_from(evidence_bundle, "branch_refs")
        distribution_refs = _refs_from(payload, "belief_distribution_refs") + _refs_from(evidence_bundle, "belief_distribution_refs")
        source_refs = _refs_from(payload, "evidence_refs") + _refs_from(evidence_bundle, "source_evidence_refs")
        for branch_ref in branch_refs:
            counts["branch_refs"] += 1
            if not isinstance(branch_ref, str) or not branch_ref:
                errors.append(f"{prefix}_invalid_branch_ref:{branch_ref}")
                checks["branch_refs_resolve"] = False
            elif branch_ref not in branches:
                errors.append(f"{prefix}_unresolved_branch_ref:{branch_ref}")
                checks["branch_refs_resolve"] = False
        for distribution_ref in distribution_refs:
            counts["distribution_refs"] += 1
            if not isinstance(distribution_ref, str) or not distribution_ref:
                errors.append(f"{prefix}_invalid_distribution_ref:{distribution_ref}")
                checks["distribution_refs_resolve"] = False
            elif distribution_ref not in distributions:
                errors.append(f"{prefix}_unresolved_distribution_ref:{distribution_ref}")
                checks["distribution_refs_resolve"] = False
        resolved_refs = _check_source_refs(source_refs, visible_refs, prefix, errors)
        counts["resolved_source_evidence_refs"] += resolved_refs
        if resolved_refs != len(source_refs):
            checks["evidence_refs_resolve"] = False

        if "predicted_next_action_distribution" in payload:
            if not _check_distribution(payload.get("predicted_next_action_distribution"), f"{prefix}_predicted_action", errors):
                checks["prediction_distributions_sum_to_one"] = False

    return errors, {
        "counts": counts,
        "checks": checks,
        "commitment_bundle_sha256": _stable_json_sha256(commitment_bundle),
        "branch_bundle_sha256": branch_bundle_sha256,
        "distribution_bundle_sha256": distribution_bundle_sha256,
    }


def build_receipt(
    corpus_path: Path,
    distributions_path: Path,
    branches_path: Path,
    commitments_path: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    errors, derived = _check_commitment_bundle(corpus_path, distributions_path, branches_path, commitments_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.gate4_prediction_commitment_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "distribution_bundle_path": str(distributions_path.resolve()),
        "branch_bundle_path": str(branches_path.resolve()),
        "commitment_bundle_path": str(commitments_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "commitment_bundle_sha256": derived["commitment_bundle_sha256"],
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
                "the supplied prediction commitments are sealed before outcome reveal",
                "prediction payloads, model receipts, and evidence bundles are hash-bound",
                "upstream Gate 2 and Gate 3 bundle hashes match the committed evidence bundle",
                "branch, distribution, and visible source-evidence references resolve",
                "forbidden outcome/ground-truth fields are absent from commitments",
                "canonical memory writes and post-reveal edits are absent",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid sealed prediction commitment bundle",
            ],
            "does_not_prove": [
                "model prediction accuracy",
                "calibration quality",
                "outcome reveal execution",
                "deterministic scoring",
                "belief revision",
                "Tau text-call execution",
                "live Memory recall",
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
    parser.add_argument("--commitments", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.distributions, args.branches, args.commitments, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
