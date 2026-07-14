from pathlib import Path

from family_orchestrator import (
    _assertion_question,
    _build_assertion_manifest,
    _usable_edge,
    requirement_content_hash,
    run_family_orchestration,
    validate_family_input,
)
from runner import restrict_to_expected_entities


def _envelope(workbook: Path, release_hash: str) -> dict:
    requirement = {
        "requirement_id": "F36B-M09-S01-C02-VER-006",
        "title": "TT&C Cybersecurity Verification",
        "statement": "The plan shall verify replay rejection.",
        "rationale": "Future evidence is required.",
        "major_system_id": "F36B-M09",
        "subsystem_id": "F36B-M09-S01",
        "component_family_id": "F36B-M09-S01-C02",
        "requirement_type": "verification_acceptance",
        "verification_method": "test",
        "verification_artifact_types": ["record"],
        "lifecycle_phase_ids": ["F36B-P01"],
        "traceability": {"supersession": {"revision_id": "F36B-M09-S01-C02-VER-006@R2"}},
    }
    family_id = "F36B-QRAF-a86bc97962a9da466808"
    answer = "The plan verifies replay rejection."
    intent_hash = "sha256:" + "1" * 64
    family = {
        "engineering_qra_family_id": family_id,
        "engineering_obligation_id": "F36B-OBL-test",
        "requirement_id": requirement["requirement_id"],
        "requirement_revision_id": "F36B-M09-S01-C02-VER-006@R2",
        "requirement_content_hash": requirement_content_hash(requirement),
        "primary_component_family_id": requirement["component_family_id"],
        "canonical_question": "What must the plan verify?",
        "canonical_answer": answer,
        "canonical_intent": {"required_behavior": "verify replay rejection"},
        "variants": [
            {
                "variant_id": f"{family_id}-V{i:02d}",
                "role": role,
                "difficulty": difficulty,
                "question": "Question",
                "answer": answer,
                "intent_hash": intent_hash,
            }
            for i, (role, difficulty) in enumerate(
                (
                    ("operator", "simple"),
                    ("project_manager", "simple"),
                    ("systems_engineer", "medium"),
                    ("cybersecurity_compliance_officer", "medium"),
                    ("mission_assurance_cybersecurity_reviewer", "advanced"),
                ),
                start=1,
            )
        ],
    }
    return {
        "schema": "f36.evidence_orchestration_family_input.v1",
        "requirement": requirement,
        "family": family,
        "sparta_corpus": {
            "release_id": "sparta-excel-v3.1-9cbd7eef12547bd0",
            "release_hash": release_hash,
            "source_path": str(workbook),
        },
        "applicability_route": "direct_space",
        "triage": {"disposition": "candidate_applicable", "reason_codes": ["direct_space_security"]},
    }


def test_family_input_rejects_variant_answer_drift(tmp_path):
    workbook = tmp_path / "SPARTA-Data.xlsx"
    workbook.write_bytes(b"fixture")
    from family_orchestrator import sha256_file

    envelope = _envelope(workbook, sha256_file(workbook))
    assert validate_family_input(envelope) == []
    envelope["family"]["variants"][2]["answer"] = "Changed"
    assert "variant answer differs from canonical answer" in validate_family_input(envelope)


def test_usable_edge_requires_direction_type_and_nonrejected_state():
    edge = {
        "_id": "sparta_relationships/example",
        "source_control_id": "SC-50",
        "target_control_id": "EX-0001.02",
        "type": "control_relationship",
        "edge_type": "control_relationship",
        "review_status": "needs_review",
    }
    assert _usable_edge(edge, "SC-50", "EX-0001.02")
    edge["normal_coverage_excluded"] = True
    assert not _usable_edge(edge, "SC-50", "EX-0001.02")


def test_family_input_rejects_unknown_triage_disposition(tmp_path):
    workbook = tmp_path / "SPARTA-Data.xlsx"
    workbook.write_bytes(b"fixture")
    from family_orchestrator import sha256_file

    envelope = _envelope(workbook, sha256_file(workbook))
    envelope["triage"]["disposition"] = "invented"
    assert "invalid triage disposition" in validate_family_input(envelope)


def test_informational_family_is_in_scope_without_evidence_execution(tmp_path):
    workbook = tmp_path / "SPARTA-Data.xlsx"
    workbook.write_bytes(b"fixture")
    from family_orchestrator import sha256_file

    envelope = _envelope(workbook, sha256_file(workbook))
    envelope["applicability_route"] = "control_only"
    envelope["triage"] = {
        "disposition": "informational",
        "reason_codes": ["no_material_sparta_assertion"],
    }
    snapshot = run_family_orchestration(envelope, tmp_path / "snapshot.json")

    assert snapshot["live"] is False
    assert snapshot["applicability"]["sparta_applicability"] == "sparta_applicable"
    assert snapshot["evidence_required"] is False
    assert snapshot["evidence_execution_state"] == "not_required"
    assert snapshot["crosswalk_resolution_state"] == "not_attempted"
    assert snapshot["evidence_verdict"] is None
    assert snapshot["family_disposition"] == "informational"
    assert snapshot["terminal_disposition"] == "INFORMATIONAL"
    assert snapshot["assertion_evidence_evaluations"] == 0
    assert snapshot["stage_receipts"]["assertion_evidence_outcomes"] == []


def test_assertion_manifest_is_frozen_and_question_is_requirement_bound():
    family = {"engineering_qra_family_id": "F36B-QRAF-test"}
    path = {
        "path_signature": "sha256:" + "2" * 64,
        "persisted_edge_ids": ["sparta_relationships/example"],
        "nodes": [
            {"source_framework": "NIST", "control_id": "AC-3", "name": "Access Enforcement"},
            {"source_framework": "SPARTA", "control_id": "IA-0007", "name": "Compromise Ground System"},
        ],
    }
    manifest = _build_assertion_manifest(family, "ground_segment", [path])
    assertion = manifest["assertions"][0]
    question = _assertion_question(
        {
            "protected_object_or_interface": "ground command interface",
            "condition": "before accepting a command",
            "required_behavior": "authenticate the command source",
            "expected_outcome": "unauthorized commands are rejected",
        },
        assertion,
    )

    assert manifest["manifest_hash"].startswith("sha256:")
    assert assertion["relationship_role"] == "mitigation"
    assert assertion["candidate_material"] is True
    assert "authenticate the command source" in question
    assert "before accepting a command" in question
    assert "ground command interface" in question
    assert "unauthorized commands are rejected" in question
    assert "NIST AC-3 (Access Enforcement)" in question
    assert "SPARTA IA-0007 (Compromise Ground System)" in question
    assert "F36B-" not in question
    assert "sparta_relationships/" not in question


def test_expected_entity_restriction_ignores_context_and_spurious_role_entity():
    entities = {
        "ok": True,
        "grounding_ok": False,
        "resolved_entities": [
            {"canonical_id": "SC-49", "canonical_name": "Hardware Separation"},
            {"canonical_id": "DE-0009.05", "canonical_name": "Ground SDA Overload"},
            {"canonical_id": "MID-001", "canonical_name": "Spurious mitigation match"},
        ],
        "unresolved_entities": [
            {"mention": "engineering obligation", "reason": "not_in_corpus"},
        ],
        "external_entities": [{"mention": "acceptance plan"}],
    }
    normalized, grounding_ok, resolved, unresolved, external = restrict_to_expected_entities(
        entities,
        ["SC-49", "DE-0009.05"],
        exact_path_proven=True,
    )

    assert grounding_ok is True
    assert [item["canonical_id"] for item in resolved] == ["SC-49", "DE-0009.05"]
    assert unresolved == []
    assert external == []
    assert normalized["technique_coherence"] == {
        "ok": True,
        "detail": "pre_grounded_exact_persisted_path",
    }
