"""Unit + integration tests for the qualification gate's record scoping.

The (run_id, revision_id) Memory keyspace legitimately holds governance/audit
records alongside the 27 qualification records.  The exact-match gate must
select the qualification records by record identity (schema / record_type /
stable-key prefix), count exactly 27, exact-reread each, and fail closed on any
missing, duplicate, tampered, or malformed qualification record -- while
ignoring (never counting) governance records that share the keyspace.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


SKILL_ROOT = Path(__file__).parents[1]
PREPARE_SCRIPT = SKILL_ROOT / "scripts" / "prepare_revision_qualification.py"
PREPARE_TESTS = SKILL_ROOT / "tests" / "test_revision_memory_qualification.py"
COLLECTION = "project_knowledge"


def load_module(name: str, path: Path) -> ModuleType:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PD = load_module("persona_dream_prepare_for_scoping", PREPARE_SCRIPT)
FIXTURE = load_module("persona_dream_memory_fixture_for_scoping", PREPARE_TESTS)
REVISION_ID = FIXTURE.REVISION_ID
SOURCE_COMMIT = FIXTURE.SOURCE_COMMIT

EXPECTED_COUNTS = {
    "revision": 1,
    "phase": 10,
    "required_artifact": 16,
    "total": 27,
}


def qualification_documents(tmp_path: Path) -> list[dict[str, Any]]:
    """Build the real 27 VERIFIED qualification documents from a fixture."""
    run_root, _ = FIXTURE.write_revision(tmp_path)
    snapshot = PD.load_snapshot(run_root, REVISION_ID, SOURCE_COMMIT)
    documents, _ = PD.build_documents(snapshot, lifecycle_state="VERIFIED")
    # Attach synced semantic pointers so the docs re-read as a live Memory would
    # return them.
    for document in documents:
        document.update(
            {
                "qdrant_collection": "memory_semantic",
                "qdrant_point_id": f"point-{document['_key']}",
                "embedding_model": "fake-embedding-model",
                "embedding_version": "v1",
                "text_hash": "deadbeef",
                "semantic_sync_state": "synced",
            }
        )
    assert len(documents) == 27
    return documents


def governance_record(suffix: str, record_type: str, **extra: Any) -> dict[str, Any]:
    document = {
        "_key": f"persona_dream:pipeline-complete:{REVISION_ID}:{suffix}",
        "schema": f"persona_dream.{record_type}.v1",
        "kind": "persona_dream_governance_audit",
        "record_type": record_type,
        "run_id": "pipeline-complete",
        "revision_id": REVISION_ID,
        "qdrant_collection": "memory_semantic",
        "qdrant_point_id": f"point-gov-{suffix}",
        "embedding_model": "fake-embedding-model",
        "embedding_version": "v1",
        "text_hash": "cafe",
        "semantic_sync_state": "synced",
    }
    document.update(extra)
    return document


GOVERNANCE = [
    governance_record("07r:reviewer_calibration_v4", "reviewer_calibration_v4"),
    governance_record("38:lane_c_blocker", "step38_lane_c_blocker"),
    governance_record("acceptance_rung_v4", "acceptance_rung_v4"),
]


# --------------------------------------------------------------------------- #
# scope_qualification_documents / validate_exact_records unit tests
# --------------------------------------------------------------------------- #


def test_scope_ignores_governance_records(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    observed = qual + GOVERNANCE
    qualification, governance = PD.scope_qualification_documents(observed)
    assert len(qualification) == 27
    assert len(governance) == len(GOVERNANCE)


def test_gate_passes_with_27_qualification_plus_n_governance(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    result = PD.validate_exact_records(qual, qual + GOVERNANCE)
    assert result["counts"] == EXPECTED_COUNTS
    assert result["governance_ignored_count"] == len(GOVERNANCE)
    # Governance records are never counted regardless of how many exist.
    many_governance = [
        governance_record(f"extra_{index}", f"gov_kind_{index}")
        for index in range(25)
    ]
    result_more = PD.validate_exact_records(qual, qual + many_governance)
    assert result_more["counts"] == EXPECTED_COUNTS
    assert result_more["governance_ignored_count"] == 25


def test_gate_fails_on_26_qualification_records(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    observed = qual[:-1] + GOVERNANCE  # 26 qualification + governance
    with pytest.raises(PD.GateBlocked) as excinfo:
        PD.validate_exact_records(qual, observed)
    assert excinfo.value.code == "BLOCKED_MEMORY_RECORD_KEYS_MISMATCH"
    assert excinfo.value.details["missing_keys"] == [qual[-1]["_key"]]


def test_gate_fails_on_duplicate_qualification_record(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    observed = qual + [copy.deepcopy(qual[0])]  # duplicate the revision record
    with pytest.raises(PD.GateBlocked) as excinfo:
        PD.validate_exact_records(qual, observed)
    assert excinfo.value.code == "BLOCKED_MEMORY_QUALIFICATION_RECORD_DUPLICATE"
    assert qual[0]["_key"] in excinfo.value.details["duplicate_keys"]


def test_gate_fails_on_tampered_content_hash(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    tampered = copy.deepcopy(qual)
    # Flip a durable content field on a phase record; its stored contract hash no
    # longer matches the expected document.
    phase = next(item for item in tampered if item["record_type"] == "phase")
    phase["document_contract_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(PD.GateBlocked) as excinfo:
        PD.validate_exact_records(qual, tampered + GOVERNANCE)
    assert excinfo.value.code == "BLOCKED_MEMORY_DOCUMENT_MISMATCH"
    assert excinfo.value.details["field"] == "document_contract_sha256"


def test_gate_fails_on_malformed_qualification_claim(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    # A record claiming a qualification schema but carrying a governance
    # record_type is malformed -> fail closed, never silently ignored.
    impostor = governance_record(
        "impostor",
        "reviewer_calibration_v4",
        schema="persona_dream.pipeline_phase.v1",
    )
    with pytest.raises(PD.GateBlocked) as excinfo:
        PD.scope_qualification_documents(qual + [impostor])
    assert excinfo.value.code == "BLOCKED_MEMORY_QUALIFICATION_RECORD_MALFORMED"


def test_semantic_pointers_scoped_to_qualification(tmp_path: Path) -> None:
    qual = qualification_documents(tmp_path)
    # A governance record with no semantic pointers must not fail the gate.
    unsynced_governance = governance_record("audit", "state_clearing_audit")
    for field in (
        "qdrant_collection",
        "qdrant_point_id",
        "embedding_model",
        "embedding_version",
        "text_hash",
    ):
        unsynced_governance.pop(field, None)
    unsynced_governance["semantic_sync_state"] = "missing"
    result = PD.validate_semantic_pointers(qual + [unsynced_governance])
    assert result["pointer_count"] == 27
    assert result["expected_pointer_count"] == 27


# --------------------------------------------------------------------------- #
# End-to-end integration through the live-shaped fake Memory server
# --------------------------------------------------------------------------- #


def _run(run_root: Path, memory_url: str, command: str) -> subprocess.CompletedProcess[str]:
    return FIXTURE.run_command(run_root, memory_url, command)


def test_end_to_end_prepare_verify_with_governance_in_keyspace(tmp_path: Path) -> None:
    run_root, revision_root = FIXTURE.write_revision(tmp_path)
    with FIXTURE.fake_memory_server() as (memory_url, state):
        prepared = _run(run_root, memory_url, "prepare")
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr

        # Inject governance/audit records into the SAME keyspace after prepare,
        # exactly as the sanctioned governance persist path historically did.
        stored = state.collections[COLLECTION]
        for record in GOVERNANCE:
            stored[record["_key"]] = dict(record)
        assert len(stored) == 27 + len(GOVERNANCE)

        verified = _run(run_root, memory_url, "verify")
        assert verified.returncode == 0, verified.stdout + verified.stderr
        verify_receipt = json.loads(
            (revision_root / "revision_memory_verify_receipt.json").read_text()
        )
        assert verify_receipt["records"]["after_counts"] == EXPECTED_COUNTS
        assert verify_receipt["records"]["before_counts"] == EXPECTED_COUNTS

        # Repeat prepare with governance still present -> still passes.
        repeated = _run(run_root, memory_url, "prepare")
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
