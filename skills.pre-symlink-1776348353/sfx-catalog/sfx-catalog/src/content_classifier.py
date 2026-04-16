"""Rule-based audio content classification."""


def classify_sound(features: dict) -> list[str]:
    """Classify sound based on audio features using rule-based heuristics.
    
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
    
    # Rule 1: Impact sounds (short, fast attack, loud)
    if duration < 2.0 and attack_ms < 50 and peak_db > -10:
        categories.append("impact")
    
    # Rule 2: Ambient (long duration, sustained envelope)
    if duration > 5.0 and envelope_type == "sustained":
        categories.append("ambient")
    
    # Rule 3: Foley (medium duration, varied characteristics)
    if 0.5 < duration < 5.0 and envelope_type in ["percussive", "sustained"]:
        categories.append("foley")
    
    # Rule 4: Transition (short, whoosh-like)
    if duration < 3.0 and 2000 < centroid < 8000:
        categories.append("transition")
    
    # Rule 5: Texture (complex spectral content)
    if centroid > 3000:
        categories.append("texture")
    
    # Rule 6: Low frequency (rumbles, bass)
    if centroid < 500:
        categories.append("low_frequency")
    
    # Ensure at least one category
    if not categories:
        categories.append("uncategorized")
    
    return categories
