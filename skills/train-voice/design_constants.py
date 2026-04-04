"""Research-backed vocal biomarker constants and accent databases for voice design."""

# =============================================================================
# RESEARCH-BACKED VOCAL BIOMARKERS
# From dogpile research on trauma, suppression, and grief expression
# =============================================================================

SUPPRESSION_INDICATORS = {
    "acoustic_markers": {
        "f0_variability": ">0.25 (vs ~0.15 baseline) - autonomic dysregulation",
        "jitter": "2.5-3.5% (normal <1%) - laryngeal instability from chronic tension",
        "extended_pauses": ">1000ms before trauma-related content - avoidance",
        "spectral_leakage": "high frequencies >4kHz during suppression efforts",
        "pitch_breaks": "50-150ms during deliberately flat delivery",
        "tremor": "8-12 Hz oscillations in pitch contour",
    },
    "defense_mechanisms": {
        "repression": {
            "acoustic": "Monotonic delivery, F0 range <30 Hz, extended pre-topic pauses",
            "tts_guidance": {"pitch_variation": "minimal", "pauses": "extended", "energy": "flat"},
        },
        "denial": {
            "acoustic": "Incongruent cheerfulness, rapid speech through difficult content",
            "tts_guidance": {"energy": "artificially_bright", "pacing": "rushed"},
        },
        "intellectualization": {
            "acoustic": "Lecture voice - steady, controlled, reduced affective variation",
            "tts_guidance": {"pitch_variation": "low", "pacing": "measured", "resonance": "head"},
        },
        "dissociation": {
            "acoustic": "Flat affect, breathy/hollow quality, 'disconnected' prosody",
            "tts_guidance": {"breathiness": "hollow", "energy": "detached", "resonance": "thin"},
        },
    },
}

GRIEF_PROCESSING_MARKERS = {
    "unprocessed": {
        "f0_elevation": "+15-40 Hz above baseline",
        "f0_variability": "bimodal extremes",
        "jitter": ">2.5%",
        "hnr": "<15 dB (voice quality)",
        "pauses": ">1000ms (avoidant)",
        "tts_guidance": {
            "pitch_variation": "erratic",
            "energy": "unstable",
            "pauses": "avoidant_long",
            "breathiness": "tight",
        },
    },
    "processed": {
        "f0_elevation": "normalized to baseline",
        "f0_variability": "moderate, contextual",
        "jitter": "<1.5%",
        "hnr": ">20 dB",
        "pauses": "200-600ms (reflective)",
        "tts_guidance": {
            "pitch_variation": "moderate",
            "energy": "stable",
            "pauses": "reflective",
            "breathiness": "natural",
        },
    },
}

# Cultural emotional display norms
CULTURAL_EMOTIONAL_NORMS = {
    "greco_roman_stoic": {
        "display_rules": "Controlled public expression, philosophical detachment",
        "grief_norms": "Public mourning rituals, private suffering",
        "suppression_level": 0.7,  # 0=free, 1=total suppression
        "tts_impact": {"energy": "controlled", "pitch_variation": "deliberate", "pauses": "rhetorical"},
    },
    "victorian_english": {
        "display_rules": "Stiff upper lip, restraint as virtue",
        "grief_norms": "Elaborate mourning customs but emotional restraint",
        "suppression_level": 0.9,
        "tts_impact": {"energy": "restrained", "pitch_variation": "minimal", "breathiness": "tight"},
    },
    "buddhist_equanimity": {
        "display_rules": "Equanimity, non-attachment to emotion",
        "grief_norms": "Acceptance, impermanence focus",
        "suppression_level": 0.5,  # Not suppression but transcendence
        "tts_impact": {"energy": "centered", "pitch_variation": "gentle", "pauses": "mindful"},
    },
    "mediterranean_expressive": {
        "display_rules": "Open emotional expression valued",
        "grief_norms": "Public mourning, wailing, communal grief",
        "suppression_level": 0.2,
        "tts_impact": {"energy": "dynamic", "pitch_variation": "wide", "pauses": "dramatic"},
    },
    "east_asian_collectivist": {
        "display_rules": "Emotional restraint for group harmony",
        "grief_norms": "Private grief, public composure",
        "suppression_level": 0.75,
        "tts_impact": {"energy": "modulated", "pitch_variation": "subtle", "pauses": "considered"},
    },
}

# Geographic accent database
ACCENT_DATABASE = {
    "boston_colonial": {
        "region": "Boston, Massachusetts",
        "era": "Colonial (1700s)",
        "characteristics": ["Non-rhotic", "Broad A sounds", "Formal cadence"],
        "modern_reference": "JFK recordings, The Witch (2015) film",
    },
    "charleston_southern": {
        "region": "Charleston, South Carolina",
        "era": "Antebellum to Modern",
        "characteristics": ["Soft R's", "Musical vowels", "Measured pace"],
        "modern_reference": "Kevin Spacey (House of Cards)",
    },
    "philadelphia_colonial": {
        "region": "Philadelphia, Pennsylvania",
        "era": "Colonial (1700s)",
        "characteristics": ["Rhotic", "Less formal than Boston", "Quaker influence"],
        "modern_reference": "Period films (1776, John Adams)",
    },
    "london_victorian": {
        "region": "London, England",
        "era": "Victorian (1800s)",
        "characteristics": ["Received Pronunciation", "Formal diction", "Clear enunciation"],
        "modern_reference": "Helena Bonham Carter, Colin Firth",
    },
    "rome_classical": {
        "region": "Rome, Italy",
        "era": "Classical (Ancient)",
        "characteristics": ["Latin influence", "Measured oratory", "Rhetorical pauses"],
        "modern_reference": "Richard Harris (Gladiator), John Hurt",
    },
    "hawaii_modern": {
        "region": "Hawaii",
        "era": "Modern",
        "characteristics": ["Pidgin influence", "Relaxed pace", "Warm tones"],
        "modern_reference": "Local recordings, Hawaii Five-0 cast",
    },
}
