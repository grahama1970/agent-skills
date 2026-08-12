"""#1382: LODO deck bar + the composed-gate coverage matrix.

Single channels have known blind spots (the deck gate cannot see roles, the
pixel floors cannot see space); what must hold is that the COMPOSITION catches
every seeded mutant while the honest deck passes every channel."""

import json
from pathlib import Path

import pytest

from pitchdeck.house_deck_gate import DeckGateCalibration, calibrate, score_deck
from pitchdeck.house_structure import check_structure

RECORDS = Path("/mnt/storage12tb/skills/pitchdeck/outputs/house-slides/records")
GOOD = Path("/tmp/pd-1384/deck.pptx")
DOC = Path("/tmp/pd-1384/deck.document.json")


def _need(*paths):
    for p in paths:
        if not p.exists():
            pytest.skip(f"artifact absent: {p}")


def test_lodo_bar_admits_every_held_out_real_deck():
    _need(RECORDS)
    cal = calibrate(RECORDS)
    # by construction the bar is the worst held-out real deck — assert it
    assert cal.median_bar == max(cal.fold_medians.values())
    assert all(m <= cal.median_bar for m in cal.fold_medians.values())
    assert len(cal.fold_medians) >= 4  # multiple decks actually folded


def test_committed_deck_calibration_digest_verifies():
    path = Path(__file__).parent.parent / "fixtures" / "house-gate" / "deck-calibration.v1.json"
    _need(path)
    payload = json.loads(path.read_text())
    recorded = payload.pop("content_digest")
    assert DeckGateCalibration.model_validate(payload).content_digest() == recorded


def test_honest_deck_gets_positive_structural_match():
    _need(RECORDS, GOOD)
    cal = calibrate(RECORDS)
    result = score_deck(GOOD, RECORDS)
    assert result["median"] <= cal.median_bar and result["p90"] <= cal.p90_bar


def test_composed_gate_catches_every_mutant(tmp_path):
    """Coverage matrix: every mutant fails at least one channel; the blind
    spots of single channels are allowed but must not compose into a hole."""
    _need(RECORDS, GOOD, DOC)
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_house_gate_adversaries import MUTANTS
    cal = calibrate(RECORDS)
    for name, fn in MUTANTS.items():
        mutant = tmp_path / f"{name}.pptx"
        fn(GOOD, mutant)
        structure_hits = len(check_structure(mutant, DOC))
        deck = score_deck(mutant, RECORDS)
        deck_fail = deck["median"] > cal.median_bar or deck["p90"] > cal.p90_bar
        assert structure_hits > 0 or deck_fail, f"{name} passed BOTH structural channels"
