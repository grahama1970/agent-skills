"""Audio content classification with acoustic categories and bridge tags.

Two classification layers:
1. Acoustic categories — what the sound IS (impact, ambient, texture, etc.)
2. Bridge tags — what narrative/emotional PURPOSE the sound serves
   (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)

Bridge tags enable cross-modal search via /taxonomy. A scene tagged
"Stealth" can pull both knowledge (tactical doctrine) and SFX (quiet,
subtle sounds) through the same query.
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

# =============================================================================
# Bridge Tag Definitions (cross-modal semantic layer)
# =============================================================================
# These map acoustic characteristics to narrative/emotional intent.
# Same bridge attributes used across knowledge, media, and personas.

BRIDGE_TAGS = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"]


def classify_sound(features: dict) -> list[str]:
    """Classify sound into acoustic categories.

    Args:
        features: Dictionary of audio features from analyzer

    Returns:
        List of category labels (multi-label classification)
    """
    categories = []

    duration = features.get("duration", 0)
    envelope = features.get("envelope", {})
    envelope_type = envelope.get("type", "sustained")
    attack_ms = envelope.get("attack_ms", 0)
    freq_profile = features.get("frequency_profile", {})
    centroid = freq_profile.get("spectral_centroid", 0)
    loudness = features.get("loudness", {})
    peak_db = loudness.get("peak_db", -60)
    onset_density = envelope.get("onset_density", 0)

    # Rule 1: Impact sounds (fast attack, loud, impulsive)
    if attack_ms < 100 and peak_db > -10 and envelope_type in ("impact", "percussive"):
        categories.append("impact")

    # Rule 2: Ambient (long duration, sustained or low onset density)
    if duration > 5.0 and (envelope_type == "sustained" or onset_density < 0.5):
        categories.append("ambient")

    # Rule 3: Foley (medium duration, moderate characteristics)
    if 0.5 < duration < 8.0 and envelope_type in ("percussive", "sustained"):
        if onset_density > 0.3:
            categories.append("foley")

    # Rule 4: Transition (whoosh-like spectral sweep)
    centroid_std = freq_profile.get("centroid_std", 0)
    if centroid_std > 500 and 1000 < centroid < 8000:
        categories.append("transition")

    # Rule 5: Texture (complex, bright spectral content)
    if centroid > 3000:
        categories.append("texture")

    # Rule 6: Low frequency (rumbles, bass, sub-bass)
    if centroid < 800:
        categories.append("low_frequency")

    # Rule 7: Rhythmic (regular onset pattern)
    if onset_density > 2.0:
        categories.append("rhythmic")

    if not categories:
        categories.append("uncategorized")

    return categories


def classify_bridge_tags(features: dict) -> dict[str, float]:
    """Predict bridge tag scores from audio features.

    Returns a score (0.0-1.0) for each of the 6 bridge attributes
    based on acoustic characteristics. Higher = stronger match.

    Bridge tag → acoustic signature mapping:
      Precision  — Clean, focused, crisp (tonal, narrow bandwidth, steady)
      Resilience — Strong, sustained, powerful (loud, wide dynamic range, energetic)
      Fragility  — Delicate, brittle, breaking (bright, impulsive, short)
      Corruption — Distorted, chaotic, noisy (noise-like, irregular, spread)
      Loyalty    — Warm, grounding, consistent (mid-range, steady, smooth)
      Stealth    — Quiet, subtle, understated (quiet, sparse, dark)

    Args:
        features: Dictionary from analyze_audio_file()

    Returns:
        Dict mapping bridge tag name → confidence score (0.0-1.0)
    """
    freq = features.get("frequency_profile", {})
    env = features.get("envelope", {})
    loud = features.get("loudness", {})

    centroid = freq.get("spectral_centroid", 2000)
    centroid_std = freq.get("centroid_std", 500)
    bandwidth = freq.get("bandwidth", 2000)
    flatness = freq.get("flatness", 0.1)
    zcr_std = freq.get("zcr_std", 0.05)

    attack_ms = env.get("attack_ms", 100)
    onset_density = env.get("onset_density", 0.5)
    onset_strength = env.get("onset_strength_mean", 1.0)
    envelope_type = env.get("type", "sustained")

    peak_db = loud.get("peak_db", -20)
    rms_db = loud.get("rms_db", -30)
    dynamic_range = loud.get("dynamic_range", 20)
    crest_factor = loud.get("crest_factor", 3.0)

    duration = features.get("duration", 5.0)

    scores = {}

    # --- Precision: clean, focused, crisp ---
    # Low flatness (tonal), narrow bandwidth, low ZCR variance
    precision = 0.0
    precision += _sigmoid_score(flatness, center=0.05, scale=-30)  # Low flatness = tonal
    precision += _sigmoid_score(bandwidth, center=2000, scale=-0.001)  # Narrow bandwidth
    precision += _sigmoid_score(zcr_std, center=0.05, scale=-20)  # Steady ZCR
    precision += _sigmoid_score(centroid_std, center=500, scale=-0.003)  # Consistent spectral
    scores["Precision"] = _clamp(precision / 4.0)

    # --- Resilience: strong, sustained, powerful ---
    # High RMS, wide dynamic range, sustained, energetic
    resilience = 0.0
    resilience += _sigmoid_score(rms_db, center=-25, scale=0.1)  # Loud
    resilience += _sigmoid_score(dynamic_range, center=25, scale=0.08)  # Wide dynamics
    resilience += _sigmoid_score(onset_strength, center=2.0, scale=0.5)  # Energetic
    resilience += 0.7 if envelope_type == "sustained" else 0.3
    scores["Resilience"] = _clamp(resilience / 4.0)

    # --- Fragility: delicate, brittle, breaking ---
    # High centroid (bright), impulsive, short transients
    fragility = 0.0
    fragility += _sigmoid_score(centroid, center=4000, scale=0.0005)  # Bright
    fragility += _sigmoid_score(crest_factor, center=5, scale=0.3)  # Impulsive
    fragility += _sigmoid_score(attack_ms, center=50, scale=-0.02)  # Fast attack
    fragility += _sigmoid_score(duration, center=3, scale=-0.5)  # Short
    scores["Fragility"] = _clamp(fragility / 4.0)

    # --- Corruption: distorted, chaotic, noisy ---
    # High flatness (noise-like), high ZCR variance, wide bandwidth
    corruption = 0.0
    corruption += _sigmoid_score(flatness, center=0.1, scale=15)  # Noisy spectrum
    corruption += _sigmoid_score(zcr_std, center=0.08, scale=15)  # Irregular
    corruption += _sigmoid_score(bandwidth, center=3000, scale=0.0005)  # Spread
    corruption += _sigmoid_score(onset_density, center=3, scale=0.3)  # Many events
    scores["Corruption"] = _clamp(corruption / 4.0)

    # --- Loyalty: warm, grounding, consistent ---
    # Mid-range centroid, low dynamic range, smooth, sustained
    loyalty = 0.0
    loyalty += _bell_score(centroid, center=1500, width=1500)  # Mid-range (warm)
    loyalty += _sigmoid_score(dynamic_range, center=15, scale=-0.1)  # Steady
    loyalty += _sigmoid_score(zcr_std, center=0.04, scale=-20)  # Smooth
    loyalty += 0.7 if envelope_type == "sustained" else 0.3
    scores["Loyalty"] = _clamp(loyalty / 4.0)

    # --- Stealth: quiet, subtle, understated ---
    # Low RMS/peak, sparse onsets, dark (low centroid)
    stealth = 0.0
    stealth += _sigmoid_score(rms_db, center=-30, scale=-0.1)  # Quiet
    stealth += _sigmoid_score(peak_db, center=-15, scale=-0.1)  # Low peak
    stealth += _sigmoid_score(onset_density, center=0.3, scale=-3)  # Sparse
    stealth += _sigmoid_score(centroid, center=1500, scale=-0.0005)  # Dark
    scores["Stealth"] = _clamp(stealth / 4.0)

    return scores


def classify_bridge_tags_binary(features: dict, threshold: float = 0.5) -> list[str]:
    """Return bridge tags that exceed the confidence threshold.

    Args:
        features: Dictionary from analyze_audio_file()
        threshold: Minimum score to include tag (default 0.5)

    Returns:
        List of bridge tag names (e.g., ["Precision", "Stealth"])
    """
    scores = classify_bridge_tags(features)
    return [tag for tag, score in scores.items() if score >= threshold]


# =============================================================================
# Trained model support (loaded from /classifier-lab output)
# =============================================================================

_trained_model = None
_trained_scaler = None


def load_trained_model(model_path: Path) -> bool:
    """Load a trained sklearn model for bridge tag prediction.

    Args:
        model_path: Path to joblib-saved model dict with keys
                    'model', 'scaler', 'tags', 'feature_names'

    Returns:
        True if loaded successfully
    """
    global _trained_model, _trained_scaler
    try:
        import joblib
        bundle = joblib.load(model_path)
        _trained_model = bundle["model"]
        _trained_scaler = bundle.get("scaler")
        logger.info(f"Loaded trained bridge tag model from {model_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to load trained model: {e}")
        return False


def classify_bridge_tags_ml(feature_vector: list[float]) -> dict[str, float]:
    """Predict bridge tags using trained model.

    Falls back to heuristic classify_bridge_tags if no model loaded.

    Args:
        feature_vector: 67-dim vector from extract_feature_vector()

    Returns:
        Dict mapping bridge tag name → predicted probability
    """
    if _trained_model is None:
        return {}

    try:
        X = np.array([feature_vector])
        if _trained_scaler is not None:
            X = _trained_scaler.transform(X)

        # Multi-label: predict_proba returns list of arrays
        if hasattr(_trained_model, "predict_proba"):
            probas = _trained_model.predict_proba(X)
            if isinstance(probas, list):
                # MultiOutputClassifier: list of arrays per label
                return {
                    BRIDGE_TAGS[i]: float(probas[i][0][1]) if probas[i].shape[1] > 1 else float(probas[i][0][0])
                    for i in range(min(len(probas), len(BRIDGE_TAGS)))
                }
            else:
                # Single output — shouldn't happen for multi-label
                return {}
        else:
            # No probabilities, use hard predictions
            preds = _trained_model.predict(X)[0]
            return {BRIDGE_TAGS[i]: float(preds[i]) for i in range(min(len(preds), len(BRIDGE_TAGS)))}

    except Exception as e:
        logger.warning(f"ML prediction failed, using heuristic fallback: {e}")
        return {}


# =============================================================================
# Scoring utilities
# =============================================================================

def _sigmoid_score(value: float, center: float, scale: float) -> float:
    """Sigmoid activation: maps value to 0-1 based on center and scale."""
    x = (value - center) * scale
    x = max(-10, min(10, x))  # Prevent overflow
    return 1.0 / (1.0 + np.exp(-x))


def _bell_score(value: float, center: float, width: float) -> float:
    """Gaussian bell curve: peaks at center, falls off with width."""
    return float(np.exp(-0.5 * ((value - center) / max(width, 1)) ** 2))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp value to [low, high] range."""
    return max(low, min(high, value))
