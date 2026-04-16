"""
Identity pack builder for create-cast skill.

Creates complete identity packs with multiple angles for Veo reference.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Optional
import yaml

from .schemas import CharacterSpec, IdentityPack, CandidateLook
from .identity_generator import (
    build_identity_prompt,
    find_create_image_skill,
    generate_candidate_looks,
)


def build_identity_pack(
    character: CharacterSpec,
    selected_look: CandidateLook,
    output_dir: Path
) -> IdentityPack:
    """
    Build a complete identity pack from a selected look.
    
    Generates:
    - Front view (from selected look or regenerated)
    - Three-quarter view
    - Full-body view
    """
    char_dir = output_dir / character.name
    identity_dir = char_dir / "identity_pack"
    identity_dir.mkdir(parents=True, exist_ok=True)
    
    images = {}
    
    # Front view - use selected look if it's front-facing
    front_path = identity_dir / "front.png"
    if "front" in selected_look.style_notes.lower():
        # Copy selected look as front
        if Path(selected_look.image_path).exists():
            shutil.copy(selected_look.image_path, front_path)
            images["front"] = str(front_path)
        else:
            images["front"] = selected_look.image_path
    else:
        # Generate front-specific image
        front_looks = generate_candidate_looks(
            character, identity_dir, num_candidates=1
        )
        if front_looks:
            if Path(front_looks[0].image_path).exists():
                shutil.copy(front_looks[0].image_path, front_path)
            images["front"] = str(front_path)
    
    # Three-quarter view
    three_quarter_path = identity_dir / "three_quarter.png"
    three_quarter_looks = _generate_angle_image(
        character, identity_dir, "three-quarter view, 45 degree angle"
    )
    if three_quarter_looks:
        if Path(three_quarter_looks.image_path).exists():
            shutil.copy(three_quarter_looks.image_path, three_quarter_path)
        images["three_quarter"] = str(three_quarter_path)
    
    # Full-body view
    full_body_path = identity_dir / "full_body.png"
    full_body_looks = _generate_angle_image(
        character, identity_dir, "full body shot, standing pose"
    )
    if full_body_looks:
        if Path(full_body_looks.image_path).exists():
            shutil.copy(full_body_looks.image_path, full_body_path)
        images["full_body"] = str(full_body_path)
    
    # Build prompt descriptors for Veo
    descriptors = character.physical.to_prompt_descriptors()
    if character.personality:
        descriptors.append(f"{character.personality[0]} demeanor")
    
    pack = IdentityPack(
        character_name=character.name,
        images=images,
        prompt_descriptors=descriptors,
        lighting_notes="Neutral studio lighting for Veo reference",
    )
    
    # Save character bible
    bible_path = char_dir / "character_bible.yaml"
    bible_path.write_text(pack.to_yaml())
    
    return pack


def _generate_angle_image(
    character: CharacterSpec,
    output_dir: Path,
    angle_description: str
) -> Optional[CandidateLook]:
    """Generate a single image at a specific angle."""
    looks = generate_candidate_looks(
        character, output_dir, num_candidates=1
    )
    if looks:
        look = looks[0]
        look.style_notes = angle_description
        return look
    return None


def export_identity_packs(
    packs: Dict[str, IdentityPack],
    output_dir: Path
) -> Dict[str, str]:
    """
    Export all identity packs to a directory.
    
    Returns mapping of character name to export path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    exports = {}
    
    for char_name, pack in packs.items():
        char_dir = output_dir / char_name
        char_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy images
        identity_dir = char_dir / "identity_pack"
        identity_dir.mkdir(exist_ok=True)
        
        for angle, src_path in pack.images.items():
            if Path(src_path).exists():
                dest_path = identity_dir / f"{angle}.png"
                shutil.copy(src_path, dest_path)
                pack.images[angle] = str(dest_path)
        
        # Write character bible
        bible_path = char_dir / "character_bible.yaml"
        bible_path.write_text(pack.to_yaml())
        
        exports[char_name] = str(char_dir)
    
    # Write combined manifest
    manifest = {
        "characters": {name: pack.to_dict() for name, pack in packs.items()},
        "export_dir": str(output_dir),
    }
    manifest_path = output_dir / "casting_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    
    return exports


def load_identity_pack(pack_dir: Path) -> Optional[IdentityPack]:
    """Load an identity pack from a directory."""
    bible_path = pack_dir / "character_bible.yaml"
    if not bible_path.exists():
        return None
    
    try:
        with open(bible_path) as f:
            data = yaml.safe_load(f)
        return IdentityPack.from_dict(data)
    except (yaml.YAMLError, KeyError):
        return None
