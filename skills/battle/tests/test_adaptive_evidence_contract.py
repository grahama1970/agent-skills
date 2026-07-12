"""Deterministic contracts for adaptive observations and fitness."""

from battle_skill.adaptive_evidence import (
    build_fitness_vector,
    build_generation_observation,
)


def test_observation_and_fitness_remain_judge_bound() -> None:
    judge = {
        "status": "PASS",
        "verdict": "BLUE_SUCCESS",
        "judged_pair_count": 1,
        "receipt_sha256": "j" * 64,
        "reviewed_judge_input_sha256": "i" * 64,
        "patched_target_tree_sha256": "p" * 64,
        "attempts": [
            {
                "exploit_confirmed_before_patch": True,
                "exploit_blocked_after_patch": True,
                "functionality_preserved": True,
            }
        ],
    }
    pipeline = {
        "status": "PASS",
        "selected_artifact_sha256": "a" * 64,
        "handoff_sha256": "h" * 64,
        "compile_receipt_sha256": "c" * 64,
        "review_receipt_sha256": "r" * 64,
    }
    genome = {"sha256": "g" * 64}
    observation = build_generation_observation(
        battle_id="battle-004",
        run_id="run",
        team="blue",
        generation=1,
        pipeline=pipeline,
        judge=judge,
        genome=genome,
        target_identity_sha256="t" * 64,
        observed_elapsed_seconds=1.0,
    )
    observation["sha256"] = "o" * 64
    vector = build_fitness_vector(observation=observation, genome=genome)
    assert observation["status"] == "PASS"
    assert vector["components"]["judge_outcome"] == {"label": "BLUE_SUCCESS", "rank": 2}
    assert vector["observation_receipt_sha256"] == "o" * 64
