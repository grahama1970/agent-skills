"""Audio evaluation metrics for persona humming quality.

All metrics use scipy + numpy + soundfile only (no librosa).
Designed for Embry's use case: naturalness and imperfection over fidelity.

Merged from hum-lab/src/evaluate.py.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.fft import dct
from scipy.spatial.distance import cosine

STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"

# Mel filterbank parameters
N_MELS = 40
N_FFT = 2048
HOP_LENGTH = 512
N_MFCC = 13


@dataclass
class EvalScores:
    """Evaluation scores for a single audio output."""

    timbre: float
    melody: float
    naturalness: float
    artifacts: float
    overall: float

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def passes_gates(self) -> tuple[bool, list[str]]:
        """Check quality gates. Returns (passed, list of failures)."""
        failures = []
        if self.artifacts < 0.7:
            failures.append(f"artifact_score {self.artifacts:.2f} < 0.7")
        if self.timbre < 0.4:
            failures.append(f"timbre_score {self.timbre:.2f} < 0.4")
        if self.melody < 0.4 or self.melody > 0.9:
            failures.append(f"melody_score {self.melody:.2f} outside 0.4-0.9")
        if self.overall < 0.5:
            failures.append(f"overall_score {self.overall:.2f} < 0.5")
        return len(failures) == 0, failures


def _load_audio(path: Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """Load audio as mono float32, resampled to target_sr."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    # Mix to mono
    audio = data.mean(axis=1)
    # Resample if needed
    if sr != target_sr:
        n_samples = int(len(audio) * target_sr / sr)
        audio = signal.resample(audio, n_samples)
        sr = target_sr
    return audio, sr


def _mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    """Build a mel-scale filterbank matrix (n_mels x n_fft//2+1)."""
    fmin, fmax = 0.0, sr / 2.0
    mel_min = 2595.0 * np.log10(1.0 + fmin / 700.0)
    mel_max = 2595.0 * np.log10(1.0 + fmax / 700.0)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)

    n_bins = n_fft // 2 + 1
    fft_freqs = np.linspace(0, sr / 2.0, n_bins)

    fb = np.zeros((n_mels, n_bins))
    for i in range(n_mels):
        lo, center, hi = hz_points[i], hz_points[i + 1], hz_points[i + 2]
        # Rising slope
        up = (fft_freqs - lo) / max(center - lo, 1e-10)
        # Falling slope
        down = (hi - fft_freqs) / max(hi - center, 1e-10)
        fb[i] = np.maximum(0, np.minimum(up, down))
    return fb


def _compute_mfcc(audio: np.ndarray, sr: int) -> np.ndarray:
    """Compute MFCCs via FFT + mel filterbank + DCT. Returns (n_frames, n_mfcc)."""
    # STFT
    _, _, Zxx = signal.stft(audio, fs=sr, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH)
    power = np.abs(Zxx) ** 2

    # Mel filterbank
    fb = _mel_filterbank(sr, N_FFT, N_MELS)
    mel_spec = fb @ power  # (n_mels, n_frames)

    # Log mel
    log_mel = np.log(mel_spec + 1e-10)

    # DCT to get MFCCs
    mfcc = dct(log_mel, type=2, axis=0, norm="ortho")[:N_MFCC]  # (n_mfcc, n_frames)
    return mfcc.T  # (n_frames, n_mfcc)


def _compute_f0_autocorr(audio: np.ndarray, sr: int) -> np.ndarray:
    """Simple autocorrelation-based F0 extraction.

    Not as good as RMVPE but works without Docker and is sufficient for
    F0 correlation measurement between two signals.
    """
    frame_len = int(0.04 * sr)  # 40ms frames
    hop = int(0.01 * sr)  # 10ms hop
    f0_min, f0_max = 50, 600
    lag_min, lag_max = sr // f0_max, sr // f0_min

    n_frames = (len(audio) - frame_len) // hop
    f0 = np.zeros(max(n_frames, 0))

    for i in range(n_frames):
        start = i * hop
        frame = audio[start : start + frame_len]
        frame = frame - frame.mean()

        if np.max(np.abs(frame)) < 1e-4:
            f0[i] = 0.0
            continue

        # Normalized autocorrelation
        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(frame) - 1 :]  # Keep positive lags only
        if corr[0] > 0:
            corr = corr / corr[0]

        # Search for peak in valid lag range
        search_start = min(lag_min, len(corr) - 1)
        search_end = min(lag_max, len(corr))
        if search_start >= search_end:
            f0[i] = 0.0
            continue

        segment = corr[search_start:search_end]
        if len(segment) == 0:
            f0[i] = 0.0
            continue

        peak_idx = np.argmax(segment) + search_start
        if corr[peak_idx] > 0.3:  # Confidence threshold
            f0[i] = sr / peak_idx
        else:
            f0[i] = 0.0

    return f0


def _rms_envelope(audio: np.ndarray, sr: int, frame_ms: int = 20) -> np.ndarray:
    """Compute RMS energy envelope."""
    frame_len = int(frame_ms * sr / 1000)
    hop = frame_len // 2
    n_frames = (len(audio) - frame_len) // hop
    env = np.zeros(max(n_frames, 0))
    for i in range(n_frames):
        start = i * hop
        frame = audio[start : start + frame_len]
        env[i] = np.sqrt(np.mean(frame**2))
    return env


def timbre_score(
    output_audio: np.ndarray,
    output_sr: int,
    reference_mfcc_mean: np.ndarray,
    reference_mfcc_std: np.ndarray,
) -> float:
    """MFCC-based spectral envelope comparison against persona reference.

    Computes cosine similarity of mean MFCC profile between output and
    the persona's speaking voice reference samples.
    Returns 0.0-1.0 (higher = more like persona).
    """
    mfcc_out = _compute_mfcc(output_audio, output_sr)
    if len(mfcc_out) == 0:
        return 0.0

    out_mean = mfcc_out.mean(axis=0)

    # Cosine similarity (1 - cosine distance)
    sim = 1.0 - cosine(out_mean, reference_mfcc_mean)
    # Clamp to [0, 1]
    return float(np.clip(sim, 0.0, 1.0))


def melody_score(
    output_audio: np.ndarray,
    output_sr: int,
    input_audio: np.ndarray,
    input_sr: int,
) -> float:
    """F0 correlation between output and input vocals.

    Uses Pearson correlation of F0 contours. Penalizes both too-low (<0.4)
    and too-high (>0.9) correlation — too high means robotic precision.
    Returns adjusted score 0.0-1.0.
    """
    f0_out = _compute_f0_autocorr(output_audio, output_sr)
    f0_in = _compute_f0_autocorr(input_audio, input_sr)

    # Align lengths
    min_len = min(len(f0_out), len(f0_in))
    if min_len < 10:
        return 0.5  # Not enough data

    f0_out = f0_out[:min_len]
    f0_in = f0_in[:min_len]

    # Only compare voiced frames (both non-zero)
    voiced = (f0_out > 0) & (f0_in > 0)
    if voiced.sum() < 10:
        return 0.5

    corr = np.corrcoef(f0_out[voiced], f0_in[voiced])[0, 1]
    if np.isnan(corr):
        return 0.5

    # Penalize both extremes — ideal is 0.6-0.8
    # Bell curve centered at 0.7 with width ~0.3
    adjusted = np.exp(-((corr - 0.7) ** 2) / (2 * 0.15**2))
    return float(np.clip(adjusted, 0.0, 1.0))


def naturalness_score(
    output_audio: np.ndarray,
    output_sr: int,
    reference_audio: Optional[np.ndarray] = None,
    reference_sr: Optional[int] = None,
) -> float:
    """Compare energy/pitch variation against human reference.

    If human reference is available: correlate RMS envelopes and compare
    pitch jitter profiles.
    If not: use synthetic heuristic (moderate jitter = good).
    Returns 0.0-1.0.
    """
    f0_out = _compute_f0_autocorr(output_audio, output_sr)
    rms_out = _rms_envelope(output_audio, output_sr)
    voiced_out = f0_out[f0_out > 0]

    if reference_audio is not None and reference_sr is not None:
        # Compare against human reference
        f0_ref = _compute_f0_autocorr(reference_audio, reference_sr)
        rms_ref = _rms_envelope(reference_audio, reference_sr)
        voiced_ref = f0_ref[f0_ref > 0]

        # RMS envelope correlation (resample to same length)
        min_rms = min(len(rms_out), len(rms_ref))
        if min_rms > 10:
            rms_corr = np.corrcoef(
                signal.resample(rms_out, min_rms),
                signal.resample(rms_ref, min_rms),
            )[0, 1]
            if np.isnan(rms_corr):
                rms_corr = 0.0
            rms_score = max(0.0, rms_corr)
        else:
            rms_score = 0.5

        # Pitch jitter comparison
        if len(voiced_out) > 2 and len(voiced_ref) > 2:
            jitter_out = np.std(np.diff(voiced_out)) / (np.mean(voiced_out) + 1e-10)
            jitter_ref = np.std(np.diff(voiced_ref)) / (np.mean(voiced_ref) + 1e-10)
            # Score based on how close jitter profiles are
            jitter_ratio = min(jitter_out, jitter_ref) / (max(jitter_out, jitter_ref) + 1e-10)
            jitter_score = jitter_ratio
        else:
            jitter_score = 0.5

        return float(np.clip(0.6 * rms_score + 0.4 * jitter_score, 0.0, 1.0))

    else:
        # Synthetic heuristic: moderate variation = natural
        if len(voiced_out) < 5:
            return 0.5

        # Pitch jitter (frame-to-frame F0 variation)
        jitter = np.std(np.diff(voiced_out)) / (np.mean(voiced_out) + 1e-10)
        # Ideal jitter range ~0.02-0.08 for natural humming
        jitter_score = np.exp(-((jitter - 0.05) ** 2) / (2 * 0.03**2))

        # Energy variation — should have dynamics, not flat
        if len(rms_out) > 5:
            rms_cv = np.std(rms_out) / (np.mean(rms_out) + 1e-10)
            # Ideal CV ~0.2-0.5
            energy_score = np.exp(-((rms_cv - 0.35) ** 2) / (2 * 0.15**2))
        else:
            energy_score = 0.5

        return float(np.clip(0.5 * jitter_score + 0.5 * energy_score, 0.0, 1.0))


def artifact_score(output_audio: np.ndarray, output_sr: int) -> float:
    """Detect robotic/metallic artifacts via spectral flux outliers.

    Frame-by-frame spectral flux (L2 norm of STFT difference).
    Count frames exceeding 3 sigma from mean — these are glitches.
    Returns 0.0-1.0 (higher = cleaner).
    """
    _, _, Zxx = signal.stft(
        output_audio, fs=output_sr, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH
    )
    mag = np.abs(Zxx)

    if mag.shape[1] < 2:
        return 1.0

    # Spectral flux: L2 norm of frame-to-frame difference
    flux = np.sqrt(np.sum(np.diff(mag, axis=1) ** 2, axis=0))

    if len(flux) == 0 or np.std(flux) < 1e-10:
        return 1.0

    mean_flux = np.mean(flux)
    std_flux = np.std(flux)

    # Count outlier frames (> 3 sigma)
    outliers = np.sum(flux > mean_flux + 3 * std_flux)
    outlier_ratio = outliers / len(flux)

    score = 1.0 - outlier_ratio * 10
    return float(np.clip(score, 0.0, 1.0))


def build_reference_profile(
    persona: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Build mean MFCC profile from persona TTS reference samples.

    Returns (mean_mfcc, std_mfcc) each of shape (n_mfcc,).
    """
    ref_dir = STORAGE_ROOT / "personas" / persona / "tts_output"
    wav_files = sorted(ref_dir.glob("*.wav"))
    if not wav_files:
        raise FileNotFoundError(f"No TTS reference WAV files in {ref_dir}")

    all_means = []
    for wav in wav_files:
        audio, sr = _load_audio(wav)
        mfcc = _compute_mfcc(audio, sr)
        if len(mfcc) > 0:
            all_means.append(mfcc.mean(axis=0))

    if not all_means:
        raise ValueError("Could not compute MFCCs from any reference sample")

    stacked = np.array(all_means)
    return stacked.mean(axis=0), stacked.std(axis=0)


def evaluate(
    output_path: Path,
    input_path: Optional[Path] = None,
    reference_path: Optional[Path] = None,
    persona: str = "embry",
    ref_mfcc_mean: Optional[np.ndarray] = None,
    ref_mfcc_std: Optional[np.ndarray] = None,
) -> EvalScores:
    """Evaluate a single converted audio file.

    Args:
        output_path: The RVC-converted audio to evaluate.
        input_path: Original vocals (for melody comparison).
        reference_path: Human humming reference (for naturalness).
        persona: Persona name (for TTS reference lookup).
        ref_mfcc_mean: Pre-computed reference MFCC mean (avoids recomputation).
        ref_mfcc_std: Pre-computed reference MFCC std.

    Returns:
        EvalScores with all metrics.
    """
    output_audio, output_sr = _load_audio(output_path)

    # Build reference profile if not provided
    if ref_mfcc_mean is None:
        ref_mfcc_mean, ref_mfcc_std = build_reference_profile(persona)

    # Timbre score
    ts = timbre_score(output_audio, output_sr, ref_mfcc_mean, ref_mfcc_std)

    # Melody score (need input vocals)
    if input_path is not None and input_path.exists():
        input_audio, input_sr = _load_audio(input_path)
        ms = melody_score(output_audio, output_sr, input_audio, input_sr)
    else:
        ms = 0.5  # Neutral if no input available

    # Naturalness score
    ref_audio, ref_sr = None, None
    if reference_path is not None and reference_path.exists():
        ref_audio, ref_sr = _load_audio(reference_path)
    ns = naturalness_score(output_audio, output_sr, ref_audio, ref_sr)

    # Artifact score
    art = artifact_score(output_audio, output_sr)

    # Adjusted melody score for overall (penalize extremes)
    # melody_score already does this internally
    overall = 0.30 * ts + 0.25 * ms + 0.25 * ns + 0.20 * art

    return EvalScores(
        timbre=round(ts, 3),
        melody=round(ms, 3),
        naturalness=round(ns, 3),
        artifacts=round(art, 3),
        overall=round(overall, 3),
    )
