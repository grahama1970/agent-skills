"""Select adaptive lineages from four hash-bound fitness receipts."""

from __future__ import annotations

import hashlib
from typing import Any

POLICY_ID = "battle-adaptive-selection-lexicographic-v1"


def build_selection_receipt(
    *, battle_id: str, run_id: str, fitness: dict[str, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    teams: dict[str, Any] = {}
    for team in ("red", "blue"):
        g1 = fitness[team][1]
        g2 = fitness[team][2]
        selected = 2 if tuple(g2["selection_key"]) > tuple(g1["selection_key"]) else 1
        teams[team] = {
            "generation_1_fitness_receipt_sha256": g1["sha256"],
            "generation_2_fitness_receipt_sha256": g2["sha256"],
            "component_comparison": [
                {
                    "component": "selection_key",
                    "generation_1": g1["selection_key"],
                    "generation_2": g2["selection_key"],
                }
            ],
            "selected_generation": selected,
            "retention_decision": f"GENERATION_{selected}_SELECTED",
            "tie_break_reason": "generation_1_stability"
            if g1["selection_key"] == g2["selection_key"]
            else None,
        }
    improvement_dimensions = [
        f"{team}:judge_or_runtime"
        for team in ("red", "blue")
        if tuple(fitness[team][2]["selection_key"][:2])
        > tuple(fitness[team][1]["selection_key"][:2])
    ]
    return {
        "schema": "battle.adaptive_selection_receipt.v1",
        "selection_id": f"{run_id}-selection",
        "status": "PASS",
        "battle_id": battle_id,
        "run_id": run_id,
        "policy_id": POLICY_ID,
        "policy_sha256": hashlib.sha256(POLICY_ID.encode()).hexdigest(),
        "teams": teams,
        "improvement_claimed": bool(improvement_dimensions),
        "improvement_dimensions": improvement_dimensions,
        "disqualifying_regressions": [],
        "claims": {
            "proves": [
                "Battle compared two generations for both teams using four bound fitness receipts."
            ],
            "does_not_prove": [
                "Exploit success beyond Judge evidence or population-scale evolution."
            ],
        },
    }
