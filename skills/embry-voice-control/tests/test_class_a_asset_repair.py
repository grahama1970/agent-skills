"""Unit tests for the Class A asset-repair mechanisms.

Covers the audio-side generation-truncation detector (used because the deployed
Orpheus server does not surface finish_reason/token counts), its wiring into the
qualification rejection reasons, and the clause-concatenation fallback helpers
(punctuation-boundary clause split + crossfade join) that recover multi-clause
sentences which keep truncating -- without changing any words.
"""

from __future__ import annotations

import io
import math
import wave

import pytest

from embry_voice_control.audio_e2e.prepare_clone_assets import (
    analyze_internal_silence,
    assemble_clause_concatenation,
    crossfade_join_pcm16,
    detect_generation_truncation,
    qualification_rejection_reasons,
    split_into_clauses,
    _utterance_boundary_policy,
)


SAMPLE_RATE = 24000
MAX_INTERNAL_SILENCE = 2.0


def _tone(seconds: float, *, amplitude: float = 0.6, freq: float = 180.0) -> list[int]:
    n = int(SAMPLE_RATE * seconds)
    return [
        int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        for i in range(n)
    ]


def _silence(seconds: float) -> list[int]:
    return [0] * int(SAMPLE_RATE * seconds)


def _write_wav(tmp_path, name: str, samples: list[int]):
    path = tmp_path / name
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(_pack(samples))
    return path


def _pack(samples: list[int]) -> bytes:
    from array import array

    return array("h", samples).tobytes()


def _wav_bytes(samples: list[int]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(_pack(samples))
    return buffer.getvalue()


def _boundary(tmp_path, name: str, samples: list[int]) -> dict:
    path = _write_wav(tmp_path, name, samples)
    return analyze_internal_silence(
        path, _utterance_boundary_policy(MAX_INTERNAL_SILENCE)
    )


# --- truncation detector (transcript-based) ---------------------------------

EXPECTED = "show the memory reasoning trace inline for the current spoken response"


def test_complete_but_mispronounced_take_is_not_truncated():
    # full-length transcript with scattered substitutions ("the"->"a",
    # "inline"->"in line"): this is the real chat_ux_sync-soak-02 candidate that
    # the old audio heuristic false-flagged. It must stay a quality sample.
    actual = "show a memory reasoning trace in line for the current spoken response"
    t = detect_generation_truncation(
        expected_text=EXPECTED, transcript=actual, wer=0.2727, max_request_wer=0.25
    )
    assert t["truncated"] is False
    assert t["detector"] == "transcript_trailing_deletion_v1"
    assert t["missing_tail_tokens"] <= 0


def test_clean_prefix_missing_tail_is_truncated():
    # a budget-cut generation: clean leading prefix, trailing words gone
    actual = "show the memory reasoning trace"
    t = detect_generation_truncation(
        expected_text=EXPECTED, transcript=actual, wer=0.4545, max_request_wer=0.25
    )
    assert t["truncated"] is True
    assert t["transcript_is_leading_prefix"] is True
    assert t["missing_tail_tokens"] >= 2


def test_short_prefix_that_passes_wer_is_not_truncated():
    # never reclassify a candidate that is within the WER ceiling
    actual = "show the memory reasoning trace"
    t = detect_generation_truncation(
        expected_text=EXPECTED, transcript=actual, wer=0.10, max_request_wer=0.25
    )
    assert t["considered"] is False
    assert t["truncated"] is False


def test_truncation_becomes_rejection_reason_first(tmp_path):
    boundary = _boundary(tmp_path, "any.wav", _tone(0.8) + _silence(0.4))
    t = detect_generation_truncation(
        expected_text=EXPECTED,
        transcript="show the memory reasoning trace",
        wer=0.4545,
        max_request_wer=0.25,
    )
    policy = {"max_request_wer": 0.25}
    reasons = qualification_rejection_reasons(
        wer=0.4545, boundary=boundary, qualification_policy=policy, truncation=t
    )
    assert reasons[0] == "tts_generation_truncated"


def test_no_truncation_reason_without_telemetry(tmp_path):
    boundary = _boundary(tmp_path, "clean2.wav", _tone(0.8) + _silence(0.5))
    policy = {"max_request_wer": 0.25}
    reasons = qualification_rejection_reasons(
        wer=0.0, boundary=boundary, qualification_policy=policy, truncation=None
    )
    assert "tts_generation_truncated" not in reasons
    assert reasons == []


# --- clause split (source text unchanged) -----------------------------------


def test_split_into_clauses_preserves_words():
    text = "Hey Embry, which source in your evidence trail supports that answer?"
    clauses = split_into_clauses(text)
    assert len(clauses) >= 2
    # every word is preserved; only split-point whitespace differs
    assert " ".join(clauses).split() == text.split()


def test_split_single_clause_returns_whole():
    assert split_into_clauses("just one clause") == ["just one clause"]


# --- crossfade join ---------------------------------------------------------


def test_crossfade_join_length_and_format():
    a = _wav_bytes(_tone(0.5))
    b = _wav_bytes(_tone(0.5))
    joined = crossfade_join_pcm16([a, b], crossfade_ms=200.0)
    with wave.open(io.BytesIO(joined), "rb") as stream:
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == SAMPLE_RATE
        frames = stream.getnframes()
    # joined length = a + b - overlap (200ms), so shorter than a naive concat
    overlap = int(SAMPLE_RATE * 0.2)
    expected = int(SAMPLE_RATE * 0.5) * 2 - overlap
    assert frames == expected


def test_crossfade_rejects_out_of_range_ms():
    a = _wav_bytes(_tone(0.3))
    with pytest.raises(ValueError, match="crossfade_out_of_range"):
        crossfade_join_pcm16([a, a], crossfade_ms=500.0)


def test_assemble_clause_concatenation_provenance():
    a = _wav_bytes(_tone(0.4))
    b = _wav_bytes(_tone(0.4))
    joined, provenance = assemble_clause_concatenation([a, b], crossfade_ms=180.0)
    assert provenance["asset_assembly"] == "clause_concatenation"
    assert provenance["source_text_unchanged"] is True
    assert provenance["clause_count"] == 2
    assert provenance["crossfade_ms"] == 180.0
    # the assembled join is itself a valid, non-truncated envelope tail
    with wave.open(io.BytesIO(joined), "rb") as stream:
        assert stream.getnframes() > 0
