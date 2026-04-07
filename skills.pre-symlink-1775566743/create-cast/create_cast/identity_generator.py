"""
Identity generator for create-cast skill.

Generates character identity images using create-image skill.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Optional

from .schemas import CharacterSpec, CandidateLook, ReferenceActor


def find_create_image_skill() -> Optional[Path]:
    """Find the create-image skill directory."""
    candidates = [
        Path(__file__).parent.parent.parent / "create-image",
        Path.home() / ".pi" / "skills" / "create-image",
        Path(__file__).resolve().parent.parent.parent / "create-image",
    ]
    
    for path in candidates:
        if (path / "run.sh").exists():
            return path
    
    return None


def is_create_image_available() -> bool:
    """Check if create-image skill is available."""
    return find_create_image_skill() is not None


def build_identity_prompt(
    character: CharacterSpec,
    reference: Optional[ReferenceActor] = None,
    style: str = "photorealistic portrait"
) -> str:
    """
    Build a prompt for identity image generation.
    
    Combines character physical description with optional reference actor.
    """
    parts = []
    
    # Base style
    parts.append(style)
    
    # Physical descriptors
    descriptors = character.physical.to_prompt_descriptors()
    if descriptors:
        parts.extend(descriptors)
    
    # Reference actor influence (if selected)
    if reference and reference.selected:
        parts.append(f"inspired by {reference.name}'s look")
    
    # Personality influence on expression
    if character.personality:
        if "determined" in character.personality:
            parts.append("determined expression")
        elif "confident" in character.personality:
            parts.append("confident expression")
        elif "vulnerable" in character.personality:
            parts.append("soft expression")
    
    # Consistent lighting for identity pack
    parts.append("studio lighting")
    parts.append("neutral background")
    parts.append("high quality")
    parts.append("4k")
    
    return ", ".join(parts)


def generate_candidate_looks(
    character: CharacterSpec,
    output_dir: Path,
    reference: Optional[ReferenceActor] = None,
    num_candidates: int = 3,
    iteration: int = 1
) -> List[CandidateLook]:
    """
    Generate candidate identity looks for a character.
    
    Uses create-image skill if available, falls back to placeholder.
    """
    skill_dir = find_create_image_skill()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    looks = []
    base_prompt = build_identity_prompt(character, reference)
    
    # Variations for diversity
    variations = [
        "front-facing view",
        "slight angle, 3/4 view",
        "dramatic lighting",
    ]
    
    for i in range(num_candidates):
        variation = variations[i % len(variations)]
        prompt = f"{base_prompt}, {variation}"
        
        output_path = output_dir / f"{character.name.lower()}_candidate_{iteration}_{i+1}.png"
        
        if skill_dir:
            try:
                result = subprocess.run(
                    ["./run.sh", "generate", prompt, "--output", str(output_path)],
                    cwd=str(skill_dir),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0 and output_path.exists():
                    looks.append(CandidateLook(
                        image_path=str(output_path),
                        prompt_used=prompt,
                        style_notes=variation,
                        iteration=iteration,
                    ))
                else:
                    # Create placeholder
                    looks.append(_create_placeholder_look(
                        character, output_path, prompt, variation, iteration
                    ))
            except subprocess.TimeoutExpired:
                looks.append(_create_placeholder_look(
                    character, output_path, prompt, variation, iteration
                ))
        else:
            looks.append(_create_placeholder_look(
                character, output_path, prompt, variation, iteration
            ))
    
    return looks


def _create_placeholder_look(
    character: CharacterSpec,
    output_path: Path,
    prompt: str,
    style_notes: str,
    iteration: int
) -> CandidateLook:
    """Create a placeholder look when image generation is unavailable."""
    # Create a placeholder text file describing what would be generated
    placeholder_path = output_path.with_suffix(".placeholder.txt")
    placeholder_path.write_text(f"""
PLACEHOLDER IMAGE
Character: {character.name}
Prompt: {prompt}
Style: {style_notes}
Iteration: {iteration}

This is a placeholder. When create-image skill is available,
this would be a generated portrait image.
""")
    
    return CandidateLook(
        image_path=str(placeholder_path),
        prompt_used=prompt,
        style_notes=f"{style_notes} (placeholder)",
        iteration=iteration,
    )


def regenerate_look(
    character: CharacterSpec,
    output_dir: Path,
    previous_looks: List[CandidateLook],
    adjustment: str = ""
) -> CandidateLook:
    """
    Regenerate a look with adjustments based on feedback.
    """
    iteration = max(look.iteration for look in previous_looks) + 1 if previous_looks else 1
    
    # Build prompt with adjustment
    base_prompt = build_identity_prompt(character)
    if adjustment:
        base_prompt = f"{base_prompt}, {adjustment}"
    
    looks = generate_candidate_looks(
        character, output_dir, num_candidates=1, iteration=iteration
    )
    
    return looks[0] if looks else None
