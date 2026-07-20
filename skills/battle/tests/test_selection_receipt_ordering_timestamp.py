"""Proves the injectable ``created_at`` that makes lineage ordering provable.

WebGPT's feedback-bound-reproduction attestation requires provable ordering
(the selection receipt written BEFORE the G2 model call). The ``adaptive_lineage``
module is intentionally deterministic and clock-free, which is exactly why the
live receipts carried no timestamp and the ordering was unprovable. The fix
injects the clock: ``None`` keeps the run fully deterministic (``created_at`` is
``None``); an injected monotonic clock stamps the receipt so ordering is
recoverable from the artifact.
"""
from __future__ import annotations

import json
from pathlib import Path

from battle_skill import adaptive_lineage as al
from test_adaptive_lineage_reducer import BATTLE_ID, RUN_ID, _valid_specimens


def _fit(specimen_id: str, *, vuln: bool, bypass: bool, novelty: int, duration: float) -> dict:
    return {
        "specimen_id": specimen_id,
        "novelty_distance": novelty,
        "judge_outcome": {
            "vulnerable_original_confirmed": vuln,
            "patched_bypass": bypass,
            "duration_seconds": duration,
        },
    }


def _pair() -> tuple[dict, dict]:
    a = _fit("G1-A", vuln=True, bypass=True, novelty=5, duration=9.0)
    b = _fit("G1-B", vuln=True, bypass=True, novelty=2, duration=1.0)
    return a, b


def test_created_at_defaults_none_and_run_stays_deterministic() -> None:
    a, b = _pair()
    r1 = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    r2 = al.select_lineage(a, b, battle_id=BATTLE_ID, run_id=RUN_ID)
    assert "created_at" in r1
    assert r1["created_at"] is None
    assert r1 == r2  # clock-free path is byte-identical across calls


def test_created_at_injected_passes_through_without_changing_selection() -> None:
    a, b = _pair()
    r = al.select_lineage(
        a, b, battle_id=BATTLE_ID, run_id=RUN_ID, created_at="2026-07-18T17:38:29Z"
    )
    assert r["created_at"] == "2026-07-18T17:38:29Z"
    assert r["selected_id"] == "G1-A"
    assert r["deciding_criterion"] == "novelty_distance"


def test_orchestrator_clock_stamps_the_written_selection_receipt(tmp_path: Path) -> None:
    provider = al.RecordedSpecimenProvider(_valid_specimens())
    al.run_adaptive_lineage_qualification(
        provider,
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
        out_dir=tmp_path,
        clock=lambda: "2026-07-18T17:38:29Z",
    )
    written = json.loads((tmp_path / "receipts" / "lineage-selection.json").read_text())
    assert written["created_at"] == "2026-07-18T17:38:29Z"


def test_orchestrator_without_clock_leaves_created_at_none(tmp_path: Path) -> None:
    provider = al.RecordedSpecimenProvider(_valid_specimens())
    al.run_adaptive_lineage_qualification(
        provider, battle_id=BATTLE_ID, run_id=RUN_ID, out_dir=tmp_path
    )
    written = json.loads((tmp_path / "receipts" / "lineage-selection.json").read_text())
    assert written["created_at"] is None
