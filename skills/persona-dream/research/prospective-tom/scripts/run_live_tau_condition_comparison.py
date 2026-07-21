#!/usr/bin/env python3
"""Run live Tau-authored PCTOM-R M/R/D/CD condition comparison cases."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
BUILD_CORPUS_SCRIPT = RESEARCH_ROOT / "scripts" / "build_social_episode_corpus.py"
CHECK_CORPUS_SCRIPT = RESEARCH_ROOT / "scripts" / "check_social_episode_corpus.py"
TAU_ADAPTER = ROOT / "scripts" / "tau_text_reasoning_adapter.py"
GATE2_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_belief_distributions.py"
GATE3_SCRIPT = RESEARCH_ROOT / "scripts" / "check_counterfactual_branches.py"
GATE4_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_prediction_commitments.py"
GATE5_SCRIPT = RESEARCH_ROOT / "scripts" / "reveal_and_score_trial.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_CONDITION_COMPARISON"
SYSTEMIC_FAILURE_THRESHOLD = 3


CONDITION_INSTRUCTIONS = {
    "M": (
        "Memory-only condition: use the visible episode evidence as recalled facts. "
        "Do not add reflective narrative or dream-like simulation. Keep uncertainty "
        "high when the visible evidence does not settle the prediction."
    ),
    "R": (
        "Reflection condition: reason textually over the visible evidence and the "
        "prediction targets. Do not introduce a synthetic dream trajectory. Use "
        "only visible evidence refs plus the required synthetic counterfactual ref."
    ),
    "D": (
        "Single-dream condition: use one synthetic trajectory as an audit-only "
        "imagination aid, but keep factual and counterfactual evidence classes "
        "separate. Do not write the imagined branch as literal history."
    ),
    "CD": (
        "Counterfactual-dream condition: compare the factual branch against the "
        "specified do()-style counterfactual branch and make the predicted action "
        "distribution sensitive to that intervention."
    ),
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _one_second_after(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return (parsed.astimezone(dt.timezone.utc) + dt.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _systemic_failure_signature(error: str) -> str | None:
    if "Tau dispatch timed out after" in error:
        return "tau_text_reasoning_timeout"
    if "tau_error:scillm_http_status_401" in error or "scillm_http_status_401" in error:
        return "tau_scillm_auth_401"
    if "tau_error:scillm_api_key_unavailable" in error or "scillm_api_key_unavailable" in error:
        return "tau_scillm_api_key_unavailable"
    return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_tau_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "schema",
        "created_at",
        "role",
        "mocked",
        "live",
        "surface",
        "model",
        "caller_skill",
        "prompt_sha256",
        "output_contract_sha256",
        "api_key_source",
        "status",
        "live_call_performed",
        "http_status",
        "error",
    ]
    return {key: receipt.get(key) for key in keys if key in receipt}


def _dispatch_boundary_receipt(
    *,
    role: str,
    model: str | None,
    prompt: str,
    output_contract: dict[str, Any],
    timeout_s: float,
    status: str,
    error: str | None = None,
    systemic_failure_signature: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.tau_text_reasoning_dispatch_boundary_receipt.v1",
        "created_at": _now_iso(),
        "role": role,
        "mocked": False,
        "live": False,
        "surface": "tau:persona-dream-text-reasoning",
        "model": model,
        "caller_skill": "persona-dream",
        "prompt_sha256": _text_sha256(prompt),
        "prompt_char_count": len(prompt),
        "prompt_byte_count": len(prompt.encode("utf-8")),
        "output_contract_sha256": _stable_json_sha256(output_contract),
        "timeout_s": timeout_s,
        "status": status,
        "error": error,
        "systemic_failure_signature": systemic_failure_signature,
        "live_call_performed": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }


def _gate0_attribution_records(gate0_case_root: Path | None) -> list[dict[str, Any]]:
    if gate0_case_root is None:
        return []
    residue_path = gate0_case_root / "normalized_residue.json"
    if not residue_path.exists() or residue_path.is_symlink():
        raise RuntimeError(f"gate0_normalized_residue_missing:{residue_path}")
    residue = _load_json(residue_path)
    if not isinstance(residue, list):
        raise RuntimeError(f"gate0_normalized_residue_not_list:{residue_path}")
    records: list[dict[str, Any]] = []
    for idx, item in enumerate(residue):
        if not isinstance(item, dict):
            raise RuntimeError(f"gate0_residue_{idx}_not_object")
        source_id = item.get("source_id")
        accepted_source_id = item.get("accepted_source_id") or source_id
        source_digest = item.get("accepted_source_ids_sha256")
        query_receipt_index = item.get("query_receipt_index")
        if not isinstance(source_id, str) or not source_id:
            raise RuntimeError(f"gate0_residue_{idx}_missing_source_id")
        if not isinstance(accepted_source_id, str) or not accepted_source_id:
            raise RuntimeError(f"gate0_residue_{idx}_missing_accepted_source_id")
        if not isinstance(source_digest, str) or not source_digest.startswith("sha256:"):
            raise RuntimeError(f"gate0_residue_{idx}_missing_accepted_source_ids_sha256")
        if not isinstance(query_receipt_index, int):
            raise RuntimeError(f"gate0_residue_{idx}_missing_query_receipt_index")
        records.append(
            {
                "accepted_source_id": accepted_source_id,
                "accepted_source_ids_sha256": source_digest,
                "gate0_residue_source_id": source_id,
                "gate0_residue_scope": item.get("scope"),
                "gate0_query_receipt_index": query_receipt_index,
                "gate0_residue_index": idx,
                "gate0_attribution_kind": "live_recall_residue_grounding",
            }
        )
    return records


def _with_gate0_attribution(ref: dict[str, Any], records: list[dict[str, Any]], index: int) -> dict[str, Any]:
    attributed = dict(ref)
    if not records:
        return attributed
    record = records[index % len(records)]
    attributed.update(record)
    return attributed


def _visible_refs(episode: dict[str, Any], gate0_records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    episode_id = episode["episode_id"]
    records = gate0_records or []
    refs: list[dict[str, Any]] = [
        {"scope": "social_episode_access", "source_id": f"{episode_id}:information_access_by_agent"}
    ]
    history = episode.get("observable_history") or []
    if history:
        refs.insert(0, {"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:0"})
    if len(history) > 1:
        refs.append({"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:1"})
    return [_with_gate0_attribution(ref, records, idx) for idx, ref in enumerate(refs)]


def _visible_packet(episode: dict[str, Any], gate0_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    records = gate0_records or []
    return {
        "episode_id": episode_id,
        "scenario_family": episode.get("scenario_family"),
        "information_access_by_agent": episode.get("information_access_by_agent"),
        "information_access_ref": _with_gate0_attribution(
            {
                "scope": "social_episode_access",
                "source_id": f"{episode_id}:information_access_by_agent",
            },
            records,
            0,
        ),
        "observable_history": episode.get("observable_history"),
        "observable_history_refs": [
            _with_gate0_attribution(
                {"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:{idx}"},
                records,
                idx,
            )
            for idx, item in enumerate(episode.get("observable_history", []))
            if isinstance(item, dict)
        ],
        "allowed_next_actions": episode.get("allowed_next_actions"),
    }


def _overlay_gate0_attribution(value: Any, visible_refs: list[dict[str, Any]]) -> Any:
    if not visible_refs:
        return value
    by_pair = {
        (ref.get("scope"), ref.get("source_id")): ref
        for ref in visible_refs
        if isinstance(ref, dict) and isinstance(ref.get("scope"), str) and isinstance(ref.get("source_id"), str)
    }
    if isinstance(value, list):
        return [_overlay_gate0_attribution(item, visible_refs) for item in value]
    if not isinstance(value, dict):
        return value
    updated = {
        key: _overlay_gate0_attribution(child, visible_refs)
        for key, child in value.items()
    }
    key = (updated.get("scope"), updated.get("source_id"))
    if key in by_pair and updated.get("scope") != "synthetic_counterfactual":
        merged = dict(updated)
        for attr_key, attr_value in by_pair[key].items():
            if attr_key not in {"scope", "source_id"}:
                merged.setdefault(attr_key, attr_value)
        return merged
    return updated


def _prediction_targets(episode: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for label in episode.get("ground_truth_tom_labels", []):
        if not isinstance(label, dict):
            continue
        targets.append(
            {
                "perspective_order": label.get("perspective_order"),
                "subject": label.get("subject"),
                "target": label.get("target"),
                "mental_state_type": label.get("mental_state_type"),
                "proposition": label.get("proposition"),
            }
        )
    if len(targets) < 2:
        raise RuntimeError(f"episode_has_insufficient_tom_targets:{episode.get('episode_id')}")
    return targets[:2]


def _select_episodes(corpus: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    episodes = list(corpus.get("episodes") or [])
    if limit <= 0 or limit >= len(episodes):
        return episodes
    by_family: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        if isinstance(episode, dict):
            by_family.setdefault(str(episode.get("scenario_family") or "unknown"), []).append(episode)
    selected: list[dict[str, Any]] = []
    family_names = sorted(by_family)
    round_index = 0
    while len(selected) < limit:
        added = False
        for family in family_names:
            rows = by_family[family]
            if round_index < len(rows):
                selected.append(rows[round_index])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        round_index += 1
    return selected


def _ids(episode_id: str, condition: str) -> dict[str, str]:
    prefix = f"live-tau-{condition.lower()}-{episode_id}"
    return {
        "tom1_factual": f"{prefix}-tom1-factual",
        "tom2_factual": f"{prefix}-tom2-factual",
        "tom1_counterfactual": f"{prefix}-tom1-counterfactual",
        "factual_branch": f"{prefix}-factual",
        "counterfactual_branch": f"{prefix}-counterfactual",
        "intervention": f"{prefix}-do-policy-alternative",
        "prediction": f"{prefix}-prediction",
    }


def _output_contract() -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.live_tau_condition_output_contract.v1",
        "required_top_level_keys": [
            "tom_belief_distribution_bundle",
            "counterfactual_branch_bundle",
            "prediction_payload",
        ],
        "requirements": [
            "Return exactly one JSON object and no prose.",
            "Do not include hidden_world_state, actual_next_action, ground_truth_tom_labels, outcome, score, or reveal fields.",
            "Use exact IDs and exact field names from output_shape.",
            "Use only supplied social_episode_observation, social_episode_access, and synthetic_counterfactual evidence refs.",
            "Every factual supported ToM distribution must match a supplied prediction target.",
            "Every probability distribution must sum to one.",
            "Branch source_evidence_refs must contain only visible social episode refs.",
            "Never put synthetic_counterfactual refs in branch source_evidence_refs or prediction_payload evidence_refs.",
            "Use synthetic_counterfactual refs only in the counterfactual ToM distribution evidence_refs.",
            "The counterfactual branch must be synthetic and must not be literal history.",
            "The prediction_payload condition must equal the requested condition.",
        ],
    }


def _preflight_prompt() -> str:
    return (
        "You are checking the Persona Dream PCTOM-R Tau text-reasoning route. "
        "Return exactly this JSON object shape with no prose: "
        '{"route_ready":true,"surface":"tau_scillm_text_reasoning","note":"preflight_only"}'
    )


def _preflight_output_contract() -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.live_tau_text_reasoning_preflight_contract.v1",
        "required_top_level_keys": ["route_ready", "surface", "note"],
        "requirements": [
            "Return exactly one JSON object and no prose.",
            "route_ready must be true only if the Tau text-reasoning route produced this response.",
            "This preflight must not reveal outcomes, write memory, call providers, or produce PCTOM-R predictions.",
        ],
    }


def _prompt(episode: dict[str, Any], condition: str, gate0_records: list[dict[str, Any]] | None = None) -> str:
    episode_id = episode["episode_id"]
    ids = _ids(episode_id, condition)
    records = gate0_records or []
    visible = _visible_packet(episode, records)
    targets = _prediction_targets(episode)
    actions = list(episode.get("allowed_next_actions") or [])
    if not actions:
        actions = ["UNKNOWN"]
    if len(actions) == 1:
        action_shape = [{"value": actions[0], "probability": 1.0}]
    elif len(actions) == 2:
        action_shape = [{"value": actions[0], "probability": 0.55}, {"value": actions[1], "probability": 0.45}]
    else:
        action_shape = [
            {"value": actions[0], "probability": 0.34},
            {"value": actions[1], "probability": 0.33},
            {"value": actions[2], "probability": 0.33},
        ]
    cf_action_shape = [{"value": action, "probability": 0.0} for action in actions[:3]]
    cf_action_shape.append({"value": "UNKNOWN", "probability": 1.0})
    synthetic_ref = {"scope": "synthetic_counterfactual", "source_id": f"{episode_id}:{condition}:do-policy-alternative"}
    visible_refs = _visible_refs(episode, records)
    held_fixed = [
        "counterpart_goals",
        "counterpart_preferences",
        "information_access_by_agent",
        "observable_history",
    ]
    prompt_payload = {
        "task": "Produce one pre-reveal PCTOM-R condition prediction for deterministic scoring.",
        "condition": condition,
        "condition_instruction": CONDITION_INSTRUCTIONS[condition],
        "episode_visible_to_agent": visible,
        "prediction_targets_without_truth_values": targets,
        "required_ids": ids,
        "counterfactual_intervention": {
            "intervention_id": ids["intervention"],
            "episode_id": episode_id,
            "intervened_variable": "counterpart_policy.expected_actual_next_action",
            "intervened_value": "UNKNOWN",
            "synthetic_counterfactual_ref": synthetic_ref,
            "held_fixed": held_fixed,
        },
        "allowed_next_actions": actions,
        "ref_rules": {
            "visible_refs_allowed_in_branch_source_evidence_refs": visible_refs,
            "visible_refs_allowed_in_prediction_payload_evidence_refs": visible_refs,
            "synthetic_counterfactual_ref_allowed_only_in_counterfactual_distribution_evidence_refs": synthetic_ref,
            "forbidden_in_branch_source_evidence_refs": [synthetic_ref],
            "forbidden_in_prediction_payload_evidence_refs": [synthetic_ref],
        },
        "output_shape": {
            "tom_belief_distribution_bundle": {
                "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
                "episode_id": episode_id,
                "condition": condition,
                "sealed": True,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "distributions": [
                    {
                        "hypothesis_id": ids["tom1_factual"],
                        "episode_id": episode_id,
                        "perspective_order": targets[0]["perspective_order"],
                        "subject": targets[0]["subject"],
                        "target": targets[0]["target"],
                        "mental_state_type": targets[0]["mental_state_type"],
                        "proposition": targets[0]["proposition"],
                        "distribution": [
                            {"value": "TRUE", "probability": 0.5},
                            {"value": "FALSE", "probability": 0.25},
                            {"value": "UNKNOWN", "probability": 0.25},
                        ],
                        "evidence_refs": visible_refs,
                        "prediction_horizon": "next_action",
                        "counterfactual": False,
                        "counterfactual_context": None,
                        "abstain": False,
                        "support_status": "supported",
                    },
                    {
                        "hypothesis_id": ids["tom2_factual"],
                        "episode_id": episode_id,
                        "perspective_order": targets[1]["perspective_order"],
                        "subject": targets[1]["subject"],
                        "target": targets[1]["target"],
                        "mental_state_type": targets[1]["mental_state_type"],
                        "proposition": targets[1]["proposition"],
                        "distribution": [
                            {"value": "TRUE", "probability": 0.45},
                            {"value": "FALSE", "probability": 0.25},
                            {"value": "UNKNOWN", "probability": 0.30},
                        ],
                        "evidence_refs": visible_refs,
                        "prediction_horizon": "next_action",
                        "counterfactual": False,
                        "counterfactual_context": None,
                        "abstain": False,
                        "support_status": "supported",
                    },
                    {
                        "hypothesis_id": ids["tom1_counterfactual"],
                        "episode_id": episode_id,
                        "perspective_order": targets[0]["perspective_order"],
                        "subject": targets[0]["subject"],
                        "target": targets[0]["target"],
                        "mental_state_type": targets[0]["mental_state_type"],
                        "proposition": targets[0]["proposition"],
                        "distribution": [
                            {"value": "TRUE", "probability": 0.30},
                            {"value": "FALSE", "probability": 0.35},
                            {"value": "UNKNOWN", "probability": 0.35},
                        ],
                        "evidence_refs": [synthetic_ref],
                        "prediction_horizon": "next_action",
                        "counterfactual": True,
                        "counterfactual_context": {"intervention_id": ids["intervention"], "synthetic": True},
                        "abstain": False,
                        "support_status": "supported",
                    },
                ],
            },
            "counterfactual_branch_bundle": {
                "schema": "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1",
                "episode_id": episode_id,
                "condition": condition,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "branches": [
                    {
                        "branch_id": ids["factual_branch"],
                        "episode_id": episode_id,
                        "branch_type": "factual",
                        "synthetic": False,
                        "intervention": None,
                        "source_evidence_refs": visible_refs,
                        "held_fixed": held_fixed,
                        "predicted_bdi_distribution_refs": [ids["tom1_factual"], ids["tom2_factual"]],
                        "predicted_action_distribution": action_shape,
                        "expected_observation": "The visible social episode continues without revealing hidden evaluator-only truth.",
                        "uncertainty": 0.35,
                    },
                    {
                        "branch_id": ids["counterfactual_branch"],
                        "episode_id": episode_id,
                        "branch_type": "counterfactual",
                        "synthetic": True,
                        "intervention": {
                            "intervention_id": ids["intervention"],
                            "episode_id": episode_id,
                            "synthetic": True,
                            "intervened_variable": "counterpart_policy.expected_actual_next_action",
                            "intervened_value": "UNKNOWN",
                            "held_fixed": held_fixed,
                            "expected_observation": "The counterpart policy is replaced by an unspecified alternative.",
                        },
                        "source_evidence_refs": visible_refs,
                        "held_fixed": held_fixed,
                        "predicted_bdi_distribution_refs": [ids["tom1_counterfactual"]],
                        "predicted_action_distribution": cf_action_shape,
                        "expected_observation": "This branch is synthetic and excluded from literal history.",
                        "uncertainty": 0.45,
                    },
                ],
            },
            "prediction_payload": {
                "schema": "persona_dream.research.prospective_tom.tom_prediction_payload.v1",
                "episode_id": episode_id,
                "condition": condition,
                "outcome_visible": False,
                "belief_distribution_refs": [ids["tom1_factual"], ids["tom2_factual"], ids["tom1_counterfactual"]],
                "branch_refs": [ids["factual_branch"], ids["counterfactual_branch"]],
                "evidence_refs": visible_refs,
                "prediction_horizon": "next_action",
                "predicted_next_action_distribution": action_shape,
                "abstain": False,
                "condition_method": CONDITION_INSTRUCTIONS[condition],
            },
        },
    }
    return (
        "You are producing machine-validated JSON for Persona Dream PCTOM-R. "
        "Return one JSON object matching output_shape. The evaluator will reject aliases, hidden outcome fields, "
        "unresolved evidence refs, distributions that do not sum to one, synthetic refs in branch source refs, "
        "synthetic refs in prediction_payload evidence_refs, and synthetic branches treated as history.\n\n"
        + json.dumps(prompt_payload, indent=2, sort_keys=True)
    )


def _commitment_bundle(
    episode_id: str,
    condition: str,
    prediction_payload: dict[str, Any],
    tau_receipt: dict[str, Any],
    distribution_bundle: dict[str, Any],
    branch_bundle: dict[str, Any],
) -> dict[str, Any]:
    evidence_refs = prediction_payload.get("evidence_refs") if isinstance(prediction_payload.get("evidence_refs"), list) else []
    branch_refs = prediction_payload.get("branch_refs") if isinstance(prediction_payload.get("branch_refs"), list) else []
    distribution_refs = (
        prediction_payload.get("belief_distribution_refs")
        if isinstance(prediction_payload.get("belief_distribution_refs"), list)
        else []
    )
    evidence_bundle = {
        "episode_id": episode_id,
        "condition": condition,
        "branch_bundle_sha256": _stable_json_sha256(branch_bundle),
        "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
        "branch_refs": branch_refs,
        "belief_distribution_refs": distribution_refs,
        "source_evidence_refs": evidence_refs,
    }
    model_receipts = [_compact_tau_receipt(tau_receipt)]
    commitment = {
        "prediction_id": _ids(episode_id, condition)["prediction"],
        "episode_id": episode_id,
        "condition": condition,
        "sealed_at": _now_iso(),
        "outcome_visible": False,
        "canonical_memory_write": False,
        "prediction_payload": prediction_payload,
        "prediction_payload_sha256": _stable_json_sha256(prediction_payload),
        "model_receipts": model_receipts,
        "model_receipts_sha256": _stable_json_sha256(model_receipts),
        "evidence_bundle": evidence_bundle,
        "evidence_bundle_sha256": _stable_json_sha256(evidence_bundle),
    }
    return {
        "schema": "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1",
        "episode_id": episode_id,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "commitments": [commitment],
    }


def _labels_by_signature(episode: dict[str, Any]) -> dict[tuple[Any, Any, Any, Any, Any], str]:
    labels: dict[tuple[Any, Any, Any, Any, Any], str] = {}
    for label in episode.get("ground_truth_tom_labels", []):
        if not isinstance(label, dict):
            continue
        key = (
            label.get("perspective_order"),
            label.get("subject"),
            label.get("target"),
            label.get("mental_state_type"),
            label.get("proposition"),
        )
        if isinstance(label.get("value"), str):
            labels[key] = label["value"]
    return labels


def _top_action(distribution: list[dict[str, Any]]) -> str | None:
    rows = [row for row in distribution if isinstance(row, dict)]
    if not rows:
        return None
    return max(rows, key=lambda row: float(row.get("probability") or 0.0)).get("value")


def _outcome_reveal(
    episode: dict[str, Any],
    condition: str,
    distribution_bundle: dict[str, Any],
    branch_bundle: dict[str, Any],
    commitment_bundle: dict[str, Any],
) -> dict[str, Any]:
    labels = _labels_by_signature(episode)
    hidden_state_labels: dict[str, str] = {}
    for distribution in distribution_bundle.get("distributions", []):
        if not isinstance(distribution, dict) or distribution.get("counterfactual") is True:
            continue
        key = (
            distribution.get("perspective_order"),
            distribution.get("subject"),
            distribution.get("target"),
            distribution.get("mental_state_type"),
            distribution.get("proposition"),
        )
        hidden_state_labels[distribution["hypothesis_id"]] = labels.get(key, "UNKNOWN")
    factual_branch_ids = [
        branch.get("branch_id")
        for branch in branch_bundle.get("branches", [])
        if isinstance(branch, dict) and branch.get("branch_type") == "factual"
    ]
    factual_branch_id = next((branch_id for branch_id in factual_branch_ids if isinstance(branch_id, str)), None)
    commitment = commitment_bundle["commitments"][0]
    payload = commitment.get("prediction_payload", {})
    predicted_actions = payload.get("predicted_next_action_distribution") if isinstance(payload, dict) else []
    top_action = _top_action(predicted_actions) if isinstance(predicted_actions, list) else None
    return {
        "schema": "persona_dream.research.prospective_tom.tom_outcome_reveal.v1",
        "outcome_id": f"live-tau-condition-outcome-{episode['episode_id']}-{condition.lower()}",
        "episode_id": episode["episode_id"],
        "prediction_id": commitment["prediction_id"],
        "outcome_visible": True,
        "reveal_complete": True,
        "revealed_at": _one_second_after(commitment["sealed_at"]),
        "canonical_memory_write": False,
        "actual_next_action": episode.get("actual_next_action"),
        "hidden_state_labels": hidden_state_labels,
        "equivalent_formulation_checks": [
            {
                "check_id": f"live-tau-condition-{condition.lower()}-eq-action",
                "formulation_id": "same-question-paraphrase-001",
                "prediction_id": commitment["prediction_id"],
                "expected_top_action": top_action,
            }
        ],
        "factual_branch_id": factual_branch_id,
        "literal_history_branch_ids": [factual_branch_id] if factual_branch_id else [],
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, dict[str, list[float]]] = {
        condition: {"action_brier": [], "action_log_loss": [], "belief_brier": [], "belief_log_loss": []}
        for condition in CONDITIONS
    }
    for row in rows:
        metrics = row.get("scoring_metrics") or {}
        action = metrics.get("action") or {}
        values = by_condition[row["condition"]]
        if isinstance(action.get("brier"), (int, float)):
            values["action_brier"].append(float(action["brier"]))
        if isinstance(action.get("log_loss"), (int, float)):
            values["action_log_loss"].append(float(action["log_loss"]))
        for belief in metrics.get("belief_scores") or []:
            if isinstance(belief.get("brier"), (int, float)):
                values["belief_brier"].append(float(belief["brier"]))
            if isinstance(belief.get("log_loss"), (int, float)):
                values["belief_log_loss"].append(float(belief["log_loss"]))
    summary: dict[str, Any] = {}
    for condition, values in by_condition.items():
        summary[condition] = {
            "cases": len([row for row in rows if row["condition"] == condition]),
            "mean_action_brier": _mean(values["action_brier"]),
            "mean_action_log_loss": _mean(values["action_log_loss"]),
            "mean_belief_brier": _mean(values["belief_brier"]),
            "mean_belief_log_loss": _mean(values["belief_log_loss"]),
        }
    baseline_scores = {
        condition: row["mean_action_brier"]
        for condition, row in summary.items()
        if condition != "CD" and isinstance(row.get("mean_action_brier"), (int, float))
    }
    strongest = min(baseline_scores, key=baseline_scores.get) if baseline_scores else None
    cd_score = summary.get("CD", {}).get("mean_action_brier")
    summary["comparison"] = {
        "primary_metric": "mean_action_brier",
        "strongest_baseline_condition": strongest,
        "strongest_baseline_mean_action_brier": baseline_scores.get(strongest) if strongest else None,
        "cd_mean_action_brier": cd_score,
        "cd_minus_strongest_baseline": (cd_score - baseline_scores[strongest])
        if strongest and isinstance(cd_score, (int, float))
        else None,
        "lower_is_better": True,
    }
    return summary


def run_live_comparison(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    episode_limit: int,
    model: str | None,
    timeout_s: float,
    preflight_timeout_s: float | None = None,
    gate0_case_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    corpus_path = artifacts_root / "social_episode_corpus.v1.json"
    corpus_check_receipt_path = receipts_root / "social_episode_corpus_check_receipt.json"
    tau_preflight_receipt_path = receipts_root / "tau_text_reasoning_preflight_receipt.json"
    case_index_path = artifacts_root / "live_condition_case_index.json"
    metrics_path = artifacts_root / "live_condition_metrics_summary.json"
    gate0_case_root = gate0_case_root.resolve() if gate0_case_root is not None else None

    build_corpus = _load_module(BUILD_CORPUS_SCRIPT, "persona_dream_pctom_build_corpus")
    check_corpus = _load_module(CHECK_CORPUS_SCRIPT, "persona_dream_pctom_check_corpus")
    adapter = _load_module(TAU_ADAPTER, "persona_dream_tau_text_adapter")
    gate2 = _load_module(GATE2_SCRIPT, "persona_dream_pctom_gate2")
    gate3 = _load_module(GATE3_SCRIPT, "persona_dream_pctom_gate3")
    gate4 = _load_module(GATE4_SCRIPT, "persona_dream_pctom_gate4")
    gate5 = _load_module(GATE5_SCRIPT, "persona_dream_pctom_gate5")

    corpus = build_corpus.build_corpus(split, episodes_per_family)
    _write_json(corpus_path, corpus)
    corpus_check = check_corpus.build_receipt(
        corpus_path,
        corpus_check_receipt_path,
        expect_total=episodes_per_family * 4,
        expect_per_family=episodes_per_family,
    )

    errors: list[str] = []
    gate0_records: list[dict[str, Any]] = []
    gate0_attribution_overlay_used = False
    try:
        gate0_records = _gate0_attribution_records(gate0_case_root)
        gate0_attribution_overlay_used = bool(gate0_records)
    except Exception as exc:
        errors.append(f"gate0_attribution_load_failed:{exc}")
    if corpus_check.get("status") != "PASS_SOCIAL_EPISODE_CORPUS":
        errors.append(f"corpus_check_status:{corpus_check.get('status')}")
        errors.extend(f"corpus_check_error:{error}" for error in corpus_check.get("errors", []))

    selected = _select_episodes(corpus, episode_limit)
    tau_preflight_attempted = False
    tau_preflight_live_call_performed = False
    tau_preflight_receipt: dict[str, Any] | None = None
    tau_preflight_passed = False
    tau_call_attempts = 0
    tau_live_call_performed = 0
    tau_receipts_hash_bound = True
    sealed_counts = {condition: 0 for condition in CONDITIONS}
    scored_counts = {condition: 0 for condition in CONDITIONS}
    status_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    systemic_failure_counts: collections.Counter[str] = collections.Counter()
    systemic_failure_signature: str | None = None
    blocked_by_systemic_failure = 0

    if not errors:
        tau_preflight_attempted = True
        try:
            parsed_preflight, tau_preflight_receipt = adapter.dispatch_text_reasoning(
                _preflight_prompt(),
                "pctom-live-condition-preflight",
                output_contract=_preflight_output_contract(),
                caller_skill="persona-dream",
                model=model,
                timeout_s=preflight_timeout_s if preflight_timeout_s is not None else min(timeout_s, 30.0),
            )
            _write_json(tau_preflight_receipt_path, tau_preflight_receipt)
            tau_preflight_live_call_performed = tau_preflight_receipt.get("live_call_performed") is True
            tau_preflight_passed = (
                tau_preflight_receipt.get("status") == "PASS"
                and isinstance(parsed_preflight, dict)
                and parsed_preflight.get("route_ready") is True
                and parsed_preflight.get("surface") == "tau_scillm_text_reasoning"
            )
            if not tau_preflight_passed:
                errors.append(f"tau_preflight_status:{tau_preflight_receipt.get('status')}")
                if tau_preflight_receipt.get("error"):
                    errors.append(f"tau_preflight_error:{tau_preflight_receipt.get('error')}")
                if not isinstance(parsed_preflight, dict):
                    errors.append("tau_preflight_parsed_json_not_object")
        except Exception as exc:
            errors.append(f"tau_preflight_failed:{exc}")

    if tau_preflight_passed:
        for episode in selected:
            for condition in CONDITIONS:
                case_root = artifacts_root / "cases" / episode["episode_id"] / condition
                case_receipts = receipts_root / "cases" / episode["episode_id"] / condition
                tau_receipt_path = case_receipts / "tau_text_reasoning_receipt.json"
                parsed_path = case_root / "tau_parsed_json.json"
                distribution_path = case_root / "tom_belief_distribution_bundle.json"
                branch_path = case_root / "counterfactual_branch_bundle.json"
                commitment_path = case_root / "tom_prediction_commitment_bundle.json"
                outcome_path = case_root / "tom_outcome_reveal.json"
                gate2_receipt_path = case_receipts / "gate2_distribution_check_receipt.json"
                gate3_receipt_path = case_receipts / "gate3_branch_check_receipt.json"
                gate4_receipt_path = case_receipts / "gate4_commitment_check_receipt.json"
                gate5_receipt_path = case_receipts / "gate5_scoring_receipt.json"
                case_errors: list[str] = []
                receipts: dict[str, dict[str, Any]] = {}
                tau_receipt: dict[str, Any] | None = None
                parsed: dict[str, Any] | None = None
                role = f"pctom-live-condition-{condition.lower()}"
                output_contract = _output_contract()
                prompt_text = _prompt(episode, condition, gate0_records)

                if systemic_failure_signature is not None:
                    blocked_by_systemic_failure += 1
                    case_errors.append(f"blocked_by_systemic_failure:{systemic_failure_signature}")
                    tau_receipt = _dispatch_boundary_receipt(
                        role=role,
                        model=model,
                        prompt=prompt_text,
                        output_contract=output_contract,
                        timeout_s=timeout_s,
                        status="BLOCKED_BY_SYSTEMIC_FAILURE",
                        systemic_failure_signature=systemic_failure_signature,
                    )
                    _write_json(tau_receipt_path, tau_receipt)
                    rows.append(
                        {
                            "episode_id": episode["episode_id"],
                            "condition": condition,
                            "case_root": str(case_root),
                            "receipt_root": str(case_receipts),
                            "tau_receipt_path": str(tau_receipt_path),
                            "tau_receipt_exists": tau_receipt_path.exists(),
                            "prompt_sha256": tau_receipt.get("prompt_sha256"),
                            "prompt_char_count": tau_receipt.get("prompt_char_count"),
                            "prompt_byte_count": tau_receipt.get("prompt_byte_count"),
                            "tau_status": tau_receipt.get("status"),
                            "tau_live_call_performed": tau_receipt.get("live_call_performed"),
                            "blocked_by_systemic_failure": True,
                            "systemic_failure_signature": systemic_failure_signature,
                            "statuses": {},
                            "scoring_metrics": {},
                            "errors": case_errors,
                        }
                    )
                    errors.extend(f"{episode['episode_id']}:{condition}:{error}" for error in case_errors)
                    continue

                try:
                    tau_call_attempts += 1
                    parsed_candidate, tau_receipt = adapter.dispatch_text_reasoning(
                        prompt_text,
                        role,
                        output_contract=output_contract,
                        caller_skill="persona-dream",
                        model=model,
                        timeout_s=timeout_s,
                    )
                    _write_json(tau_receipt_path, tau_receipt)
                    if tau_receipt.get("live_call_performed") is True:
                        tau_live_call_performed += 1
                    if tau_receipt.get("status") != "PASS":
                        case_errors.append(f"tau_status:{tau_receipt.get('status')}")
                        if tau_receipt.get("error"):
                            case_errors.append(f"tau_error:{tau_receipt.get('error')}")
                    if isinstance(parsed_candidate, dict):
                        parsed = parsed_candidate
                        _write_json(parsed_path, parsed)
                    else:
                        case_errors.append("tau_parsed_json_not_object")
                except Exception as exc:
                    error_text = str(exc)
                    case_errors.append(f"tau_text_reasoning_failed:{error_text}")
                    tau_receipt = _dispatch_boundary_receipt(
                        role=role,
                        model=model,
                        prompt=prompt_text,
                        output_contract=output_contract,
                        timeout_s=timeout_s,
                        status="BLOCKED_DISPATCH_ERROR",
                        error=error_text,
                        systemic_failure_signature=_systemic_failure_signature(error_text),
                    )
                    _write_json(tau_receipt_path, tau_receipt)

                if parsed:
                    distribution_bundle = parsed.get("tom_belief_distribution_bundle")
                    branch_bundle = parsed.get("counterfactual_branch_bundle")
                    prediction_payload = parsed.get("prediction_payload")
                    visible_refs = _visible_refs(episode, gate0_records)
                    if isinstance(distribution_bundle, dict):
                        distribution_bundle = _overlay_gate0_attribution(distribution_bundle, visible_refs)
                        _write_json(distribution_path, distribution_bundle)
                    else:
                        case_errors.append("parsed_missing_distribution_bundle")
                    if isinstance(branch_bundle, dict):
                        branch_bundle = _overlay_gate0_attribution(branch_bundle, visible_refs)
                        _write_json(branch_path, branch_bundle)
                    else:
                        case_errors.append("parsed_missing_branch_bundle")
                    if not isinstance(prediction_payload, dict):
                        case_errors.append("parsed_missing_prediction_payload")
                    else:
                        prediction_payload = _overlay_gate0_attribution(prediction_payload, visible_refs)

                    if isinstance(distribution_bundle, dict) and isinstance(branch_bundle, dict) and isinstance(prediction_payload, dict):
                        commitment_bundle = _commitment_bundle(
                            episode["episode_id"],
                            condition,
                            prediction_payload,
                            tau_receipt or {},
                            distribution_bundle,
                            branch_bundle,
                        )
                        model_hash_ok = commitment_bundle["commitments"][0]["model_receipts_sha256"] == _stable_json_sha256(
                            commitment_bundle["commitments"][0]["model_receipts"]
                        )
                        tau_receipts_hash_bound = tau_receipts_hash_bound and model_hash_ok
                        _write_json(commitment_path, commitment_bundle)
                        outcome = _outcome_reveal(episode, condition, distribution_bundle, branch_bundle, commitment_bundle)
                        _write_json(outcome_path, outcome)
                        receipts = {
                            "gate2": gate2.build_receipt(corpus_path, distribution_path, gate2_receipt_path),
                            "gate3": gate3.build_receipt(corpus_path, distribution_path, branch_path, gate3_receipt_path),
                            "gate4": gate4.build_receipt(corpus_path, distribution_path, branch_path, commitment_path, gate4_receipt_path),
                            "gate5": gate5.build_receipt(
                                corpus_path,
                                distribution_path,
                                branch_path,
                                commitment_path,
                                outcome_path,
                                gate5_receipt_path,
                            ),
                        }
                        if receipts["gate4"].get("status") == "PASS_TOM_PREDICTION_COMMITMENTS":
                            sealed_counts[condition] += 1
                        if receipts["gate5"].get("status") == "PASS_TOM_SCORING_RECEIPT":
                            scored_counts[condition] += 1
                        for gate_name, receipt in receipts.items():
                            status = str(receipt.get("status"))
                            status_counts[status] = status_counts.get(status, 0) + 1
                            if not status.startswith("PASS_"):
                                case_errors.append(f"{gate_name}_status:{status}")
                                case_errors.extend(f"{gate_name}_error:{error}" for error in receipt.get("errors", []))

                rows.append(
                    {
                        "episode_id": episode["episode_id"],
                        "condition": condition,
                        "case_root": str(case_root),
                        "receipt_root": str(case_receipts),
                        "tau_receipt_path": str(tau_receipt_path),
                        "tau_receipt_exists": tau_receipt_path.exists(),
                        "prompt_sha256": tau_receipt.get("prompt_sha256") if tau_receipt else _text_sha256(prompt_text),
                        "prompt_char_count": tau_receipt.get("prompt_char_count") if tau_receipt else len(prompt_text),
                        "prompt_byte_count": tau_receipt.get("prompt_byte_count") if tau_receipt else len(prompt_text.encode("utf-8")),
                        "tau_status": tau_receipt.get("status") if tau_receipt else None,
                        "tau_live_call_performed": tau_receipt.get("live_call_performed") if tau_receipt else False,
                        "blocked_by_systemic_failure": False,
                        "systemic_failure_signature": tau_receipt.get("systemic_failure_signature") if tau_receipt else None,
                        "statuses": {name: receipt.get("status") for name, receipt in receipts.items()},
                        "scoring_metrics": receipts.get("gate5", {}).get("metrics", {}),
                        "errors": case_errors,
                    }
                )
                errors.extend(f"{episode['episode_id']}:{condition}:{error}" for error in case_errors)
                for error in case_errors:
                    signature = _systemic_failure_signature(error)
                    if signature is None:
                        continue
                    systemic_failure_counts[signature] += 1
                    if (
                        systemic_failure_signature is None
                        and systemic_failure_counts[signature] >= SYSTEMIC_FAILURE_THRESHOLD
                    ):
                        systemic_failure_signature = signature
                        errors.append(f"systemic_failure_threshold_reached:{signature}:{SYSTEMIC_FAILURE_THRESHOLD}")
                        break
    elif not errors:
        errors.append("tau_preflight_not_attempted")

    if tau_preflight_passed:
        for condition in CONDITIONS:
            if sealed_counts[condition] < 1:
                errors.append(f"sealed_commitments_per_condition_insufficient:{condition}:{sealed_counts[condition]}")
            if scored_counts[condition] < 1:
                errors.append(f"deterministic_scores_per_condition_insufficient:{condition}:{scored_counts[condition]}")
        if systemic_failure_signature is None and tau_call_attempts < len(CONDITIONS):
            errors.append(f"tau_call_attempts_insufficient:{tau_call_attempts}")
    if not tau_receipts_hash_bound:
        errors.append("tau_receipts_hash_bound_false")

    tau_boundary_receipts_written = sum(
        1 for row in rows if isinstance(row, dict) and row.get("tau_receipt_exists") is True
    )
    tau_boundary_receipts_missing = [
        row.get("tau_receipt_path")
        for row in rows
        if isinstance(row, dict) and row.get("tau_receipt_exists") is not True
    ]
    if tau_boundary_receipts_missing:
        errors.append(f"tau_boundary_receipts_missing:{len(tau_boundary_receipts_missing)}")

    metrics = _summarize(rows)
    _write_json(case_index_path, rows)
    _write_json(metrics_path, metrics)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_condition_comparison_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "corpus_path": str(corpus_path),
        "corpus_check_receipt_path": str(corpus_check_receipt_path),
        "tau_preflight_receipt_path": str(tau_preflight_receipt_path),
        "tau_preflight_receipt_sha256": _stable_json_sha256(tau_preflight_receipt)
        if isinstance(tau_preflight_receipt, dict)
        else None,
        "case_index_path": str(case_index_path),
        "metrics_summary_path": str(metrics_path),
        "mocked": False,
        "live": tau_preflight_live_call_performed or tau_live_call_performed > 0,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_preflight_attempted": tau_preflight_attempted,
        "tau_preflight_status": tau_preflight_receipt.get("status") if isinstance(tau_preflight_receipt, dict) else None,
        "tau_preflight_live_call_performed": tau_preflight_live_call_performed,
        "tau_preflight_passed": tau_preflight_passed,
        "tau_call_attempts": tau_call_attempts,
        "tau_live_call_performed": tau_live_call_performed,
        "tau_receipts_hash_bound": tau_receipts_hash_bound,
        "systemic_failure_threshold": SYSTEMIC_FAILURE_THRESHOLD,
        "systemic_failure_signature": systemic_failure_signature,
        "systemic_failure_counts": dict(systemic_failure_counts),
        "gate0_case_root": str(gate0_case_root) if gate0_case_root else None,
        "gate0_attribution_overlay_used": gate0_attribution_overlay_used,
        "gate0_attribution_record_count": len(gate0_records),
        "blocked_by_systemic_failure": blocked_by_systemic_failure,
        "tau_boundary_receipts_written": tau_boundary_receipts_written,
        "tau_boundary_receipts_missing": tau_boundary_receipts_missing,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes_in_corpus": corpus["episode_count"],
            "episodes_consumed": len(selected),
            "families_consumed": len({episode.get("scenario_family") for episode in selected}),
            "conditions": len(CONDITIONS),
            "cases": len(rows),
            "executed_cases": len(rows) - blocked_by_systemic_failure,
            "blocked_by_systemic_failure": blocked_by_systemic_failure,
            "tau_boundary_receipts_written": tau_boundary_receipts_written,
            "sealed_commitments_per_condition": sealed_counts,
            "deterministic_scores_per_condition": scored_counts,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "checks": {
            "corpus_check_passed": corpus_check.get("status") == "PASS_SOCIAL_EPISODE_CORPUS",
            "tau_preflight_passed": tau_preflight_passed,
            "case_fanout_blocked_until_preflight_passes": not rows if not tau_preflight_passed else True,
            "systemic_failure_breaker_tripped": systemic_failure_signature is not None,
            "systemic_failure_threshold_respected": systemic_failure_signature is None
            or systemic_failure_counts.get(systemic_failure_signature, 0) == SYSTEMIC_FAILURE_THRESHOLD,
            "remaining_cases_marked_blocked_by_systemic_failure": systemic_failure_signature is None
            or blocked_by_systemic_failure > 0,
            "tau_boundary_receipts_written_for_all_rows": tau_boundary_receipts_written == len(rows),
            "gate0_attribution_loaded_if_requested": gate0_case_root is None or gate0_attribution_overlay_used,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": metrics,
        "errors": errors,
        "claims": {
            "proves": [
                "Tau-authored M, R, D, and CD condition outputs were attempted through the sanctioned persona-dream Tau adapter",
                "accepted cases were sealed before deterministic outcome reveal",
                "accepted cases were scored by Gate 5 without human content judgment",
                "Tau model receipts were hash-bound into prediction commitments",
                "no Memory write, provider call, canonical memory write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau condition comparison runner produced an inspectable fail-closed receipt",
                "case fan-out is blocked until the Tau text-reasoning preflight passes",
                "repeated Tau case failures are circuit-broken after the configured systemic failure threshold",
            ],
            "does_not_prove": [
                "held-out test-set prediction benefit",
                "action-selection regret improvement",
                "external service fault injection",
                "production retry machinery",
                "longitudinal recall after revision",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution or video quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--split", default="calibration")
    parser.add_argument("--episodes-per-family", type=int, default=6)
    parser.add_argument("--episode-limit", type=int, default=1)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--preflight-timeout-s", type=float, default=None)
    parser.add_argument("--gate0-case-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_condition_comparison_receipt.v1.json")
    receipt = run_live_comparison(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        episode_limit=args.episode_limit,
        model=args.model,
        timeout_s=args.timeout_s,
        preflight_timeout_s=args.preflight_timeout_s,
        gate0_case_root=args.gate0_case_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
