"""Canonicalize provider strategy genomes and compute semantic deltas."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

SEMANTIC_FIELDS = (
    "selected_methods",
    "rejected_methods",
    "parameters",
    "mutation_origin",
    "expected_observation",
)
POLICY_ID = "battle-semantic-genome-canonicalization-v1"


def semantic_payload(genome: dict[str, Any]) -> dict[str, Any]:
    return {field: genome.get(field) for field in SEMANTIC_FIELDS}


def semantic_sha256(genome: dict[str, Any]) -> str:
    return _json_sha(semantic_payload(genome))


def build_semantic_genome_delta(
    *,
    battle_id: str,
    run_id: str,
    team: str,
    parent: dict[str, Any],
    child: dict[str, Any],
) -> dict[str, Any]:
    parent_selected = _strings(parent.get("selected_methods"))
    child_selected = _strings(child.get("selected_methods"))
    parent_rejected = _strings(parent.get("rejected_methods"))
    child_rejected = _strings(child.get("rejected_methods"))
    parent_parameters: dict[str, Any] = (
        cast(dict[str, Any], parent.get("parameters"))
        if isinstance(parent.get("parameters"), dict)
        else {}
    )
    child_parameters: dict[str, Any] = (
        cast(dict[str, Any], child.get("parameters"))
        if isinstance(child.get("parameters"), dict)
        else {}
    )
    parameter_changes = [
        {
            "name": key,
            "parent": parent_parameters.get(key),
            "child": child_parameters.get(key),
        }
        for key in sorted(set(parent_parameters) | set(child_parameters))
        if parent_parameters.get(key) != child_parameters.get(key)
    ]
    mutation_changed = parent.get("mutation_origin") != child.get("mutation_origin")
    expected_parent = _json_sha(parent.get("expected_observation"))
    expected_child = _json_sha(child.get("expected_observation"))
    expected_changed = expected_parent != expected_child
    retained = sorted(parent_selected & child_selected)
    added = sorted(child_selected - parent_selected)
    removed = sorted(parent_selected - child_selected)
    newly_rejected = sorted(child_rejected - parent_rejected)
    no_longer_rejected = sorted(parent_rejected - child_rejected)
    change_count = sum(
        [
            len(added),
            len(removed),
            len(newly_rejected),
            len(no_longer_rejected),
            len(parameter_changes),
            int(mutation_changed),
            int(expected_changed),
        ]
    )
    return {
        "schema": "battle.semantic_genome_delta.v1",
        "delta_id": f"{run_id}-{team}-g1-g2-delta",
        "status": "PASS" if change_count else "BLOCKED",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "from_generation": 1,
        "to_generation": 2,
        "canonicalization_policy_id": POLICY_ID,
        "canonicalization_policy_sha256": hashlib.sha256(
            POLICY_ID.encode()
        ).hexdigest(),
        "parent_genome_sha256": parent.get("sha256"),
        "child_genome_sha256": child.get("sha256"),
        "parent_semantic_sha256": semantic_sha256(parent),
        "child_semantic_sha256": semantic_sha256(child),
        "retained_methods": retained,
        "added_methods": added,
        "removed_methods": removed,
        "newly_rejected_methods": newly_rejected,
        "no_longer_rejected_methods": no_longer_rejected,
        "parameter_changes": parameter_changes,
        "mutation_origin": {
            "parent": parent.get("mutation_origin"),
            "child": child.get("mutation_origin"),
            "changed": mutation_changed,
        },
        "expected_observation": {
            "parent_sha256": expected_parent,
            "child_sha256": expected_child,
            "changed": expected_changed,
        },
        "semantic_change_count": change_count,
        "nonempty_semantic_delta": bool(change_count),
        "claims": {
            "proves": [
                "The child provider genome differs semantically from its parent."
            ]
            if change_count
            else [],
            "does_not_prove": [
                "The semantic change improved fitness or exploit success."
            ],
        },
    }


def _strings(value: Any) -> set[str]:
    return {str(item) for item in value} if isinstance(value, list) else set()


def _json_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
