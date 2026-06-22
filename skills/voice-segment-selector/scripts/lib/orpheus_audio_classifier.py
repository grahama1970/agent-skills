#!/usr/bin/env python3
"""Audio classifier gate for synthetic Orpheus emotion-tag candidates.

Purpose
-------
This module is a fail-closed prefilter for persona emotion-tag audio candidates
before they are allowed into an Orpheus-TTS training dataset. It is meant to
catch obvious wrong-tag samples such as:

- a `<laugh>` candidate that is actually a short low-amplitude chuckle
- a `<chuckle>` candidate that looks like a sustained laugh
- a `<sigh>` candidate with repeated transient laugh/cough-like pulses
- a `<gasp>` candidate that is too long or has too many pulses
- a classifier match for a neighboring reject label such as laugh vs chuckle

It combines two evidence sources:

1. deterministic waveform features: duration, RMS/peak amplitude, active burst
   count, transient peak count, peak spacing, and envelope smoothness
2. optional AudioSet AST predictions from
   ``MIT/ast-finetuned-audioset-16-16-0.442``

Important boundary
------------------
Waveform checks alone are not semantic proof that a clip is the intended
emotion. If AST predictions are unavailable, a waveform pass is only a
``manual_review`` prefilter, not an acceptance. Final training eligibility still
requires reviewed candidates plus export/inference receipts from the surrounding
``voice-segment-selector`` / ``orpheus-tts-voice-trainer`` pipeline.

This module does not generate ElevenLabs prompts, mutate prompt candidates, run
ASR literal-tag checks, or decide whether a clip sounds like Horus or Embry.
Those are separate pipeline stages.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Protocol

import librosa
import numpy as np
from scipy.signal import find_peaks, peak_prominences, peak_widths

ORPHEUS_AUDIO_CLASSIFIER_SCHEMA = "voice_segment_selector.orpheus_audio_classifier_result.v1"
DEFAULT_AST_MODEL = "MIT/ast-finetuned-audioset-16-16-0.442"

TAG_LABELS: dict[str, tuple[str, ...]] = {
    "laugh": ("belly laugh", "laughter", "laugh"),
    "chuckle": ("chuckle", "chortle"),
    "sigh": ("sigh",),
    "cough": ("cough",),
    "sniffle": ("sniff", "sniffle"),
    "groan": ("groan", "grunt"),
    "yawn": ("yawn",),
    "gasp": ("gasp",),
}

NEIGHBOR_REJECTS: dict[str, tuple[str, ...]] = {
    "laugh": ("chuckle", "chortle", "giggle"),
    "chuckle": ("belly laugh", "laughter"),
    "sigh": ("gasp", "yawn"),
    "gasp": ("sigh", "yawn"),
    "yawn": ("sigh", "gasp"),
    "cough": ("sniff", "sigh"),
    "sniffle": ("cough", "gasp"),
    "groan": ("sigh", "yawn", "laugh"),
}

WAVEFORM_PREFILTER_ONLY_REASON = "waveform_prefilter_pass_classifier_unavailable"


@dataclass(frozen=True)
class WaveformFeatures:
    duration_seconds: float
    rms: float
    peak: float
    active_ratio: float
    burst_count: int
    longest_burst_seconds: float
    transient_peak_count: int
    transient_peak_density: float
    peak_prominence_mean: float
    peak_width_mean_seconds: float
    inter_peak_interval_mean_seconds: float
    inter_peak_interval_std_seconds: float
    envelope_cv: float


def normalize_tag(tag: str) -> str:
    return tag.strip().lower().removeprefix("<").removesuffix(">")


def waveform_features(audio_path: Path, *, sample_rate: int = 16_000) -> WaveformFeatures:
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    if y.size == 0:
        return WaveformFeatures(0.0, 0.0, 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    duration = float(y.size / sr)
    rms = float(np.sqrt(np.mean(np.square(y), dtype=np.float64)))
    peak = float(np.max(np.abs(y)))
    frame = max(128, int(sr * 0.025))
    hop = max(64, int(sr * 0.010))
    envelope = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop, center=True)[0]
    if envelope.size == 0:
        return WaveformFeatures(duration, rms, peak, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    threshold = max(float(np.percentile(envelope, 65)) * 1.25, float(envelope.max()) * 0.18, 1e-5)
    active = envelope >= threshold
    active_ratio = float(active.mean())
    bursts: list[int] = []
    run = 0
    for value in active:
        if bool(value):
            run += 1
        elif run:
            bursts.append(run)
            run = 0
    if run:
        bursts.append(run)
    # Suppress tiny clicks that are unlikely to be intentional vocal pulses.
    min_frames = max(1, int(0.045 / (hop / sr)))
    bursts = [count for count in bursts if count >= min_frames]
    longest = max(bursts, default=0) * hop / sr
    active_envelope = envelope[active]
    if active_envelope.size:
        active_mean = float(np.mean(active_envelope))
        envelope_cv = float(np.std(active_envelope) / max(active_mean, 1e-8))
    else:
        envelope_cv = 0.0

    transient_peak_count = 0
    peak_prominence_mean = 0.0
    peak_width_mean_seconds = 0.0
    inter_peak_interval_mean_seconds = 0.0
    inter_peak_interval_std_seconds = 0.0
    if envelope.size >= 3:
        peak_floor = max(threshold, float(envelope.max()) * 0.30)
        min_peak_gap = max(1, int(0.055 / (hop / sr)))
        peak_indexes, _ = find_peaks(envelope, height=peak_floor, distance=min_peak_gap)
        transient_peak_count = int(peak_indexes.size)
        if peak_indexes.size:
            prominences = peak_prominences(envelope, peak_indexes)[0]
            widths = peak_widths(envelope, peak_indexes, rel_height=0.5)[0]
            peak_prominence_mean = float(np.mean(prominences))
            peak_width_mean_seconds = float(np.mean(widths) * hop / sr)
        if peak_indexes.size >= 2:
            intervals = np.diff(peak_indexes) * hop / sr
            inter_peak_interval_mean_seconds = float(np.mean(intervals))
            inter_peak_interval_std_seconds = float(np.std(intervals))
    transient_peak_density = float(transient_peak_count / max(duration, 1e-8))
    return WaveformFeatures(
        duration,
        rms,
        peak,
        active_ratio,
        len(bursts),
        float(longest),
        transient_peak_count,
        transient_peak_density,
        peak_prominence_mean,
        peak_width_mean_seconds,
        inter_peak_interval_mean_seconds,
        inter_peak_interval_std_seconds,
        envelope_cv,
    )


class AudioPredictor(Protocol):
    def predict(self, audio_path: Path, *, top_k: int = 12) -> tuple[list[dict], str | None]:
        ...


class AstAudioSetPredictor:
    def __init__(self, *, model_name: str = DEFAULT_AST_MODEL) -> None:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self.torch = torch
        self.model_name = model_name
        self.extractor = AutoFeatureExtractor.from_pretrained(model_name)
        self.model = AutoModelForAudioClassification.from_pretrained(model_name)
        self.model.eval()

    def predict(self, audio_path: Path, *, top_k: int = 12) -> tuple[list[dict], str | None]:
        try:
            y, sr = librosa.load(audio_path, sr=16_000, mono=True)
            inputs = self.extractor(y, sampling_rate=sr, return_tensors="pt")
            with self.torch.no_grad():
                logits = self.model(**inputs).logits[0]
                probs = self.torch.softmax(logits, dim=-1)
                values, indices = self.torch.topk(probs, k=min(top_k, probs.numel()))
            id2label = self.model.config.id2label
            predictions = []
            for score, index in zip(values.tolist(), indices.tolist(), strict=False):
                predictions.append(
                    {
                        "label": str(id2label.get(index, index)),
                        "score": float(score),
                    }
                )
            return predictions, None
        except Exception as exc:  # pragma: no cover - depends on HF/cache/runtime state
            return [], f"classifier_runtime_error:{type(exc).__name__}:{exc}"


def build_ast_predictor(*, model_name: str = DEFAULT_AST_MODEL) -> tuple[AudioPredictor | None, str | None]:
    try:
        return AstAudioSetPredictor(model_name=model_name), None
    except Exception as exc:  # pragma: no cover - exercised in environments without optional deps
        return None, f"classifier_dependency_unavailable:{type(exc).__name__}:{exc}"


def load_ast_predictions(audio_path: Path, *, model_name: str = DEFAULT_AST_MODEL, top_k: int = 12) -> tuple[list[dict], str | None]:
    predictor, error = build_ast_predictor(model_name=model_name)
    if predictor is None:
        return [], error
    return predictor.predict(audio_path, top_k=top_k)


def label_score(predictions: Iterable[dict], needles: Iterable[str]) -> tuple[float, list[dict]]:
    lowered = tuple(needle.lower() for needle in needles)
    matches: list[dict] = []
    score = 0.0
    for prediction in predictions:
        label = str(prediction.get("label", "")).lower()
        if any(needle in label for needle in lowered):
            matches.append(prediction)
            score = max(score, float(prediction.get("score", 0.0)))
    return score, matches


def waveform_gate(tag: str, features: WaveformFeatures) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if features.duration_seconds <= 0.05 or not math.isfinite(features.duration_seconds):
        return "reject", ["audio_unreadable_or_empty"]
    if tag == "laugh":
        if features.duration_seconds < 0.9:
            reasons.append("laugh_too_short")
        if features.burst_count < 2:
            reasons.append("laugh_needs_multiple_sustained_pulses")
        if reasons:
            return "reject", reasons
        review_reasons: list[str] = []
        if features.duration_seconds < 1.8:
            review_reasons.append("laugh_duration_chuckle_like")
        if features.burst_count < 4 or features.transient_peak_count < 4:
            review_reasons.append("laugh_needs_repeated_transient_spikes")
        if features.inter_peak_interval_mean_seconds > 0.75 and features.transient_peak_count < 5:
            review_reasons.append("laugh_transients_too_sparse")
        if features.rms < 0.030 or features.peak < 0.20:
            review_reasons.append("laugh_amplitude_chuckle_like")
        return ("review" if review_reasons else "pass", review_reasons)
    if tag == "chuckle":
        if (
            features.duration_seconds >= 2.0
            and (features.burst_count >= 4 or features.transient_peak_count >= 4)
            and features.rms >= 0.030
            and features.inter_peak_interval_mean_seconds <= 0.75
        ):
            reasons.append("chuckle_looks_like_sustained_laugh")
        if features.peak >= 0.45 and features.duration_seconds >= 1.6:
            reasons.append("chuckle_amplitude_laugh_like")
        return ("review" if reasons else "pass", reasons)
    if tag == "gasp":
        if features.duration_seconds > 0.9:
            reasons.append("gasp_duration_above_expected")
        if features.burst_count > 2:
            reasons.append("gasp_has_too_many_pulses")
        return ("review" if reasons else "pass", reasons)
    if tag == "sigh":
        if features.duration_seconds < 0.55:
            reasons.append("sigh_duration_below_expected")
        if features.burst_count > 2 or features.transient_peak_count > 2:
            reasons.append("sigh_has_transient_pulses")
        if features.envelope_cv > 1.0 and features.transient_peak_count > 1:
            reasons.append("sigh_envelope_not_smooth")
        if features.peak_prominence_mean > 0.025 and features.transient_peak_count > 1:
            reasons.append("sigh_has_prominent_peaks")
        return ("review" if reasons else "pass", reasons)
    if tag == "cough":
        if features.duration_seconds > 1.25:
            reasons.append("cough_duration_above_expected")
        if features.transient_peak_count == 0:
            reasons.append("cough_missing_sharp_transient")
        if features.burst_count > 3:
            reasons.append("cough_has_too_many_bursts")
        return ("review" if reasons else "pass", reasons)
    if tag == "yawn":
        if features.duration_seconds < 0.9:
            reasons.append("yawn_duration_below_expected")
        if features.transient_peak_count > 5 and features.burst_count > 3:
            reasons.append("yawn_too_pulsed_laugh_like")
        return ("review" if reasons else "pass", reasons)
    return "pass", reasons


def context_waveform_gate(tag: str, features: WaveformFeatures) -> tuple[str, list[str]]:
    """Gate only the nonverbal event shape inside short ElevenLabs context lines.

    Eleven v3 often needs a short carrier phrase to perform a tag naturally.
    The full clip duration then includes speech/silence, so the regular
    isolated-SFX gate can incorrectly mark a good gasp/sigh as too long.
    """
    status, reasons = waveform_gate(tag, features)
    if tag == "gasp" and "gasp_duration_above_expected" in reasons:
        event_reasons: list[str] = []
        if features.burst_count > 2:
            event_reasons.append("context_gasp_has_too_many_active_bursts")
        if features.longest_burst_seconds > 0.45:
            event_reasons.append("context_gasp_active_burst_too_long")
        if features.transient_peak_count > 3:
            event_reasons.append("context_gasp_has_too_many_transients")
        return ("pass" if not event_reasons else "review", event_reasons)
    if tag == "sigh" and (
        "sigh_has_transient_pulses" in reasons
        or "sigh_envelope_not_smooth" in reasons
        or "sigh_has_prominent_peaks" in reasons
    ):
        event_reasons = []
        if features.burst_count > 4:
            event_reasons.append("context_sigh_has_too_many_active_bursts")
        if features.longest_burst_seconds < 0.20:
            event_reasons.append("context_sigh_active_burst_too_short")
        if features.transient_peak_count > 5:
            event_reasons.append("context_sigh_too_many_transients")
        return ("pass" if not event_reasons else "review", event_reasons)
    return status, reasons


def classify_audio_file(
    audio_path: Path,
    *,
    expected_tag: str,
    source_type: str | None = None,
    model_name: str = DEFAULT_AST_MODEL,
    top_k: int = 12,
    min_label_score: float = 0.08,
    hard_neighbor_reject_score: float = 0.20,
    use_ast: bool = True,
    predictor: AudioPredictor | None = None,
    predictor_error: str | None = None,
) -> dict:
    tag = normalize_tag(expected_tag)
    features = waveform_features(audio_path)
    waveform_status, waveform_reasons = waveform_gate(tag, features)
    is_elevenlabs_context = str(source_type or "").startswith("elevenlabs_voice_context")
    context_waveform_status: str | None = None
    context_waveform_reasons: list[str] = []
    if is_elevenlabs_context:
        context_waveform_status, context_waveform_reasons = context_waveform_gate(tag, features)
    predictions: list[dict] = []
    classifier_error: str | None = None
    if use_ast:
        if predictor is not None:
            predictions, classifier_error = predictor.predict(audio_path, top_k=top_k)
        elif predictor_error:
            predictions, classifier_error = [], predictor_error
        else:
            predictions, classifier_error = load_ast_predictions(audio_path, model_name=model_name, top_k=top_k)

    expected_score, expected_matches = label_score(predictions, TAG_LABELS.get(tag, (tag,)))
    reject_score, reject_matches = label_score(predictions, NEIGHBOR_REJECTS.get(tag, ()))
    decision = "manual_review"
    reasons: list[str] = []
    ast_context_accept = (
        is_elevenlabs_context
        and waveform_status == "review"
        and (
            (tag == "gasp" and expected_score >= 0.40 and reject_score < hard_neighbor_reject_score)
            or (tag == "sigh" and expected_score >= 0.25 and reject_score < hard_neighbor_reject_score)
        )
    )
    waveform_context_accept = (
        bool(predictions)
        and
        is_elevenlabs_context
        and context_waveform_status == "pass"
        and (
            (tag in {"gasp", "sigh"} and reject_score < max(hard_neighbor_reject_score, expected_score * 3.0, 0.08))
            or (tag == "chuckle" and reject_score < max(hard_neighbor_reject_score, expected_score * 2.0, 0.08))
        )
    )
    hard_waveform_reject = waveform_status == "reject" and (
        "audio_unreadable_or_empty" in waveform_reasons
        or tag == "laugh"
    )
    hard_neighbor_reject = tag == "laugh" and reject_score >= max(hard_neighbor_reject_score, expected_score * 1.5)
    if hard_neighbor_reject:
        decision = "reject"
        reasons.append("classifier_matched_neighbor_reject_label")
    elif ast_context_accept:
        decision = "accept"
        reasons.append("classifier_expected_tag_overrides_context_clip_waveform_review")
        reasons.extend(f"waveform_context_review:{reason}" for reason in waveform_reasons)
    elif waveform_context_accept:
        decision = "accept"
        reasons.append("context_event_waveform_accept")
        if waveform_status != "pass":
            reasons.extend(f"waveform_context_review:{reason}" for reason in waveform_reasons)
    elif expected_score >= min_label_score and waveform_status == "pass":
        decision = "accept"
        reasons.append("classifier_and_waveform_match_expected_tag")
    elif not predictions and waveform_status == "pass":
        decision = "manual_review"
        reasons.append(WAVEFORM_PREFILTER_ONLY_REASON)
    elif hard_waveform_reject:
        decision = "reject"
        reasons.extend(waveform_reasons)
    elif waveform_status == "reject":
        decision = "manual_review"
        reasons.extend(f"waveform_review:{reason}" for reason in waveform_reasons)
    elif waveform_status == "review":
        decision = "manual_review"
        reasons.extend(f"waveform_review:{reason}" for reason in waveform_reasons)
    elif reject_score >= min_label_score:
        decision = "manual_review"
        reasons.append("classifier_neighbor_label_requires_human_review")
    else:
        reasons.append("classifier_confidence_below_threshold")

    return {
        "schema": ORPHEUS_AUDIO_CLASSIFIER_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "audio_path": str(audio_path.resolve()),
        "expected_tag": f"<{tag}>",
        "decision": decision,
        "reasons": reasons,
        "model": model_name if use_ast else None,
        "classifier_error": classifier_error,
        "scores": {
            "expected_label_score": expected_score,
            "neighbor_reject_score": reject_score,
            "min_label_score": min_label_score,
            "hard_neighbor_reject_score": hard_neighbor_reject_score,
        },
        "matches": {
            "expected": expected_matches,
            "neighbor_reject": reject_matches,
        },
        "top_predictions": predictions,
        "waveform": {
            "duration_seconds": features.duration_seconds,
            "rms": features.rms,
            "peak": features.peak,
            "active_ratio": features.active_ratio,
            "burst_count": features.burst_count,
            "longest_burst_seconds": features.longest_burst_seconds,
            "transient_peak_count": features.transient_peak_count,
            "transient_peak_density": features.transient_peak_density,
            "peak_prominence_mean": features.peak_prominence_mean,
            "peak_width_mean_seconds": features.peak_width_mean_seconds,
            "inter_peak_interval_mean_seconds": features.inter_peak_interval_mean_seconds,
            "inter_peak_interval_std_seconds": features.inter_peak_interval_std_seconds,
            "envelope_cv": features.envelope_cv,
            "decision": waveform_status,
            "reasons": waveform_reasons,
            "context_decision": context_waveform_status,
            "context_reasons": context_waveform_reasons,
        },
    }


def classify_manifest(
    *,
    manifest_path: Path,
    out_path: Path | None = None,
    model_name: str = DEFAULT_AST_MODEL,
    top_k: int = 12,
    min_label_score: float = 0.08,
    hard_neighbor_reject_score: float = 0.20,
    use_ast: bool = True,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    predictor: AudioPredictor | None = None
    predictor_error: str | None = None
    if use_ast:
        predictor, predictor_error = build_ast_predictor(model_name=model_name)
    records = []
    for record in manifest.get("records", []):
        wav_path = record.get("wav_path") or record.get("audio_path")
        if not wav_path:
            continue
        records.append(
            {
                "id": record.get("id"),
                "prompt": record.get("prompt"),
                "tts_text": record.get("tts_text"),
                "source_type": record.get("source_type"),
                "classification": classify_audio_file(
                    Path(wav_path),
                    expected_tag=record.get("orpheus_tag") or record.get("tts_text") or "",
                    source_type=record.get("source_type"),
                    model_name=model_name,
                    top_k=top_k,
                    min_label_score=min_label_score,
                    hard_neighbor_reject_score=hard_neighbor_reject_score,
                    use_ast=use_ast,
                    predictor=predictor,
                    predictor_error=predictor_error,
                ),
            }
        )
    counts: dict[str, int] = {}
    by_tag: dict[str, dict[str, int]] = {}
    for row in records:
        classification = row["classification"]
        decision = classification["decision"]
        tag = classification["expected_tag"]
        counts[decision] = counts.get(decision, 0) + 1
        by_tag.setdefault(tag, {})
        by_tag[tag][decision] = by_tag[tag].get(decision, 0) + 1
    result = {
        "schema": ORPHEUS_AUDIO_CLASSIFIER_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path.resolve()),
        "model": model_name if use_ast else None,
        "use_ast": use_ast,
        "record_count": len(records),
        "decision_counts": counts,
        "decision_counts_by_tag": by_tag,
        "records": records,
    }
    target = out_path or (manifest_path.parent / "classifier-result.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    result["classifier_result_path"] = str(target.resolve())
    return result
