"""TTS guidance generation from emotional analysis with research-backed parameters."""

from design_constants import CULTURAL_EMOTIONAL_NORMS


def generate_tts_guidance(
    emotional_layers: dict,
    emotions: list,
    cultural_norm: str = None,
    suppression_level: str = None,
    recent_event: str = None,
    current_age: str = None
) -> dict:
    """Generate specific TTS guidance from emotional analysis with research-backed parameters.

    Research basis:
    - Suppression produces measurable microstructural leakage at 50-150ms timescales
    - F0 variability >0.25 indicates autonomic dysregulation
    - Cultural norms affect baseline suppression and expression patterns
    - Recent events create emotional "freshness" that affects voice quality
    """
    # Initialize with baseline defaults
    guidance = {
        "tempo": 1.0,  # Neutral
        "pitch_variance": 0.5,  # Baseline
        "formality": 0.5,
        "emotional_range": 0.5,
        "vocal_weight": 0.5,
        "breath_pattern": "normal",
        "cultural_suppression_level": 0.5,
        # Original baseline fields
        "pacing": "moderate",
        "energy": "moderate",
        "breathiness": "low",
        "resonance": "chest",
        "pitch_variation": "moderate",
        "pauses": "natural",
        "emphasis_style": "subtle",
        # Research-backed additions
        "f0_variability": "normal",
        "jitter": "normal",
        "microstructure_leakage": False,
        "voice_quality_hnr": "normal",
    }

    # Foundational affects baseline
    foundational = " ".join(emotional_layers.get("foundational", []))
    if "grief" in foundational or "guarded" in foundational:
        guidance["breathiness"] = "slight"
        guidance["pauses"] = "contemplative"
        guidance["voice_quality_hnr"] = "slightly_low"
    if "hypervigilance" in foundational:
        guidance["pacing"] = "slightly_quick"
        guidance["energy"] = "tense"
        guidance["f0_variability"] = "elevated"
    if "determination" in foundational:
        guidance["resonance"] = "forward"
        guidance["emphasis_style"] = "purposeful"

    # Defining layer affects conscious delivery
    defining = " ".join(emotional_layers.get("defining", []))
    if "urgency" in defining:
        guidance["pacing"] = "driven"
        guidance["pitch_variation"] = "dynamic"
    if "authority" in defining:
        guidance["resonance"] = "deep_chest"
        guidance["pacing"] = "deliberate"
    if "conviction" in defining:
        guidance["emphasis_style"] = "strong"
        guidance["energy"] = "passionate"

    # Current demeanor is most audible
    current = " ".join(emotional_layers.get("current", []))
    if "contemplative" in current:
        guidance["pacing"] = "unhurried"
        guidance["pauses"] = "reflective"
    if "warmth" in current:
        guidance["resonance"] = "warm_chest"
        guidance["breathiness"] = "slight"
    if "sardonic" in current:
        guidance["pitch_variation"] = "ironic"
        guidance["emphasis_style"] = "wry"

    # Explicit emotions override
    if "Hopeful" in emotions:
        guidance["energy"] = "lifted"
    if "Weathered" in emotions:
        guidance["resonance"] = "weathered"
    if "Fierce" in emotions:
        guidance["energy"] = "intense"
        guidance["emphasis_style"] = "controlled_power"

    # Apply cultural emotional norms (from research)
    if cultural_norm:
        norm_key = cultural_norm.lower().replace(" ", "_").replace("-", "_")
        for key, norm_data in CULTURAL_EMOTIONAL_NORMS.items():
            if key in norm_key or norm_key in key:
                guidance.update(norm_data.get("tts_impact", {}))
                guidance["cultural_suppression_level"] = norm_data.get("suppression_level", 0.5)
                break

    # Apply suppression level (research-backed acoustic markers)
    if suppression_level:
        if "highly" in suppression_level.lower():
            guidance["pitch_variation"] = "minimal"
            guidance["f0_variability"] = "low"
            guidance["microstructure_leakage"] = True
            guidance["jitter"] = "elevated"
            guidance["pauses"] = "extended"
        elif "moderate" in suppression_level.lower():
            guidance["pitch_variation"] = "controlled"
            guidance["microstructure_leakage"] = True
            guidance["jitter"] = "slight"
        elif "contextual" in suppression_level.lower():
            guidance["pitch_variation"] = "variable"

    # Apply recent impactful event
    if recent_event:
        if "loss" in recent_event.lower() or "grief" in recent_event.lower():
            guidance["f0_variability"] = "elevated"
            guidance["voice_quality_hnr"] = "low"
            guidance["pauses"] = "avoidant_long"
            guidance["breathiness"] = "tight"
        elif "achievement" in recent_event.lower():
            guidance["energy"] = "confident"
            guidance["resonance"] = "forward"
        elif "health" in recent_event.lower():
            guidance["breathiness"] = "slight"
            guidance["pacing"] = "measured"
            guidance["energy"] = "subdued"
        elif "betrayal" in recent_event.lower() or "conflict" in recent_event.lower():
            guidance["energy"] = "controlled_tension"
            guidance["pitch_variation"] = "guarded"
            guidance["jitter"] = "slight"

    # Apply age-related voice quality
    if current_age:
        if "elder" in current_age.lower() or "65+" in current_age:
            guidance["resonance"] = "mellowed"
            guidance["pacing"] = "unhurried"
            guidance["breathiness"] = "natural_age"
            guidance["f0_variability"] = "reduced"
        elif "mature" in current_age.lower():
            guidance["resonance"] = "full_chest"
            guidance["pacing"] = "deliberate"
        elif "young" in current_age.lower():
            guidance["energy"] = "lifted"
            guidance["pacing"] = "slightly_quick"

    return guidance
