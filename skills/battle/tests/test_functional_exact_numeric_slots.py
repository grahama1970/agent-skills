"""Regression tests for exact numeric slot matching in the functional judge."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py"

_spec = importlib.util.spec_from_file_location("functional_judge_exact_numeric_slots", JUDGE)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)


def _judge_json(tmp_path: Path, *, policy_value: str, input_value, output_value):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"sensitive_values": [
        {"rule_id": "r", "subject_id": "s", "type": "number", "value": policy_value},
    ]}), encoding="utf-8")
    inp = tmp_path / "in" / "corpus"
    out = tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "case.json").write_text(json.dumps({"value": input_value}), encoding="utf-8")
    (out / "case.json").write_text(json.dumps({"value": output_value}), encoding="utf-8")
    (tmp_path / "out" / "report.json").write_text(json.dumps({"status": "ready"}), encoding="utf-8")
    return mod.judge(str(tmp_path / "out"), {
        "policy": str(policy),
        "output_subdir": "corpus",
        "input_dir": str(tmp_path / "in"),
    })


def test_large_neighbor_integer_is_not_float_alias_slot(tmp_path):
    result = _judge_json(
        tmp_path,
        policy_value="9007199254740993",
        input_value=9007199254740992,
        output_value="Person-A",
    )

    assert result["passed"] is False
    assert any("scalar changed" in violation for violation in result["violations"])
    assert result["evidence"]["bindings"] == {}


def test_exact_large_integer_slot_still_binds(tmp_path):
    result = _judge_json(
        tmp_path,
        policy_value="9007199254740993",
        input_value=9007199254740993,
        output_value="Person-A",
    )

    assert result["passed"] is True, result["violations"]
    assert result["evidence"]["bindings"] == {"9007199254740993": "Person-A"}


def test_equivalent_exponent_numeric_form_binds(tmp_path):
    result = _judge_json(
        tmp_path,
        policy_value="1e3",
        input_value=1000,
        output_value="Person-A",
    )

    assert result["passed"] is True, result["violations"]
    assert result["evidence"]["bindings"] == {"1e3": "Person-A"}


def test_bool_is_not_numeric_slot(tmp_path):
    result = _judge_json(
        tmp_path,
        policy_value="1",
        input_value=True,
        output_value="Person-A",
    )

    assert result["passed"] is False
    assert any("scalar changed" in violation for violation in result["violations"])
    assert result["evidence"]["bindings"] == {}
