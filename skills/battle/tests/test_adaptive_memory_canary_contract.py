from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_skill.adaptive_memory_canary import (
    build_memory_document,
    build_memory_promotion_receipt,
    build_memory_use_acknowledgement,
)


def test_promotion_and_document_are_team_scoped_and_receipt_bound() -> None:
    source = _source()
    promotion = build_memory_promotion_receipt(
        battle_id="battle-004", run_id="v14", team="red", source=source
    )
    promotion["receipt_sha256"] = "promotion-sha"
    document = build_memory_document(team="red", promotion=promotion, source=source)

    assert promotion["status"] == "PASS"
    assert promotion["visibility_scope"] == "red_only"
    assert promotion["evidence_classification"] == "validated_negative_exploit_evidence"
    assert document["team"] == "red"
    assert "team:red" in document["tags"]
    assert document["source_receipts"]["promotion_receipt_sha256"] == "promotion-sha"
    assert "/tmp/" not in json.dumps(document)


def test_memory_use_requires_exact_citations_method_reuse_and_changed_artifact(
    tmp_path: Path,
) -> None:
    source = _source()
    promotion = build_memory_promotion_receipt(
        battle_id="battle-004", run_id="v14", team="red", source=source
    )
    promotion["receipt_sha256"] = "promotion-sha"
    document = build_memory_document(team="red", promotion=promotion, source=source)
    recall = {
        "receipt_sha256": "recall-sha",
        "recalled_document": {"solution": document["solution"]},
    }
    artifact = tmp_path / "red_exploit_submission.py"
    artifact.write_text("print('changed')\n", encoding="utf-8")
    response = {
        "rationale": (
            f"Use {document['_key']} {document['content_sha256']} recall-sha"
        ),
        "strategy_genome": {"selected_methods": ["method-a"]},
    }
    call = tmp_path / "scillm-call.json"
    call.write_text(json.dumps({"parsed_json": response}), encoding="utf-8")
    manifest = {
        "teams": [
            {
                "team": "red",
                "scillm_call": str(call),
                "materialized": {
                    "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
                },
            }
        ]
    }
    parent = {**source["genomes"]["red"], "sha256": "parent-genome-sha"}
    child = {
        "selected_methods": ["method-a", "method-c"],
        "sha256": "child-genome-sha",
    }

    receipt = build_memory_use_acknowledgement(
        battle_id="battle-004",
        run_id="v14",
        team="red",
        manifest=manifest,
        genome=child,
        parent_genome=parent,
        document=document,
        recall=recall,
        parent_artifact_sha256="parent-artifact-sha",
    )

    assert receipt["status"] == "PASS"
    assert receipt["reused_selected_methods"] == ["method-a"]
    assert all(receipt["provider_citations"].values())
    assert receipt["artifact_changed"] is True


def _source() -> dict[str, object]:
    fitness = {
        "status": "PASS",
        "sha256": "fitness-sha",
        "observation_receipt_sha256": "observation-sha",
        "judge_receipt_sha256": "judge-sha",
        "genome_sha256": "genome-sha",
        "selected_artifact_sha256": "artifact-sha",
        "components": {"judge_outcome": {"label": "BLUE_SUCCESS"}},
    }
    genome = {
        "selected_methods": ["method-a", "method-b"],
        "rejected_methods": ["method-z"],
        "parameters": {"mode": "bounded"},
        "expected_observation": "Judge evaluates the selected artifact.",
    }
    observation = {"judge": {"verdict": "BLUE_SUCCESS"}}
    return {
        "campaign": {"run_id": "v13"},
        "selection_sha256": "selection-sha",
        "fitness": {"red": fitness, "blue": fitness},
        "genomes": {"red": genome, "blue": genome},
        "observations": {"red": observation, "blue": observation},
    }
