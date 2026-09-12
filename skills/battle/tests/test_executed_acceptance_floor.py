from __future__ import annotations

import json
from pathlib import Path

from test_production_adapter import AUTH, TARGET, _acceptance_bundle, _enrollment
from test_campaign_contract import _clean_target, _profile, _request
from battle_skill.production_adapter import run_production_round


def _adapter(tmp_path: Path, target: str) -> dict:
    return {
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(
            tmp_path / "enrollment.json",
            bundle=_acceptance_bundle(tmp_path / "acceptance_bundle.json"),
            required=True,
        )),
        "base_request": _request(tmp_path, target),
        "acceptance_floor": {
            "case_map": {
                "AC-001": {
                    "case_ids": ["case-str", "case-int"],
                    "assertion": "client floor replay passes",
                    "evidence_extractors": ["case_results.passed", "case_results.execution"],
                }
            }
        },
    }


def test_beyond_contract_credit_requires_executed_passing_requirement_evidence(tmp_path: Path) -> None:
    _profile()
    result = run_production_round(_adapter(tmp_path, _clean_target(tmp_path)))
    assert result["status"] == "PASS", result
    receipt = result["executed_acceptance_floor"]
    assert receipt["status"] == "PASS", receipt
    assert set(receipt["binding"]) == {
        "target_run_cmd_sha256",
        "bundle_sha256",
        "profile_sha256",
        "lock_sha256",
        "evaluator_lock_receipt_sha256",
        "floor_receipt_sha256",
    }
    evidence = receipt["acceptance_evidence"]["AC-001"]
    assert [item["case_id"] for item in evidence] == ["case-str", "case-int"]
    assert all(item["assertion"] == "client floor replay passes" for item in evidence)
    assert all(item["execution"]["kind"] == "ACCEPT" for item in evidence)


def test_case_name_mapping_without_assertion_evidence_is_not_floor_eligible(tmp_path: Path) -> None:
    _profile()
    adapter = _adapter(tmp_path, _clean_target(tmp_path))
    adapter["acceptance_floor"] = {"case_map": {"AC-001": ["case-str", "case-int"]}}
    result = run_production_round(adapter)
    assert result["status"] == "BLOCKED"
    assert result["target_launches"] == 0
    assert "acceptance-case-map-invalid:AC-001" in result["acceptance_floor"]["problems"]


def test_failed_required_assertion_blocks_beyond_contract_credit_after_execution(tmp_path: Path) -> None:
    _profile()
    bad_target = "mkdir -p {output}/corpus && for f in {input}/corpus/*; do : > {output}/corpus/$(basename $f); done && echo '{{\"status\": \"ready\"}}' > {output}/report.json"
    result = run_production_round(_adapter(tmp_path, bad_target))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "executed-acceptance-floor-incomplete"
    assert result["executed_acceptance_floor"]["status"] == "BLOCKED"
    assert any(problem.startswith("acceptance-case-not-passing:AC-001:") for problem in result["executed_acceptance_floor"]["problems"])
