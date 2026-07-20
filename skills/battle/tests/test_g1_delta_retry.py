"""Proves descendant-retry robustness: a delta-invalid G1 draw (the generator
over-mutated past its declared operator, or produced no real mutation) is
regenerated IN PLACE up to the budget allowance, so a single unlucky draw does
not fail the whole run — and when the allowance is exhausted the run still fails
closed on ``g1_delta_validation_failed``.

The canonical envelope is preserved: regenerations replace a slot and never add
a red-3 sibling, so ``red_specimens`` stays <= 4 and the budget does not overrun.
"""
from __future__ import annotations

from pathlib import Path

from battle_skill import adaptive_lineage as al
from test_adaptive_lineage_reducer import (
    BATTLE_ID,
    G0_SOURCE,
    RUN_ID,
    _specimen,
    _valid_specimens,
)


def _delta_invalid_g1a() -> dict:
    # source identical to the parent G0 => no real mutation => delta_status FAIL.
    return _specimen("G1-A", G0_SOURCE, "method_replace", vuln=True, duration=20.0)


def test_g1_delta_retry_regenerates_then_passes(tmp_path: Path) -> None:
    specs = _valid_specimens()
    good_g1a = specs["G1-A"]
    bad_g1a = _delta_invalid_g1a()
    calls = {"n": 0}

    def g1a_entry(*, stage: str, context: dict) -> dict:
        calls["n"] += 1
        return bad_g1a if calls["n"] == 1 else good_g1a

    provider = al.RecordedSpecimenProvider(
        {"G0": specs["G0"], "G1-A": g1a_entry, "G1-B": specs["G1-B"], "G2": specs["G2"]}
    )
    result = al.run_adaptive_lineage_qualification(
        provider, battle_id=BATTLE_ID, run_id=RUN_ID, out_dir=tmp_path
    )
    assert result["status"] == "PASS"
    assert result["stop_condition"] is None
    assert result["specimen_ids"] == ["G0", "G1-A", "G1-B", "G2"]
    assert result["budget"]["g1_regen_attempts"] == 1  # exactly one regeneration
    assert result["budget"]["red_specimens"] == 4  # no red-3 from the retry
    assert result["budget"]["overrun"] is False


def test_g1_delta_retry_exhausts_then_fails_closed(tmp_path: Path) -> None:
    specs = _valid_specimens()
    # A static delta-invalid G1-A: every regeneration returns the same failing
    # draw, so the allowance is exhausted and the run must fail closed.
    provider = al.RecordedSpecimenProvider(
        {
            "G0": specs["G0"],
            "G1-A": _delta_invalid_g1a(),
            "G1-B": specs["G1-B"],
            "G2": specs["G2"],
        }
    )
    result = al.run_adaptive_lineage_qualification(
        provider, battle_id=BATTLE_ID, run_id=RUN_ID, out_dir=tmp_path
    )
    assert result["status"] == "FAIL"
    assert result["stop_condition"] == "g1_delta_validation_failed"
    assert result["budget"]["g1_regen_attempts"] == 2  # full allowance consumed
    assert result["budget"]["red_specimens"] <= 4  # regenerations are not red-3
    assert result["budget"]["overrun"] is False  # regenerations stay within cap
    assert "G2" not in provider.requested_stages  # fail-closed before G2


def test_g1_regen_budget_accounting() -> None:
    b = al.AdaptiveLineageBudget()
    assert b.g1_regen_budget_remaining() == 2
    b.record_g1_regen()
    assert b.g1_regen_budget_remaining() == 1
    b.record_g1_regen()
    assert b.g1_regen_budget_remaining() == 0
    assert b.overrun()[0] is False
    b.record_g1_regen()  # over the cap
    over, reasons = b.overrun()
    assert over is True
    assert any("regeneration" in r for r in reasons)
