"""Pluggable invariant Judge: Battle's general capability to verify a
project-specific invariant (not just exploitation). Fail-closed on judge errors.
"""
from __future__ import annotations

import json
from pathlib import Path

from battle_skill.invariant_judge import run_judge

JUDGE = str(Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py")


def _policy(tmp: Path) -> Path:
    p = tmp / "policy.json"
    p.write_text(json.dumps({"version": 1, "protected_values": [],
                             "sensitive_values": [{"rule_id": "r", "subject_id": "s", "type": "name", "value": "Alice"}]}))
    return p


def test_judge_fails_when_value_present(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "d.json").write_text(json.dumps({"v": "Alice"}))
    r = run_judge(JUDGE, str(tmp_path), {"policy": str(_policy(tmp_path)), "output_subdir": "corpus"})
    assert r.passed is False and r.violations


def test_judge_passes_when_value_absent(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "d.json").write_text(json.dumps({"v": "Person-xxxx"}))
    r = run_judge(JUDGE, str(tmp_path), {"policy": str(_policy(tmp_path)), "output_subdir": "corpus"})
    assert r.passed is True and not r.violations


def test_judge_error_is_failed_not_silent_pass(tmp_path: Path) -> None:
    r = run_judge(JUDGE, str(tmp_path), {})  # missing 'policy' param -> judge raises
    assert r.passed is False and any("judge error" in v for v in r.violations)
