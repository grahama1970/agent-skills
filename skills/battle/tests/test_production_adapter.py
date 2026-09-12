"""Production adapter tests: authorization-first, zero launches on failure."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.production_adapter import run_production_round  # noqa: E402
from test_campaign_contract import (  # noqa: E402
    _profile, _request, _clean_target,
)

AUTH = str(HERE.parent / "fixtures" / "reactive-judge" / "authorization.json")
TARGET = "battle-reactive-judge-fixture@sha256:reactive-judge-v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _enrollment(path: Path, *, bundle: Path | None = None, required: bool = False) -> Path:
    doc = {
        "schema": "battle.project_contract_enrollment.v1",
        "target_identity": TARGET,
        "acceptance_contract": {"required": required},
    }
    if required:
        doc["acceptance_contract"].update({"bundle_path": str(bundle), "sha256": _sha256(bundle)})
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_invalid_authorization_means_zero_launches(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": "some-other-target-id",
               "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
               "base_request": base}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "adapter-authorization-invalid"
    assert result["target_launches"] == 0
    # the contract work root must not contain any executed output
    assert not (tmp_path / "work" / "out").exists() or not any(
        (tmp_path / "work" / "out").iterdir())


def test_missing_authorization_fields_block(tmp_path: Path):
    result = run_production_round({"schema": "battle.production_adapter_request.v1"})
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "adapter-authorization-missing"
    assert result["target_launches"] == 0


def test_valid_authorization_delegates_to_the_same_evaluator(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
               "base_request": base}
    result = run_production_round(adapter)
    assert result["status"] == "PASS", result.get("campaign", {}).get("aggregation")
    assert result["target_launches"] == 2
    assert result["campaign"]["schema"] == "battle.campaign_contract_receipt.v1"


def _acceptance_bundle(path: Path, *, open_questions: bool = False) -> Path:
    bundle = {
        "schema": "acceptance_contract.bundle.v1",
        "project_name": "demo",
        "source": {"kind": "file", "path": "brief.md", "sha256": "0" * 64, "files": []},
        "requirements": [{
            "id": "REQ-001",
            "kind": "acceptance",
            "statement": "The arena must replay the client floor cases.",
            "source_path": "brief.md",
            "source_line": 1,
            "evidence_text": "The arena must replay the client floor cases.",
        }],
        "acceptance_cases": [{
            "id": "AC-001",
            "requirement_id": "REQ-001",
            "kind": "MUST_VERIFY",
            "predicate": "client floor replay passes",
            "deterministic_check": "battle campaign required case replay",
            "proof_artifacts": ["receipt.json"],
        }],
        "open_questions": ([{"id": "Q-001", "question": "missing?", "source_path": "brief.md", "source_line": 2}]
                           if open_questions else []),
        "immutable_goal": None,
        "non_claims": ["fixture"],
    }
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def test_acceptance_contract_floor_is_required_before_launch(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(
                   tmp_path / "enrollment.json",
                   bundle=_acceptance_bundle(tmp_path / "acceptance_bundle.json"),
                   required=True,
               )),
               "base_request": base,
               "acceptance_floor": {
                   "case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}},
               }}
    result = run_production_round(adapter)
    assert result["status"] == "PASS", result.get("acceptance_floor")
    assert result["acceptance_floor"]["status"] == "PASS"
    assert result["acceptance_floor"]["case_map"]["AC-001"]["case_ids"] == ["case-str", "case-int"]
    assert result["executed_acceptance_floor"]["status"] == "PASS"
    assert result["target_launches"] == 2
    phase_plan = result["post_acceptance_phase_plan"]
    assert phase_plan["phase_order"] == ["acceptance-floor", "research-expansion", "adaptive-lineage"]
    assert phase_plan["release_gate"]["must_run_ask_one_shot_or_attach_reviewer_receipts"] is True
    assert phase_plan["phases"][1]["id"] == "research-expansion"
    assert phase_plan["phases"][2]["id"] == "adaptive-lineage"


def test_acceptance_contract_floor_blocks_unmapped_cases_before_launch(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(
                   tmp_path / "enrollment.json",
                   bundle=_acceptance_bundle(tmp_path / "acceptance_bundle.json"),
                   required=True,
               )),
               "base_request": base,
               "acceptance_floor": {
                   "case_map": {},
               }}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "acceptance-floor-incomplete"
    assert result["target_launches"] == 0
    assert "acceptance-case-unmapped:AC-001" in result["acceptance_floor"]["problems"]


def test_acceptance_contract_floor_blocks_cases_not_in_required_profile(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(
                   tmp_path / "enrollment.json",
                   bundle=_acceptance_bundle(tmp_path / "acceptance_bundle.json"),
                   required=True,
               )),
               "base_request": base,
               "acceptance_floor": {
                   "case_map": {"AC-001": {"case_ids": ["case-str", "bonus-fuzz"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}},
               }}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["target_launches"] == 0
    assert "acceptance-case-not-required:AC-001:bonus-fuzz" in result["acceptance_floor"]["problems"]


def test_acceptance_contract_floor_blocks_open_questions_before_launch(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(
                   tmp_path / "enrollment.json",
                   bundle=_acceptance_bundle(tmp_path / "acceptance_bundle.json", open_questions=True),
                   required=True,
               )),
               "base_request": base,
               "acceptance_floor": {
                   "case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}},
               }}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["target_launches"] == 0
    assert "bundle-open-questions" in result["acceptance_floor"]["problems"]


def test_docker_boundary_blocks_host_commands_before_launch(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    base["target_run_cmd"] = "python3 -c 'print(1)'"
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": TARGET,
               "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
               "base_request": base,
               "enforce_docker_boundary": True}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "docker-boundary-invalid"
    assert result["target_launches"] == 0
    assert "docker-command-required" in result["docker_boundary"]["problems"]
