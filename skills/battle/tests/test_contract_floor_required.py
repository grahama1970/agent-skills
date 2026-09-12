"""Battle B03: enrollment-owned acceptance floor cannot be bypassed."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.production_adapter import run_production_round  # noqa: E402
from test_campaign_contract import _clean_target, _profile, _request  # noqa: E402
from test_production_adapter import AUTH, _acceptance_bundle  # noqa: E402

TARGET = "battle-reactive-judge-fixture@sha256:reactive-judge-v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _enrollment(path: Path, *, bundle: Path | None, required: bool = True, digest: str | None = None) -> Path:
    payload = {
        "schema": "battle.project_contract_enrollment.v1",
        "target_identity": TARGET,
        "acceptance_contract": {"required": required},
    }
    if required:
        payload["acceptance_contract"].update({
            "bundle_path": str(bundle),
            "sha256": digest or _sha256(bundle),
        })
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _adapter(tmp_path: Path, *, enrollment: Path | None, acceptance_floor: dict | None) -> dict:
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "base_request": base,
    }
    if enrollment is not None:
        adapter["project_contract_enrollment"] = str(enrollment)
    if acceptance_floor is not None:
        adapter["acceptance_floor"] = acceptance_floor
    return adapter


def test_enrolled_contract_floor_runs_from_retained_approved_bundle(tmp_path: Path):
    bundle = _acceptance_bundle(tmp_path / "acceptance_bundle.json")
    enrollment = _enrollment(tmp_path / "enrollment.json", bundle=bundle)
    result = run_production_round(_adapter(
        tmp_path,
        enrollment=enrollment,
        acceptance_floor={"case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}}},
    ))
    assert result["status"] == "PASS", result.get("acceptance_floor")
    retained = result["retained_acceptance_bundle"]
    assert retained["status"] == "PASS"
    assert retained["sha256"] == _sha256(bundle)
    assert Path(retained["path"]).is_file()
    assert result["acceptance_floor"]["bundle_sha256"] == result["acceptance_floor"]["approved_bundle_sha256"]
    assert result["target_launches"] == 2


def test_missing_enrollment_blocks_before_launch(tmp_path: Path):
    result = run_production_round(_adapter(
        tmp_path,
        enrollment=None,
        acceptance_floor={"case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}}},
    ))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "project-contract-enrollment-invalid"
    assert result["target_launches"] == 0
    assert "project-enrollment-missing" in result["project_contract_enrollment"]["problems"]


def test_null_acceptance_floor_blocks_when_enrollment_requires_contract(tmp_path: Path):
    bundle = _acceptance_bundle(tmp_path / "acceptance_bundle.json")
    enrollment = _enrollment(tmp_path / "enrollment.json", bundle=bundle)
    result = run_production_round(_adapter(tmp_path, enrollment=enrollment, acceptance_floor=None))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "acceptance-floor-invalid"
    assert result["target_launches"] == 0


def test_modified_bundle_digest_blocks_before_launch(tmp_path: Path):
    bundle = _acceptance_bundle(tmp_path / "acceptance_bundle.json")
    enrollment = _enrollment(tmp_path / "enrollment.json", bundle=bundle)
    doc = json.loads(bundle.read_text(encoding="utf-8"))
    doc["acceptance_cases"].append(copy.deepcopy(doc["acceptance_cases"][0]))
    doc["acceptance_cases"][-1]["id"] = "AC-002"
    bundle.write_text(json.dumps(doc), encoding="utf-8")
    result = run_production_round(_adapter(
        tmp_path,
        enrollment=enrollment,
        acceptance_floor={"case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}}},
    ))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "project-contract-enrollment-invalid"
    assert result["target_launches"] == 0
    assert "acceptance-contract-bundle-digest-mismatch" in result["project_contract_enrollment"]["problems"]


def test_substituted_bundle_path_in_campaign_request_is_ignored(tmp_path: Path):
    approved = _acceptance_bundle(tmp_path / "approved_bundle.json")
    substituted = _acceptance_bundle(tmp_path / "substituted_bundle.json", open_questions=True)
    enrollment = _enrollment(tmp_path / "enrollment.json", bundle=approved)
    result = run_production_round(_adapter(
        tmp_path,
        enrollment=enrollment,
        acceptance_floor={
            "bundle_path": str(substituted),
            "case_map": {"AC-001": {"case_ids": ["case-str", "case-int"], "assertion": "client floor replay passes", "evidence_extractors": ["case_results.passed"]}},
        },
    ))
    assert result["status"] == "PASS", result.get("acceptance_floor")
    assert result["acceptance_floor"]["bundle_sha256"] == _sha256(approved)
    assert result["acceptance_floor"]["bundle_sha256"] != _sha256(substituted)
    assert result["target_launches"] == 2


def test_project_explicitly_enrolled_without_contract_still_runs(tmp_path: Path):
    enrollment = _enrollment(tmp_path / "enrollment.json", bundle=None, required=False)
    result = run_production_round(_adapter(tmp_path, enrollment=enrollment, acceptance_floor=None))
    assert result["status"] == "PASS", result.get("campaign", {}).get("aggregation")
    assert result["acceptance_floor"] is None
    assert result["target_launches"] == 2
