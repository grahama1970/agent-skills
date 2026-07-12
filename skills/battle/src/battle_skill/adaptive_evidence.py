"""Build deterministic generation observations and fitness vectors."""

from __future__ import annotations

import hashlib
from typing import Any

FITNESS_POLICY_ID = "battle-adaptive-fitness-lexicographic-v1"


def build_generation_observation(
    *,
    battle_id: str,
    run_id: str,
    team: str,
    generation: int,
    pipeline: dict[str, Any],
    judge: dict[str, Any],
    genome: dict[str, Any],
    target_identity_sha256: str,
    observed_elapsed_seconds: float,
) -> dict[str, Any]:
    attempt = (judge.get("attempts") or [{}])[0]
    selected_sha = pipeline.get("selected_artifact_sha256")
    return {
        "schema": "battle.generation_observation_receipt.v1",
        "receipt_id": f"{run_id}-{team}-g{generation}-observation",
        "status": "PASS"
        if pipeline.get("status") == "PASS" and judge.get("status") == "PASS"
        else "BLOCKED",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "generation": generation,
        "observed_elapsed_seconds": observed_elapsed_seconds,
        "target_identity": {
            "original_target_tree_sha256": target_identity_sha256,
            "patched_target_tree_sha256": judge.get("patched_target_tree_sha256"),
        },
        "artifact": {
            "selected_artifact_sha256": selected_sha,
            "pipeline_handoff_sha256": pipeline.get("handoff_sha256"),
            "compile_receipt_sha256": pipeline.get("compile_receipt_sha256"),
            "review_receipt_sha256": pipeline.get("review_receipt_sha256"),
            "genome_sha256": genome.get("sha256"),
        },
        "judge": {
            "judge_receipt_sha256": judge.get("receipt_sha256"),
            "reviewed_judge_input_sha256": judge.get("reviewed_judge_input_sha256"),
            "status": judge.get("status"),
            "verdict": judge.get("verdict"),
            "judged_pair_count": judge.get("judged_pair_count"),
        },
        "measurements": {
            "compile_status": pipeline.get("status"),
            "review_status": pipeline.get("status"),
            "runtime_status": "PASS"
            if int(judge.get("judged_pair_count") or 0)
            else "NOT_RUN",
            "target_contact": attempt.get("target_contact", "UNKNOWN"),
            "exploit_confirmed_before_patch": attempt.get(
                "exploit_confirmed_before_patch", "UNKNOWN"
            ),
            "exploit_blocked_after_patch": attempt.get(
                "exploit_blocked_after_patch", "UNKNOWN"
            ),
            "functionality_preserved": attempt.get(
                "functionality_preserved", "UNKNOWN"
            ),
            "repair_attempt_count": 0,
            "provider_attempt_count": 1,
            "execution_elapsed_seconds": attempt.get("elapsed_seconds", "UNKNOWN"),
        },
        "claims": {
            "proves": [
                "Battle projected measured pipeline and Judge evidence for one team generation."
            ],
            "does_not_prove": [
                "The team improved or achieved exploit success beyond the cited Judge verdict."
            ],
        },
    }


def build_fitness_vector(
    *,
    observation: dict[str, Any],
    genome: dict[str, Any],
    parent_artifact_sha256: str | None = None,
    semantic_delta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    team = str(observation["team"])
    measurements = observation["measurements"]
    verdict = str(observation["judge"]["verdict"])
    judge_rank = _judge_rank(team, verdict)
    runtime_evaluated = measurements["runtime_status"] == "PASS"
    semantic_changed = bool((semantic_delta or {}).get("nonempty_semantic_delta"))
    selected_sha = observation["artifact"]["selected_artifact_sha256"]
    changed = (
        parent_artifact_sha256 is not None and selected_sha != parent_artifact_sha256
    )
    key = [
        judge_rank,
        int(runtime_evaluated),
        int(semantic_changed),
        -int(measurements.get("provider_attempt_count") or 0),
    ]
    return {
        "schema": "battle.fitness_vector.v1",
        "fitness_id": f"{observation['run_id']}-{team}-g{observation['generation']}-fitness",
        "status": "PASS" if observation.get("status") == "PASS" else "BLOCKED",
        "battle_id": observation["battle_id"],
        "run_id": observation["run_id"],
        "team": team,
        "generation": observation["generation"],
        "policy_id": FITNESS_POLICY_ID,
        "policy_sha256": hashlib.sha256(FITNESS_POLICY_ID.encode()).hexdigest(),
        "observation_receipt_sha256": observation.get("sha256"),
        "judge_receipt_sha256": observation["judge"].get("judge_receipt_sha256"),
        "pipeline_handoff_sha256": observation["artifact"].get(
            "pipeline_handoff_sha256"
        ),
        "selected_artifact_sha256": selected_sha,
        "genome_sha256": genome.get("sha256"),
        "eligibility": {
            "eligible_for_selection": observation.get("status") == "PASS",
            "disqualifiers": [],
        },
        "components": {
            "judge_outcome": {"label": verdict, "rank": judge_rank},
            "compile_pass": measurements["compile_status"] == "PASS",
            "runtime_evaluated": runtime_evaluated,
            "exploit_confirmed_before_patch": measurements[
                "exploit_confirmed_before_patch"
            ],
            "exploit_blocked_after_patch": measurements["exploit_blocked_after_patch"],
            "functionality_preserved": measurements["functionality_preserved"],
            "artifact_changed_from_parent": changed
            if parent_artifact_sha256
            else "NOT_APPLICABLE",
            "semantic_genome_changed_from_parent": semantic_changed
            if semantic_delta
            else "NOT_APPLICABLE",
            "provider_attempt_count": measurements["provider_attempt_count"],
        },
        "selection_key": key,
        "claims": {
            "proves": [
                "Battle computed a reproducible fitness vector from cited evidence."
            ],
            "does_not_prove": ["A child improved unless selection establishes it."],
        },
    }


def _judge_rank(team: str, verdict: str) -> int:
    if verdict == ("RED_SUCCESS" if team == "red" else "BLUE_SUCCESS"):
        return 2
    return (
        1 if verdict in {"RED_SUCCESS", "BLUE_SUCCESS", "INSUFFICIENT_EVIDENCE"} else 0
    )
