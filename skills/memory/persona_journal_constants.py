#!/usr/bin/env python3
"""
Persona Journal constants and time/season helper functions.

Defines mood states, energy levels, time-based modifiers, day-of-week
modifiers, and seasonal modifiers used by the journal generation pipeline.
"""

from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SKILLS_DIR.parent

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
