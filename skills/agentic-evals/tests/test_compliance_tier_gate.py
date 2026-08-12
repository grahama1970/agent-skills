"""Regression pins for the compliance-tier slop gate.

eval_tier=compliance MANDATES what practice alone does not guarantee: a strict
adversarial majority, at least one non-deterministic case, and >= 50 samples
per non-deterministic case. These pins prove each rule rejects its weakening --
the mandate cannot be quietly relaxed (operator directive 2026-08-12).
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from runner import _compliance_tier_problems, _is_non_deterministic  # noqa: E402


def _case(name: str, type_: str, cmd: str) -> dict:
    return {"name": name, "type": type_, "command": ["bash", "-c", cmd]}


def _compliant_cases() -> list[dict]:
    return [
        _case("route", "positive", "uv run python probe.py routing --samples 300"),
        _case("clarify", "adversarial", "uv run python probe.py clarify --samples 300"),
        _case("verbatim", "adversarial", "uv run python probe.py verbatim --samples 200"),
        _case("offtopic", "adversarial", "uv run python probe.py offtopic --samples 200"),
    ]


def test_non_deterministic_requires_explicit_sampling() -> None:
    assert _is_non_deterministic(_case("x", "adversarial", "probe.py mutate --samples 200"))
    assert _is_non_deterministic(_case("x", "adversarial", "probe.py mutate --seed 7"))
    assert _is_non_deterministic(_case("x", "adversarial", 'ID="CVE-$RANDOM"; run'))
    # a probe SCRIPT name with a fixed key is NOT non-deterministic
    assert not _is_non_deterministic(_case("x", "adversarial", "analyst_probe.py resolve CWE-999999"))


def test_compliant_fixture_passes() -> None:
    assert _compliance_tier_problems({"eval_tier": "compliance"}, _compliant_cases()) == []


def test_non_compliance_tier_is_unaffected() -> None:
    # ordinary skills keep the baseline gate; this stronger gate does not apply
    weak = [_case("a", "positive", "echo hi"), _case("b", "positive", "echo ho")]
    assert _compliance_tier_problems({}, weak) == []


def test_rejects_stripped_non_determinism() -> None:
    cases = _compliant_cases()
    for c in cases:
        c["command"][-1] = "analyst_probe.py resolve CWE-79"
    problems = _compliance_tier_problems({"eval_tier": "compliance"}, cases)
    assert any("non-deterministic" in p for p in problems)


def test_rejects_minority_adversarial() -> None:
    cases = _compliant_cases()
    for c in cases[:3]:
        c["type"] = "positive"  # only 1/4 adversarial
    problems = _compliance_tier_problems({"eval_tier": "compliance"}, cases)
    assert any("majority" in p.lower() for p in problems)


def test_rejects_exactly_half_adversarial() -> None:
    cases = _compliant_cases()
    cases[1]["type"] = "positive"  # 2/4 -- exactly half is not a majority
    problems = _compliance_tier_problems({"eval_tier": "compliance"}, cases)
    assert any("majority" in p.lower() for p in problems)


def test_rejects_small_sample_size() -> None:
    cases = _compliant_cases()
    cases[1]["command"][-1] = "uv run python probe.py clarify --samples 5"
    problems = _compliance_tier_problems({"eval_tier": "compliance"}, cases)
    assert any("samples only 5" in p for p in problems)
