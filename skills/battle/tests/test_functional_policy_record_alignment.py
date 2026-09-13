"""Regression tests for functional judge policy-record identity alignment."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py"

_spec = importlib.util.spec_from_file_location("functional_judge_policy_alignment", JUDGE)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)


def _judge(tmp_path: Path, output_text: str):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"sensitive_values": [
        {"rule_id": "r1", "subject_id": "s1", "type": "token", "value": "A"},
        {"rule_id": "r2", "subject_id": "s1", "type": "token", "value": "BBBB"},
        {"rule_id": "r3", "subject_id": "s2", "type": "token", "value": "CC"},
    ]}), encoding="utf-8")
    inp = tmp_path / "in" / "corpus"
    out = tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "case.txt").write_text("A BBBB CC\n", encoding="utf-8")
    (out / "case.txt").write_text(output_text, encoding="utf-8")
    (tmp_path / "out" / "report.json").write_text(json.dumps({"status": "ready"}), encoding="utf-8")
    return mod.judge(str(tmp_path / "out"), {
        "policy": str(policy),
        "output_subdir": "corpus",
        "input_dir": str(tmp_path / "in"),
    })


def test_sorted_values_keep_subject_association_when_checking_collisions(tmp_path):
    result = _judge(tmp_path, "X Y Y\n")

    assert result["passed"] is False
    assert any("'BBBB' (subject 's1') and 'CC' (subject 's2')" in v for v in result["violations"])


def test_approved_aliases_still_converge_after_policy_record_sorting(tmp_path):
    result = _judge(tmp_path, "X X Z\n")

    assert result["passed"] is True, result["violations"]
    assert result["evidence"]["bindings"] == {"A": "X", "BBBB": "X", "CC": "Z"}
