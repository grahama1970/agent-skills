"""
Voice matcher for create-cast skill.

Matches characters to existing voice models from learn-artist/tts-train.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .schemas import CharacterSpec, VoiceAssignment


def find_voice_models_dir() -> Optional[Path]:
    """Find the voice models directory."""
    candidates = [
        Path.home() / ".pi" / "voice-models",
        Path.home() / "memory" / "artifacts" / "tts",
        Path.home() / ".pi" / "tts-checkpoints",
        Path(__file__).resolve().parents[4] / "memory" / "artifacts" / "tts",
    ]
    
    for path in candidates:
        if path.exists():
            return path
    
    return None


def list_available_voice_models() -> List[Dict[str, str]]:
    """List all available voice models."""
    models_dir = find_voice_models_dir()
    if not models_dir:
        return []
    
    models = []
    
    # Look for RVC models
    for path in models_dir.glob("**/index*.pth"):
        name = path.parent.name
        models.append({
            "name": name,
            "path": str(path.parent),
            "type": "rvc",
        })
    
    # Look for TTS checkpoints
    for path in models_dir.glob("**/checkpoint*"):
        if path.is_dir():
            name = path.parent.name
            models.append({
                "name": name,
                "path": str(path),
                "type": "tts-train",
            })
    
    # Deduplicate by name
    seen = set()
    unique = []
    for m in models:
        if m["name"] not in seen:
            seen.add(m["name"])
            unique.append(m)
    
    return unique


def match_voice_to_character(
    character: CharacterSpec,
    available_models: List[Dict[str, str]]
) -> Optional[VoiceAssignment]:
    """
    Match a character to an available voice model.
    
    Matching strategy:
    1. Exact name match (character name in model name)
    2. Voice type match (gender, age)
    3. Random selection from appropriate gender pool
    """
    if not available_models:
        return VoiceAssignment(
            character_name=character.name,
            needs_training=True,
        )
    
    char_lower = character.name.lower()
    
    # Strategy 1: Exact name match
    for model in available_models:
        model_lower = model["name"].lower()
        if char_lower in model_lower or model_lower in char_lower:
            return VoiceAssignment(
                character_name=character.name,
                model_name=model["name"],
                model_path=model["path"],
                model_type=model["type"],
            )
    
    # Strategy 2: Voice type match
    gender = character.physical.gender.lower() if character.physical.gender else ""
    voice_type = character.voice_type.lower() if character.voice_type else ""
    
    gender_keywords = {
        "female": ["female", "woman", "girl", "actress", "she", "her"],
        "male": ["male", "man", "boy", "actor", "he", "him"],
    }
    
    for model in available_models:
        model_lower = model["name"].lower()
        
        if gender and gender in gender_keywords:
            for keyword in gender_keywords[gender]:
                if keyword in model_lower:
                    return VoiceAssignment(
                        character_name=character.name,
                        model_name=model["name"],
                        model_path=model["path"],
                        model_type=model["type"],
                    )
    
    # Strategy 3: Fall back to first available or mark for training
    if available_models:
        # Return first model as fallback
        model = available_models[0]
        return VoiceAssignment(
            character_name=character.name,
            model_name=model["name"],
            model_path=model["path"],
            model_type=model["type"],
        )
    
    return VoiceAssignment(
        character_name=character.name,
        needs_training=True,
    )


def find_voices_for_all_characters(
    characters: Dict[str, CharacterSpec]
) -> Dict[str, VoiceAssignment]:
    """
    Find voice assignments for all characters.
    """
    from .schemas import CharacterRole
    
    available = list_available_voice_models()
    assignments = {}
    
    for char_name, char in characters.items():
        # Only assign voices to speaking characters
        if char.dialogue_count > 0 or char.role in [CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST]:
            assignment = match_voice_to_character(char, available)
            if assignment:
                assignments[char_name] = assignment
    
    return assignments


def queue_voice_training(
    character: CharacterSpec,
    reference_actor: str
) -> VoiceAssignment:
    """
    Queue a character for voice training based on a reference actor.
    
    This creates a VoiceAssignment that marks the character as needing
    training, with the reference actor stored for the learn-artist skill.
    """
    return VoiceAssignment(
        character_name=character.name,
        needs_training=True,
        training_reference=reference_actor,
    )
