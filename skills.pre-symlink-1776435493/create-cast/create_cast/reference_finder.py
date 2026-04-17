"""
Reference finder for create-cast skill.

Integrates with discover-talent to find reference actors
for character casting.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .schemas import CharacterSpec, ReferenceActor


def find_discover_talent_skill() -> Optional[Path]:
    """Find the discover-talent skill directory."""
    candidates = [
        Path(__file__).parent.parent.parent / "discover-talent",
        Path.home() / ".pi" / "skills" / "discover-talent",
        Path(__file__).resolve().parent.parent.parent / "discover-talent",
    ]
    
    for path in candidates:
        if (path / "run.sh").exists():
            return path
    
    return None


def is_discover_talent_available() -> bool:
    """Check if discover-talent skill is available."""
    return find_discover_talent_skill() is not None


def search_reference_actors(
    character: CharacterSpec,
    limit: int = 5
) -> List[ReferenceActor]:
    """
    Search for reference actors matching a character spec.
    
    Uses discover-talent skill if available.
    """
    skill_dir = find_discover_talent_skill()
    if not skill_dir:
        return []
    
    refs = []
    
    # Strategy 1: Search by bridge attribute
    if character.bridge_attributes:
        for bridge in character.bridge_attributes[:1]:  # Use first bridge
            try:
                result = subprocess.run(
                    ["./run.sh", "bridge", bridge, "--limit", str(limit), "--json"],
                    cwd=str(skill_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for r in data.get("results", []):
                        refs.append(ReferenceActor(
                            tmdb_id=r.get("id", 0),
                            name=r.get("name", "Unknown"),
                            profile_url=r.get("profile_url", ""),
                            known_for=[m.get("title", "") for m in r.get("known_for", [])[:3]],
                        ))
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                pass
    
    # Strategy 2: If character has gender/age, search by popular actors
    if not refs and (character.physical.gender or character.physical.age_range):
        # Build a generic search based on character type
        search_terms = []
        if character.physical.gender == "female":
            search_terms.extend(["actress", "leading actress"])
        elif character.physical.gender == "male":
            search_terms.extend(["actor", "leading actor"])
        
        # TODO: integrate with discover-talent's similar command for sophisticated matching

    return refs[:limit]


def search_by_actor_name(name: str, limit: int = 5) -> List[ReferenceActor]:
    """Search for actors by name using discover-talent."""
    skill_dir = find_discover_talent_skill()
    if not skill_dir:
        return []
    
    try:
        result = subprocess.run(
            ["./run.sh", "search", name, "--limit", str(limit), "--json"],
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            refs = []
            for r in data.get("results", []):
                refs.append(ReferenceActor(
                    tmdb_id=r.get("id", 0),
                    name=r.get("name", "Unknown"),
                    profile_url=r.get("profile_url", ""),
                    known_for=[m.get("title", "") for m in r.get("known_for", [])[:3]],
                ))
            return refs
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    
    return []


def get_actor_images(name: str, limit: int = 3) -> List[str]:
    """Get profile images for an actor using discover-talent."""
    skill_dir = find_discover_talent_skill()
    if not skill_dir:
        return []
    
    try:
        result = subprocess.run(
            ["./run.sh", "images", name, "--limit", str(limit), "--json"],
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return [img.get("url", "") for img in data.get("results", [])]
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    
    return []


def find_references_for_all_characters(
    characters: Dict[str, CharacterSpec],
    limit_per_char: int = 5
) -> Dict[str, List[ReferenceActor]]:
    """
    Find reference actors for all characters.
    
    Only searches for protagonists, antagonists, and supporting characters.
    """
    from .schemas import CharacterRole
    
    references = {}
    
    for char_name, char in characters.items():
        if char.role in [CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST, CharacterRole.SUPPORTING]:
            refs = search_reference_actors(char, limit=limit_per_char)
            if refs:
                references[char_name] = refs
    
    return references
