from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from lib.orpheus_audio_classifier import (
    classify_audio_file,
    classify_manifest,
    context_waveform_gate,
    label_score,
    waveform_gate,
    waveform_features,
)


def write_tone_bursts(path, *, bursts: int, duration: float = 1.4, sr: int = 16_000) -> None:
    y = np.zeros(int(duration * sr), dtype=np.float32)
    starts = np.linspace(0.12, duration - 0.18, bursts)
    for start in starts:
        start_i = int(start * sr)
        end_i = min(y.size, start_i + int(0.08 * sr))
        t = np.arange(end_i - start_i, dtype=np.float32) / sr
        y[start_i:end_i] += 0.35 * np.sin(2 * np.pi * 180 * t)
    sf.write(path, y, sr)


def write_smooth_sigh(path, *, duration: float = 2.2, sr: int = 16_000) -> None:
    t = np.arange(int(duration * sr), dtype=np.float32) / sr
    y = 0.18 * np.sin(2 * np.pi * 130 * t)
    fade = np.sin(np.linspace(0, np.pi, y.size, dtype=np.float32))
    sf.write(path, (y * fade).astype(np.float32), sr)


def test_label_score_matches_audioset_neighbor_labels() -> None:
    predictions = [
        {"label": "Chuckle, chortle", "score": 0.63},
        {"label": "Belly laugh", "score": 0.21},
    ]

    score, matches = label_score(predictions, ["chuckle", "chortle"])

    assert score == 0.63
    assert matches == [predictions[0]]


def test_waveform_gate_rejects_short_single_burst_laugh(tmp_path) -> None:
    path = tmp_path / "chuckle_like.wav"
    write_tone_bursts(path, bursts=1, duration=0.5)

    features = waveform_features(path)
    decision, reasons = waveform_gate("laugh", features)

    assert decision == "reject"
    assert "laugh_too_short" in reasons
    assert "laugh_needs_multiple_sustained_pulses" in reasons


def test_waveform_gate_reviews_low_amplitude_short_laugh_as_chuckle_like(tmp_path) -> None:
    path = tmp_path / "quiet_chuckle_like_laugh.wav"
    write_tone_bursts(path, bursts=3, duration=1.25)

    features = waveform_features(path)
    decision, reasons = waveform_gate("laugh", features)

    assert decision == "review"
    assert "laugh_duration_chuckle_like" in reasons
    assert "laugh_needs_repeated_transient_spikes" in reasons


def test_waveform_gate_accepts_sustained_multi_pulse_laugh(tmp_path) -> None:
    path = tmp_path / "laugh_like.wav"
    write_tone_bursts(path, bursts=6, duration=2.4)

    features = waveform_features(path)
    decision, reasons = waveform_gate("laugh", features)

    assert decision == "pass"
    assert reasons == []


def test_waveform_gate_reviews_sustained_high_energy_chuckle_as_laugh_like(tmp_path) -> None:
    path = tmp_path / "laugh_like_chuckle.wav"
    write_tone_bursts(path, bursts=6, duration=2.4)

    features = waveform_features(path)
    decision, reasons = waveform_gate("chuckle", features)

    assert decision == "review"
    assert "chuckle_looks_like_sustained_laugh" in reasons


def test_waveform_gate_accepts_smooth_single_envelope_sigh(tmp_path) -> None:
    path = tmp_path / "smooth_sigh.wav"
    write_smooth_sigh(path, duration=2.2)

    features = waveform_features(path)
    decision, reasons = waveform_gate("sigh", features)

    assert decision == "pass"
    assert reasons == []
    assert features.transient_peak_count <= 2


def test_waveform_gate_reviews_pulsed_sigh_as_not_smooth(tmp_path) -> None:
    path = tmp_path / "pulsed_sigh.wav"
    write_tone_bursts(path, bursts=5, duration=2.2)

    features = waveform_features(path)
    decision, reasons = waveform_gate("sigh", features)

    assert decision == "review"
    assert "sigh_has_transient_pulses" in reasons


def test_waveform_gate_reviews_long_gasp_instead_of_hard_reject(tmp_path) -> None:
    path = tmp_path / "long_gasp.wav"
    write_tone_bursts(path, bursts=1, duration=1.4)

    features = waveform_features(path)
    decision, reasons = waveform_gate("gasp", features)

    assert decision == "review"
    assert "gasp_duration_above_expected" in reasons


def test_waveform_gate_reviews_short_sigh_instead_of_hard_reject(tmp_path) -> None:
    path = tmp_path / "short_sigh.wav"
    write_smooth_sigh(path, duration=0.4)

    features = waveform_features(path)
    decision, reasons = waveform_gate("sigh", features)

    assert decision == "review"
    assert "sigh_duration_below_expected" in reasons


def test_context_waveform_gate_accepts_short_event_inside_long_gasp_context(tmp_path) -> None:
    path = tmp_path / "context_gasp.wav"
    write_tone_bursts(path, bursts=1, duration=1.6)

    features = waveform_features(path)
    decision, reasons = context_waveform_gate("gasp", features)

    assert decision == "pass"
    assert reasons == []


def test_context_waveform_gate_accepts_breathy_sigh_context(tmp_path) -> None:
    path = tmp_path / "context_sigh.wav"
    write_smooth_sigh(path, duration=2.2)

    features = waveform_features(path)
    decision, reasons = context_waveform_gate("sigh", features)

    assert decision == "pass"
    assert reasons == []


def test_classify_manifest_writes_classifier_result_without_ast(tmp_path) -> None:
    wav = tmp_path / "horus_laugh_0001.wav"
    write_tone_bursts(wav, bursts=6, duration=2.4)
    manifest = {
        "records": [
            {
                "id": "horus_laugh_0001",
                "orpheus_tag": "<laugh>",
                "prompt": "[1.4 second sustained laugh]",
                "tts_text": "<laugh>",
                "source_type": "elevenlabs_voice_context",
                "wav_path": str(wav),
            }
        ]
    }
    manifest_path = tmp_path / "elevenlabs_orpheus_sfx_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = classify_manifest(manifest_path=manifest_path, use_ast=False)

    assert result["record_count"] == 1
    assert result["decision_counts"] == {"manual_review": 1}
    assert (tmp_path / "classifier-result.json").exists()
    row = result["records"][0]["classification"]
    assert row["waveform"]["decision"] == "pass"
    assert row["reasons"] == ["waveform_prefilter_pass_classifier_unavailable"]


class StubPredictor:
    def __init__(self, predictions):
        self.predictions = predictions

    def predict(self, audio_path, *, top_k):  # noqa: ANN001
        return self.predictions, None


def test_context_gasp_can_accept_when_ast_strong_even_if_whole_clip_is_long(tmp_path) -> None:
    wav = tmp_path / "context_gasp.wav"
    write_tone_bursts(wav, bursts=1, duration=1.6)

    result = classify_audio_file(
        wav,
        expected_tag="<gasp>",
        source_type="elevenlabs_voice_context",
        predictor=StubPredictor([{"label": "Gasp", "score": 0.91}, {"label": "Sigh", "score": 0.03}]),
    )

    assert result["decision"] == "accept"
    assert "classifier_expected_tag_overrides_context_clip_waveform_review" in result["reasons"]
    assert result["waveform"]["decision"] == "review"


def test_context_gasp_override_does_not_apply_to_movie_clip(tmp_path) -> None:
    wav = tmp_path / "movie_gasp.wav"
    write_tone_bursts(wav, bursts=1, duration=1.6)

    result = classify_audio_file(
        wav,
        expected_tag="<gasp>",
        source_type="movie_or_aligned",
        predictor=StubPredictor([{"label": "Gasp", "score": 0.91}, {"label": "Sigh", "score": 0.03}]),
    )

    assert result["decision"] == "manual_review"
    assert "waveform_review:gasp_duration_above_expected" in result["reasons"]


def test_context_sigh_can_accept_when_ast_is_confident(tmp_path) -> None:
    wav = tmp_path / "context_sigh.wav"
    write_tone_bursts(wav, bursts=4, duration=2.4)

    result = classify_audio_file(
        wav,
        expected_tag="<sigh>",
        source_type="elevenlabs_voice_context",
        predictor=StubPredictor([{"label": "Sigh", "score": 0.32}, {"label": "Gasp", "score": 0.02}]),
    )

    assert result["decision"] == "accept"
    assert "classifier_expected_tag_overrides_context_clip_waveform_review" in result["reasons"]


def test_context_gasp_can_accept_on_event_waveform_when_classifier_is_uncertain(tmp_path) -> None:
    wav = tmp_path / "context_gasp_uncertain.wav"
    write_tone_bursts(wav, bursts=1, duration=1.6)

    result = classify_audio_file(
        wav,
        expected_tag="<gasp>",
        source_type="elevenlabs_voice_context",
        predictor=StubPredictor([{"label": "Speech", "score": 0.04}, {"label": "Sigh", "score": 0.02}]),
    )

    assert result["decision"] == "accept"
    assert "context_event_waveform_accept" in result["reasons"]
    assert result["waveform"]["decision"] == "review"
    assert result["waveform"]["context_decision"] == "pass"


def test_context_event_waveform_accept_does_not_apply_to_movie_clip(tmp_path) -> None:
    wav = tmp_path / "movie_context_gasp.wav"
    write_tone_bursts(wav, bursts=1, duration=1.6)

    result = classify_audio_file(
        wav,
        expected_tag="<gasp>",
        source_type="movie_or_aligned",
        predictor=StubPredictor([{"label": "Speech", "score": 0.04}, {"label": "Sigh", "score": 0.02}]),
    )

    assert result["decision"] == "manual_review"
    assert "context_event_waveform_accept" not in result["reasons"]
    assert result["waveform"]["context_decision"] is None
