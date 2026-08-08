"""The tone she picks must be the tone Chatterbox is asked for.

A reply gets two tones near it and they are not the same thing. The dream has a
dominant tension axis, which is what the journal was arguing about. The reply
has whatever she just said, which may be nothing like it -- she can answer a
question about a competence dream by admitting she does not know.

`map_mood(mood_label, contradictions)` takes the label as PROVENANCE only. It
returns it as persona_mood_label and never lets it pick a tone; the tone comes
from the axis. Passing her choice as that first argument therefore sent the axis
tone while recording hers, so the request and the record disagreed by
construction, every time, and the mismatch surfaced as a `tone_did_not_survive`
gate that read like a renderer fault. It was not: Chatterbox rendered exactly
what it was handed.

These tests pin the invariant that failure violated -- what we send equals what
we record -- rather than the specific pair that exposed it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import speak_reply  # noqa: E402


@pytest.fixture()
def competence_dream(tmp_path: Path) -> Path:
    """A dream whose axis maps to memory_confident, so a mismatch is visible."""
    import json

    (tmp_path / "contradiction_report.json").write_text(
        json.dumps({"contradictions": [
            {"bridge_a": "Competence", "bridge_b": "Inadequacy"},
            {"bridge_a": "Competence", "bridge_b": "Inadequacy"},
        ]}),
        encoding="utf-8",
    )
    return tmp_path


def test_her_choice_is_what_gets_sent_not_just_what_gets_recorded(competence_dream):
    """The whole defect in one assertion."""
    tone, delivery = speak_reply.choose_tone(competence_dream, "curious_searching")
    assert tone == "curious_searching"
    assert delivery["tone"] == "curious_searching", (
        "the envelope carried the dream's axis tone while the record claimed hers"
    )


@pytest.mark.parametrize("chosen", sorted(speak_reply._load("map_delivery_tone").ALLOWED_TONES))
def test_every_tone_in_the_vocabulary_survives_the_round_trip(competence_dream, chosen):
    """One pair happened to expose this; the invariant is not about that pair."""
    tone, delivery = speak_reply.choose_tone(competence_dream, chosen)
    assert tone == chosen == delivery["tone"]


def test_pace_still_comes_from_the_dream(competence_dream):
    """Tone is about the reply; pace is not calibrated per-tone, so it stays."""
    _, delivery = speak_reply.choose_tone(competence_dream, "curious_searching")
    assert delivery["pace"] == "brisk", "Competence maps to brisk; that mapping is not hers to override"
    assert delivery["emotion_realization"] == "audible"


def test_a_tone_outside_the_vocabulary_falls_back_to_the_dream(competence_dream):
    """She may return junk. The dream's own axis is the honest default."""
    tone, delivery = speak_reply.choose_tone(competence_dream, "exposed, honest")
    assert tone == "memory_confident"
    assert delivery["tone"] == tone
