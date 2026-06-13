"""Clip quality scoring."""

from __future__ import annotations

import numpy as np


def score_clip(y: np.ndarray, sr: int) -> tuple[float, dict[str, float]]:
    if y.size == 0:
        return 0.0, {"rms": 0.0, "peak": 0.0, "clip_ratio": 1.0, "speech_ratio": 0.0}

    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(np.square(y))))
    clip_ratio = float(np.mean(np.abs(y) > 0.98))

    frame = 1024
    hop = 512
    energies: list[float] = []
    for offset in range(0, max(len(y) - frame, 0), hop):
        chunk = y[offset : offset + frame]
        energies.append(float(np.sqrt(np.mean(np.square(chunk)))))
    energies_arr = np.asarray(energies)
    if energies_arr.size == 0:
        speech_ratio = 0.0
    else:
        threshold = float(np.percentile(energies_arr, 35))
        speech_ratio = float(np.mean(energies_arr > max(threshold * 2.0, 0.01)))

    if rms < 0.008 or rms > 0.25:
        rms_score = 0.0
    elif rms < 0.02:
        rms_score = rms / 0.02 * 0.5
    elif rms <= 0.12:
        rms_score = 1.0
    else:
        rms_score = max(0.0, 1.0 - (rms - 0.12) / 0.13)

    score = (
        speech_ratio * 0.45
        + rms_score * 0.25
        + max(0.0, 1.0 - clip_ratio * 20) * 0.20
        + max(0.0, 1.0 - max(peak - 0.95, 0.0) * 20) * 0.10
    )
    return round(score, 5), {
        "rms": round(rms, 5),
        "peak": round(peak, 5),
        "clip_ratio": round(clip_ratio, 5),
        "speech_ratio": round(speech_ratio, 5),
    }


def rank_score(row: dict) -> float:
    quality = float(row.get("quality_score") or 0.0)
    asr = float(row.get("asr_confidence") or 0.0)
    agreement = 0.05 if row.get("f0_guess") == row.get("gender_label") else 0.0
    duration = float(row.get("duration_sec") or 0.0)
    duration_bonus = min(duration / 10.0, 0.1)
    gender = float(row.get("gender_score") or 0.0) * 0.05
    return quality + asr * 0.2 + agreement + duration_bonus + gender
