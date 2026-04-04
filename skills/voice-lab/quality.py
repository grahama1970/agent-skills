#!/usr/bin/env python3
"""
Quality evaluation metrics for voice-lab.
Measures speaker similarity, naturalness, and artifact detection.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import typer


@dataclass
class QualityMetrics:
    """Quality evaluation results."""
    similarity: float  # 0-1, cosine similarity to reference
    naturalness: float  # 1-5 MOS score
    artifact_score: float  # 0-1, higher is better (fewer artifacts)
    pitch_variation: float  # F0 std dev
    speaking_rate: float  # estimated words per minute
    overall_score: float  # weighted average

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load audio file and return samples + sample rate."""
    try:
        import soundfile as sf
        audio, sr = sf.read(str(path))
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        return audio, sr
    except ImportError:
        from scipy.io import wavfile
        sr, audio = wavfile.read(str(path))
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0
        return audio, sr


def compute_speaker_similarity(
    generated_audio: np.ndarray,
    reference_audio: np.ndarray,
    sample_rate: int,
) -> float:
    """
    Compute speaker similarity using embedding cosine distance.
    Uses resemblyzer if available, otherwise falls back to spectral comparison.
    """
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav

        encoder = VoiceEncoder()

        # Preprocess and get embeddings
        gen_wav = preprocess_wav(generated_audio, source_sr=sample_rate)
        ref_wav = preprocess_wav(reference_audio, source_sr=sample_rate)

        gen_embed = encoder.embed_utterance(gen_wav)
        ref_embed = encoder.embed_utterance(ref_wav)

        # Cosine similarity
        similarity = np.dot(gen_embed, ref_embed) / (
            np.linalg.norm(gen_embed) * np.linalg.norm(ref_embed) + 1e-10
        )
        return float(np.clip(similarity, 0, 1))

    except ImportError:
        # Fallback: MFCC-based spectral similarity
        return compute_spectral_similarity(generated_audio, reference_audio, sample_rate)


def compute_spectral_similarity(
    audio1: np.ndarray,
    audio2: np.ndarray,
    sample_rate: int,
) -> float:
    """Fallback spectral similarity using MFCCs."""
    try:
        import librosa

        # Compute MFCCs
        mfcc1 = librosa.feature.mfcc(y=audio1, sr=sample_rate, n_mfcc=13)
        mfcc2 = librosa.feature.mfcc(y=audio2, sr=sample_rate, n_mfcc=13)

        # Average over time
        mean1 = mfcc1.mean(axis=1)
        mean2 = mfcc2.mean(axis=1)

        # Cosine similarity
        similarity = np.dot(mean1, mean2) / (
            np.linalg.norm(mean1) * np.linalg.norm(mean2) + 1e-10
        )
        return float(np.clip(similarity, 0, 1))

    except ImportError:
        # Very basic fallback
        return 0.5  # Unknown


def compute_naturalness(audio: np.ndarray, sample_rate: int) -> float:
    """
    Estimate naturalness (MOS-like score).
    Uses NISQA if available, otherwise heuristics.
    """
    try:
        # Try NISQA (neural MOS predictor)
        from nisqa.NISQA_model import nisqaModel

        model = nisqaModel()
        mos = model.predict(audio, sample_rate)
        return float(np.clip(mos, 1, 5))

    except ImportError:
        pass

    # Heuristics-based naturalness estimation
    score = 3.0  # Start at neutral

    # Check for clipping (bad)
    peak = np.max(np.abs(audio))
    if peak > 0.99:
        score -= 0.5  # Clipping penalty

    # Check for silence ratio (too much is bad)
    silence_threshold = 0.01
    silence_ratio = np.mean(np.abs(audio) < silence_threshold)
    if silence_ratio > 0.3:
        score -= 0.3  # Too much silence

    # Check for dynamic range (some variation is good)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 0.05:
        score -= 0.3  # Too quiet
    elif rms > 0.3:
        score -= 0.2  # Too loud/compressed

    # Check for sudden amplitude changes (artifacts)
    diff = np.abs(np.diff(audio))
    sudden_changes = np.sum(diff > 0.5) / len(diff)
    if sudden_changes > 0.001:
        score -= 0.5 * min(sudden_changes * 100, 1)  # Click/pop penalty

    return float(np.clip(score, 1, 5))


def detect_artifacts(audio: np.ndarray, sample_rate: int) -> float:
    """
    Detect common TTS artifacts.
    Returns 0-1 score where 1 = no artifacts detected.
    """
    artifact_penalty = 0.0

    # 1. Click/pop detection (sudden amplitude spikes)
    diff = np.abs(np.diff(audio))
    threshold = np.std(diff) * 5
    clicks = np.sum(diff > threshold)
    click_ratio = clicks / len(diff)
    artifact_penalty += min(click_ratio * 10, 0.3)

    # 2. Clipping detection
    clipping = np.sum(np.abs(audio) > 0.99) / len(audio)
    artifact_penalty += min(clipping * 5, 0.2)

    # 3. DC offset
    dc_offset = abs(np.mean(audio))
    if dc_offset > 0.05:
        artifact_penalty += 0.1

    # 4. Spectral discontinuities (using short-time energy)
    frame_length = int(sample_rate * 0.025)  # 25ms frames
    hop_length = int(sample_rate * 0.010)  # 10ms hop

    # Compute short-time energy
    energy = []
    for i in range(0, len(audio) - frame_length, hop_length):
        frame = audio[i:i + frame_length]
        energy.append(np.sum(frame ** 2))

    if len(energy) > 2:
        energy = np.array(energy)
        energy_diff = np.abs(np.diff(energy))
        energy_threshold = np.std(energy_diff) * 4
        discontinuities = np.sum(energy_diff > energy_threshold) / len(energy_diff)
        artifact_penalty += min(discontinuities, 0.2)

    return float(np.clip(1.0 - artifact_penalty, 0, 1))


def estimate_pitch_variation(audio: np.ndarray, sample_rate: int) -> float:
    """Estimate F0 (pitch) variation."""
    try:
        import librosa

        # Extract F0
        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C6'),
            sr=sample_rate,
        )

        # Filter to voiced segments
        voiced_f0 = f0[voiced_flag]
        if len(voiced_f0) > 0:
            return float(np.std(voiced_f0))
        return 0.0

    except ImportError:
        # Basic zero-crossing rate as proxy
        zcr = np.sum(np.abs(np.diff(np.sign(audio)))) / (2 * len(audio))
        return float(zcr * sample_rate)


def estimate_speaking_rate(audio: np.ndarray, sample_rate: int, text: str = "") -> float:
    """Estimate speaking rate in words per minute."""
    duration_sec = len(audio) / sample_rate

    if text:
        # If text is provided, calculate actual WPM
        word_count = len(text.split())
        return word_count / (duration_sec / 60) if duration_sec > 0 else 0

    # Estimate from syllable rate using energy peaks
    # Simple heuristic: count energy peaks as syllables
    frame_length = int(sample_rate * 0.025)
    hop_length = int(sample_rate * 0.010)

    energy = []
    for i in range(0, len(audio) - frame_length, hop_length):
        frame = audio[i:i + frame_length]
        energy.append(np.sum(frame ** 2))

    if len(energy) < 3:
        return 0.0

    energy = np.array(energy)
    # Find peaks (simple method)
    peaks = 0
    for i in range(1, len(energy) - 1):
        if energy[i] > energy[i-1] and energy[i] > energy[i+1]:
            if energy[i] > np.mean(energy) * 0.5:  # Above threshold
                peaks += 1

    # Assume ~1.5 syllables per word
    estimated_words = peaks / 1.5
    wpm = estimated_words / (duration_sec / 60) if duration_sec > 0 else 0
    return float(wpm)


def evaluate_quality(
    generated_path: Path,
    reference_path: Optional[Path] = None,
    text: str = "",
    weights: Optional[dict] = None,
) -> QualityMetrics:
    """
    Run full quality evaluation on generated audio.

    Args:
        generated_path: Path to generated audio file
        reference_path: Optional path to reference audio for similarity
        text: Optional text for speaking rate calculation
        weights: Optional custom weights for overall score
    """
    if weights is None:
        weights = {
            "similarity": 0.3,
            "naturalness": 0.4,
            "artifacts": 0.3,
        }

    gen_audio, gen_sr = load_audio(generated_path)

    # Compute similarity if reference provided
    if reference_path and reference_path.exists():
        ref_audio, ref_sr = load_audio(reference_path)
        # Resample if needed
        if gen_sr != ref_sr:
            try:
                import librosa
                ref_audio = librosa.resample(ref_audio, orig_sr=ref_sr, target_sr=gen_sr)
            except ImportError:
                pass  # Use as-is
        similarity = compute_speaker_similarity(gen_audio, ref_audio, gen_sr)
    else:
        similarity = 0.5  # Unknown without reference

    # Compute other metrics
    naturalness = compute_naturalness(gen_audio, gen_sr)
    artifact_score = detect_artifacts(gen_audio, gen_sr)
    pitch_variation = estimate_pitch_variation(gen_audio, gen_sr)
    speaking_rate = estimate_speaking_rate(gen_audio, gen_sr, text)

    # Compute weighted overall score (normalize to 1-5 range)
    overall = (
        weights.get("similarity", 0.3) * (similarity * 4 + 1) +  # Scale 0-1 to 1-5
        weights.get("naturalness", 0.4) * naturalness +
        weights.get("artifacts", 0.3) * (artifact_score * 4 + 1)  # Scale 0-1 to 1-5
    )

    return QualityMetrics(
        similarity=similarity,
        naturalness=naturalness,
        artifact_score=artifact_score,
        pitch_variation=pitch_variation,
        speaking_rate=speaking_rate,
        overall_score=overall,
    )


def main(
    audio_file: str = typer.Argument(..., help="Audio file to evaluate"),
    reference: Optional[str] = typer.Option(None, help="Reference audio for similarity"),
    text: str = typer.Option("", help="Text for speaking rate"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """CLI for quality evaluation."""

    if not audio_file.exists():
        print(f"Error: File not found: {audio_file}")
        return 1

    metrics = evaluate_quality(audio_file, reference, text)

    if json:
        print(metrics.to_json())
    else:
        print(f"Quality Evaluation: {audio_file.name}")
        print("=" * 50)
        print(f"  Similarity:      {metrics.similarity:.2f}")
        print(f"  Naturalness:     {metrics.naturalness:.2f}/5.0")
        print(f"  Artifact Score:  {metrics.artifact_score:.2f}")
        print(f"  Pitch Variation: {metrics.pitch_variation:.1f} Hz")
        print(f"  Speaking Rate:   {metrics.speaking_rate:.0f} WPM")
        print("-" * 50)
        print(f"  Overall Score:   {metrics.overall_score:.2f}/5.0")

        # Quality rating
        if metrics.overall_score >= 4.0:
            rating = "Excellent"
        elif metrics.overall_score >= 3.5:
            rating = "Good"
        elif metrics.overall_score >= 2.5:
            rating = "Acceptable"
        else:
            rating = "Poor"
        print(f"  Rating:          {rating}")

    return 0


if __name__ == "__main__":
    exit(main())
