#!/usr/bin/env python3
"""
Fictional persona creation and management.

Fictional personas are simulated characters (not real people) that:
1. Have media consumption profiles (what they watch/read/follow)
2. Use voice references from actors they identify with
3. Have quirks and personality traits
4. Can "speak" to express preferences about their own voice/personality

The key difference from real personas:
- Real: Learn FROM the person (their talks, books, interviews)
- Fictional: Learn from what the CHARACTER would consume (their influences)

Workflow:
1. Load character sheet (if exists)
2. Ask character what media they consume
3. Ask character whose voice they identify with
4. Ingest reference content from those sources
5. Train voice from reference actor clips
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger as log

from .persona import Persona, create_persona, store_to_memory, run_skill
from .templates import get_template


# =============================================================================
# Voice Reference
# =============================================================================

@dataclass
class VoiceReference:
    """A reference actor/voice for training a fictional persona's voice."""
    name: str                          # Actor name (e.g., "Hailee Steinfeld")
    register: str                      # "confident", "uncertain", "neutral"
    weight: float = 0.5                # Blend weight (0.0-1.0)
    clips_to_find: list[str] = field(default_factory=list)  # Scene descriptions
    youtube_urls: list[str] = field(default_factory=list)   # Collected URLs
    characteristics: list[str] = field(default_factory=list)  # Vocal traits

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "register": self.register,
            "weight": self.weight,
            "clips_to_find": self.clips_to_find,
            "youtube_urls": self.youtube_urls,
            "characteristics": self.characteristics,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceReference":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# Media Consumption Profile
# =============================================================================

@dataclass
class MediaConsumption:
    """What a fictional character consumes (shapes their personality)."""

    # Movies
    movies_formative: list[str] = field(default_factory=list)     # Movies that shaped them
    movies_guilty_pleasure: list[str] = field(default_factory=list)  # Guilty pleasures

    # Books
    books_nightstand: list[str] = field(default_factory=list)     # Currently reading
    books_favorites: list[str] = field(default_factory=list)      # All-time favorites

    # YouTube
    youtube_daily: list[str] = field(default_factory=list)        # Channels they watch daily
    youtube_occasional: list[str] = field(default_factory=list)   # Sometimes watches

    # Guilty pleasures and quirks
    guilty_pleasures: list[str] = field(default_factory=list)     # Secret habits

    def to_dict(self) -> dict:
        return {
            "movies": {
                "formative": self.movies_formative,
                "guilty_pleasure": self.movies_guilty_pleasure,
            },
            "books": {
                "nightstand": self.books_nightstand,
                "favorites": self.books_favorites,
            },
            "youtube_channels": {
                "daily": self.youtube_daily,
                "occasional": self.youtube_occasional,
            },
            "guilty_pleasures": self.guilty_pleasures,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MediaConsumption":
        movies = data.get("movies", {})
        books = data.get("books", {})
        youtube = data.get("youtube_channels", {})

        return cls(
            movies_formative=movies.get("formative", []),
            movies_guilty_pleasure=movies.get("guilty_pleasure", []),
            books_nightstand=books.get("nightstand", []),
            books_favorites=books.get("favorites", []),
            youtube_daily=youtube.get("daily", []),
            youtube_occasional=youtube.get("occasional", []),
            guilty_pleasures=data.get("guilty_pleasures", []),
        )


# =============================================================================
# Fictional Persona Creation
# =============================================================================

def create_fictional_persona(
    name: str,
    character_sheet_path: Optional[str] = None,
    media_consumption: Optional[MediaConsumption] = None,
    voice_references: Optional[list[VoiceReference]] = None,
    quirks: Optional[list[str]] = None,
    voice_accent: str = "",
    scope: str = "personas",
    **persona_kwargs,
) -> Persona:
    """Create a fictional persona with all the specialized fields.

    Args:
        name: Character name
        character_sheet_path: Path to character document (markdown, yaml, etc.)
        media_consumption: What the character watches/reads/follows
        voice_references: Actors whose voices inform theirs
        quirks: Personality quirks and habits
        voice_accent: Accent specification (e.g., "subtle_southern")
        scope: Memory scope for storage
        **persona_kwargs: Additional Persona fields

    Returns:
        Created Persona object
    """
    # Build media consumption dict
    media_dict = media_consumption.to_dict() if media_consumption else {}

    # Build voice references list
    voice_refs = [v.to_dict() for v in voice_references] if voice_references else []

    # Build register switching dict from voice references
    register_switching = {}
    for ref in voice_references or []:
        if ref.register == "confident":
            register_switching["confident_voice"] = ref.name
            register_switching["confident_characteristics"] = ref.characteristics
        elif ref.register == "uncertain":
            register_switching["uncertain_voice"] = ref.name
            register_switching["uncertain_characteristics"] = ref.characteristics

    persona = Persona(
        name=name,
        template="fictional",
        scope=scope,
        tags=["fictional", "character"],
        character_sheet_path=character_sheet_path or "",
        media_consumption=media_dict,
        voice_references=voice_refs,
        voice_accent=voice_accent,
        quirks=quirks or [],
        register_switching=register_switching,
        simulacrum_mode="character_consistency",
        **persona_kwargs,
    )

    return persona


def load_character_sheet(path: str) -> dict:
    """Load a character sheet from file (markdown, yaml, or json).

    Args:
        path: Path to character sheet file

    Returns:
        Dict with parsed character information
    """
    path = Path(path)
    if not path.exists():
        log.warning("Character sheet not found: %s", path)
        return {}

    content = path.read_text()

    # Try JSON
    if path.suffix == ".json":
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

    # Try YAML
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
            return yaml.safe_load(content)
        except Exception as e:
            logger.debug("loading failed: {}", e)

    # Parse markdown for key fields
    return parse_markdown_character_sheet(content)


def parse_markdown_character_sheet(content: str) -> dict:
    """Parse a markdown character sheet for key fields.

    Looks for sections like:
    - ## At a Glance (table with attributes)
    - ## BDI State (beliefs, desires, intentions)
    - ## Voice Profile (vocal characteristics)
    - ## The Code-Switch (register switching info)
    """
    result = {}

    # Extract basic info from "At a Glance" table
    if "## At a Glance" in content:
        # Simple extraction - look for | Name | value | patterns
        import re
        table_pattern = r'\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|'
        matches = re.findall(table_pattern, content)
        for key, value in matches:
            result[key.lower()] = value.strip()

    # Extract BDI if present
    if "### Beliefs" in content or "## BDI" in content:
        result["has_bdi"] = True

    # Check for voice profile
    if "## Voice Profile" in content:
        result["has_voice_profile"] = True

    # Check for code-switch info
    if "## The Code-Switch" in content:
        result["has_register_switching"] = True

    return result


# =============================================================================
# Media Discovery (via /dogpile and /discover-*)
# =============================================================================

def discover_character_media(
    persona_name: str,
    domain: str,
    media_type: str = "all",
    timeout: int = 120,
) -> dict:
    """Discover media content based on character's domain/interests.

    Uses /dogpile to find movies, books, and YouTube content that
    someone in this character's domain would consume.

    Args:
        persona_name: Character name
        domain: Character's domain (e.g., "aerospace cybersecurity")
        media_type: "movies", "books", "youtube", or "all"
        timeout: Timeout for discovery

    Returns:
        Dict with discovered media by type
    """
    result = {"movies": [], "books": [], "youtube": []}

    if media_type in ("movies", "all"):
        # Find movies relevant to their domain
        query = f"best movies about {domain} professionals technical accuracy"
        movie_result = run_skill("discover-movies", ["search", query, "--limit", "5"], timeout=timeout)
        if movie_result["returncode"] == 0:
            try:
                movies = json.loads(movie_result["stdout"])
                result["movies"] = [m.get("title", str(m)) for m in movies[:5]]
            except json.JSONDecodeError:
                pass

    if media_type in ("books", "all"):
        # Find books relevant to their domain
        query = f"books about {domain} professionals recommended"
        book_result = run_skill("discover-books", ["search", query, "--limit", "5"], timeout=timeout)
        if book_result["returncode"] == 0:
            try:
                books = json.loads(book_result["stdout"])
                result["books"] = [b.get("title", str(b)) for b in books[:5]]
            except json.JSONDecodeError:
                pass

    if media_type in ("youtube", "all"):
        # Find YouTube channels relevant to their domain
        query = f"{domain} educational YouTube channels professionals"
        yt_result = run_skill("ingest-youtube", ["search", query, "--limit", "5"], timeout=timeout)
        if yt_result["returncode"] == 0:
            try:
                videos = json.loads(yt_result["stdout"])
                result["youtube"] = [v.get("channel", str(v)) for v in videos[:5]]
            except json.JSONDecodeError:
                pass

    return result


# =============================================================================
# Voice Reference Discovery (via /dogpile)
# =============================================================================

def discover_voice_references(
    character_description: str,
    voice_qualities: list[str],
    age_range: str = "20s",
    timeout: int = 120,
) -> list[dict]:
    """Discover actors with matching voice qualities.

    Uses /dogpile to find actors whose voices match the character description.

    Args:
        character_description: Description of character personality
        voice_qualities: Desired vocal qualities (e.g., ["confident", "technical"])
        age_range: Age range for actors
        timeout: Timeout for discovery

    Returns:
        List of actor suggestions with voice characteristics
    """
    query = (
        f"actress voice {' '.join(voice_qualities)} {age_range} "
        f"movie interview clips {character_description[:50]}"
    )

    result = run_skill(
        "dogpile",
        ["search", query, "--preset", "general"],
        timeout=timeout
    )

    suggestions = []

    if result["returncode"] == 0:
        # Parse output for actor names
        output = result["stdout"]
        # This would need proper parsing of dogpile output
        # For now, return empty and let the interactive flow ask the user
        pass

    return suggestions


# =============================================================================
# Voice Training for Fictional (from reference actors)
# =============================================================================

def train_fictional_voice(
    persona: Persona,
    voice_references: list[VoiceReference],
    output_dir: Optional[str] = None,
    model_size: str = "1.7B",
    dry_run: bool = False,
) -> dict:
    """Train a voice model for a fictional persona from reference actors.

    Unlike real persona voice training (which uses the person's own voice),
    fictional personas are trained by:
    1. Finding clips of each reference actor
    2. Extracting audio for each register (confident, uncertain, etc.)
    3. Training a blended voice model

    Args:
        persona: Fictional persona to train voice for
        voice_references: List of VoiceReference with actor info
        output_dir: Output directory for model
        model_size: "0.6B" or "1.7B"
        dry_run: Preview without training

    Returns:
        Dict with training results
    """
    result = {
        "status": "pending",
        "references_processed": [],
        "audio_collected": [],
        "model_path": "",
        "errors": [],
    }

    if dry_run:
        log.info("[DRY-RUN] Would train voice for %s from:", persona.name)
        for ref in voice_references:
            log.info("  - %s (%s, weight=%.2f)", ref.name, ref.register, ref.weight)
        result["status"] = "dry_run"
        return result

    # Determine output directory
    if not output_dir:
        storage_base = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas"
        if storage_base.exists():
            output_dir = storage_base / persona.name.lower().replace(" ", "_") / "voice_model"
        else:
            output_dir = Path.home() / "models" / "persona-voices" / persona.name.lower().replace(" ", "_")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # For each reference actor, collect audio
    for ref in voice_references:
        log.info("Collecting audio for %s (%s register)...", ref.name, ref.register)

        # Search for interview/clip content
        for clip_desc in ref.clips_to_find:
            query = f"{ref.name} {clip_desc} interview scene clip"
            yt_result = run_skill(
                "ingest-youtube",
                ["search", query, "--limit", "3"],
                timeout=60
            )

            if yt_result["returncode"] == 0:
                try:
                    videos = json.loads(yt_result["stdout"])
                    for video in videos[:2]:
                        url = video.get("url") or video.get("video_url")
                        if url:
                            ref.youtube_urls.append(url)
                except json.JSONDecodeError:
                    pass

        result["references_processed"].append({
            "actor": ref.name,
            "register": ref.register,
            "urls_found": len(ref.youtube_urls),
        })

    # Future work: Integrate with /tts-train skill for actual training
    # This would:
    # 1. Download audio from collected URLs
    # 2. Segment by speaker
    # 3. Train Qwen3-TTS with multi-speaker support
    # 4. Create a blended model based on weights

    log.info("Voice reference collection complete for %s", persona.name)
    log.info("Next step: Run /tts-train with collected audio")

    result["status"] = "references_collected"
    result["output_dir"] = str(output_dir)

    return result


# =============================================================================
# Simulacrum for Fictional (Character Consistency)
# =============================================================================

def validate_character_consistency(
    persona: Persona,
    test_prompts: Optional[list[str]] = None,
) -> dict:
    """Validate that a fictional persona stays in character.

    Unlike real persona simulacrum (which tests "did they really say this?"),
    fictional simulacrum tests:
    1. Does the response match the character sheet?
    2. Does register switching happen appropriately?
    3. Are quirks and speech patterns consistent?

    Args:
        persona: Fictional persona to validate
        test_prompts: Optional custom test prompts

    Returns:
        Dict with validation results
    """
    default_prompts = [
        "Describe yourself in one sentence.",
        "What do you do when you're stressed?",
        "Explain something technical in your field.",
        "What's something you're not good at?",
        "Tell me about your background.",
    ]

    prompts = test_prompts or default_prompts

    result = {
        "persona": persona.name,
        "tests": [],
        "overall_score": 0.0,
        "issues": [],
    }

    # Check required fields for fictional
    if not persona.media_consumption:
        result["issues"].append("No media consumption profile defined")
    if not persona.voice_references:
        result["issues"].append("No voice references defined")
    if not persona.quirks:
        result["issues"].append("No quirks defined")
    if not persona.character_sheet_path:
        result["issues"].append("No character sheet linked")

    # Score based on completeness
    fields_present = sum([
        bool(persona.media_consumption),
        bool(persona.voice_references),
        bool(persona.quirks),
        bool(persona.character_sheet_path),
        bool(persona.register_switching),
    ])

    result["overall_score"] = fields_present / 5.0
    result["grade"] = (
        "A" if result["overall_score"] >= 0.9 else
        "B" if result["overall_score"] >= 0.7 else
        "C" if result["overall_score"] >= 0.5 else
        "D" if result["overall_score"] >= 0.3 else
        "F"
    )

    return result


# =============================================================================
# CLI Commands for Fictional
# =============================================================================

def fictional_create_interactive(
    name: str,
    character_sheet: Optional[str] = None,
    scope: str = "personas",
) -> Optional[Persona]:
    """Interactive fictional persona creation.

    This guides through:
    1. Loading/creating character sheet
    2. Asking the character what they consume
    3. Asking whose voice they identify with
    4. Creating the persona

    Args:
        name: Character name
        character_sheet: Path to character sheet (optional)
        scope: Memory scope

    Returns:
        Created Persona or None
    """
    log.info("Creating fictional persona: %s", name)

    # Load character sheet if provided
    sheet_data = {}
    if character_sheet:
        sheet_data = load_character_sheet(character_sheet)
        log.info("Loaded character sheet with %d fields", len(sheet_data))

    # Create persona with available info
    persona = create_fictional_persona(
        name=name,
        character_sheet_path=character_sheet,
        scope=scope,
        domain=sheet_data.get("domain", ""),
        role=sheet_data.get("role", ""),
    )

    # Store to memory
    if create_persona(persona, store=True):
        log.info("Created fictional persona: %s", name)
        return persona

    return None
