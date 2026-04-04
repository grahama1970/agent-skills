"""
Scene analyzer for extracting SFX cues from scripts and storyboards.

Parses screenplay JSON and storyboard YAML to identify sound effect opportunities.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from loguru import logger

from .schemas import SFXCue


# Action verbs that suggest foley sounds
FOLEY_VERBS = {
    "slam", "slams", "slammed", "slamming",
    "crash", "crashes", "crashed", "crashing",
    "open", "opens", "opened", "opening",
    "close", "closes", "closed", "closing",
    "walk", "walks", "walked", "walking",
    "run", "runs", "ran", "running",
    "knock", "knocks", "knocked", "knocking",
    "drop", "drops", "dropped", "dropping",
    "break", "breaks", "broke", "breaking",
    "click", "clicks", "clicked", "clicking",
    "type", "types", "typed", "typing",
    "pour", "pours", "poured", "pouring",
    "drink", "drinks", "drank", "drinking",
    "eat", "eats", "ate", "eating",
    "sit", "sits", "sat", "sitting",
    "stand", "stands", "stood", "standing",
    "fall", "falls", "fell", "falling",
    "hit", "hits", "hitting",
    "punch", "punches", "punched", "punching",
    "kick", "kicks", "kicked", "kicking",
    "shoot", "shoots", "shot", "shooting",
    "fire", "fires", "fired", "firing",
    "explode", "explodes", "exploded", "exploding",
}

# Environment markers for ambient sounds
AMBIENT_MARKERS = {
    "INT.": "interior",
    "EXT.": "exterior",
    "rain": "weather",
    "raining": "weather",
    "storm": "weather",
    "stormy": "weather",
    "thunder": "weather",
    "wind": "weather",
    "windy": "weather",
    "snow": "weather",
    "snowing": "weather",
    "night": "time",
    "day": "time",
    "morning": "time",
    "evening": "time",
    "city": "location",
    "street": "location",
    "forest": "location",
    "ocean": "location",
    "beach": "location",
    "office": "location",
    "bar": "location",
    "restaurant": "location",
    "traffic": "urban",
    "crowd": "urban",
    "busy": "urban",
}

# Transition markers
TRANSITION_MARKERS = [
    "CUT TO",
    "FADE TO",
    "FADE IN",
    "FADE OUT",
    "DISSOLVE TO",
    "SMASH CUT",
    "MATCH CUT",
    "JUMP CUT",
    "WIPE TO",
]

# Explicit SFX markers in scripts
SFX_PATTERNS = [
    r"\[SFX:\s*([^\]]+)\]",           # [SFX: door creaks]
    r"\(sound of ([^)]+)\)",           # (sound of footsteps)
    r"\(SFX:\s*([^)]+)\)",            # (SFX: explosion)
    r"SOUND:\s*(.+?)(?:\n|$)",         # SOUND: thunder rumbles
    r"AUDIO:\s*(.+?)(?:\n|$)",         # AUDIO: phone rings
]


def categorize_cue(description: str) -> str:
    """
    Classify a cue description into a category.
    
    Categories: foley, ambient, impact, transition, ui, vocal, nature
    """
    desc_lower = description.lower()
    
    # Check for impact sounds
    impact_words = ["explosion", "crash", "smash", "bang", "boom", "hit", "punch", "kick", "gunshot", "shot"]
    if any(word in desc_lower for word in impact_words):
        return "impact"
    
    # Check for transition sounds
    if any(trans.lower() in desc_lower for trans in TRANSITION_MARKERS):
        return "transition"
    
    # Check for foley (human actions)
    if any(verb in desc_lower for verb in FOLEY_VERBS):
        return "foley"
    
    # Check for nature sounds
    nature_words = ["bird", "animal", "insect", "water", "river", "ocean", "wave", "tree", "leaves", "wind"]
    if any(word in desc_lower for word in nature_words):
        return "nature"
    
    # Check for vocal sounds
    vocal_words = ["scream", "yell", "shout", "whisper", "laugh", "cry", "gasp", "sigh", "moan", "groan"]
    if any(word in desc_lower for word in vocal_words):
        return "vocal"
    
    # Check for UI sounds
    ui_words = ["beep", "notification", "ring", "phone", "computer", "alert", "chime"]
    if any(word in desc_lower for word in ui_words):
        return "ui"
    
    # Check for ambient
    if any(marker.lower() in desc_lower for marker in AMBIENT_MARKERS.keys()):
        return "ambient"
    
    # Default to foley
    return "foley"


def infer_intensity(description: str) -> str:
    """Infer the intensity level from description."""
    desc_lower = description.lower()
    
    # Prominent indicators
    prominent_words = ["loud", "explosive", "thunderous", "massive", "intense", "violent", "powerful"]
    if any(word in desc_lower for word in prominent_words):
        return "prominent"
    
    # Subtle indicators
    subtle_words = ["soft", "quiet", "gentle", "faint", "subtle", "slight", "distant", "barely"]
    if any(word in desc_lower for word in subtle_words):
        return "subtle"
    
    return "moderate"


def extract_explicit_sfx(text: str, scene_id: str, cue_counter: int) -> List[SFXCue]:
    """Extract explicitly marked SFX from text."""
    cues = []
    
    for pattern in SFX_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            description = match.group(1).strip()
            cue_id = f"{scene_id}_cue_{cue_counter:03d}"
            cue_counter += 1
            
            cues.append(SFXCue(
                cue_id=cue_id,
                scene_id=scene_id,
                description=description,
                category=categorize_cue(description),
                intensity=infer_intensity(description),
                source_line=match.group(0),
            ))
    
    return cues


def extract_action_sfx(text: str, scene_id: str, start_counter: int) -> List[SFXCue]:
    """Extract implied SFX from action descriptions."""
    cues = []
    counter = start_counter
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Look for action verbs
        words = sentence.lower().split()
        found_verbs = [w for w in words if w in FOLEY_VERBS]
        
        if found_verbs:
            cue_id = f"{scene_id}_cue_{counter:03d}"
            counter += 1
            
            cues.append(SFXCue(
                cue_id=cue_id,
                scene_id=scene_id,
                description=sentence,
                category="foley",
                intensity=infer_intensity(sentence),
                source_line=sentence,
            ))
    
    return cues


def extract_ambient_from_heading(heading: str, scene_id: str) -> Optional[SFXCue]:
    """Extract ambient cue from scene heading (INT./EXT.)."""
    for marker, marker_type in AMBIENT_MARKERS.items():
        if marker.upper() in heading.upper():
            # Build ambient description from heading
            description = f"ambient: {heading}"
            return SFXCue(
                cue_id=f"{scene_id}_ambient",
                scene_id=scene_id,
                description=description,
                category="ambient",
                intensity="subtle",
                source_line=heading,
            )
    return None


def analyze_markdown_script(script_path: str) -> List[SFXCue]:
    """
    Parse markdown screenplay for SFX cues.

    Supports formats:
    - ## INT. LOCATION - TIME (markdown scene headings)
    - **CHARACTER** > dialogue
    - [AUDIO: description], [SFX: description]
    - Action text with FOLEY_VERBS
    """
    path = Path(script_path)
    if not path.exists():
        logger.warning(f"Script not found: {script_path}")
        return []

    content = path.read_text()
    lines = content.split('\n')

    cues = []
    cue_counter = 1
    current_scene_id = "scene_00"
    current_scene_num = 0
    current_heading = ""

    # Pattern for markdown scene headings: ## INT. LOCATION or plain INT. LOCATION
    scene_heading_pattern = re.compile(r'^#{0,6}\s*(INT\.|EXT\.)\s*(.+)', re.IGNORECASE)

    # Pattern for audio notes
    audio_note_pattern = re.compile(r'\[AUDIO:\s*([^\]]+)\]', re.IGNORECASE)
    sfx_note_pattern = re.compile(r'\[SFX:\s*([^\]]+)\]', re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for scene heading
        scene_match = scene_heading_pattern.match(stripped)
        if scene_match:
            current_scene_num += 1
            current_scene_id = f"scene_{current_scene_num:02d}"
            current_heading = stripped

            # Extract ambient from heading
            ambient_cue = extract_ambient_from_heading(stripped, current_scene_id)
            if ambient_cue:
                cues.append(ambient_cue)
            continue

        # Check for explicit audio/SFX notes
        for pattern in [audio_note_pattern, sfx_note_pattern]:
            for match in pattern.finditer(stripped):
                description = match.group(1).strip()
                cue_id = f"{current_scene_id}_cue_{cue_counter:03d}"
                cue_counter += 1
                cues.append(SFXCue(
                    cue_id=cue_id,
                    scene_id=current_scene_id,
                    description=description,
                    category=categorize_cue(description),
                    intensity=infer_intensity(description),
                    source_line=stripped,
                ))

        # Check for other explicit SFX patterns
        explicit = extract_explicit_sfx(stripped, current_scene_id, cue_counter)
        for cue in explicit:
            cues.append(cue)
            cue_counter += 1

        # Check for action verbs in text (not dialogue or headings)
        if not stripped.startswith('#') and not stripped.startswith('*') and not stripped.startswith('>') and not stripped.startswith('['):
            action_cues = extract_action_sfx(stripped, current_scene_id, cue_counter)
            for cue in action_cues:
                cues.append(cue)
                cue_counter += 1

    logger.info(f"Extracted {len(cues)} SFX cues from markdown script")
    return cues


def analyze_script(script_path: str) -> List[SFXCue]:
    """
    Parse script for SFX cues. Supports JSON and Markdown formats.

    JSON format:
    {
        "title": "Movie Title",
        "scenes": [
            {
                "scene_number": 1,
                "heading": "INT. APARTMENT - NIGHT",
                "action": "Sarah enters slowly...",
                "dialogue": [...],
                "duration": 45.0
            }
        ]
    }

    Markdown format:
    ## INT. LOCATION - TIME
    Action text...
    [AUDIO: sound cue]
    """
    path = Path(script_path)
    if not path.exists():
        logger.warning(f"Script not found: {script_path}")
        return []

    # Check file extension and content to determine format
    if path.suffix in ['.md', '.txt', '.fountain']:
        return analyze_markdown_script(script_path)

    # Try JSON first
    try:
        with open(path) as f:
            script = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse script JSON: {e}, trying markdown parser")
        return analyze_markdown_script(script_path)
    
    cues = []
    cue_counter = 1
    
    scenes = script.get("scenes", [])
    if not scenes:
        # Try alternative structure
        scenes = script.get("screenplay", {}).get("scenes", [])
    
    for scene in scenes:
        scene_num = scene.get("scene_number", scene.get("id", len(cues) + 1))
        scene_id = f"scene_{scene_num:02d}"
        
        # Extract from heading
        heading = scene.get("heading", scene.get("slug", ""))
        if heading:
            ambient_cue = extract_ambient_from_heading(heading, scene_id)
            if ambient_cue:
                cues.append(ambient_cue)
        
        # Extract from action lines
        action = scene.get("action", scene.get("description", ""))
        if isinstance(action, list):
            action = " ".join(str(a) for a in action)
        if action:
            # Explicit SFX markers
            explicit = extract_explicit_sfx(action, scene_id, cue_counter)
            cues.extend(explicit)
            cue_counter += len(explicit)
            
            # Implied action SFX
            action_cues = extract_action_sfx(action, scene_id, cue_counter)
            cues.extend(action_cues)
            cue_counter += len(action_cues)
        
        # Check for audio_cues field (modern scripts)
        audio_cues = scene.get("audio_cues", [])
        for ac in audio_cues:
            if isinstance(ac, str):
                cue_id = f"{scene_id}_cue_{cue_counter:03d}"
                cue_counter += 1
                cues.append(SFXCue(
                    cue_id=cue_id,
                    scene_id=scene_id,
                    description=ac,
                    category=categorize_cue(ac),
                    intensity=infer_intensity(ac),
                    source_line=ac,
                ))
            elif isinstance(ac, dict):
                cue_id = f"{scene_id}_cue_{cue_counter:03d}"
                cue_counter += 1
                cues.append(SFXCue(
                    cue_id=cue_id,
                    scene_id=scene_id,
                    description=ac.get("description", ""),
                    category=ac.get("category", categorize_cue(ac.get("description", ""))),
                    timestamp_hint=ac.get("timestamp"),
                    duration_hint=ac.get("duration"),
                    intensity=ac.get("intensity", "moderate"),
                    source_line=str(ac),
                ))
    
    logger.info(f"Extracted {len(cues)} SFX cues from script")
    return cues


def analyze_storyboard(storyboard_path: str) -> List[SFXCue]:
    """
    Parse storyboard YAML for SFX cues.
    
    Expected format (HorusShotSpec):
    scenes:
      - scene_id: scene_01
        shots:
          - shot_id: shot_001
            duration: 5.0
            audio_cues:
              - description: "footsteps on gravel"
                timestamp: 1.5
                category: foley
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not available, skipping storyboard")
        return []
    
    path = Path(storyboard_path)
    if not path.exists():
        logger.warning(f"Storyboard not found: {storyboard_path}")
        return []
    
    try:
        with open(path) as f:
            storyboard = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse storyboard YAML: {e}")
        return []
    
    cues = []
    cue_counter = 1
    
    scenes = storyboard.get("scenes", [])
    for scene in scenes:
        scene_id = scene.get("scene_id", f"scene_{len(cues) + 1:02d}")
        
        shots = scene.get("shots", [])
        for shot in shots:
            audio_cues = shot.get("audio_cues", [])
            shot_start = shot.get("start_time", 0.0)
            
            for ac in audio_cues:
                if isinstance(ac, str):
                    description = ac
                    timestamp = None
                    duration = None
                    category = categorize_cue(ac)
                    intensity = "moderate"
                else:
                    description = ac.get("description", "")
                    timestamp = ac.get("timestamp")
                    if timestamp is not None:
                        timestamp += shot_start
                    duration = ac.get("duration")
                    category = ac.get("category", categorize_cue(description))
                    intensity = ac.get("intensity", infer_intensity(description))
                
                cue_id = f"{scene_id}_cue_{cue_counter:03d}"
                cue_counter += 1
                
                cues.append(SFXCue(
                    cue_id=cue_id,
                    scene_id=scene_id,
                    description=description,
                    category=category,
                    timestamp_hint=timestamp,
                    duration_hint=duration,
                    intensity=intensity,
                    source_line=str(ac),
                ))
    
    logger.info(f"Extracted {len(cues)} SFX cues from storyboard")
    return cues


def merge_cues(
    script_cues: List[SFXCue],
    storyboard_cues: List[SFXCue]
) -> List[SFXCue]:
    """
    Combine and deduplicate cues from script and storyboard.
    
    Storyboard cues take precedence for timing information.
    """
    # Build index by scene_id + description similarity
    merged = {}
    
    # Add script cues first
    for cue in script_cues:
        key = (cue.scene_id, cue.description.lower()[:50])
        merged[key] = cue
    
    # Storyboard cues override/enhance
    for cue in storyboard_cues:
        key = (cue.scene_id, cue.description.lower()[:50])
        if key in merged:
            # Enhance existing cue with timing from storyboard
            existing = merged[key]
            if cue.timestamp_hint is not None:
                existing.timestamp_hint = cue.timestamp_hint
            if cue.duration_hint is not None:
                existing.duration_hint = cue.duration_hint
        else:
            merged[key] = cue
    
    # Sort by scene_id and timestamp
    result = sorted(
        merged.values(),
        key=lambda c: (c.scene_id, c.timestamp_hint or 999999)
    )
    
    logger.info(f"Merged to {len(result)} unique SFX cues")
    return result


def get_scenes_from_cues(cues: List[SFXCue]) -> Dict[str, List[SFXCue]]:
    """Group cues by scene_id."""
    scenes = {}
    for cue in cues:
        if cue.scene_id not in scenes:
            scenes[cue.scene_id] = []
        scenes[cue.scene_id].append(cue)
    return scenes
