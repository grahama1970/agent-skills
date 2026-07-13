from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from f36_requirement_qra import (  # noqa: E402
    CONTRACT_VERSION,
    OUTPUT_BATCH_SCHEMA,
    CompleteBatchEnvelope,
    CompleteFamily,
    WEBGPT_EXPECTED_BATCH_PATH,
    build_export_bundle,
    canonical_json_hash,
    export_webgpt_batch,
    import_webgpt_batch,
    review_manifest,
    sha256_file,
)


def make_manifest(count: int = 205) -> dict:
    jobs = []
    families = []
    variant_plan = [
        {"role": "operator", "difficulty": "simple"},
        {"role": "project_manager", "difficulty": "simple"},
        {"role": "systems_engineer", "difficulty": "medium"},
        {"role": "cybersecurity_compliance_officer", "difficulty": "medium"},
        {"role": "mission_assurance_cybersecurity_reviewer", "difficulty": "advanced"},
    ]
    for index in range(1, count + 1):
        suffix = f"{index:04d}"
        family_id = f"F36B-QRAF-{suffix}"
        requirement_id = f"F36B-REQ-{suffix}"
        jobs.append(
            {
                "job_id": f"F36B-JOB-{suffix}",
                "job_type": "engineering_qra_family",
                "stable_item_id": f"F36B-QRAF-STABLE-{suffix}",
                "engineering_qra_family_id": family_id,
                "engineering_obligation_id": f"F36B-OBL-{suffix}",
                "requirement_revision_id": f"{requirement_id}-R1",
                "requirement_content_hash": "sha256:" + f"{index:064x}"[-64:],
                "requested_variant_plan": variant_plan,
                "source_record": {
                    "requirement_id": requirement_id,
                    "title": "Transition-command acceptance function",
                    "statement": (
                        "The transition-command acceptance function shall accept the command only from an "
                        "authenticated source when a transition command is received so unauthenticated "
                        "transition commands are rejected."
                    ),
                    "rationale": "This preserves authenticated transition-command handling.",
                    "requirement_type": "cybersecurity",
                    "major_system_id": "F36B-M00",
                    "subsystem_id": "F36B-M00-S01",
                    "primary_component_family_id": "F36B-M00-S01-C01",
                    "affected_component_family_ids": [],
                    "source_artifact_ids": ["F36B-ARCH-R2"],
                },
            }
        )
        families.append(
            {
                "engineering_qra_family_id": family_id,
                "variants": [
                    {"variant_id": f"{family_id}-V{position:02d}"} for position in range(1, 6)
                ],
            }
        )
    return {
        "schema": "f36.synthetic_engineering_qra_generation_manifest.v1",
        "jobs": jobs,
        "families": families,
    }


def make_complete_family(exported: dict) -> dict:
    intent = {
        "engineering_obligation_id": exported["engineering_obligation_id"],
        "primary_component_family_id": exported["primary_component_family_id"],
        "protected_object_or_interface": "transition-command acceptance function",
        "condition": "when a transition command is received",
        "required_behavior": "accept the command only from an authenticated source",
        "expected_outcome": "unauthenticated transition commands are rejected",
        "source_fragments": {
            "protected_object_or_interface": "transition-command acceptance function",
            "condition": "when a transition command is received",
            "required_behavior": "accept the command only from an authenticated source",
            "expected_outcome": "unauthenticated transition commands are rejected",
        },
    }
    answer = (
        "When a transition command is received, the transition-command acceptance function must "
        "accept the command only from an authenticated source so unauthenticated transition commands are rejected."
    )
    questions = [
        "When a transition command is received, what must the transition-command acceptance function do to accept the command only from an authenticated source so unauthenticated transition commands are rejected?",
        "When a transition command is received, how should the transition-command acceptance function accept the command only from an authenticated source and ensure unauthenticated transition commands are rejected?",
        "For project delivery, when a transition command is received, what must the transition-command acceptance function do to accept the command only from an authenticated source so unauthenticated transition commands are rejected?",
        "For systems engineering, when a transition command is received, how shall the transition-command acceptance function accept the command only from an authenticated source so unauthenticated transition commands are rejected?",
        "For cybersecurity compliance, when a transition command is received, what must the transition-command acceptance function do to accept the command only from an authenticated source so unauthenticated transition commands are rejected?",
        "For mission assurance review, when a transition command is received, how must the transition-command acceptance function accept the command only from an authenticated source so unauthenticated transition commands are rejected?",
    ]
    intent_hash = canonical_json_hash(intent)
    return {
        "schema": "f36.webgpt_complete_family.v1",
        "stable_item_id": exported["stable_item_id"],
        "engineering_qra_family_id": exported["engineering_qra_family_id"],
        "engineering_obligation_id": exported["engineering_obligation_id"],
        "requirement_id": exported["requirement_id"],
        "requirement_revision_id": exported["requirement_revision_id"],
        "requirement_content_hash": exported["requirement_content_hash"],
        "primary_component_family_id": exported["primary_component_family_id"],
        "canonical_question": questions[0],
        "canonical_answer": answer,
        "canonical_intent": intent,
        "variants": [
            {
                "variant_id": variant["variant_id"],
                "role": variant["role"],
                "difficulty": variant["difficulty"],
                "question": questions[position],
                "answer": answer,
                "intent_hash": intent_hash,
            }
            for position, variant in enumerate(exported["variants"], start=1)
        ],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "engineering_qra_state": "generated_candidate",
        "sparta_applicability": "not_assessed",
        "sparta_resolution": "not_run",
        "resolved_control_ids": [],
        "crosswalk_chain_ids": [],
        "evidence_case_id": None,
    }


def write_batch(path: Path, exported_bundle: dict, families: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": OUTPUT_BATCH_SCHEMA,
                "export_id": exported_bundle["export_id"],
                "canonical_input_sha256": exported_bundle["canonical_input_sha256"],
                "synthetic": True,
                "operational_authority": False,
                "certification_authority": False,
                "families": families,
            },
            indent=2,
        )
        + "\n"
    )


def run_import(tmp_path: Path, exported_bundle: dict, output_batch: dict | None = None, transport=False):
    requirements_path = tmp_path / "requirements.json"
    request_path = tmp_path / "request.md"
    complete_path = tmp_path / "complete.json"
    accepted_path = tmp_path / "accepted.json"
    quarantine_path = tmp_path / "quarantine.json"
    receipt_path = tmp_path / "receipt.json"
    requirements_path.write_text(json.dumps(exported_bundle, indent=2) + "\n")
    request_path.write_text("request\n")
    if output_batch is None:
        families = [make_complete_family(item) for item in exported_bundle["requirements"]]
        write_batch(complete_path, exported_bundle, families)
    else:
        complete_path.write_text(json.dumps(output_batch, indent=2) + "\n")
    transport_path = None
    if transport:
        transport_path = tmp_path / "transport.json"
        transport_path.write_text(
            json.dumps(
                {
                    "schema": "create_qras.webgpt_transport_receipt.v1",
                    "status": "completed",
                    "export_id": exported_bundle["export_id"],
                    "canonical_input_sha256": exported_bundle["canonical_input_sha256"],
                    "request_sha256": sha256_file(request_path),
                    "output_sha256": sha256_file(complete_path),
                    "mocked": False,
                    "live": True,
                },
                indent=2,
            )
            + "\n"
        )
    receipt = import_webgpt_batch(
        requirements_path,
        complete_path,
        accepted_path,
        quarantine_path,
        receipt_path,
        transport_path,
    )
    return receipt, json.loads(accepted_path.read_text()), json.loads(quarantine_path.read_text())


def test_expected_one_record_webgpt_fixture_is_closed_and_concrete() -> None:
    payload = json.loads(WEBGPT_EXPECTED_BATCH_PATH.read_text())
    envelope = CompleteBatchEnvelope.model_validate(payload)
    assert len(envelope.families) == 1
    family = CompleteFamily.model_validate(envelope.families[0])
    assert len(family.variants) == 5
    assert all(item.answer == family.canonical_answer for item in family.variants)


def test_export_batch_one_size_200_has_stable_order_and_1000_variants(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(make_manifest(205)))
    receipt = export_webgpt_batch(manifest_path, 1, 200, tmp_path / "out")
    exported = json.loads((tmp_path / "out" / "requirements.json").read_text())
    assert receipt["requirement_count"] == 200
    assert receipt["expected_family_count"] == 200
    assert receipt["expected_variant_count"] == 1000
    assert exported["requirements"][0]["stable_item_id"] == "F36B-QRAF-STABLE-0001"
    assert exported["requirements"][-1]["stable_item_id"] == "F36B-QRAF-STABLE-0200"
    assert [item["role"] for item in exported["requirements"][0]["variants"]] == [
        "operator",
        "project_manager",
        "systems_engineer",
        "cybersecurity_compliance_officer",
        "mission_assurance_cybersecurity_reviewer",
    ]
    assert (tmp_path / "out" / "request.md").exists()
    assert (tmp_path / "out" / "export-receipt.json").exists()


def test_export_batch_ordinal_selects_stable_manifest_slice() -> None:
    exported = build_export_bundle(make_manifest(205), batch_ordinal=2, batch_size=200)
    assert exported["requirement_count"] == 5
    assert exported["requirements"][0]["stable_item_id"] == "F36B-QRAF-STABLE-0201"
    assert exported["requirements"][-1]["stable_item_id"] == "F36B-QRAF-STABLE-0205"


def test_positive_import_accepts_one_family_and_is_not_live_without_transport(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    receipt, accepted, quarantine = run_import(tmp_path, exported)
    assert receipt["status"] == "completed"
    assert receipt["accepted_family_count"] == 1
    assert receipt["accepted_variant_count"] == 5
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert accepted["usable"] is True
    assert quarantine["records"] == []


def test_proven_transport_receipt_sets_live_true(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    receipt, accepted, _ = run_import(tmp_path, exported, transport=True)
    assert receipt["status"] == "completed"
    assert receipt["transport_state"] == "verified"
    assert receipt["live"] is True
    assert accepted["live"] is True


def test_byte_identical_answer_is_required(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    family = make_complete_family(exported["requirements"][0])
    family["variants"][2]["answer"] += " changed"
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [family],
    }
    receipt, accepted, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert accepted["families"] == []
    assert "variant_3_answer_not_byte_identical" in quarantine["records"][0]["reasons"]


@pytest.mark.parametrize(
    ("mutator", "expected_reason"),
    [
        (lambda family: family.update({"unexpected": True}), "closed_schema_invalid"),
        (lambda family: family.update({"requirement_id": "F36B-REQ-WRONG"}), "requirement_id_mismatch"),
        (lambda family: family.update({"operational_authority": True}), "closed_schema_invalid"),
        (lambda family: family.update({"resolved_control_ids": ["CWE-79"]}), "closed_schema_invalid"),
        (lambda family: family.update({"canonical_answer": family["canonical_answer"] + " SPARTA CWE-79"}), "sparta_or_control_id_introduced"),
    ],
)
def test_adversarial_family_rejections(tmp_path: Path, mutator, expected_reason: str) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    family = make_complete_family(exported["requirements"][0])
    mutator(family)
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [family],
    }
    receipt, accepted, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert accepted["usable"] is False
    assert any(expected_reason in reason for reason in quarantine["records"][0]["reasons"])


def test_duplicate_family_rejects_entire_batch_atomically(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(2), 1, 2)
    first = make_complete_family(exported["requirements"][0])
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [first, deepcopy(first)],
    }
    receipt, accepted, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert receipt["accepted_family_count"] == 0
    assert receipt["quarantined_family_count"] == 2
    assert accepted["families"] == []
    reasons = {item["engineering_qra_family_id"]: item["reasons"] for item in quarantine["records"]}
    assert any("duplicate_family_id" in reason for reason in reasons[first["engineering_qra_family_id"]])
    assert "missing_family" in reasons[exported["requirements"][1]["engineering_qra_family_id"]]


def test_missing_family_rejects_whole_batch_and_withholds_valid_family(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(2), 1, 2)
    valid = make_complete_family(exported["requirements"][0])
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [valid],
    }
    receipt, accepted, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert accepted["families"] == []
    reasons = {item["engineering_qra_family_id"]: item["reasons"] for item in quarantine["records"]}
    assert reasons[valid["engineering_qra_family_id"]] == ["atomic_batch_withheld"]
    assert reasons[exported["requirements"][1]["engineering_qra_family_id"]] == ["missing_family"]


def test_invented_numeric_threshold_is_rejected(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    family = make_complete_family(exported["requirements"][0])
    family["canonical_answer"] += " The response occurs within 17 milliseconds."
    for variant in family["variants"]:
        variant["answer"] = family["canonical_answer"]
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [family],
    }
    receipt, _, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert any("invented_numeric_values:17" in reason for reason in quarantine["records"][0]["reasons"])



def test_semantic_expansion_is_rejected(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    family = make_complete_family(exported["requirements"][0])
    family["canonical_answer"] += " It also inspects the thermal manifold."
    for variant in family["variants"]:
        variant["answer"] = family["canonical_answer"]
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [family],
    }
    receipt, _, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert any("semantic_expansion_tokens" in reason for reason in quarantine["records"][0]["reasons"])


def test_tampered_export_hash_rejects_batch(tmp_path: Path) -> None:
    exported = build_export_bundle(make_manifest(1), 1, 1)
    exported["requirements"][0]["source_record"]["statement"] += " tampered"
    family = make_complete_family(exported["requirements"][0])
    output = {
        "schema": OUTPUT_BATCH_SCHEMA,
        "export_id": exported["export_id"],
        "canonical_input_sha256": exported["canonical_input_sha256"],
        "synthetic": True,
        "operational_authority": False,
        "certification_authority": False,
        "families": [family],
    }
    receipt, accepted, quarantine = run_import(tmp_path, exported, output)
    assert receipt["status"] == "rejected"
    assert accepted["usable"] is False
    assert "requirements_export_canonical_input_hash_mismatch" in quarantine["batch_errors"]

def test_review_manifest_uses_webgpt_contract_and_no_provider() -> None:
    result = review_manifest(make_manifest(3680))
    assert result["verdict"]["status"] == "FULL_RUN_OK"
    assert result["execution_surface"] == "deterministic_webgpt_export_import"
    assert result["provider_calls"] is False
    assert result["contract"] == CONTRACT_VERSION
