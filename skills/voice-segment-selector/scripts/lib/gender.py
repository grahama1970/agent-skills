"""Pitch and optional HF vocal characteristic classifiers."""

from __future__ import annotations

from typing import Any, Literal

import librosa
import numpy as np

from lib.constants import HF_MIN_SCORE, HF_MODEL, MALE_F0_HZ

ClassifierMode = Literal["hf", "f0", "both"]


def estimate_f0(y: np.ndarray, sr: int) -> tuple[float | None, str]:
    if y.size < sr:
        return None, "unknown"
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
    )
    voiced = f0[voiced_flag] if voiced_flag is not None else np.array([])
    voiced = voiced[~np.isnan(voiced)]
    if voiced.size < 8:
        return None, "unknown"
    median_f0 = float(np.median(voiced))
    return median_f0, ("male" if median_f0 < MALE_F0_HZ else "female")


def load_hf_classifier() -> Any:
    from transformers import pipeline

    return pipeline("audio-classification", model=HF_MODEL)


def classify_with_hf(pipe: Any, clip: np.ndarray, sr: int) -> tuple[str, float]:
    result = pipe({"raw": clip, "sampling_rate": sr})[0]
    label = str(result["label"]).lower()
    score = float(result["score"])
    if label not in {"male", "female"}:
        return "unknown", score
    return label, score


def choose_gender(
    mode: ClassifierMode,
    hf_pipe: Any | None,
    clip: np.ndarray,
    sr: int,
    f0_guess: str,
) -> tuple[str, float | None, str]:
    if mode == "f0":
        return f0_guess, None, "f0"
    assert hf_pipe is not None
    hf_label, hf_score = classify_with_hf(hf_pipe, clip, sr)
    if mode == "hf":
        if hf_score >= HF_MIN_SCORE and hf_label in {"male", "female"}:
            return hf_label, hf_score, "norwood-hf"
        return "unknown", hf_score, "norwood-hf"
    if hf_score >= HF_MIN_SCORE and hf_label in {"male", "female"}:
        return hf_label, hf_score, "norwood-hf+f0-fallback"
    if f0_guess in {"male", "female"}:
        return f0_guess, hf_score, "norwood-hf+f0-fallback"
    return "unknown", hf_score, "norwood-hf+f0-fallback"
