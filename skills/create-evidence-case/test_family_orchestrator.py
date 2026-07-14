from pathlib import Path

from family_orchestrator import (
    _usable_edge,
    requirement_content_hash,
    validate_family_input,
)


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
