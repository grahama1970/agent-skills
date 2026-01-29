# Code Review Request: create-storyboard Skill

**Task**: Brutal review of the create-storyboard skill for brittle, aspirational, or overengineered code. Focus on ease of use and collaborative design.

## Review Focus Areas

### 1. Brittleness & Overengineering

- Are there features that are aspirational but don't work reliably?
- Is there unnecessary complexity for the current scope?
- Are there hardcoded assumptions that will break?

### 2. Ease of Use

- Is the CLI intuitive for agents calling it?
- Are error messages helpful?
- Is the skill self-documenting?

### 3. **CRITICAL: Collaborative Design**

- The skill currently runs autonomously with zero user interaction
- It SHOULD ask clarifying questions when parsing a screenplay:
  - "I found 5 scenes. Scene 3 has ambiguous emotional tone - is this tense or contemplative?"
  - "No camera notes found in screenplay. Should I auto-select all shots?"
  - "Scene 2 references 'Blade Runner lighting' - should I search /memory for this?"
- The skill MUST integrate with a project agent (like /create-movie) that mediates user interaction
- Currently: Parse → Auto-select → Generate → Done (no checkpoints)
- Should be: Parse → ASK → Plan → ASK → Generate → Review → Done

## Files to Review

### Core Implementation

```python
# FILE: screenplay_parser.py
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
            words = len(element.text.split())
            duration += words / 3.0
        elif isinstance(element, ActionBlock):
            words = len(element.text.split())
            duration += words / 2.0

    return max(3.0, duration)
```

---

```python
# FILE: camera_planner.py (key function)
def auto_select_shot(
    scene_type: str,
    emotion: Optional[str] = None,
    beat_position: str = "middle"
) -> str:
    """
    Auto-select appropriate shot based on scene context.

    PROBLEM: This is entirely automated with NO user input.
    Should this ask for confirmation on ambiguous scenes?
    """
    # If emotion specified, prioritize that
    if emotion and emotion.lower() in EMOTION_SHOT_MAP:
        shots = EMOTION_SHOT_MAP[emotion.lower()]
        if beat_position == "opening":
            return shots[0] if shots else "MS"
        elif beat_position == "climax":
            return shots[-1] if shots else "CU"
        else:
            return shots[len(shots) // 2] if shots else "MS"

    # Fall back to scene type patterns
    if scene_type.lower() in SCENE_PATTERNS:
        pattern = SCENE_PATTERNS[scene_type.lower()]
        position_map = {
            "opening": 0,
            "middle": len(pattern) // 2,
            "climax": -2 if len(pattern) > 2 else -1,
            "closing": -1
        }
        idx = position_map.get(beat_position, 1)
        return pattern[idx]

    return "MS"  # DEFAULT - no user consultation
```

---

```python
# FILE: orchestrator.py (main entry point)
@app.command()
def create(
    screenplay: Path = typer.Argument(...),
    output: Path = typer.Option(Path("animatic.mp4")),
    fidelity: str = typer.Option("sketch"),
    format: str = typer.Option("mp4"),
    duration: Optional[float] = typer.Option(None),
    store_learnings: bool = typer.Option(True)
):
    """
    PROBLEM: This runs end-to-end with ZERO checkpoints.
    No way for calling agent to:
    1. Review parsed scenes before planning
    2. Approve shot selections
    3. Preview panels before assembly
    """
    typer.echo(f"🎬 Creating storyboard from {screenplay}")

    # Phase 1: Parse - NO CHECKPOINT
    parsed = parse_file(screenplay)

    # Phase 2: Camera Planning - NO CHECKPOINT
    shot_plan = generate_shot_plan(scenes_data)

    # Phase 3: Generate Panels - NO CHECKPOINT
    panel_paths = generate_panels(plan_data, panels_dir, fidelity=fidelity)

    # Phase 4: Assemble - FINAL OUTPUT, TOO LATE TO CHANGE
    result = assemble(panels_dir, plan_path, output, format)
```

---

```python
# FILE: panel_generator.py (fidelity handling)
def generate_panels(
    shot_plan: dict,
    output_dir: Path,
    fidelity: str = 'sketch',
    config: Optional[PanelConfig] = None
) -> list[Path]:
    """
    PROBLEM: 'generated' fidelity is STUB CODE that just calls reference.
    This is aspirational - claims to integrate with /create-image but doesn't.
    """
    for shot in shot_plan.get('shots', []):
        if fidelity == 'sketch':
            generate_sketch_panel(shot, config, output_path)
        elif fidelity == 'reference':
            generate_reference_panel(shot, config, output_path)
        elif fidelity == 'generated':
            # For generated, we create a reference panel with a note
            # Actual AI generation would call /create-image skill
            generate_reference_panel(shot, config, output_path)  # <-- STUB!
            # TODO: Integrate with /create-image skill for AI generation
```

---

## Specific Questions for Reviewer

1. **Collaborative Checkpoints**: How should the skill pause and query the calling agent?
   - JSON output for structured questions?
   - Return partial results with "needs_input" flag?
   - Interactive mode vs batch mode?

2. **Aspirational Features**: Which should be removed vs stubbed clearly?
   - `fidelity=generated` doesn't work
   - `store_learnings` doesn't work
   - Memory integration is stubbed

3. **Error Handling**: The skill has almost no error handling for:
   - Empty screenplays
   - Missing fonts
   - FFmpeg failures
   - Invalid shot plan data

4. **Agent Integration**: How should this skill communicate with /create-movie?
   - CLI subprocess calls?
   - Python imports?
   - Shared data files?

## Expected Output

Please provide:

1. A list of **CRITICAL** issues that must be fixed
2. A list of **OVERENGINEERED** features to simplify
3. A list of **MISSING** features for collaborative use
4. Concrete recommendations for making this skill actually usable
