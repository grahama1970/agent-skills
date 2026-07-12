"""Evaluate adaptive evidence for memory promotion without writing memory."""

from __future__ import annotations

import hashlib
from typing import Any

POLICY_ID = "battle-memory-promotion-evaluate-only-v1"


def build_memory_evaluation(
    *,
    battle_id: str,
    run_id: str,
    selection: dict[str, Any],
    fitness: dict[str, dict[int, dict[str, Any]]],
    deltas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluations = []
    for team in ("red", "blue"):
        generation = int(selection["teams"][team]["selected_generation"])
        selected = fitness[team][generation]
        evaluations.append(
            {
                "team": team,
                "selected_generation": generation,
                "fitness_receipt_sha256": selected["sha256"],
                "judge_receipt_sha256": selected["judge_receipt_sha256"],
                "genome_delta_sha256": deltas[team]["sha256"],
                "evidence_classification": "neutral",
                "eligible_decisions": ["NO_PROMOTION"],
                "decision": "NO_PROMOTION",
                "reason_codes": ["evaluate_only_canary", "durable_write_out_of_scope"],
                "judge_requirement_satisfied": True,
                "visibility_scope": f"{team}_only",
                "memory_write_required": False,
                "memory_write_receipt_sha256": None,
                "durable_recall_proven": False,
            }
        )
    return {
        "schema": "battle.memory_promotion_evaluation.v1",
        "evaluation_id": f"{run_id}-memory-evaluation",
        "status": "PASS",
        "battle_id": battle_id,
        "run_id": run_id,
        "policy_id": POLICY_ID,
        "policy_sha256": hashlib.sha256(POLICY_ID.encode()).hexdigest(),
        "policy_mode": "evaluate_only",
        "selection_receipt_sha256": selection["sha256"],
        "evaluations": evaluations,
        "claims": {
            "proves": ["Battle evaluated selected evidence under the memory policy."],
            "does_not_prove": ["Memory was written, promoted, or durably recalled."],
        },
    }
