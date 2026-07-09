"""Battle-owned spawn policy receipts for combiner proof rungs."""

from __future__ import annotations

from typing import Any


SPAWN_POLICY_DECISION_SCHEMA = "battle.spawn_policy_decision.v1"


def combiner_pr1_spawn_policy_decision(*, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema": SPAWN_POLICY_DECISION_SCHEMA,
        "status": "NOT_REQUESTED",
        "decision": "NOT_REQUESTED",
        "reason": "combiner proof validates specimen lifecycle only; child materialization deferred",
        "parent_terminal": False,
        "strategic_pre_kill_proven": False,
        "materialized_child": False,
        "evidence_refs": evidence_refs or [],
        "claims": {
            "proves": ["Battle evaluated spawn policy as out of scope for PR1 combiner proof."],
            "does_not_prove": ["A child exploit spawned.", "Strategic pre-kill replication occurred."],
        },
    }
