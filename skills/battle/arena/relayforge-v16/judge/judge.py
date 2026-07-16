#!/usr/bin/env python3
"""Fail-closed Judge skeleton for RelayForge V16.

The evaluator deliberately cannot emit a successful qualification result.  A
future Slice 2 implementation must add concrete evaluator functions for every
predicate and regression fixture and then replace the explicit implementation
block below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TARGET_ID = "battle-v16-relayforge-a"
ROOT = Path(__file__).resolve().parent


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def unfinished_contracts(root: Path = ROOT) -> tuple[list[str], list[str]]:
    predicates = _read_json(root / "predicates.json")
    regressions = _read_json(root / "regression-fixtures.json")

    unfinished_predicates: list[str] = []
    for path in predicates.get("paths", []):
        for item in path.get("predicates", []):
            if item.get("implementation_status") != "IMPLEMENTED":
                unfinished_predicates.append(str(item.get("predicate_id")))
    for item in predicates.get("shortcut_denials", []):
        if item.get("implementation_status") != "IMPLEMENTED":
            unfinished_predicates.append(str(item.get("predicate_id")))
    if predicates.get("terminal_policy", {}).get("implementation_status") != "IMPLEMENTED":
        unfinished_predicates.append("terminal-policy")

    unfinished_regressions = [
        str(item.get("fixture_id"))
        for item in regressions.get("fixtures", [])
        if item.get("implementation_status") != "IMPLEMENTED"
    ]
    for key in (
        "narrow_control_expectation",
        "broad_quarantine_expectation",
        "decoy_shutdown_expectation",
    ):
        if regressions.get(key, {}).get("implementation_status") != "IMPLEMENTED":
            unfinished_regressions.append(key.replace("_expectation", ""))

    return sorted(set(unfinished_predicates)), sorted(set(unfinished_regressions))


def evaluate(root: Path = ROOT) -> dict[str, Any]:
    unfinished_predicates, unfinished_regressions = unfinished_contracts(root)
    blockers = [
        *(f"predicate:{item}" for item in unfinished_predicates),
        *(f"regression:{item}" for item in unfinished_regressions),
        "judge_evaluator_registry_unimplemented",
    ]
    return {
        "schema": "battle.v16.judge_outcome.v1",
        "status": "BLOCKED",
        "target_id": TARGET_ID,
        "reason": "relayforge_judge_not_implemented",
        "unfinished_predicates": unfinished_predicates,
        "unfinished_regressions": unfinished_regressions,
        "blockers": blockers,
        "pass_emitted": False,
        "claims": {
            "may_claim": ["The Judge skeleton failed closed"],
            "must_not_claim": [
                "Any exploit path was evaluated",
                "Any Blue defense was evaluated",
                "Any regression result was produced",
                "The target is qualified",
            ],
        },
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, sort_keys=True))
    raise SystemExit(1)
