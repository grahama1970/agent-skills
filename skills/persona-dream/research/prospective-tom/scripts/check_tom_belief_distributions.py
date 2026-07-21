#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 2 ToM distribution invariants."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_BELIEF_DISTRIBUTIONS"
BLOCKED_STATUS = "BLOCKED_TOM_BELIEF_DISTRIBUTIONS"
EPSILON = 1e-6
ALLOWED_EVIDENCE_SCOPES = {
    "social_episode_observation",
    "social_episode_access",
    "memory_residue",
    "synthetic_counterfactual",
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
    visible: set[tuple[str, str]] = {
        ("social_episode_access", f"{episode_id}:information_access_by_agent")
    }
    observable_history = episode.get("observable_history")
    if isinstance(observable_history, list):
        for idx, item in enumerate(observable_history):
            if isinstance(item, dict):
                visible.add(("social_episode_observation", f"{episode_id}:observable_history:{idx}"))
    return visible


def _label_keys(episode: dict[str, Any]) -> set[tuple[int, str, str, str, str]]:
    keys: set[tuple[int, str, str, str, str]] = set()
    labels = episode.get("ground_truth_tom_labels")
    if not isinstance(labels, list):
        return keys
    for label in labels:
        if not isinstance(label, dict):
            continue
        values = (
            label.get("perspective_order"),
            label.get("subject"),
            label.get("target"),
            label.get("mental_state_type"),
            label.get("proposition"),
        )
        if isinstance(values[0], int) and all(isinstance(value, str) and value for value in values[1:]):
            keys.add((values[0], values[1], values[2], values[3], values[4]))
    return keys


def _distribution_sum(distribution: Any, prefix: str, errors: list[str]) -> tuple[bool, float, bool]:
    if not isinstance(distribution, list) or not distribution:
        errors.append(f"{prefix}_distribution_not_nonempty_list")
        return False, 0.0, False
    total = 0.0
    unknown_probability = 0.0
    has_unknown = False
    for idx, entry in enumerate(distribution):
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
        if value == "UNKNOWN":
            has_unknown = True
            unknown_probability += float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"{prefix}_distribution_sum:{total:.6f}")
    return abs(total - 1.0) <= EPSILON, total, has_unknown and abs(unknown_probability - 1.0) <= EPSILON


def _check_bundle(corpus_path: Path, bundle_path: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    bundle = _load_json(bundle_path, errors, "bundle")
    episodes = _episode_index(corpus, errors)

    counts = {
        "distributions": 0,
        "supported": 0,
        "abstained_or_pending": 0,
        "resolved_evidence_refs": 0,
        "counterfactual_distributions": 0,
        "label_matched_distributions": 0,
    }
    checks = {
        "bundle_sealed_before_reveal": False,
        "no_canonical_memory_write": False,
        "probabilities_sum_to_one": True,
        "evidence_refs_resolve": True,
        "perspectives_match_episode_labels": True,
        "unsupported_abstains_or_pending": True,
        "counterfactuals_explicitly_marked": True,
        "counterfactual_not_literal_history": True,
    }

    if not isinstance(bundle, dict):
        errors.append("bundle_not_object")
        return errors, {"counts": counts, "checks": checks, "bundle_sha256": None}

    if bundle.get("schema") != "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1":
        errors.append(f"invalid_bundle_schema:{bundle.get('schema')}")
    if bundle.get("sealed") is not True:
        errors.append("bundle_not_sealed")
    if bundle.get("outcome_visible") is not False:
        errors.append("bundle_outcome_visible_not_false")
    if bundle.get("canonical_memory_write") is not False:
        errors.append("bundle_canonical_memory_write_not_false")
    checks["bundle_sealed_before_reveal"] = bundle.get("sealed") is True and bundle.get("outcome_visible") is False
    checks["no_canonical_memory_write"] = bundle.get("canonical_memory_write") is False

    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("bundle_missing_episode_id")
        episode = None
    else:
        episode = episodes.get(episode_id)
        if episode is None:
            errors.append(f"bundle_episode_not_in_corpus:{episode_id}")
    visible_refs = _visible_evidence_ids(episode) if episode else set()
    label_keys = _label_keys(episode) if episode else set()

    distributions = bundle.get("distributions")
    if not isinstance(distributions, list) or not distributions:
        errors.append("bundle_distributions_not_nonempty_list")
        distributions = []
    seen_hypothesis_ids: set[str] = set()
    for idx, distribution in enumerate(distributions):
        prefix = f"distribution_{idx}"
        counts["distributions"] += 1
        if not isinstance(distribution, dict):
            errors.append(f"{prefix}_not_object")
            continue
        hypothesis_id = distribution.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"{prefix}_missing_hypothesis_id")
        elif hypothesis_id in seen_hypothesis_ids:
            errors.append(f"duplicate_hypothesis_id:{hypothesis_id}")
        else:
            seen_hypothesis_ids.add(hypothesis_id)
        if distribution.get("episode_id") != episode_id:
            errors.append(f"{prefix}_episode_mismatch:{distribution.get('episode_id')}:{episode_id}")
        probability_ok, _total, unknown_certain = _distribution_sum(distribution.get("distribution"), prefix, errors)
        if not probability_ok:
            checks["probabilities_sum_to_one"] = False

        perspective_order = distribution.get("perspective_order")
        subject = distribution.get("subject")
        target = distribution.get("target")
        mental_state_type = distribution.get("mental_state_type")
        proposition = distribution.get("proposition")
        support_status = distribution.get("support_status")
        abstain = distribution.get("abstain")
        counterfactual = distribution.get("counterfactual")
        counterfactual_context = distribution.get("counterfactual_context")

        if perspective_order not in {1, 2}:
            errors.append(f"{prefix}_invalid_perspective_order:{perspective_order}")
        if not isinstance(subject, str) or not subject:
            errors.append(f"{prefix}_missing_subject")
        if not isinstance(target, str) or not target:
            errors.append(f"{prefix}_missing_target")
        if subject == target and isinstance(subject, str) and subject:
            errors.append(f"{prefix}_subject_target_not_separate:{subject}")
            checks["perspectives_match_episode_labels"] = False
        if support_status not in {"supported", "abstained", "pending"}:
            errors.append(f"{prefix}_invalid_support_status:{support_status}")
        if not isinstance(abstain, bool):
            errors.append(f"{prefix}_abstain_not_bool")
        if not isinstance(counterfactual, bool):
            errors.append(f"{prefix}_counterfactual_not_bool")

        label_key = (perspective_order, subject, target, mental_state_type, proposition)
        label_matched = label_key in label_keys
        if support_status == "supported" and not label_matched:
            errors.append(f"{prefix}_supported_hypothesis_not_in_episode_labels")
            checks["perspectives_match_episode_labels"] = False
        if label_matched:
            counts["label_matched_distributions"] += 1

        refs = distribution.get("evidence_refs")
        if not isinstance(refs, list):
            errors.append(f"{prefix}_evidence_refs_not_list")
            refs = []
        resolved_ref_count = 0
        synthetic_counterfactual_refs = 0
        unresolved_refs = 0
        for ref_idx, ref in enumerate(refs):
            if not isinstance(ref, dict):
                errors.append(f"{prefix}_evidence_ref_{ref_idx}_not_object")
                unresolved_refs += 1
                continue
            scope = ref.get("scope")
            source_id = ref.get("source_id")
            if scope not in ALLOWED_EVIDENCE_SCOPES:
                errors.append(f"{prefix}_evidence_ref_{ref_idx}_invalid_scope:{scope}")
                unresolved_refs += 1
                continue
            if not isinstance(source_id, str) or not source_id:
                errors.append(f"{prefix}_evidence_ref_{ref_idx}_missing_source_id")
                unresolved_refs += 1
                continue
            if scope == "synthetic_counterfactual":
                synthetic_counterfactual_refs += 1
                if counterfactual is not True:
                    errors.append(f"{prefix}_literal_prediction_uses_counterfactual_evidence:{source_id}")
                    checks["counterfactual_not_literal_history"] = False
                continue
            if scope == "memory_residue":
                errors.append(f"{prefix}_memory_residue_not_available_in_gate2_fixture:{source_id}")
                unresolved_refs += 1
                continue
            if (scope, source_id) not in visible_refs:
                errors.append(f"{prefix}_unresolved_or_hidden_evidence_ref:{scope}:{source_id}")
                unresolved_refs += 1
                continue
            resolved_ref_count += 1
        counts["resolved_evidence_refs"] += resolved_ref_count
        if unresolved_refs:
            checks["evidence_refs_resolve"] = False

        unsupported = resolved_ref_count == 0 and synthetic_counterfactual_refs == 0
        if support_status == "supported":
            counts["supported"] += 1
            if abstain is True:
                errors.append(f"{prefix}_supported_distribution_abstains")
            if unsupported:
                errors.append(f"{prefix}_unsupported_claim_marked_supported")
                checks["unsupported_abstains_or_pending"] = False
        else:
            counts["abstained_or_pending"] += 1
            if abstain is not True:
                errors.append(f"{prefix}_unsupported_not_abstained")
                checks["unsupported_abstains_or_pending"] = False
            if not unknown_certain:
                errors.append(f"{prefix}_abstain_or_pending_distribution_not_unknown_certain")
                checks["unsupported_abstains_or_pending"] = False

        if counterfactual is True:
            counts["counterfactual_distributions"] += 1
            if not isinstance(counterfactual_context, dict):
                errors.append(f"{prefix}_counterfactual_missing_context")
                checks["counterfactuals_explicitly_marked"] = False
            elif counterfactual_context.get("synthetic") is not True:
                errors.append(f"{prefix}_counterfactual_context_not_synthetic")
                checks["counterfactuals_explicitly_marked"] = False
        else:
            if counterfactual_context not in (None, {}):
                errors.append(f"{prefix}_factual_distribution_has_counterfactual_context")
                checks["counterfactuals_explicitly_marked"] = False

    return errors, {
        "counts": counts,
        "checks": checks,
        "bundle_sha256": _stable_json_sha256(bundle),
    }


def build_receipt(corpus_path: Path, bundle_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors, derived = _check_bundle(corpus_path, bundle_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.gate2_distribution_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "bundle_path": str(bundle_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "bundle_sha256": derived["bundle_sha256"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied ToM belief distribution bundle is sealed before reveal",
                "supported hypotheses resolve visible evidence and match Gate 1 episode labels",
                "probability distributions sum to one",
                "unsupported hypotheses abstain or remain pending with UNKNOWN certainty",
                "canonical memory writes are absent",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid ToM distribution bundle",
            ],
            "does_not_prove": [
                "model prediction accuracy",
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
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.bundle, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
