"""
Screenplay Parser for create-storyboard skill.

Parses screenplay markdown (from /create-story) into structured scene data.
Handles Fountain-style format and markdown with embedded notes.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class DialogueLine:
    """A line of dialogue."""
    character: str
    text: str
    parenthetical: Optional[str] = None


@dataclass
class ActionBlock:
    """An action/description block."""
    text: str


@dataclass
class SceneHeading:
    """Scene heading (slug line)."""
    int_ext: str  # INT. or EXT.
    location: str
    time: str  # DAY, NIGHT, etc.
    raw: str


@dataclass
class Scene:
    """A complete scene with all elements."""
    number: int
    heading: SceneHeading
    elements: list  # Mix of DialogueLine, ActionBlock
    notes: dict = field(default_factory=dict)  # Embedded notes (lighting, references, etc.)
    duration_estimate: float = 0.0  # Estimated duration in seconds


@dataclass
class Screenplay:
    """Complete parsed screenplay."""
    title: str
    scenes: list[Scene]
    metadata: dict = field(default_factory=dict)


# Regex patterns for Fountain-style screenplay parsing
SCENE_HEADING_PATTERN = re.compile(
    r'^(INT\.|EXT\.|INT/EXT\.|I/E\.)\s*(.+?)\s*[-–—]\s*(.+?)$',
    re.IGNORECASE | re.MULTILINE
)

# Alternative: Simpler scene heading (just INT./EXT. location)
SIMPLE_SCENE_HEADING = re.compile(
    r'^(INT\.|EXT\.|INT/EXT\.|I/E\.)\s*(.+?)$',
    re.IGNORECASE | re.MULTILINE
)

# Character name (ALL CAPS, optionally with parenthetical)
CHARACTER_PATTERN = re.compile(r'^([A-Z][A-Z\s]+)(?:\s*\((.+?)\))?$')

# Parenthetical (direction for actor)
PARENTHETICAL_PATTERN = re.compile(r'^\((.+?)\)$')

# Note markers (embedded comments for storyboarding)
NOTE_PATTERN = re.compile(r'^\[NOTE:\s*(.+?)\]$', re.IGNORECASE)
LIGHTING_NOTE = re.compile(r'^\[LIGHTING:\s*(.+?)\]$', re.IGNORECASE)  
CAMERA_NOTE = re.compile(r'^\[CAMERA:\s*(.+?)\]$', re.IGNORECASE)
REFERENCE_NOTE = re.compile(r'^\[REF:\s*(.+?)\]$', re.IGNORECASE)
BEAT_NOTE = re.compile(r'^\[BEAT:\s*(.+?)\]$', re.IGNORECASE)


def parse_scene_heading(line: str) -> Optional[SceneHeading]:
    """Parse a scene heading line."""
    # Try full format first: INT. LOCATION - TIME
    match = SCENE_HEADING_PATTERN.match(line.strip())
    if match:
        return SceneHeading(
            int_ext=match.group(1).upper(),
            location=match.group(2).strip(),
            time=match.group(3).strip(),
            raw=line.strip()
        )
    
    # Try simple format: INT. LOCATION
    match = SIMPLE_SCENE_HEADING.match(line.strip())
    if match:
        return SceneHeading(
            int_ext=match.group(1).upper(),
            location=match.group(2).strip(),
            time="",
            raw=line.strip()
        )
    
    return None


def parse_screenplay(content: str, title: str = "Untitled") -> Screenplay:
    """
    Parse screenplay markdown content into structured data.
    
    Args:
        content: Screenplay text in markdown/Fountain format
        title: Title of the screenplay
        
    Returns:
        Screenplay object with parsed scenes
    """
    lines = content.split('\n')
    scenes: list[Scene] = []
    current_scene: Optional[Scene] = None
    current_character: Optional[str] = None
    scene_number = 0
    
    metadata = {}
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            current_character = None
            i += 1
            continue
        
        # Check for scene heading
        heading = parse_scene_heading(stripped)
        if heading:
            # Save previous scene
            if current_scene:
                scenes.append(current_scene)
            
            scene_number += 1
            current_scene = Scene(
                number=scene_number,
                heading=heading,
                elements=[],
                notes={}
            )
            current_character = None
            i += 1
            continue
        
        # Check for note markers
        note_match = NOTE_PATTERN.match(stripped)
        if note_match and current_scene:
            current_scene.notes.setdefault('general', []).append(note_match.group(1))
            i += 1
            continue
            
        lighting_match = LIGHTING_NOTE.match(stripped)
        if lighting_match and current_scene:
            current_scene.notes.setdefault('lighting', []).append(lighting_match.group(1))
            i += 1
            continue
            
        camera_match = CAMERA_NOTE.match(stripped)
        if camera_match and current_scene:
            current_scene.notes.setdefault('camera', []).append(camera_match.group(1))
            i += 1
            continue
            
        ref_match = REFERENCE_NOTE.match(stripped)
        if ref_match and current_scene:
            current_scene.notes.setdefault('references', []).append(ref_match.group(1))
            i += 1
            continue
            
        beat_match = BEAT_NOTE.match(stripped)
        if beat_match and current_scene:
            current_scene.notes.setdefault('beats', []).append(beat_match.group(1))
            i += 1
            continue
        
        # Check for character name (ALL CAPS)
        char_match = CHARACTER_PATTERN.match(stripped)
        if char_match and current_scene:
            current_character = char_match.group(1).strip()
            # Next line should be dialogue
            i += 1
            continue
        
        # If we have a current character, this is dialogue
        if current_character and current_scene:
            # Check for parenthetical first
            paren_match = PARENTHETICAL_PATTERN.match(stripped)
            if paren_match:
                # Store parenthetical for next dialogue line
                parenthetical = paren_match.group(1)
                i += 1
                # Get actual dialogue on next line
                if i < len(lines) and lines[i].strip():
                    dialogue = DialogueLine(
                        character=current_character,
                        text=lines[i].strip(),
                        parenthetical=parenthetical
                    )
                    current_scene.elements.append(dialogue)
                    i += 1
                continue
            else:
                # This is regular dialogue
                dialogue = DialogueLine(
                    character=current_character,
                    text=stripped
                )
                current_scene.elements.append(dialogue)
                i += 1
                continue
        
        # Otherwise, it's action/description
        if current_scene:
            current_scene.elements.append(ActionBlock(text=stripped))
        
        i += 1
    
    # Don't forget the last scene
    if current_scene:
        scenes.append(current_scene)
    
    # Estimate durations
    for scene in scenes:
        scene.duration_estimate = estimate_scene_duration(scene)
    
    return Screenplay(
        title=title,
        scenes=scenes,
        metadata=metadata
    )


def estimate_scene_duration(scene: Scene) -> float:
    """
    Estimate scene duration in seconds.
    
    Rules of thumb:
    - 1 page of screenplay ≈ 1 minute of screen time
    - 1 line of dialogue ≈ 2-3 seconds
    - 1 action line ≈ 3-5 seconds
    """
    duration = 0.0
    
    for element in scene.elements:
        if isinstance(element, DialogueLine):
            # Rough estimate: 3 words per second
            words = len(element.text.split())
            duration += words / 3.0
        elif isinstance(element, ActionBlock):
            # Action takes longer - estimate based on length
            words = len(element.text.split())
            duration += words / 2.0  # Action is slower to show
    
    # Minimum 3 seconds per scene
    return max(3.0, duration)


def screenplay_to_dict(screenplay: Screenplay) -> dict:
    """Convert screenplay to JSON-serializable dict."""
    def element_to_dict(elem):
        if isinstance(elem, DialogueLine):
            return {
                "type": "dialogue",
                "character": elem.character,
                "text": elem.text,
                "parenthetical": elem.parenthetical
            }
        elif isinstance(elem, ActionBlock):
            return {
                "type": "action",
                "text": elem.text
            }
        return {}
    
    return {
        "title": screenplay.title,
        "metadata": screenplay.metadata,
        "scenes": [
            {
                "number": scene.number,
                "heading": asdict(scene.heading),
                "elements": [element_to_dict(e) for e in scene.elements],
                "notes": scene.notes,
                "duration_estimate": scene.duration_estimate
            }
            for scene in screenplay.scenes
        ]
    }


def parse_file(filepath: Path) -> Screenplay:
    """Parse a screenplay file."""
    content = filepath.read_text()
    title = filepath.stem.replace('_', ' ').title()
    return parse_screenplay(content, title)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        # Demo with sample content
        sample = """
# Test Screenplay

INT. APARTMENT - NIGHT

[LIGHTING: Low key, practical desk lamp only]
[CAMERA: Start wide, slowly push in]
[REF: Blade Runner 2049 apartment scene]

SARAH enters the dark apartment, flipping on a small desk lamp.

SARAH
(whispering)
Hello? Is anyone here?

[BEAT: Tension building]

She moves cautiously through the room.

MYSTERIOUS VOICE (O.S.)
I've been waiting for you.

Sarah spins around, fear in her eyes.

EXT. CITY STREET - DAY

[NOTE: Fast-paced montage sequence]

Cars rush by. People hurry along the sidewalk.

SARAH walks determinedly, phone pressed to her ear.

SARAH
I need backup. Now.
"""
        screenplay = parse_screenplay(sample, "Test Screenplay")
        print(json.dumps(screenplay_to_dict(screenplay), indent=2))
    else:
        # Parse specified file
        filepath = Path(sys.argv[1])
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        
        screenplay = parse_file(filepath)
        output = json.dumps(screenplay_to_dict(screenplay), indent=2)
        
        # Output to file or stdout
        if len(sys.argv) > 2 and sys.argv[2] == "--output":
            output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else filepath.with_suffix('.json')
            output_path.write_text(output)
            print(f"Wrote to {output_path}")
        else:
            print(output)
