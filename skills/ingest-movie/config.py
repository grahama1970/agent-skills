"""
Movie Ingest Skill - Configuration
Constants, emotion mappings, paths, and environment configuration.
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------
NZB_API_KEY = os.environ.get("NZBD_GEEK_API_KEY") or os.environ.get("NZB_GEEK_API_KEY")
NZB_BASE_URL = (
    os.environ.get("NZBD_GEEK_BASE_URL")
    or os.environ.get("NZB_GEEK_BASE_URL")
    or "https://api.nzbgeek.info/"
)
WHISPER_BIN = os.environ.get("WHISPER_BIN", os.path.expanduser("~/.local/bin/whisper"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

# Audio intensity tagging thresholds (override via env)
RMS_THRESHOLD = float(os.environ.get("AUDIO_RMS_THRESHOLD", "0.2"))
RMS_WINDOW_SEC = float(os.environ.get("AUDIO_RMS_WINDOW_SEC", "0.5"))

# Radarr configuration
RADARR_URL = os.environ.get("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent
CLIPS_DIR = SKILL_DIR / "clips"
INVENTORY_FILE = SKILL_DIR / "inventory.json"
INVENTORY_LOCK_FILE = SKILL_DIR / ".inventory.lock"
DOGPILE_DIR = SKILL_DIR.parent / "dogpile"

# Media library paths (default, override with CLI args)
DEFAULT_MOVIE_LIBRARY = Path("/mnt/storage12tb/media/movies")
DEFAULT_TV_LIBRARY = Path("/mnt/storage12tb/media/tv")

# -----------------------------------------------------------------------------
# Subtitle Keywords
# -----------------------------------------------------------------------------
SUBTITLE_HINT_KEYWORDS = (" subs", "subbed", "subtitle", "subtitles", ".srt", "cc", "sdh", "caption")

# -----------------------------------------------------------------------------
# Cue Keywords - Maps subtitle stage directions to tags
# -----------------------------------------------------------------------------
CUE_KEYWORDS = {
    # Camaraderie indicators (Stilgar model)
    "laugh": "laugh",
    "laughs": "laugh",
    "chuckle": "laugh",
    "giggle": "laugh",
    "snicker": "laugh",
    # Sorrow indicators (Katsumoto model)
    "sob": "cry",
    "sobbing": "cry",
    "cry": "cry",
    "crying": "cry",
    "weep": "cry",
    "weeping": "cry",
    "mourn": "cry",
    "mourning": "cry",
    "grief": "cry",
    "sigh": "sigh",
    "sighing": "sigh",
    "breath": "breath",
    "breathing": "breath",
    "whisper": "whisper",
    "whispering": "whisper",
    # Anger indicators (Pacino model)
    "scream": "shout",
    "screaming": "shout",
    "shout": "shout",
    "shouting": "shout",
    "yell": "shout",
    "yelling": "shout",
    "angry": "anger",
    "anger": "anger",
    # Rage indicators (DDL model)
    "rage": "rage",
    "raging": "rage",
    "fury": "rage",
    "furious": "rage",
    "snarl": "rage",
    "snarling": "rage",
    "growl": "rage",
    "growling": "rage",
}

# Valid inputs for CLI validation
VALID_TAGS = set(CUE_KEYWORDS.values())  # Valid tag outputs (laugh, cry, shout, etc.)

# Horus ToM emotions aligned with PersonaPlex actor models
VALID_EMOTIONS = {
    "rage",        # Daniel Plainview - manic precision, mockery
    "anger",       # Michael Corleone - cold intensity, calculated fury
    "sorrow",      # Katsumoto/Maximus - stoic honor, duty-bound loss
    "regret",      # George Carlin - cynical deconstruction, strategic error
    "camaraderie", # Stilgar - fierce tribal loyalty, warrior bond
    "command",     # Pre-corruption Horus - affable warrior, inspiring leadership
}

# -----------------------------------------------------------------------------
# Emotion-Tag Mappings
# -----------------------------------------------------------------------------
EMOTION_TAG_MAP = {
    # Maps emotions to the subtitle tags that indicate them
    "rage": {"rage", "rage_candidate", "anger_candidate", "shout"},
    "anger": {"anger", "anger_candidate", "shout"},
    "sorrow": {"cry", "sob", "sigh", "whisper", "whisper_candidate", "breath"},
    "regret": {"sigh"},  # Regret often explicit in dialogue, not cues
    "camaraderie": {"laugh"},  # Shared laughter indicates bond
}

TAG_TO_EMOTION = {
    # Rage - explosive fury (DDL model)
    "rage": "rage",
    "rage_candidate": "rage",
    # Anger - cold calculated (Pacino model)
    "anger": "anger",
    "anger_candidate": "anger",
    "shout": "anger",
    # Sorrow - stoic loss (Katsumoto model)
    "cry": "sorrow",
    "sob": "sorrow",
    "sigh": "sorrow",
    "whisper": "sorrow",  # Quiet grief
    "whisper_candidate": "sorrow",
    "breath": "sorrow",  # Heavy breathing from grief
    # Regret - cynical reflection (Carlin model)
    # Note: regret is detected via explicit --emotion flag or text analysis
    # Camaraderie - warrior bond (Stilgar model)
    "laugh": "camaraderie",  # Shared laughter = bond
}

# -----------------------------------------------------------------------------
# ToM/BDI: Emotional dimensions for Horus persona training
# Based on Russell's Circumplex Model (valence, arousal) + dominance
# -----------------------------------------------------------------------------
EMOTION_DIMENSIONS: Dict[str, Dict[str, float]] = {
    # Daniel Plainview - manic precision, competitive fury, mockery
    "rage": {"valence": -0.9, "arousal": 1.0, "dominance": 0.95},
    # Michael Corleone - cold intensity, deadly quiet, calculated fury
    "anger": {"valence": -0.7, "arousal": 0.6, "dominance": 0.85},
    # Katsumoto/Maximus/Tywin - stoic honor, weary dignity, duty-bound loss
    "sorrow": {"valence": -0.8, "arousal": 0.3, "dominance": 0.4},
    # George Carlin - cynical deconstruction of strategic error
    "regret": {"valence": -0.5, "arousal": 0.4, "dominance": 0.3},
    # Stilgar - fierce tribal loyalty, warrior bond, protective fury
    "camaraderie": {"valence": 0.6, "arousal": 0.7, "dominance": 0.6},
    # Pre-corruption Horus - affable warrior, inspiring leadership, personable
    "command": {"valence": 0.7, "arousal": 0.6, "dominance": 0.9},
}

# -----------------------------------------------------------------------------
# ToM/BDI: Archetype mapping for Horus lore transfer
# Maps movie emotions to Horus psychological archetypes
# -----------------------------------------------------------------------------
HORUS_ARCHETYPE_MAP: Dict[str, Dict[str, Any]] = {
    "rage": {
        "primary_archetype": "betrayal_fury",
        "actor_model": "Daniel Day-Lewis (Daniel Plainview)",
        "trauma_equivalent": "sanguinius",  # Brother-related trauma
        "belief_pattern": "perceived_betrayal_by_trusted_figure",
        "desire_pattern": "destroy_source_of_betrayal",
        "intention_pattern": "explosive_confrontation",
        "voice_tone": "manic_precision",
        "personaplex_voice": "horus_traumatized.pt",
        "personaplex_fallback": "horus_resentful.pt",
        "rhythm_target": {"wpm_range": [100, 180], "pause_pattern": "staccato"},
    },
    "anger": {
        "primary_archetype": "cold_wrath",
        "actor_model": "Al Pacino (Michael Corleone)",
        "trauma_equivalent": "emperor",  # Authority-related
        "belief_pattern": "injustice_demands_calculated_response",
        "desire_pattern": "assert_dominance_through_control",
        "intention_pattern": "deadly_quiet_correction",
        "voice_tone": "cold_intensity",
        "personaplex_voice": "horus_authoritative.pt",
        "personaplex_fallback": "horus_contemptuous.pt",
        "rhythm_target": {"wpm_range": [80, 120], "pause_pattern": "deliberate"},
    },
    "sorrow": {
        "primary_archetype": "stoic_grief",
        "actor_model": "Ken Watanabe (Katsumoto) / Russell Crowe (Maximus)",
        "trauma_equivalent": "sanguinius",  # Loss of beloved brother
        "belief_pattern": "duty_transcends_personal_pain",
        "desire_pattern": "honor_the_fallen_through_action",
        "intention_pattern": "dignified_acceptance",
        "voice_tone": "weary_dignity",
        "personaplex_voice": "horus_weary.pt",
        "personaplex_fallback": "horus_anguished.pt",
        "rhythm_target": {"wpm_range": [60, 100], "pause_pattern": "heavy_pauses"},
    },
    "regret": {
        "primary_archetype": "cynical_reflection",
        "actor_model": "George Carlin",
        "trauma_equivalent": "davin",  # Corruption-related mistake
        "belief_pattern": "strategic_error_cannot_be_undone",
        "desire_pattern": "deconstruct_failure_with_bitter_clarity",
        "intention_pattern": "sardonic_self_criticism",
        "voice_tone": "cynical_deconstruction",
        "personaplex_voice": "horus_contemptuous.pt",
        "personaplex_fallback": "horus_tactical.pt",
        "rhythm_target": {"wpm_range": [120, 160], "pause_pattern": "comedic_timing"},
    },
    "camaraderie": {
        "primary_archetype": "warrior_bond",
        "actor_model": "Javier Bardem (Stilgar)",
        "trauma_equivalent": None,  # Positive emotion, healing
        "belief_pattern": "brothers_stand_together",
        "desire_pattern": "protect_and_elevate_trusted_allies",
        "intention_pattern": "fierce_loyalty_declaration",
        "voice_tone": "tribal_intensity",
        "personaplex_voice": "horus_protective.pt",
        "personaplex_fallback": "horus_authoritative.pt",
        "rhythm_target": {"wpm_range": [90, 130], "pause_pattern": "emphatic"},
    },
    "command": {
        "primary_archetype": "affable_commander",
        "actor_model": "Gerard Butler (Leonidas) / Russell Crowe (Maximus)",
        "trauma_equivalent": None,  # Pre-corruption, positive leadership
        "belief_pattern": "lead_from_front_with_warmth",
        "desire_pattern": "inspire_through_example_and_presence",
        "intention_pattern": "charismatic_rallying_call",
        "voice_tone": "warm_authority",
        "personaplex_voice": "horus_authoritative.pt",
        "personaplex_fallback": "horus_protective.pt",
        "rhythm_target": {"wpm_range": [100, 140], "pause_pattern": "inspiring"},
    },
}

# -----------------------------------------------------------------------------
# Curated emotion-movie mappings (from dogpile research)
# -----------------------------------------------------------------------------
EMOTION_MOVIE_MAPPINGS: Dict[str, list[Dict[str, Any]]] = {
    "rage": [
        {"title": "There Will Be Blood", "year": 2007, "scenes": ["I drink your milkshake", "Bowling alley finale"]},
        {"title": "Sicario", "year": 2015, "scenes": ["Border crossing", "Tunnel assault"]},
        {"title": "No Country for Old Men", "year": 2007, "scenes": ["Coin toss", "Hotel confrontation"]},
    ],
    "anger": [
        {"title": "The Godfather", "year": 1972, "scenes": ["Baptism montage", "Horse head"]},
        {"title": "Heat", "year": 1995, "scenes": ["Bank heist", "Coffee shop"]},
        {"title": "Apocalypse Now", "year": 1979, "scenes": ["Kurtz monologue", "Indy 500 speech"]},
    ],
    "sorrow": [
        {"title": "Gladiator", "year": 2000, "scenes": ["My name is Maximus", "Elysium ending"]},
        {"title": "The Last Samurai", "year": 2003, "scenes": ["Final battle", "Cherry blossoms"]},
        {"title": "Schindler's List", "year": 1993, "scenes": ["I could have done more", "Ring scene"]},
    ],
    "regret": [
        {"title": "Full Metal Jacket", "year": 1987, "scenes": ["Gunnery Hartman", "Sniper scene"]},
    ],
    "camaraderie": [
        {"title": "Dune", "year": 2021, "scenes": ["Stilgar introduction", "Fremen camp"]},
        {"title": "Dune: Part Two", "year": 2024, "scenes": ["Water ceremony", "Sietch bonding"]},
        {"title": "Band of Brothers", "year": 2001, "scenes": ["Easy Company", "Bastogne"]},
        {"title": "Saving Private Ryan", "year": 1998, "scenes": ["Omaha Beach", "Final stand"]},
        {"title": "Fury", "year": 2014, "scenes": ["Tank crew bonding", "Final battle"]},
    ],
    "command": [
        {"title": "300", "year": 2006, "scenes": ["This is Sparta", "Tonight we dine in hell"]},
        {"title": "Gladiator", "year": 2000, "scenes": ["Opening battle", "At my signal"]},
        {"title": "Troy", "year": 2004, "scenes": ["Beach landing", "Achilles rallies Myrmidons"]},
    ],
}

# -----------------------------------------------------------------------------
# Radarr Horus TTS Preset
# -----------------------------------------------------------------------------
RADARR_HORUS_PRESET = {
    "name": "Horus TTS",
    "description": "1080p max, 15GB limit, English audio, SDH subtitles preferred",
    "quality_profile": {
        "enabled_qualities": ["Bluray-1080p", "WEB 1080p", "HDTV-1080p"],
        "disabled_qualities": ["Bluray-2160p", "WEB 2160p", "HDTV-2160p", "Raw-HD", "BR-DISK"],
        "max_size_mb": 15000,  # 15GB max
    },
    "custom_formats": {
        "SDH Subtitles": {
            "conditions": ["SDH", "CC", "Subs"],
            "score": 100,
        },
        "English Audio": {
            "conditions": ["English", "ENG"],
            "score": 50,
        },
    },
    "language": "English",
    "monitor": "movieOnly",
}


def validate_env(console) -> None:
    """Validate environment configuration and print warnings."""
    if os.environ.get("NZBD_GEEK_API_KEY") and not os.environ.get("NZB_GEEK_API_KEY"):
        console.print("[yellow]Note: prefer NZB_GEEK_API_KEY (without the extra 'D').[/yellow]")
    if not NZB_API_KEY:
        console.print(
            "[yellow]Warning: NZB_GEEK_API_KEY not set. NZB search will fail.[/yellow]"
        )
    # Validate base URL
    try:
        parsed = urlparse(NZB_BASE_URL)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            console.print("[yellow]Invalid NZB_BASE_URL; expected http(s) URL.[/yellow]")
    except Exception:
        console.print("[yellow]Invalid NZB_BASE_URL; parsing failed.[/yellow]")
    # Validate binaries existence (non-fatal warnings)
    if not shutil.which("ffmpeg"):
        console.print("[yellow]ffmpeg not found; clipping will fail.[/yellow]")
    if not shutil.which("whisper"):
        console.print("[yellow]whisper not found; transcription will fail.[/yellow]")
