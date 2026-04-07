"""
Script analyzer for create-cast skill.

Extracts characters from screenplay/script files:
- Parses JSON script format from create-story
- Identifies characters from dialogue and action
- Estimates screen time
- Infers physical descriptions
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any, Optional

from .schemas import CharacterSpec, CharacterRole, PhysicalDescription


def load_script(script_path: str) -> Dict[str, Any]:
    """Load script from JSON file."""
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    
    with open(path) as f:
        return json.load(f)


def extract_characters_from_script(script: Dict[str, Any]) -> Dict[str, CharacterSpec]:
    """
    Extract character information from a script.
    
    Supports create-story script format:
    {
        "scenes": [
            {
                "number": 1,
                "heading": "INT. LOCATION - DAY",
                "action": "Character SARAH enters...",
                "dialogue": [
                    {"character": "SARAH", "line": "Hello."},
                    {"character": "VILLAIN", "line": "Welcome."}
                ]
            }
        ]
    }
    """
    characters: Dict[str, CharacterSpec] = {}
    scenes = script.get("scenes", [])
    
    # Track character mentions
    dialogue_counts: Counter = Counter()
    scene_appearances: Dict[str, List[int]] = {}
    raw_mentions: Dict[str, List[str]] = {}
    
    for scene in scenes:
        scene_num = scene.get("number", 0)
        
        # Extract from dialogue
        for d in scene.get("dialogue", []):
            char_name = d.get("character", "").upper()
            if char_name:
                dialogue_counts[char_name] += 1
                scene_appearances.setdefault(char_name, []).append(scene_num)
        
        # Extract from action text
        action = scene.get("action", "") or scene.get("description", "")
        # Normalize action to string (may be a list of strings from some script formats)
        if isinstance(action, list):
            action = " ".join(str(a) for a in action)
        if action:
            # Find character names (typically UPPERCASE)
            names = re.findall(r'\b([A-Z]{2,}(?:\s+[A-Z]+)?)\b', action)
            for name in names:
                # Filter out common non-character words
                if name not in ["INT", "EXT", "CONTINUOUS", "LATER", "DAY", "NIGHT", "MORNING", "EVENING", "CUT", "FADE"]:
                    scene_appearances.setdefault(name, []).append(scene_num)
                    raw_mentions.setdefault(name, []).append(action[:100])
    
    # Estimate screen time (5 seconds per dialogue line, 3 per scene appearance)
    screen_times: Dict[str, float] = {}
    for char_name in set(list(dialogue_counts.keys()) + list(scene_appearances.keys())):
        dialogue_time = dialogue_counts.get(char_name, 0) * 5.0
        scene_time = len(set(scene_appearances.get(char_name, []))) * 3.0
        screen_times[char_name] = dialogue_time + scene_time
    
    # Sort by screen time and assign roles
    sorted_chars = sorted(screen_times.items(), key=lambda x: x[1], reverse=True)
    
    for i, (char_name, screen_time) in enumerate(sorted_chars):
        # Skip if too little screen time
        if screen_time < 5:
            continue
            
        # Assign role based on rank
        if i == 0:
            role = CharacterRole.PROTAGONIST
        elif i == 1 and screen_time > sorted_chars[0][1] * 0.3:
            role = CharacterRole.ANTAGONIST
        elif screen_time > 15:
            role = CharacterRole.SUPPORTING
        elif screen_time > 5:
            role = CharacterRole.MINOR
        else:
            role = CharacterRole.BACKGROUND
        
        # Infer physical description from mentions
        physical = infer_physical_description(
            char_name, 
            raw_mentions.get(char_name, [])
        )
        
        characters[char_name] = CharacterSpec(
            name=char_name,
            role=role,
            screen_time_estimate=screen_time,
            physical=physical,
            dialogue_count=dialogue_counts.get(char_name, 0),
            scenes=list(set(scene_appearances.get(char_name, []))),
            raw_mentions=raw_mentions.get(char_name, [])[:5],
        )
    
    return characters


def infer_physical_description(char_name: str, mentions: List[str]) -> PhysicalDescription:
    """
    Infer physical description from text mentions of a character.
    """
    combined = " ".join(mentions).lower()
    
    # Age inference
    age_range = ""
    age_patterns = [
        (r'\byoung\b|\bteen\b|\byouth\b', "20s"),
        (r'\bmiddle.aged\b|\bforties\b|\b40s\b', "40s"),
        (r'\belderly\b|\bold\b|\bsenior\b', "60s+"),
        (r'\bchild\b|\bkid\b', "child"),
    ]
    for pattern, age in age_patterns:
        if re.search(pattern, combined):
            age_range = age
            break
    
    # Gender inference
    gender = ""
    if re.search(r'\bshe\b|\bher\b|\bwoman\b|\bfemale\b|\bgirl\b', combined):
        gender = "female"
    elif re.search(r'\bhe\b|\bhis\b|\bman\b|\bmale\b|\bboy\b', combined):
        gender = "male"
    
    # Build inference
    build = ""
    build_patterns = [
        (r'\btall\b|\bimposing\b|\blarge\b', "tall"),
        (r'\bsmall\b|\bpetite\b|\bthin\b|\bslim\b', "slim"),
        (r'\bmuscular\b|\bstrong\b|\bathletic\b', "athletic"),
    ]
    for pattern, b in build_patterns:
        if re.search(pattern, combined):
            build = b
            break
    
    # Hair inference
    hair = ""
    hair_patterns = [
        (r'\bblond\b|\bblonde\b', "blonde"),
        (r'\bdark.hair\b|\bblack.hair\b|\bbrunette\b', "dark"),
        (r'\bred.hair\b|\bginger\b', "red"),
        (r'\bgray\b|\bgrey\b|\bwhite.hair\b', "gray"),
    ]
    for pattern, h in hair_patterns:
        if re.search(pattern, combined):
            hair = h
            break
    
    # Distinguishing features
    distinguishing = ""
    feature_patterns = [
        (r'\bscar\b|\bscarred\b', "scarred"),
        (r'\bglasses\b|\bspectacles\b', "wears glasses"),
        (r'\bbeard\b|\bbearded\b', "bearded"),
        (r'\btattoo\b', "tattooed"),
    ]
    for pattern, feature in feature_patterns:
        if re.search(pattern, combined):
            distinguishing = feature
            break
    
    return PhysicalDescription(
        age_range=age_range,
        gender=gender,
        build=build,
        hair=hair,
        distinguishing=distinguishing,
    )


def extract_characters_from_markdown(script_path: str) -> Dict[str, CharacterSpec]:
    """
    Extract characters from a markdown screenplay.

    Supports multiple formats:
    1. Standard fountain: INT. LOCATION - DAY followed by CHARACTER
    2. Markdown screenplay: ## INT. LOCATION and **CHARACTER (parenthetical)**
    3. Horus format: ## INT. LOCATION and **CHARACTER** with > dialogue
    """
    path = Path(script_path)
    content = path.read_text()

    characters: Dict[str, CharacterSpec] = {}
    dialogue_counts: Counter = Counter()
    scene_appearances: Dict[str, List[int]] = {}
    raw_mentions: Dict[str, List[str]] = {}
    current_scene = 0

    lines = content.split("\n")

    # Patterns for markdown screenplay format
    # Scene heading: ## INT. LOCATION or plain INT. LOCATION
    scene_pattern = re.compile(r'^#{0,3}\s*(INT\.|EXT\.)', re.IGNORECASE)

    # Character dialogue: **CHARACTER** or **CHARACTER (parenthetical)**
    # Must be followed by dialogue (> blockquote or plain text)
    char_dialogue_pattern = re.compile(r'^\*\*([A-Z][A-Z0-9_/\s]+?)(?:\s*\([^)]*\))?\*\*\s*$')

    # Plain fountain character: ALL CAPS on own line
    plain_char_pattern = re.compile(r'^([A-Z][A-Z0-9_\s]+)$')

    # Scene title (not a character): **SCENE 1: TITLE**
    scene_title_pattern = re.compile(r'^\*\*SCENE\s+\d+:', re.IGNORECASE)

    # Non-character uppercase items to exclude
    non_characters = {
        "FADE IN", "FADE OUT", "CUT TO", "THE END", "SMASH CUT",
        "INT", "EXT", "CONTINUOUS", "LATER", "DAY", "NIGHT",
        "MORNING", "EVENING", "CUT", "FADE", "END DRAFT",
        "WHY", "BECAUSE YOU CHOSE", "I KNOW",  # Dialogue content, not characters
        "CUT TO BLACK", "BEAT",
    }

    def is_followed_by_dialogue(idx: int) -> bool:
        """Check if line at idx is followed by dialogue content."""
        for j in range(idx + 1, min(idx + 4, len(lines))):
            next_line = lines[j].strip()
            if not next_line:
                continue
            # Markdown blockquote dialogue
            if next_line.startswith(">"):
                return True
            # Plain dialogue (non-empty, not a heading or character)
            if not next_line.startswith("#") and not next_line.startswith("*") and not next_line.startswith("["):
                # Check it's not just action/description
                if len(next_line) > 5 and not scene_pattern.match(next_line):
                    return True
            break
        return False

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Scene heading (markdown or plain)
        if scene_pattern.match(line):
            current_scene += 1
            i += 1
            continue

        # Skip scene titles like **SCENE 1: LODGE FIRES**
        if scene_title_pattern.match(line):
            i += 1
            continue

        # Check for markdown character dialogue: **CHARACTER** or **CHARACTER (whisper)**
        char_match = char_dialogue_pattern.match(line)
        if char_match:
            char_name = char_match.group(1).strip()
            # Handle combined characters like SANGUINIUS/HORUS
            char_names = [c.strip() for c in char_name.split("/")]
            for name in char_names:
                if name and name.upper() not in non_characters:
                    # Verify it's followed by dialogue
                    if is_followed_by_dialogue(i):
                        dialogue_counts[name] += 1
                        scene_appearances.setdefault(name, []).append(current_scene)
            i += 1
            continue

        # Check for plain fountain character (ALL CAPS, followed by dialogue)
        if line and not line.startswith("#") and not line.startswith("*") and not line.startswith("["):
            plain_match = plain_char_pattern.match(line)
            if plain_match:
                char_name = plain_match.group(1).strip()
                if char_name.upper() not in non_characters and len(char_name) < 30:
                    if is_followed_by_dialogue(i):
                        dialogue_counts[char_name] += 1
                        scene_appearances.setdefault(char_name, []).append(current_scene)

        # Extract character mentions from action text
        if line and not line.startswith("#") and not line.startswith("*"):
            # Look for UPPERCASE names in action text
            names = re.findall(r'\b([A-Z]{2,}(?:\'[A-Z]+)?)\b', line)
            for name in names:
                if name not in non_characters and len(name) > 1 and len(name) < 20:
                    raw_mentions.setdefault(name, []).append(line[:100])

        i += 1

    # Build character specs
    screen_times: Dict[str, float] = {}
    for char_name in dialogue_counts:
        dialogue_time = dialogue_counts[char_name] * 5.0
        scene_time = len(set(scene_appearances.get(char_name, []))) * 3.0
        screen_times[char_name] = dialogue_time + scene_time

    sorted_chars = sorted(screen_times.items(), key=lambda x: x[1], reverse=True)

    for idx, (char_name, screen_time) in enumerate(sorted_chars):
        if screen_time < 5:
            continue

        if idx == 0:
            role = CharacterRole.PROTAGONIST
        elif idx == 1:
            role = CharacterRole.ANTAGONIST
        elif screen_time > 15:
            role = CharacterRole.SUPPORTING
        else:
            role = CharacterRole.MINOR

        # Infer physical description from mentions
        physical = infer_physical_description(
            char_name,
            raw_mentions.get(char_name, [])
        )

        characters[char_name] = CharacterSpec(
            name=char_name,
            role=role,
            screen_time_estimate=screen_time,
            physical=physical,
            dialogue_count=dialogue_counts.get(char_name, 0),
            scenes=list(set(scene_appearances.get(char_name, []))),
            raw_mentions=raw_mentions.get(char_name, [])[:5],
        )

    return characters


def analyze_script(script_path: str) -> Dict[str, CharacterSpec]:
    """
    Analyze a script file and extract characters.
    
    Automatically detects format (JSON or Markdown).
    """
    path = Path(script_path)
    
    if path.suffix == ".json":
        script = load_script(script_path)
        return extract_characters_from_script(script)
    elif path.suffix in [".md", ".fountain", ".txt"]:
        return extract_characters_from_markdown(script_path)
    else:
        # Try JSON first, fall back to markdown
        try:
            script = load_script(script_path)
            return extract_characters_from_script(script)
        except json.JSONDecodeError:
            return extract_characters_from_markdown(script_path)
