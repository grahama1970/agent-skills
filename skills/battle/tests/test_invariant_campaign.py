"""Invariant campaign: Red generates a matrix of input versions, runs the target
on each, and an independent Judge scores every output. Proven both directions.
"""
from __future__ import annotations

from pathlib import Path

from battle_skill.invariant_campaign import run_campaign

HERE = Path(__file__).resolve().parent
GEN = str(HERE / "fixtures/mini_generator.py")
JUDGE = str(HERE.parent / "fixtures/reference-judges/no_data_leak_judge.py")


def test_campaign_fails_on_leaky_target() -> None:
    # target = plain copy (no anonymization) -> every version leaks.
    r = run_campaign(
        GEN,
        "mkdir -p {output}/corpus && cp -r {input}/corpus/. {output}/corpus/ && echo '{{}}' > {output}/report.json",
        JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert r.failures and any(f["violations"] for f in r.failures)


def test_campaign_passes_when_value_removed() -> None:
    # target = strip the value from every file -> no version leaks.
    r = run_campaign(
        GEN,
        "mkdir -p {output}/corpus && for f in {input}/corpus/*; do sed 's/5551234567/REDACTED/g' \"$f\" > {output}/corpus/$(basename \"$f\"); done && echo '{{}}' > {output}/report.json",
        JUDGE, output_subdir="corpus")
    assert r.passed is True and not r.failures
