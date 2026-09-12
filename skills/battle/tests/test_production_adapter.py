"""Production adapter tests: authorization-first, zero launches on failure."""
from __future__ import annotations

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


def test_invalid_authorization_means_zero_launches(tmp_path: Path):
    _profile()
    base = _request(tmp_path, _clean_target(tmp_path))
    adapter = {"schema": "battle.production_adapter_request.v1",
               "authorization_manifest": AUTH,
               "expected_target": "some-other-target-id",
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
               "expected_target": "battle-reactive-judge-fixture@sha256:reactive-judge-v1",
               "base_request": base}
    result = run_production_round(adapter)
    assert result["status"] == "PASS", result.get("campaign", {}).get("aggregation")
    assert result["target_launches"] == 2
    assert result["campaign"]["schema"] == "battle.campaign_contract_receipt.v1"
