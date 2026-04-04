"""Interview result processing for voice design."""

from design_constants import ACCENT_DATABASE, SUPPRESSION_INDICATORS
from design_guidance import generate_tts_guidance


def process_interview_results(persona: str, responses: dict) -> dict:
    """Process interview responses into voice design spec.

    Uses research-backed understanding of:
    - Trauma/suppression vocal biomarkers (F0 variability, jitter, pitch breaks)
    - Cultural emotional display norms (Stoic vs Victorian vs Buddhist)
    - Family structure effects on emotional development
    - Religious context and expression norms
    - Age-at-event correlation for layered emotional texture
    """
    r = responses.get("responses", {})

    # Age-correlated event processing
    formative = r.get("formative_events", [])  # Youth: deep, often unconscious
    prime = r.get("prime_events", [])          # Prime: defining, conscious
    late = r.get("late_events", [])            # Later: wisdom, acceptance

    # Build layered emotional profile
    emotional_layers = {
        "foundational": [],  # From youth - always present
        "defining": [],      # From prime - conscious identity
        "current": [],       # From late life - present demeanor
    }

    # Youth events become foundational voice texture
    if "Loss of parent/family" in formative:
        emotional_layers["foundational"].append("underlying grief, guarded vulnerability")
    if "War witnessed young" in formative:
        emotional_layers["foundational"].append("hypervigilance, controlled intensity")
    if "Poverty/hardship" in formative:
        emotional_layers["foundational"].append("scrappy determination, no-nonsense")
    if "Privileged education" in formative:
        emotional_layers["foundational"].append("confident articulation")
    if "Displacement/migration" in formative:
        emotional_layers["foundational"].append("adaptive, slightly guarded")

    # Prime years define conscious voice identity
    if "War/Conflict" in prime:
        emotional_layers["defining"].append("urgency, weathered quality")
    if "Revolution/Upheaval" in prime:
        emotional_layers["defining"].append("conviction, hopeful intensity")
    if "Loss of loved one" in prime:
        emotional_layers["defining"].append("depth of feeling, gravitas")
    if "Political Power" in prime:
        emotional_layers["defining"].append("authority, measured weight")

    # Late life adds current demeanor
    if "Reflection/Writing" in late:
        emotional_layers["current"].append("contemplative, unhurried")
    if "Tragedy/Loss" in late:
        emotional_layers["current"].append("profound acceptance")
    if "Teaching/Mentoring" in late:
        emotional_layers["current"].append("patient warmth")
    if "Bitterness/Regret" in late:
        emotional_layers["current"].append("sardonic edge")

    # Family structure effects (research: shapes attachment and expression)
    family = r.get("family_structure", [])
    if isinstance(family, list):
        if "Orphaned early" in family:
            emotional_layers["foundational"].append("self-reliant, guarded attachment")
        if "Eldest child" in family:
            emotional_layers["foundational"].append("responsibility, leadership weight")
        if "Only child" in family:
            emotional_layers["foundational"].append("self-sufficient, articulate")
        if "Unstable/fractured family" in family:
            emotional_layers["foundational"].append("adaptable, trust caution")

    # Religious context (affects emotional expression norms)
    religion = r.get("religion", "")
    religiosity = r.get("religiosity_level", "")
    religious_voice_impact = ""

    if "Buddhist" in religion or "Eastern" in religion:
        religious_voice_impact = "equanimity, non-attachment"
        emotional_layers["defining"].append("centered stillness")
    elif "Stoic" in religion:
        religious_voice_impact = "philosophical acceptance, self-mastery"
        emotional_layers["defining"].append("controlled dignity")
    elif "Devout Christian" in religion and "Devout" in religiosity:
        religious_voice_impact = "conviction, hope, moral weight"
        emotional_layers["defining"].append("righteous certainty")
    elif "Jewish" in religion:
        religious_voice_impact = "questioning, scholarly, argumentative tradition"
        emotional_layers["defining"].append("intellectual probing")

    # Get new fields
    cultural_norm = r.get("cultural_emotional_norms", "")
    suppression_level = r.get("suppression_level", "")
    current_age = r.get("current_persona_age", "")
    recent_event = r.get("recent_impactful_event", "")

    # Apply recent event to current layer
    if recent_event and recent_event != "None significant":
        if "loss" in recent_event.lower() or "grief" in recent_event.lower():
            emotional_layers["current"].append("fresh grief, raw vulnerability")
        elif "achievement" in recent_event.lower():
            emotional_layers["current"].append("satisfaction, confident energy")
        elif "health" in recent_event.lower():
            emotional_layers["current"].append("mortality awareness, measured presence")
        elif "betrayal" in recent_event.lower() or "conflict" in recent_event.lower():
            emotional_layers["current"].append("guarded wariness, controlled anger")
        elif "awakening" in recent_event.lower():
            emotional_layers["current"].append("transformed clarity, inner peace")

    # Map responses to voice design
    design = {
        "persona": persona,
        "voice_design": {
            "geographic_origin": r.get("geographic_origin", "Unknown"),
            "time_period": r.get("time_period", "Unknown"),
            "lifespan": r.get("birth_death_years", "Unknown"),
            "social_class": r.get("social_class", "Unknown"),
            "personality": r.get("personality", []),
            "modern_reference": r.get("modern_reference", []),
            "life_events": {
                "formative_youth": formative,
                "defining_prime": prime,
                "later_years": late,
            },
            "emotional_layers": emotional_layers,
            "emotional_undertones": r.get("emotional_coloring", []),
            # New fields from research
            "family_structure": family,
            "religion": {
                "tradition": religion,
                "religiosity": religiosity,
                "voice_impact": religious_voice_impact,
            },
            "cultural_emotional_norms": cultural_norm,
            "suppression_level": suppression_level,
            "current_age": current_age,
            "recent_impactful_event": recent_event,
        },
    }

    # Infer accent from geographic origin
    origin = r.get("geographic_origin", "")
    for key, accent in ACCENT_DATABASE.items():
        if accent["region"].lower() in origin.lower():
            design["voice_design"]["inferred_accent"] = key
            design["voice_design"]["accent_characteristics"] = accent["characteristics"]
            design["voice_design"]["suggested_references"] = accent["modern_reference"]
            break

    # Generate register map from personality
    personalities = r.get("personality", [])
    registers = {"default": "neutral"}

    if "Authoritative" in personalities:
        registers["default"] = "commanding"
    if "Warm/Avuncular" in personalities:
        registers["friendly"] = "warm"
    if "Witty/Playful" in personalities:
        registers["joking"] = "light"
    if "Stoic/Measured" in personalities:
        registers["serious"] = "grave"

    design["voice_design"]["register_map"] = registers

    # Generate voice coloring description from emotional layers
    coloring_parts = []

    if emotional_layers["foundational"]:
        coloring_parts.append(f"Foundation: {', '.join(emotional_layers['foundational'][:2])}")

    if emotional_layers["defining"]:
        coloring_parts.append(f"Core: {', '.join(emotional_layers['defining'][:2])}")

    if emotional_layers["current"]:
        coloring_parts.append(f"Present: {', '.join(emotional_layers['current'][:2])}")

    emotions = r.get("emotional_coloring", [])
    if emotions:
        coloring_parts.append(f"Undertones: {', '.join(emotions[:3])}")

    design["voice_design"]["voice_coloring"] = " | ".join(coloring_parts) if coloring_parts else "Neutral"

    # Generate voice guidance for TTS with research-backed parameters
    design["voice_design"]["tts_guidance"] = generate_tts_guidance(
        emotional_layers=emotional_layers,
        emotions=emotions,
        cultural_norm=cultural_norm,
        suppression_level=suppression_level,
        recent_event=recent_event,
        current_age=current_age,
    )

    # Add suppression detection notes (from research)
    if suppression_level and "highly" in suppression_level.lower():
        design["voice_design"]["suppression_notes"] = {
            "detection": "High suppression - expect microstructural leakage",
            "markers": SUPPRESSION_INDICATORS["acoustic_markers"],
            "defense_mechanism": "likely repression or intellectualization",
            "tts_recommendation": "Use monotonic base with subtle 50-150ms pitch breaks",
        }

    return design
