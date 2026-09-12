"""Fixture witness contract tests for Battle campaign prechecks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.invariant_campaign import _fixture_precheck, run_campaign  # noqa: E402

JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py")


def _case(root: Path, value: str = "5551234567") -> Path:
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text(json.dumps({
        "version": 1,
        "protected_values": [],
        "sensitive_values": [{"rule_id": "REQ-PII", "subject_id": "customer", "type": "phone", "value": value}],
    }), encoding="utf-8")
    (root / "corpus" / "record.txt").write_text(value, encoding="utf-8")
    return root


def test_positive_fixture_witness_names_rule_interpretation_and_input_digest(tmp_path: Path) -> None:
    root = _case(tmp_path / "case")

    receipt = _fixture_precheck(root, JUDGE, {"interpretation_profile": {"decoders": ["base64"]}}, "MUST_ACCEPT")

    match = receipt["witness"]["matches"][0]
    assert receipt["status"] == "PASS"
    assert receipt["witness"]["kind"] == "POLICY_VALUE_WITNESS"
    assert match["requirement"] == "policy-value-present-in-fixture"
    assert match["rule_id"] == "REQ-PII"
    assert match["subject_id"] == "customer"
    assert match["type"] == "phone"
    assert match["interpretation"] == {"decoders": ["base64"]}
    assert match["input_manifest_sha256"] == receipt["evidence_sha256"]
    assert match["value_sha256"].startswith("sha256:")


def test_unrelated_judge_failure_is_invalid_case_not_positive_witness(tmp_path: Path) -> None:
    root = _case(tmp_path / "case")
    judge = tmp_path / "bad_judge.py"
    judge.write_text("def judge(target_dir, params):\n    return {'passed': False, 'violations': ['parser failure'], 'evidence': {}}\n", encoding="utf-8")

    receipt = _fixture_precheck(root, str(judge), {}, "MUST_ACCEPT")

    assert receipt["status"] == "INVALID_CASE"
    assert receipt["violations"] == ["fixture_precheck:no_typed_policy_value_witness"]
    assert "witness" not in receipt


def test_must_reject_uses_approved_invalid_input_predicate(tmp_path: Path) -> None:
    root = _case(tmp_path / "case")
    (root / "invalid_input.json").write_text(json.dumps({
        "schema": "battle.invalid_input_predicate.v1",
        "approved": True,
        "predicate": "malformed input is outside the accepted contract",
    }), encoding="utf-8")

    receipt = _fixture_precheck(root, JUDGE, {}, "MUST_REJECT")

    assert receipt["status"] == "PASS"
    assert receipt["witness"] == {
        "schema": "battle.fixture_witness.v1",
        "kind": "INVALID_INPUT_PREDICATE",
        "predicate": "malformed input is outside the accepted contract",
        "input_manifest_sha256": receipt["evidence_sha256"],
    }


def test_invalid_fixture_gets_invalid_case_and_no_target_launch(tmp_path: Path) -> None:
    sentinel = tmp_path / "target-ran"
    generator = tmp_path / "gen.py"
    generator.write_text('''
from pathlib import Path

def generate(work_dir, params):
    root = Path(work_dir) / "case"
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text('{"version":1,"protected_values":[],"sensitive_values":[{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}]}')
    (root / "corpus" / "record.txt").write_text("5551234567")
    yield "case", root, "MUST_REJECT"
''', encoding="utf-8")

    result = run_campaign(str(generator), f"touch {sentinel}", JUDGE, output_subdir="corpus")

    receipt = result.case_receipts[0]
    assert result.passed is False
    assert receipt["fixture_precheck"]["status"] == "INVALID_CASE"
    assert receipt["execution"]["kind"] == "INVALID_CASE"
    assert result.aggregation["invalid_case_count"] == 1
    assert result.aggregation["observed_target_launch_count"] == 0
    assert not sentinel.exists()
