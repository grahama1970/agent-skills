#!/usr/bin/env python3
"""
PersonaPlex integration for create-persona.

PersonaPlex is NVIDIA's full-duplex speech-to-speech model for real-time
conversational AI. This module handles:

1. Voice Prompt Extraction: Extract speaker embeddings (.pt files) from reference clips
2. Emotional Mannerisms: State machines for register-based voice switching
3. Text Prompts: Context-aware prompts that condition conversation behavior
4. Register Switching: Dynamic voice selection based on triggers (keywords, context, time)

PersonaPlex Architecture:
- Voice Prompts (.pt): Speaker embeddings extracted from 10-30 second reference clips
- Text Prompts: System prompts that define personality/behavior for each register
- Emotional States: State machine mapping triggers to voice/behavior combinations

Workflow:
1. Define emotional mannerisms (YAML config with states, triggers, vernacular)
2. Extract voice prompts from reference actor clips
3. Create register-specific text prompts
4. Deploy to PersonaPlex for real-time conversation

Integration with Fictional Personas:
- Fictional personas have voice_references (actors they identify with)
- PersonaPlex uses these to extract speaker embeddings
- Each register (confident, uncertain, etc.) maps to a different voice prompt
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from loguru import logger as log

# Paths
SKILLS_DIR = Path(__file__).parent.parent.parent
PERSONAS_BASE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas"
PERSONAPLEX_CACHE = Path.home() / ".cache" / "personaplex"

# Fallback for systems without 12TB storage
if not PERSONAS_BASE.exists():
    PERSONAS_BASE = Path.home() / "personas"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class VoicePrompt:
    """A PersonaPlex voice prompt (speaker embedding)."""
    name: str                          # e.g., "embry_confident"
    file_path: str                     # Path to .pt file
    source: str                        # Source description (e.g., "Hailee Steinfeld reference clips")
    characteristics: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0      # Duration of source audio used

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "source": self.source,
            "characteristics": self.characteristics,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class EmotionalState:
    """An emotional state in the PersonaPlex state machine."""
    name: str                          # e.g., "technical_flow", "uncertain_deflecting"
    voice: str                         # Voice prompt to use (e.g., "confident", "uncertain")
    triggers: dict = field(default_factory=dict)  # {keywords: [], context: [], time: []}
    behavior: dict = field(default_factory=dict)  # {speech_rate, pauses, filler_words, etc.}
    vernacular: list[str] = field(default_factory=list)  # Unlocked phrases in this state
    example: str = ""                  # Example line in this state

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "voice": self.voice,
            "triggers": self.triggers,
            "behavior": self.behavior,
            "vernacular": self.vernacular,
            "example": self.example,
        }


@dataclass
class VernacularPhrase:
    """A vernacular phrase with emotional weight."""
    phrase: str
    meaning: str
    emotional_weight: str = "none"     # none, slight, warm, high_hurts, critical_never_say
    usage: str = ""                    # When/how it's used
    origin: str = ""                   # Where it comes from (Charleston, Hawaiian, etc.)

    def to_dict(self) -> dict:
        return {
            "phrase": self.phrase,
            "meaning": self.meaning,
            "emotional_weight": self.emotional_weight,
            "usage": self.usage,
            "origin": self.origin,
        }


@dataclass
class PersonaPlexConfig:
    """Full PersonaPlex configuration for a persona."""
    name: str
    version: str = "1.0"

    # Model settings
    model: str = "nvidia/personaplex-7b-v1"
    inference_seed: int = 42424242
    cpu_offload: bool = False

    # Voice prompts
    voice_prompts: dict[str, VoicePrompt] = field(default_factory=dict)
    default_voice: str = "confident"

    # Emotional state machine
    states: list[EmotionalState] = field(default_factory=list)

    # Vernacular libraries
    vernacular: dict[str, list[VernacularPhrase]] = field(default_factory=dict)

    # Transition behaviors
    transitions: list[dict] = field(default_factory=list)

    # Prompt templates (references to text prompts)
    prompt_templates: dict[str, str] = field(default_factory=dict)

    # Paths
    config_dir: str = ""
    voices_dir: str = ""
    prompts_dir: str = ""

    def __post_init__(self):
        if not self.config_dir:
            base = PERSONAS_BASE / self.name.lower().replace(" ", "_")
            self.config_dir = str(base / "personaplex" / "configs")
            self.voices_dir = str(base / "personaplex" / "voices")
            self.prompts_dir = str(base / "personaplex" / "prompts")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "personaplex": {
                "model": self.model,
                "voice_switching": {
                    "enabled": True,
                    "method": "register_based",
                    "default_voice": self.default_voice,
                },
                "inference_settings": {
                    "seed": self.inference_seed,
                    "cpu_offload": self.cpu_offload,
                },
            },
            "voice_prompts": {k: v.to_dict() for k, v in self.voice_prompts.items()},
            "states": [s.to_dict() for s in self.states],
            "vernacular": {
                k: [p.to_dict() for p in phrases]
                for k, phrases in self.vernacular.items()
            },
            "transitions": self.transitions,
            "prompt_templates": self.prompt_templates,
        }


# =============================================================================
# Voice Prompt Extraction
# =============================================================================

def extract_speaker_embedding(
    audio_path: Path,
    output_path: Path,
    model: str = "resemblyzer",
    timeout: int = 120,
) -> tuple[bool, str]:
    """Extract a speaker embedding from audio for PersonaPlex.

    PersonaPlex uses speaker embeddings (.pt files) to condition voice generation.
    This function extracts embeddings from 10-30 second audio clips.

    Args:
        audio_path: Path to source audio (WAV, MP3, etc.)
        output_path: Path for output .pt file
        model: Embedding model ("resemblyzer", "ecapa", "speakernet")
        timeout: Extraction timeout in seconds

    Returns:
        Tuple of (success, error_message)
    """
    if not audio_path.exists():
        return False, f"Audio file not found: {audio_path}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if model == "resemblyzer":
            # Use resemblyzer for speaker embeddings
            import torch
            from resemblyzer import VoiceEncoder, preprocess_wav

            encoder = VoiceEncoder()
            wav = preprocess_wav(str(audio_path))
            embedding = encoder.embed_utterance(wav)

            # Save as PyTorch tensor
            torch.save(torch.from_numpy(embedding), output_path)
            log.info("Extracted speaker embedding: %s", output_path)
            return True, ""

        elif model == "ecapa":
            # Use ECAPA-TDNN via speechbrain
            import torch
            import torchaudio
            from speechbrain.inference.speaker import EncoderClassifier

            classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(PERSONAPLEX_CACHE / "ecapa"),
            )

            signal, fs = torchaudio.load(str(audio_path))
            embedding = classifier.encode_batch(signal)

            torch.save(embedding.squeeze(), output_path)
            log.info("Extracted ECAPA embedding: %s", output_path)
            return True, ""

        else:
            return False, f"Unknown embedding model: {model}"

    except ImportError as e:
        log.warning("Embedding extraction requires: pip install resemblyzer speechbrain")
        return False, f"Missing dependency: {e}"
    except Exception as e:
        log.error("Embedding extraction failed: %s", e)
        return False, str(e)


def extract_voice_prompts_from_references(
    persona_name: str,
    voice_references: list[dict],
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> dict:
    """Extract PersonaPlex voice prompts from reference actor clips.

    For each voice reference (actor + register), this:
    1. Downloads sample clips from YouTube (or uses provided clips)
    2. Extracts speaker embeddings
    3. Saves as .pt files for PersonaPlex

    Args:
        persona_name: Name of the persona
        voice_references: List of voice reference dicts with:
            - name: Actor name
            - register: Voice register (confident, uncertain, etc.)
            - youtube_urls: URLs to clips (optional)
            - clips_to_find: Descriptions of clips to search for
        output_dir: Directory for .pt files
        dry_run: Preview without extracting

    Returns:
        Dict with extraction results
    """
    slug = persona_name.lower().replace(" ", "_")

    if not output_dir:
        output_dir = PERSONAS_BASE / slug / "personaplex" / "voices"

    output_dir = Path(output_dir)

    result = {
        "persona": persona_name,
        "extracted": [],
        "failed": [],
        "voice_prompts": {},
    }

    if dry_run:
        log.info("[DRY-RUN] Would extract voice prompts for %s:", persona_name)
        for ref in voice_references:
            name = ref.get("name", "unknown")
            register = ref.get("register", "neutral")
            log.info("  - %s_%s.pt from %s", slug, register, name)
        result["status"] = "dry_run"
        return result

    output_dir.mkdir(parents=True, exist_ok=True)

    for ref in voice_references:
        actor_name = ref.get("name", "unknown")
        register = ref.get("register", "neutral")
        urls = ref.get("youtube_urls", [])
        clips_to_find = ref.get("clips_to_find", [])

        prompt_name = f"{slug}_{register}"
        output_path = output_dir / f"{prompt_name}.pt"

        log.info("Extracting %s voice prompt from %s...", register, actor_name)

        # Check if we already have extracted audio
        audio_cache = PERSONAPLEX_CACHE / "audio" / actor_name.lower().replace(" ", "_")
        audio_files = list(audio_cache.glob("*.wav")) if audio_cache.exists() else []

        if not audio_files and urls:
            # Download audio from URLs
            audio_cache.mkdir(parents=True, exist_ok=True)
            for url in urls[:3]:  # Limit to 3 clips per reference
                try:
                    video_id = _extract_video_id(url)
                    if video_id:
                        audio_path = audio_cache / f"{video_id}.wav"
                        if not audio_path.exists():
                            _download_audio(url, audio_path)
                        if audio_path.exists():
                            audio_files.append(audio_path)
                except Exception as e:
                    log.warning("Failed to download %s: %s", url, e)

        if not audio_files:
            result["failed"].append({
                "actor": actor_name,
                "register": register,
                "error": "No audio files available",
            })
            continue

        # Use the first available audio file
        audio_file = audio_files[0]

        # Extract embedding
        success, error = extract_speaker_embedding(audio_file, output_path)

        if success:
            voice_prompt = VoicePrompt(
                name=prompt_name,
                file_path=str(output_path),
                source=f"{actor_name} reference clips",
                characteristics=ref.get("characteristics", []),
            )
            result["extracted"].append(voice_prompt.to_dict())
            result["voice_prompts"][register] = voice_prompt
        else:
            result["failed"].append({
                "actor": actor_name,
                "register": register,
                "error": error,
            })

    result["status"] = "complete" if result["extracted"] else "failed"
    return result


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None


def _download_audio(url: str, output_path: Path, timeout: int = 120) -> bool:
    """Download audio from YouTube URL using ingest-youtube skill."""
    import sys as _sys

    _iy_dir = str(SKILLS_DIR / "ingest-youtube")
    if _iy_dir not in _sys.path:
        _sys.path.insert(0, _iy_dir)

    from youtube_transcripts.downloader import download_audio as _dl_audio

    video_id = _extract_video_id(url)
    if not video_id:
        log.error("Could not extract video ID from: %s", url)
        return False

    audio_path, error = _dl_audio(video_id, output_path.parent)
    if error or audio_path is None:
        log.error("Audio download failed: %s", error)
        return False

    # Move/rename to expected output_path if different
    if audio_path != output_path and audio_path.exists():
        import shutil
        shutil.move(str(audio_path), str(output_path))

    return output_path.exists()


# =============================================================================
# Emotional Mannerisms Configuration
# =============================================================================

def load_emotional_mannerisms(config_path: Path) -> PersonaPlexConfig:
    """Load emotional mannerisms from YAML config.

    Args:
        config_path: Path to emotional_mannerisms.yaml

    Returns:
        PersonaPlexConfig with loaded settings
    """
    import yaml

    if not config_path.exists():
        log.warning("Config not found: %s", config_path)
        return PersonaPlexConfig(name="unknown")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    config = PersonaPlexConfig(
        name=data.get("name", "unknown"),
        version=data.get("version", "1.0"),
    )

    # Load voice prompts
    for key, prompt_data in data.get("voice_prompts", {}).items():
        config.voice_prompts[key] = VoicePrompt(
            name=key,
            file_path=prompt_data.get("file", ""),
            source=prompt_data.get("source", ""),
            characteristics=prompt_data.get("characteristics", []),
        )

    # Load emotional states
    for state_name, state_data in data.get("states", {}).items():
        config.states.append(EmotionalState(
            name=state_name,
            voice=state_data.get("voice", "confident"),
            triggers=state_data.get("triggers", {}),
            behavior=state_data.get("behavior", {}),
            vernacular=state_data.get("vernacular_unlocked", []),
            example=state_data.get("example", ""),
        ))

    # Load vernacular libraries
    for origin, phrases in data.get("vernacular", {}).items():
        config.vernacular[origin] = []
        for category in ["safe", "loaded", "forbidden"]:
            for phrase_data in phrases.get(category, []):
                weight = (
                    "none" if category == "safe" else
                    "high_hurts" if category == "loaded" else
                    "critical_never_say"
                )
                config.vernacular[origin].append(VernacularPhrase(
                    phrase=phrase_data.get("phrase", ""),
                    meaning=phrase_data.get("meaning", ""),
                    emotional_weight=phrase_data.get("emotional_weight", weight),
                    usage=phrase_data.get("usage", ""),
                    origin=origin,
                ))

    # Load transitions
    config.transitions = data.get("transitions", [])

    # Load PersonaPlex settings
    plex_data = data.get("personaplex", {})
    config.model = plex_data.get("model", config.model)
    config.default_voice = plex_data.get("voice_switching", {}).get("default_voice", "confident")
    config.prompt_templates = plex_data.get("prompt_templates", {})

    inference = plex_data.get("inference_settings", {})
    config.inference_seed = inference.get("seed", 42424242)
    config.cpu_offload = inference.get("cpu_offload", False)

    return config


def save_emotional_mannerisms(config: PersonaPlexConfig, output_path: Path) -> bool:
    """Save emotional mannerisms to YAML config.

    Args:
        config: PersonaPlexConfig to save
        output_path: Output YAML file path

    Returns:
        Success boolean
    """
    import yaml

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to YAML-friendly format
    data = {
        "name": config.name,
        "version": config.version,
        "voice_prompts": {},
        "states": {},
        "vernacular": {},
        "transitions": config.transitions,
        "personaplex": {
            "model": config.model,
            "voice_switching": {
                "enabled": True,
                "method": "register_based",
                "default_voice": config.default_voice,
            },
            "prompt_templates": config.prompt_templates,
            "inference_settings": {
                "seed": config.inference_seed,
                "cpu_offload": config.cpu_offload,
            },
        },
    }

    # Voice prompts
    for key, prompt in config.voice_prompts.items():
        data["voice_prompts"][key] = {
            "file": prompt.file_path,
            "source": prompt.source,
            "characteristics": prompt.characteristics,
        }

    # States
    for state in config.states:
        data["states"][state.name] = {
            "voice": state.voice,
            "triggers": state.triggers,
            "behavior": state.behavior,
            "vernacular_unlocked": state.vernacular,
            "example": state.example,
        }

    # Vernacular (group by origin, then by weight)
    for origin, phrases in config.vernacular.items():
        data["vernacular"][origin] = {"safe": [], "loaded": [], "forbidden": []}
        for phrase in phrases:
            category = (
                "safe" if phrase.emotional_weight in ["none", "slight", "warm"] else
                "loaded" if phrase.emotional_weight == "high_hurts" else
                "forbidden"
            )
            data["vernacular"][origin][category].append({
                "phrase": phrase.phrase,
                "meaning": phrase.meaning,
                "emotional_weight": phrase.emotional_weight,
                "usage": phrase.usage,
            })

    try:
        with open(output_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        log.info("Saved emotional mannerisms: %s", output_path)
        return True
    except Exception as e:
        log.error("Failed to save config: %s", e)
        return False


# =============================================================================
# Register Detection
# =============================================================================

def detect_register(
    text: str,
    context: dict,
    config: PersonaPlexConfig,
) -> str:
    """Detect which emotional register should be active based on input.

    Checks triggers (keywords, context, time) against all states
    and returns the most appropriate voice register.

    Args:
        text: Input text to analyze
        context: Context dict with keys like:
            - time: Current time (for late-night triggers)
            - failure_count: Number of recent failures
            - user_relationship: Relationship level with current user
        config: PersonaPlex configuration

    Returns:
        Register name (e.g., "confident", "uncertain", "tired")
    """
    text_lower = text.lower()

    for state in config.states:
        triggers = state.triggers

        # Check keyword triggers
        keywords = triggers.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                log.debug("Triggered %s via keyword: %s", state.name, keyword)
                return state.voice

        # Check context triggers
        contexts = triggers.get("context", [])
        for ctx in contexts:
            if ctx in context.values():
                log.debug("Triggered %s via context: %s", state.name, ctx)
                return state.voice

        # Check time triggers
        time_triggers = triggers.get("time", [])
        current_time = context.get("time")
        if current_time:
            for time_trigger in time_triggers:
                if time_trigger.startswith("after_"):
                    hour = int(time_trigger.replace("after_", ""))
                    if current_time.hour >= hour:
                        log.debug("Triggered %s via time: %s", state.name, time_trigger)
                        return state.voice

    return config.default_voice


# =============================================================================
# CLI Integration
# =============================================================================

def personaplex_status(persona_name: str) -> dict:
    """Get PersonaPlex setup status for a persona.

    Args:
        persona_name: Name of the persona

    Returns:
        Status dict with component readiness
    """
    slug = persona_name.lower().replace(" ", "_")
    base_dir = PERSONAS_BASE / slug / "personaplex"

    status = {
        "persona": persona_name,
        "ready": False,
        "components": {
            "config": False,
            "voice_prompts": {},
            "text_prompts": False,
        },
        "paths": {
            "config_dir": str(base_dir / "configs"),
            "voices_dir": str(base_dir / "voices"),
            "prompts_dir": str(base_dir / "prompts"),
        },
        "issues": [],
    }

    # Check config
    config_path = base_dir / "configs" / "emotional_mannerisms.yaml"
    if config_path.exists():
        status["components"]["config"] = True
        config = load_emotional_mannerisms(config_path)
        status["config_version"] = config.version
        status["states_count"] = len(config.states)
    else:
        status["issues"].append("Missing emotional_mannerisms.yaml")

    # Check voice prompts
    voices_dir = base_dir / "voices"
    if voices_dir.exists():
        for pt_file in voices_dir.glob("*.pt"):
            register = pt_file.stem.replace(f"{slug}_", "")
            status["components"]["voice_prompts"][register] = str(pt_file)
    else:
        status["issues"].append("No voice prompts extracted")

    # Check text prompts
    prompts_file = base_dir / "prompts" / f"{slug}_prompts.yaml"
    if prompts_file.exists():
        status["components"]["text_prompts"] = True
    else:
        status["issues"].append("Missing text prompts")

    # Overall readiness
    status["ready"] = (
        status["components"]["config"] and
        len(status["components"]["voice_prompts"]) >= 1 and
        status["components"]["text_prompts"]
    )

    return status


def setup_personaplex(
    persona_name: str,
    voice_references: Optional[list[dict]] = None,
    character_sheet_path: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Full PersonaPlex setup for a fictional persona.

    This orchestrates:
    1. Loading character sheet (if provided)
    2. Extracting voice prompts from references
    3. Creating emotional mannerism config
    4. Creating text prompts

    Args:
        persona_name: Name of the persona
        voice_references: Voice reference actors/clips
        character_sheet_path: Path to character document
        dry_run: Preview without changes

    Returns:
        Setup result dict
    """
    slug = persona_name.lower().replace(" ", "_")
    base_dir = PERSONAS_BASE / slug / "personaplex"

    result = {
        "persona": persona_name,
        "status": "pending",
        "steps_completed": [],
        "errors": [],
    }

    if dry_run:
        log.info("[DRY-RUN] Would setup PersonaPlex for %s:", persona_name)
        log.info("  - Base dir: %s", base_dir)
        if voice_references:
            for ref in voice_references:
                log.info("  - Voice: %s (%s)", ref.get("name"), ref.get("register"))
        result["status"] = "dry_run"
        return result

    # Create directories
    for subdir in ["configs", "voices", "prompts"]:
        (base_dir / subdir).mkdir(parents=True, exist_ok=True)
    result["steps_completed"].append("directories_created")

    # Extract voice prompts if references provided
    if voice_references:
        extract_result = extract_voice_prompts_from_references(
            persona_name,
            voice_references,
            output_dir=base_dir / "voices",
        )
        if extract_result.get("extracted"):
            result["steps_completed"].append("voice_prompts_extracted")
            result["voice_prompts"] = extract_result["extracted"]
        else:
            result["errors"].extend(extract_result.get("failed", []))

    # Check for existing configs (Embry already has them)
    config_path = base_dir / "configs" / "emotional_mannerisms.yaml"
    prompts_path = base_dir / "prompts" / f"{slug}_prompts.yaml"

    if config_path.exists():
        result["steps_completed"].append("config_exists")
    if prompts_path.exists():
        result["steps_completed"].append("prompts_exist")

    result["status"] = "complete" if len(result["errors"]) == 0 else "partial"
    return result
