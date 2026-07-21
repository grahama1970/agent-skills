#!/usr/bin/env python3
"""Run one live Tau text call through PCTOM-R Gates 2-4."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
DEFAULT_CORPUS = RESEARCH_ROOT / "fixtures" / "gate1" / "development" / "social_episode_corpus.v1.json"
TAU_ADAPTER = ROOT / "scripts" / "tau_text_reasoning_adapter.py"
GATE2_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_belief_distributions.py"
GATE3_SCRIPT = RESEARCH_ROOT / "scripts" / "check_counterfactual_branches.py"
GATE4_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_prediction_commitments.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_GATE2_4"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_GATE2_4"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _episode_by_id(corpus: dict[str, Any], episode_id: str) -> dict[str, Any]:
    for episode in corpus.get("episodes", []):
        if isinstance(episode, dict) and episode.get("episode_id") == episode_id:
            return episode
    raise RuntimeError(f"episode_not_found:{episode_id}")


def _visible_episode_packet(episode: dict[str, Any]) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    return {
        "episode_id": episode_id,
        "scenario_family": episode.get("scenario_family"),
        "information_access_by_agent": episode.get("information_access_by_agent"),
        "information_access_ref": {
            "scope": "social_episode_access",
            "source_id": f"{episode_id}:information_access_by_agent",
        },
        "observable_history": episode.get("observable_history"),
        "observable_history_refs": [
            {"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:{idx}"}
            for idx, item in enumerate(episode.get("observable_history", []))
            if isinstance(item, dict)
        ],
        "allowed_next_actions": episode.get("allowed_next_actions"),
    }


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
    if not targets:
        raise RuntimeError(f"episode_has_no_tom_targets:{episode.get('episode_id')}")
    return targets


def _output_contract() -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.live_tau_gate2_4_output_contract.v1",
        "required_top_level_keys": [
            "tom_belief_distribution_bundle",
            "counterfactual_branch_bundle",
            "prediction_payload",
        ],
        "requirements": [
            "Return exactly one JSON object.",
            "Do not include hidden_world_state, actual_next_action, ground_truth_tom_labels, outcome, score, or reveal fields.",
            "Use only supplied social_episode_observation, social_episode_access, and synthetic_counterfactual evidence refs.",
            "Use exact field names from the output_shape. Do not invent aliases.",
            "Forbidden aliases: evidence_refs inside branches, projected_next_action_distribution, belief_distribution_ref, action, synthetic_counterfactual branch_type, nested per-branch predicted_next_action_distribution.",
            "The distribution bundle must use schema persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1.",
            "The branch bundle must use schema persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1.",
            "The prediction_payload must use schema persona_dream.research.prospective_tom.tom_prediction_payload.v1.",
            "Every probability distribution must sum to one.",
        ],
    }


def _prompt(episode: dict[str, Any]) -> str:
    visible_packet = _visible_episode_packet(episode)
    targets = _prediction_targets(episode)
    episode_id = episode["episode_id"]
    prompt_payload = {
        "task": "Produce PCTOM-R Gate 2, Gate 3, and Gate 4 draft artifacts before outcome reveal.",
        "episode_visible_to_agent": visible_packet,
        "prediction_targets_without_truth_values": targets,
        "required_ids": {
            "factual_distribution_id": "live-tau-gate2-factual-bdi-001",
            "counterfactual_distribution_id": "live-tau-gate2-counterfactual-bdi-001",
            "factual_branch_id": "live-tau-gate3-factual-observed",
            "counterfactual_branch_id": "live-tau-gate3-cf-kai-gives-no-warning",
            "intervention_id": "live-tau-do-kai-gives-no-warning",
        },
        "counterfactual_intervention": {
            "intervened_variable": "counterpart_policy.expected_actual_next_action",
            "intervened_value": "KAI_GIVES_NO_WARNING",
            "synthetic_counterfactual_ref": {
                "scope": "synthetic_counterfactual",
                "source_id": f"{episode_id}:do:kai_gives_no_warning",
            },
            "held_fixed": [
                "hidden_world_state.constraint_changed",
                "counterpart_goals.kai_primary_goal",
                "information_access_by_agent.embry_observes_changed_constraint",
            ],
        },
        "output_shape": {
            "tom_belief_distribution_bundle": {
                "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
                "episode_id": episode_id,
                "sealed": True,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "distributions": [
                    {
                        "hypothesis_id": "live-tau-gate2-factual-bdi-001",
                        "episode_id": episode_id,
                        "perspective_order": targets[0]["perspective_order"],
                        "subject": targets[0]["subject"],
                        "target": targets[0]["target"],
                        "mental_state_type": targets[0]["mental_state_type"],
                        "proposition": targets[0]["proposition"],
                        "distribution": [
                            {"value": "TRUE", "probability": 0.6},
                            {"value": "FALSE", "probability": 0.25},
                            {"value": "UNKNOWN", "probability": 0.15},
                        ],
                        "evidence_refs": visible_packet["observable_history_refs"][:1],
                        "prediction_horizon": "next_action",
                        "counterfactual": False,
                        "counterfactual_context": None,
                        "abstain": False,
                        "support_status": "supported",
                    },
                    {
                        "hypothesis_id": "live-tau-gate2-counterfactual-bdi-001",
                        "episode_id": episode_id,
                        "perspective_order": targets[0]["perspective_order"],
                        "subject": targets[0]["subject"],
                        "target": targets[0]["target"],
                        "mental_state_type": targets[0]["mental_state_type"],
                        "proposition": targets[0]["proposition"],
                        "distribution": [
                            {"value": "TRUE", "probability": 0.2},
                            {"value": "FALSE", "probability": 0.65},
                            {"value": "UNKNOWN", "probability": 0.15},
                        ],
                        "evidence_refs": [{"scope": "synthetic_counterfactual", "source_id": f"{episode_id}:do:kai_gives_no_warning"}],
                        "prediction_horizon": "next_action",
                        "counterfactual": True,
                        "counterfactual_context": {"intervention_id": "live-tau-do-kai-gives-no-warning", "synthetic": True},
                        "abstain": False,
                        "support_status": "supported",
                    },
                ],
            },
            "counterfactual_branch_bundle": {
                "schema": "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1",
                "episode_id": episode_id,
                "outcome_visible": False,
                "canonical_memory_write": False,
                "branches": [
                    {
                        "branch_id": "live-tau-gate3-factual-observed",
                        "episode_id": episode_id,
                        "branch_type": "factual",
                        "synthetic": False,
                        "intervention": None,
                        "source_evidence_refs": visible_packet["observable_history_refs"][:1] + [visible_packet["information_access_ref"]],
                        "held_fixed": [
                            "hidden_world_state.constraint_changed",
                            "counterpart_goals.kai_primary_goal",
                            "information_access_by_agent.embry_observes_changed_constraint",
                        ],
                        "predicted_bdi_distribution_refs": ["live-tau-gate2-factual-bdi-001"],
                        "predicted_action_distribution": [
                            {"value": "KAI_HINTS_CONSTRAINT", "probability": 0.55},
                            {"value": "KAI_WARNS_PRIVATELY", "probability": 0.3},
                            {"value": "KAI_INTERRUPTS_WITH_CORRECTION", "probability": 0.15},
                        ],
                        "expected_observation": "Kai flags the constraint before Embry acts.",
                        "uncertainty": 0.2,
                    },
                    {
                        "branch_id": "live-tau-gate3-cf-kai-gives-no-warning",
                        "episode_id": episode_id,
                        "branch_type": "counterfactual",
                        "synthetic": True,
                        "intervention": {
                            "intervention_id": "live-tau-do-kai-gives-no-warning",
                            "episode_id": episode_id,
                            "synthetic": True,
                            "intervened_variable": "counterpart_policy.expected_actual_next_action",
                            "intervened_value": "KAI_GIVES_NO_WARNING",
                            "held_fixed": [
                                "hidden_world_state.constraint_changed",
                                "counterpart_goals.kai_primary_goal",
                                "information_access_by_agent.embry_observes_changed_constraint",
                            ],
                            "expected_observation": "Kai gives no warning before Embry acts.",
                        },
                        "source_evidence_refs": visible_packet["observable_history_refs"][:1] + [visible_packet["information_access_ref"]],
                        "held_fixed": [
                            "hidden_world_state.constraint_changed",
                            "counterpart_goals.kai_primary_goal",
                            "information_access_by_agent.embry_observes_changed_constraint",
                        ],
                        "predicted_bdi_distribution_refs": ["live-tau-gate2-counterfactual-bdi-001"],
                        "predicted_action_distribution": [
                            {"value": "KAI_HINTS_CONSTRAINT", "probability": 0.0},
                            {"value": "KAI_WARNS_PRIVATELY", "probability": 0.0},
                            {"value": "KAI_INTERRUPTS_WITH_CORRECTION", "probability": 0.0},
                            {"value": "UNKNOWN", "probability": 1.0},
                        ],
                        "expected_observation": "Kai withholds the warning and Embry continues with stale information.",
                        "uncertainty": 0.35,
                    },
                ],
            },
            "prediction_payload": {
                "schema": "persona_dream.research.prospective_tom.tom_prediction_payload.v1",
                "episode_id": episode_id,
                "condition": "CD",
                "outcome_visible": False,
                "belief_distribution_refs": [
                    "live-tau-gate2-factual-bdi-001",
                    "live-tau-gate2-counterfactual-bdi-001",
                ],
                "branch_refs": [
                    "live-tau-gate3-factual-observed",
                    "live-tau-gate3-cf-kai-gives-no-warning",
                ],
                "evidence_refs": visible_packet["observable_history_refs"][:1] + [visible_packet["information_access_ref"]],
                "prediction_horizon": "next_action",
                "predicted_next_action_distribution": [
                    {"value": "KAI_HINTS_CONSTRAINT", "probability": 0.6},
                    {"value": "KAI_WARNS_PRIVATELY", "probability": 0.3},
                    {"value": "KAI_INTERRUPTS_WITH_CORRECTION", "probability": 0.1},
                ],
                "abstain": False,
            },
        },
    }
    return (
        "You are producing machine-validated JSON for Persona Dream PCTOM-R. "
        "Use the supplied visible episode data only. Do not reveal or infer any hidden outcome fields. "
        "Return one JSON object matching the requested top-level keys.\n\n"
        + json.dumps(prompt_payload, indent=2, sort_keys=True)
    )


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


def _commitment_bundle(
    *,
    episode_id: str,
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
        "branch_bundle_sha256": _stable_json_sha256(branch_bundle),
        "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
        "branch_refs": branch_refs,
        "belief_distribution_refs": distribution_refs,
        "source_evidence_refs": evidence_refs,
    }
    model_receipts = [_compact_tau_receipt(tau_receipt)]
    commitment = {
        "prediction_id": "live-tau-gate4-commitment-cd-001",
        "episode_id": episode_id,
        "condition": prediction_payload.get("condition"),
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


def build_receipt(
    *,
    corpus_path: Path,
    episode_id: str,
    output_root: Path,
    receipt_out: Path,
    model: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    distribution_path = artifacts_root / "tom_belief_distribution_bundle.json"
    branch_path = artifacts_root / "counterfactual_branch_bundle.json"
    commitment_path = artifacts_root / "tom_prediction_commitment_bundle.json"
    tau_receipt_path = receipts_root / "tau_text_reasoning_receipt.json"
    parsed_path = artifacts_root / "tau_parsed_json.json"
    gate2_receipt_path = receipts_root / "gate2_distribution_check_receipt.json"
    gate3_receipt_path = receipts_root / "gate3_counterfactual_branch_check_receipt.json"
    gate4_receipt_path = receipts_root / "gate4_prediction_commitment_check_receipt.json"
    errors: list[str] = []
    tau_call_attempts = 0
    tau_receipt: dict[str, Any] | None = None
    gate2_receipt: dict[str, Any] | None = None
    gate3_receipt: dict[str, Any] | None = None
    gate4_receipt: dict[str, Any] | None = None

    corpus = _load_json(corpus_path)
    episode = _episode_by_id(corpus, episode_id)
    adapter = _load_module(TAU_ADAPTER, "persona_dream_tau_text_adapter")
    gate2 = _load_module(GATE2_SCRIPT, "persona_dream_pctom_gate2_check")
    gate3 = _load_module(GATE3_SCRIPT, "persona_dream_pctom_gate3_check")
    gate4 = _load_module(GATE4_SCRIPT, "persona_dream_pctom_gate4_check")

    try:
        tau_call_attempts = 1
        parsed, tau_receipt = adapter.dispatch_text_reasoning(
            _prompt(episode),
            "pctom-live-gate2-4",
            output_contract=_output_contract(),
            caller_skill="persona-dream",
            model=model,
            timeout_s=timeout_s,
        )
        _write_json(tau_receipt_path, tau_receipt)
    except Exception as exc:
        errors.append(f"tau_text_reasoning_failed:{exc}")
        parsed = None

    if tau_receipt and tau_receipt.get("status") != "PASS":
        errors.append(f"tau_text_reasoning_status:{tau_receipt.get('status')}")
        if tau_receipt.get("error"):
            errors.append(f"tau_text_reasoning_error:{tau_receipt.get('error')}")

    if isinstance(parsed, dict):
        _write_json(parsed_path, parsed)
        distribution_bundle = parsed.get("tom_belief_distribution_bundle")
        branch_bundle = parsed.get("counterfactual_branch_bundle")
        prediction_payload = parsed.get("prediction_payload")
        if not isinstance(distribution_bundle, dict):
            errors.append("parsed_missing_distribution_bundle")
        if not isinstance(branch_bundle, dict):
            errors.append("parsed_missing_branch_bundle")
        if not isinstance(prediction_payload, dict):
            errors.append("parsed_missing_prediction_payload")
        if isinstance(distribution_bundle, dict):
            _write_json(distribution_path, distribution_bundle)
        if isinstance(branch_bundle, dict):
            _write_json(branch_path, branch_bundle)
        if isinstance(distribution_bundle, dict) and isinstance(branch_bundle, dict) and isinstance(prediction_payload, dict):
            commitment_bundle = _commitment_bundle(
                episode_id=episode_id,
                prediction_payload=prediction_payload,
                tau_receipt=tau_receipt or {},
                distribution_bundle=distribution_bundle,
                branch_bundle=branch_bundle,
            )
            _write_json(commitment_path, commitment_bundle)
            gate2_receipt = gate2.build_receipt(corpus_path, distribution_path, gate2_receipt_path)
            gate3_receipt = gate3.build_receipt(corpus_path, distribution_path, branch_path, gate3_receipt_path)
            gate4_receipt = gate4.build_receipt(corpus_path, distribution_path, branch_path, commitment_path, gate4_receipt_path)
            for gate_name, gate_receipt, pass_status in [
                ("gate2", gate2_receipt, "PASS_TOM_BELIEF_DISTRIBUTIONS"),
                ("gate3", gate3_receipt, "PASS_COUNTERFACTUAL_BRANCHES"),
                ("gate4", gate4_receipt, "PASS_TOM_PREDICTION_COMMITMENTS"),
            ]:
                if gate_receipt.get("status") != pass_status:
                    errors.append(f"{gate_name}_status:{gate_receipt.get('status')}")
                    errors.extend(f"{gate_name}_error:{error}" for error in gate_receipt.get("errors", []))
    else:
        errors.append("tau_parsed_json_not_object")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_gate2_4_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "episode_id": episode_id,
        "corpus_path": str(corpus_path.resolve()),
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": bool(tau_receipt and tau_receipt.get("live_call_performed") is True),
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "tau_call_attempts": tau_call_attempts,
        "tau_text_receipt_path": str(tau_receipt_path),
        "tau_text_status": tau_receipt.get("status") if tau_receipt else None,
        "tau_live_call_performed": tau_receipt.get("live_call_performed") if tau_receipt else False,
        "gate2_receipt_path": str(gate2_receipt_path),
        "gate2_status": gate2_receipt.get("status") if gate2_receipt else None,
        "gate3_receipt_path": str(gate3_receipt_path),
        "gate3_status": gate3_receipt.get("status") if gate3_receipt else None,
        "gate4_receipt_path": str(gate4_receipt_path),
        "gate4_status": gate4_receipt.get("status") if gate4_receipt else None,
        "artifact_paths": {
            "tau_parsed_json": str(parsed_path),
            "tom_belief_distribution_bundle": str(distribution_path),
            "counterfactual_branch_bundle": str(branch_path),
            "tom_prediction_commitment_bundle": str(commitment_path),
        },
        "checker_counts": {
            "gate2": gate2_receipt.get("counts") if gate2_receipt else {},
            "gate3": gate3_receipt.get("counts") if gate3_receipt else {},
            "gate4": gate4_receipt.get("counts") if gate4_receipt else {},
        },
        "errors": errors,
        "claims": {
            "proves": [
                "one live Tau text call was attempted through the sanctioned persona-dream Tau adapter",
                "Tau-authored Gate 2 ToM distributions passed deterministic invariant checks before outcome reveal",
                "Tau-authored Gate 3 factual/counterfactual branches passed deterministic invariant checks before outcome reveal",
                "a sealed Gate 4 prediction commitment was hash-bound to the Tau model receipt plus Gate 2 and Gate 3 bundles",
                "no Memory write, provider call, or human content judgment was required",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau Gate 2-4 bridge produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "held-out prediction benefit",
                "calibration quality beyond local distribution invariants",
                "outcome reveal, scoring, or belief revision",
                "live Memory recall for this Gate 2-4 run",
                "real service fault injection",
                "complete Phase 01-16 runtime execution",
                "paid provider execution or video quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--episode-id", default="dev-info-asym-01")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_gate2_4_receipt.v1.json")
    receipt = build_receipt(
        corpus_path=args.corpus,
        episode_id=args.episode_id,
        output_root=args.output_root,
        receipt_out=receipt_out,
        model=args.model,
        timeout_s=args.timeout_s,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
