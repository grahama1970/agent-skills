"""Strict campaign and acceptance envelope validation tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.acceptance_floor import validate_acceptance_floor, validate_project_contract_enrollment  # noqa: E402
from battle_skill.campaign_contract import validate_request  # noqa: E402
from battle_skill.invariant_campaign import load_profile  # noqa: E402
from battle_skill.strict_json import load_path  # noqa: E402
from test_campaign_contract import _profile, _request  # noqa: E402
from test_production_adapter import TARGET, _acceptance_bundle  # noqa: E402


def test_duplicate_json_keys_are_rejected_before_decode_loses_them(tmp_path: Path) -> None:
    path = tmp_path / "dup.json"
    path.write_text('{"schema":"x", "schema":"y"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key: schema"):
        load_path(path)


def test_campaign_request_rejects_extra_fields_non_finite_and_bad_shapes(tmp_path: Path) -> None:
    _profile()
    request = _request(tmp_path, "python3 target.py")
    request["unexpected"] = True
    with pytest.raises(ValueError, match="request contains unknown fields"):
        validate_request(request)

    request = _request(tmp_path, "python3 target.py")
    request["gen_params"] = ["not", "object"]
    with pytest.raises(ValueError, match="gen_params must be an object"):
        validate_request(request)

    request = _request(tmp_path, "python3 target.py")
    request["judge_params"] = {"threshold": float("nan")}
    with pytest.raises(ValueError, match="request contains non-finite numeric value"):
        validate_request(request)


def test_profile_rejects_duplicate_empty_and_unknown_envelope_fields(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "demo",
        "required_judges": ["security"],
        "required_case_ids": ["case-a", "case-a"],
        "expectation_overrides": {},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="required_case_ids must be a duplicate-free list"):
        load_profile(str(profile))

    profile.write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "demo",
        "required_case_ids": ["case-a"],
        "expectation_overrides": {"": "MUST_ACCEPT"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="expectation override IDs must be non-empty strings"):
        load_profile(str(profile))

    profile.write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "demo",
        "required_case_ids": ["case-a"],
        "expectation_overrides": {},
        "extra": True,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="profile contains unknown fields"):
        load_profile(str(profile))


def test_acceptance_floor_returns_blocking_receipts_for_invalid_envelopes(tmp_path: Path) -> None:
    bundle = _acceptance_bundle(tmp_path / "bundle.json")
    profile = {"schema": "battle.campaign_profile.v1", "profile_id": "demo", "required_case_ids": ["case-str"]}

    result = validate_acceptance_floor(
        bundle_path=bundle,
        campaign_profile=profile,
        case_map={"AC-001": {"case_ids": ["case-str", "case-str"], "assertion": "a", "evidence_extractors": ["e"]}},
    )
    assert result["status"] == "BLOCKED"
    assert "acceptance-case-map-invalid:AC-001" in result["problems"]

    doc = json.loads(bundle.read_text())
    doc["acceptance_cases"].append(dict(doc["acceptance_cases"][0]))
    bundle.write_text(json.dumps(doc), encoding="utf-8")
    result = validate_acceptance_floor(
        bundle_path=bundle,
        campaign_profile=profile,
        case_map={"AC-001": {"case_ids": ["case-str"], "assertion": "a", "evidence_extractors": ["e"]}},
    )
    assert result["status"] == "BLOCKED"
    assert "acceptance-case-duplicate:AC-001" in result["problems"]


def test_project_enrollment_rejects_extra_fields_before_execution(tmp_path: Path) -> None:
    enrollment = tmp_path / "enrollment.json"
    enrollment.write_text(json.dumps({
        "schema": "battle.project_contract_enrollment.v1",
        "target_identity": TARGET,
        "acceptance_contract": {"required": False, "extra": True},
    }), encoding="utf-8")
    result = validate_project_contract_enrollment(enrollment, expected_target=TARGET)
    assert result["status"] == "BLOCKED"
    assert "acceptance-contract-enrollment-extra-fields:extra" in result["problems"]
