from __future__ import annotations

import json
from pathlib import Path

import pytest

from f36_requirement_qra import (
    EXPECTED_RESPONSE_PATH,
    EngineeringIntent,
    EngineeringSemanticCore,
    assemble_family,
    build_calls,
    canonical_json_hash,
    render_questions,
    review_manifest,
    select_jobs,
    validate_core_against_job,
    validate_materialized_family,
    validate_source_grounding,
)


def expected_core() -> EngineeringSemanticCore:
    return EngineeringSemanticCore.model_validate(json.loads(EXPECTED_RESPONSE_PATH.read_text()))


def example_job() -> dict:
    core = expected_core()
    return {
        "stable_item_id": "F36B-QRAF-example",
        "engineering_qra_family_id": "F36B-QRAF-example",
        "engineering_obligation_id": core.canonical_intent.engineering_obligation_id,
        "requirement_revision_id": core.requirement_revision_id,
        "requirement_content_hash": core.requirement_content_hash,
        "source_record": {
            "requirement_id": core.requirement_id,
            "title": "Transition Command Authentication",
            "statement": "The function shall accept a transition command only from an authenticated source.",
            "rationale": "This protects decision authority.",
            "requirement_type": "cybersecurity",
            "major_system_id": "F36B-M00",
            "subsystem_id": "F36B-M00-S01",
            "primary_component_family_id": core.canonical_intent.primary_component_family_id,
            "source_artifact_ids": ["F36B-ASM-PLANNING-BASELINE-R1-001"],
        },
    }


def example_family() -> dict:
    return {
        "engineering_qra_family_id": "F36B-QRAF-example",
        "canonical_qra": {},
        "variants": [
            {"variant_id": f"F36B-QRAF-example-V{index:02d}", "variant_resolution": {}}
            for index in range(1, 6)
        ],
        "claim_support": [],
        "sparta_applicability": {"state": "not_assessed"},
        "sparta_resolution": {"state": "not_run"},
        "projection_eligibility": {"qra_engineering_inventory": False, "reason_codes": []},
        "operational_authority": False,
        "certification_authority": False,
    }


def test_expected_response_is_semantic_core_without_questions() -> None:
    payload = json.loads(EXPECTED_RESPONSE_PATH.read_text())
    result = EngineeringSemanticCore.model_validate(payload)
    assert result.canonical_answer
    assert "question" not in payload
    assert "variants" not in payload


def test_semantic_core_rejects_extra_model_authored_question() -> None:
    payload = json.loads(EXPECTED_RESPONSE_PATH.read_text())
    payload["canonical_question"] = "What should happen?"
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        EngineeringSemanticCore.model_validate(payload)


def test_sparta_control_claim_is_rejected_in_engineering_stage() -> None:
    payload = json.loads(EXPECTED_RESPONSE_PATH.read_text())
    payload["canonical_answer"] += " It implements SPARTA control CM0001."
    with pytest.raises(ValueError, match="must not introduce SPARTA"):
        EngineeringSemanticCore.model_validate(payload)


def test_question_renderer_is_deterministic_and_unique() -> None:
    intent = expected_core().canonical_intent
    canonical_a, variants_a = render_questions(intent)
    canonical_b, variants_b = render_questions(intent)
    assert (canonical_a, variants_a) == (canonical_b, variants_b)
    assert canonical_a["question"].endswith("?")
    assert len({item["question"] for item in variants_a}) == 5
    assert all(item["question"].endswith("?") for item in variants_a)


def test_assembly_injects_one_byte_identical_answer_and_intent_hash() -> None:
    core = expected_core()
    assembled = assemble_family(example_family(), core, {"batch_id": "b", "item_id": "i"})
    answer = assembled["canonical_qra"]["canonical_answer_text"]
    assert all(item["answer"] == answer for item in assembled["variants"])
    assert len({item["canonical_answer_hash"] for item in assembled["variants"]}) == 1
    assert len({item["intent_hash"] for item in assembled["variants"]}) == 1
    assert assembled["variant_validator_receipt"]["status"] == "PASS"
    assert all(item["variant_resolution"]["available_for_use"] for item in assembled["variants"])


def test_independent_validator_rejects_mutated_question() -> None:
    core = expected_core()
    assembled = assemble_family(example_family(), core, {"batch_id": "b", "item_id": "i"})
    assembled["variants"][2]["question"] = "What unrelated behavior is required?"
    receipt = validate_materialized_family(assembled, core.canonical_intent)
    assert receipt["status"] == "FAIL"
    assert "variant_3_question_template_mismatch" in receipt["errors"]


def test_immutable_identity_and_source_artifacts_are_enforced() -> None:
    core = expected_core()
    validate_core_against_job(core, example_job())
    changed = core.model_copy(update={"requirement_id": "F36B-WRONG"})
    with pytest.raises(ValueError, match="immutable identity mismatch"):
        validate_core_against_job(changed, example_job())
    payload = json.loads(EXPECTED_RESPONSE_PATH.read_text())
    payload["canonical_claims"][0]["source_artifact_ids"] = ["UNSUPPLIED"]
    with pytest.raises(ValueError, match="unsupplied source"):
        validate_core_against_job(EngineeringSemanticCore.model_validate(payload), example_job())


def test_source_grounding_rejects_invented_numeric_threshold() -> None:
    payload = json.loads(EXPECTED_RESPONSE_PATH.read_text())
    payload["canonical_answer"] += " The function must respond within 17 milliseconds."
    with pytest.raises(ValueError, match="unsupplied numeric values"):
        validate_source_grounding(EngineeringSemanticCore.model_validate(payload), example_job())


def test_source_grounding_receipt_is_explicitly_bounded() -> None:
    receipt = validate_source_grounding(expected_core(), example_job())
    assert receipt["status"] == "PASS"
    assert "engineering correctness" in " ".join(receipt["claims"]["does_not_prove"])


def test_repeat_calls_have_unique_provider_ids_and_identical_prompts() -> None:
    items, call_map = build_calls([example_job()], repeat=2)
    assert [item["id"] for item in items] == [
        "F36B-QRAF-example::repeat-01",
        "F36B-QRAF-example::repeat-02",
    ]
    assert items[0]["messages"] == items[1]["messages"]
    assert [call_map[item["id"]][1] for item in items] == [1, 2]


def test_heterogeneous_selector_uses_manifest_requirement_types() -> None:
    jobs = []
    for stable_id, requirement_type in (
        ("a", "cybersecurity"),
        ("b", "supply_chain_provenance"),
        ("c", "verification_acceptance"),
    ):
        jobs.append({"stable_item_id": stable_id, "source_record": {"requirement_type": requirement_type}})
    selected = select_jobs(
        {"jobs": jobs}, 0, None, "cybersecurity,supply_chain,verification"
    )
    assert [item["stable_item_id"] for item in selected] == ["a", "b", "c"]


def test_intent_hash_is_stable_for_structurally_equal_intents() -> None:
    intent = expected_core().canonical_intent
    copy = EngineeringIntent.model_validate(intent.model_dump())
    assert canonical_json_hash(intent.model_dump()) == canonical_json_hash(copy.model_dump())


def test_review_blocks_wrong_cardinality() -> None:
    result = review_manifest({"families": [], "jobs": [], "generation_contract": {}})
    assert result["verdict"]["status"] == "BLOCKED"
    assert result["blocking_issues"]
