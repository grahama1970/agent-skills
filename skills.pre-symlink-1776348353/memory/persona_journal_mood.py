"""
Persona Journal - Mood State Module

Constants, time helpers, mood calculation, and intensity scoring.
"""

import random
from datetime import datetime
from typing import Any, Dict, List

# Mood constants
MOOD_STATES = [
    "energized", "contemplative", "frustrated", "satisfied",
    "curious", "weary", "playful", "focused", "melancholic",
    "anxious", "hopeful", "restless"
]

ENERGY_LEVELS = ["low", "moderate", "high", "depleted", "surging"]

# Time-based mood modifiers
TIME_MOOD_MODIFIERS = {
    "early_morning": {"energy": -1, "mood_bias": ["weary", "contemplative"]},
    "morning": {"energy": 1, "mood_bias": ["energized", "hopeful"]},
    "midday": {"energy": 0, "mood_bias": ["focused", "satisfied"]},
    "afternoon": {"energy": -1, "mood_bias": ["weary", "restless"]},
    "evening": {"energy": 0, "mood_bias": ["contemplative", "satisfied"]},
    "late_night": {"energy": -2, "mood_bias": ["melancholic", "contemplative", "restless"]},
}

# Day of week modifiers
DAY_MOOD_MODIFIERS = {
    0: {"mood_bias": ["anxious", "focused"], "label": "Monday"},  # Monday
    1: {"mood_bias": ["focused", "restless"], "label": "Tuesday"},
    2: {"mood_bias": ["focused", "weary"], "label": "Wednesday"},
    3: {"mood_bias": ["hopeful", "energized"], "label": "Thursday"},
    4: {"mood_bias": ["playful", "satisfied"], "label": "Friday"},
    5: {"mood_bias": ["playful", "contemplative"], "label": "Saturday"},
    6: {"mood_bias": ["melancholic", "contemplative"], "label": "Sunday"},
}

# Season modifiers (Northern Hemisphere default)
SEASON_MODIFIERS = {
    "winter": {"energy": -1, "mood_bias": ["melancholic", "contemplative", "weary"]},
    "spring": {"energy": 1, "mood_bias": ["hopeful", "energized", "curious"]},
    "summer": {"energy": 1, "mood_bias": ["playful", "energized", "satisfied"]},
    "fall": {"energy": 0, "mood_bias": ["contemplative", "melancholic", "focused"]},
}


def get_current_season() -> str:
    """Determine current season based on month."""
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "winter"
    elif month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    else:
        return "fall"


def get_time_period() -> str:
    """Get current time period label."""
    hour = datetime.now().hour
    if 5 <= hour < 8:
        return "early_morning"
    elif 8 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "midday"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    else:
        return "late_night"


def calculate_mood_state(
    persona: Dict[str, Any],
    episodes: List[Dict[str, Any]],
    recent_journals: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate current mood state based on multiple factors."""

    # Base energy level
    base_energy = 3  # Out of 5

    # Time modifiers
    time_period = get_time_period()
    time_mod = TIME_MOOD_MODIFIERS.get(time_period, {"energy": 0, "mood_bias": []})

    # Day of week modifiers
    day_of_week = datetime.now().weekday()
    day_mod = DAY_MOOD_MODIFIERS.get(day_of_week, {"mood_bias": [], "label": "Unknown"})

    # Season modifiers
    season = get_current_season()
    season_mod = SEASON_MODIFIERS.get(season, {"energy": 0, "mood_bias": []})

    # Calculate energy
    energy = base_energy + time_mod.get("energy", 0) + season_mod.get("energy", 0)

    # Adjust based on interaction outcomes
    satisfying_count = 0
    frustrating_count = 0

    for ep in episodes:
        category = ep.get("category", "").lower()
        if category in ["solution", "success"]:
            satisfying_count += 1
        elif category in ["error", "failure"]:
            frustrating_count += 1

    # Frustration accumulates
    if frustrating_count > satisfying_count:
        energy -= 1

    # Check recent journal mood for continuity
    mood_history = []
    for journal in recent_journals:
        if "mood" in journal:
            mood_history.append(journal["mood"])

    # Combine mood biases
    mood_candidates = (
        time_mod.get("mood_bias", []) +
        day_mod.get("mood_bias", []) +
        season_mod.get("mood_bias", [])
    )

    # Add frustration/satisfaction based moods
    if frustrating_count > 2:
        mood_candidates.extend(["frustrated", "weary", "anxious"])
    elif satisfying_count > 2:
        mood_candidates.extend(["satisfied", "energized", "hopeful"])

    # Pick mood (weighted by frequency in candidates)
    if mood_candidates:
        mood = random.choice(mood_candidates)
    else:
        mood = random.choice(MOOD_STATES)

    # Clamp energy
    energy = max(1, min(5, energy))
    energy_label = ENERGY_LEVELS[min(energy - 1, len(ENERGY_LEVELS) - 1)]

    return {
        "mood": mood,
        "energy": energy,
        "energy_label": energy_label,
        "time_period": time_period,
        "day_of_week": day_mod.get("label", "Unknown"),
        "season": season,
        "satisfying_interactions": satisfying_count,
        "frustrating_interactions": frustrating_count,
        "mood_continuity": mood_history[:3] if mood_history else [],
    }


def calculate_intensity(mood_state: Dict[str, Any], episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate emotional intensity for taxonomy tagging.

    Intensity affects how strongly the journal influences future responses.
    High intensity = more impact on persona's mood coloring.
    """

    base_intensity = 0.5

    # Frustration/satisfaction ratio affects intensity
    frustrating = mood_state.get("frustrating_interactions", 0)
    satisfying = mood_state.get("satisfying_interactions", 0)

    if frustrating > 3:
        base_intensity += 0.3
    elif frustrating > satisfying + 2:
        base_intensity += 0.2

    if satisfying > 3:
        base_intensity += 0.2

    # Mood extremes increase intensity
    high_intensity_moods = ["frustrated", "anxious", "energized", "melancholic"]
    low_intensity_moods = ["contemplative", "weary", "satisfied"]

    mood = mood_state.get("mood", "neutral")
    if mood in high_intensity_moods:
        base_intensity += 0.2
    elif mood in low_intensity_moods:
        base_intensity -= 0.1

    # Energy level affects intensity
    energy = mood_state.get("energy", 3)
    if energy >= 4:
        base_intensity += 0.1
    elif energy <= 2:
        base_intensity -= 0.1

    # Clamp to 0.1 - 1.0
    intensity = max(0.1, min(1.0, base_intensity))

    # Categorize
    if intensity >= 0.8:
        intensity_label = "high"
        thematic_weight = "Critical" if frustrating > satisfying else "Emotion"
    elif intensity >= 0.5:
        intensity_label = "moderate"
        thematic_weight = "Stress" if frustrating > 0 else "Cognition"
    else:
        intensity_label = "low"
        thematic_weight = "Cooperation" if satisfying > 0 else "Emotion"

    return {
        "intensity": intensity,
        "intensity_label": intensity_label,
        "thematic_weight": thematic_weight,
    }
