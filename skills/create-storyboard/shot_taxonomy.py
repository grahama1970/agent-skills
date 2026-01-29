"""
Camera Shot Taxonomy for create-storyboard skill.

Provides classification system for cinematographic shots based on
field size, camera placement, and narrative purpose.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ShotSize(Enum):
    """Shot size classification based on field size."""
    EXTREME_WIDE = "EWS"
    WIDE = "WS"
    FULL = "FS"
    MEDIUM_WIDE = "MWS"
    MEDIUM = "MS"
    MEDIUM_CLOSEUP = "MCU"
    CLOSEUP = "CU"
    EXTREME_CLOSEUP = "ECU"


class ShotType(Enum):
    """Special shot types based on camera placement."""
    ESTABLISHING = "EST"
    OVER_THE_SHOULDER = "OTS"
    POINT_OF_VIEW = "POV"
    TWO_SHOT = "2S"
    MASTER = "MASTER"
    DUTCH_ANGLE = "DUTCH"
    TRACKING = "TRACK"
    DOLLY = "DOLLY"


class CameraMovement(Enum):
    """Camera movement types."""
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    DOLLY = "dolly"
    TRACKING = "tracking"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    HANDHELD = "handheld"


@dataclass
class ShotDefinition:
    """Complete shot definition with metadata."""
    code: str
    name: str
    emotion: str
    use_case: str
    framing_guide: str
    typical_lens: str = "50mm"
    

SHOT_TAXONOMY: dict[str, ShotDefinition] = {
    "EWS": ShotDefinition(
        code="EWS",
        name="Extreme Wide Shot",
        emotion="scale, isolation, grandeur",
        use_case="establishing, showing environment",
        framing_guide="Subject very small in frame, environment dominates",
        typical_lens="14-24mm"
    ),
    "WS": ShotDefinition(
        code="WS",
        name="Wide Shot",
        emotion="context, space",
        use_case="scene introduction, geography",
        framing_guide="Full body with significant environment",
        typical_lens="24-35mm"
    ),
    "FS": ShotDefinition(
        code="FS",
        name="Full Shot",
        emotion="action, physicality",
        use_case="physical action, dance, fight",
        framing_guide="Head to toe, minimal headroom",
        typical_lens="35-50mm"
    ),
    "MWS": ShotDefinition(
        code="MWS",
        name="Medium Wide Shot",
        emotion="tension, anticipation",
        use_case="standoff, western cowboy shot",
        framing_guide="Knee to head, shows holster/hands",
        typical_lens="50mm"
    ),
    "MS": ShotDefinition(
        code="MS",
        name="Medium Shot",
        emotion="conversation, connection",
        use_case="dialogue, interview",
        framing_guide="Waist to head",
        typical_lens="50-85mm"
    ),
    "MCU": ShotDefinition(
        code="MCU",
        name="Medium Close-Up",
        emotion="engagement, attention",
        use_case="monologue, important dialogue",
        framing_guide="Chest to head",
        typical_lens="85mm"
    ),
    "CU": ShotDefinition(
        code="CU",
        name="Close-Up",
        emotion="intimacy, vulnerability",
        use_case="emotional moments, reactions",
        framing_guide="Face fills frame",
        typical_lens="85-135mm"
    ),
    "ECU": ShotDefinition(
        code="ECU",
        name="Extreme Close-Up",
        emotion="intensity, detail",
        use_case="eyes, hands, objects",
        framing_guide="Single feature fills frame",
        typical_lens="100-200mm"
    ),
    "OTS": ShotDefinition(
        code="OTS",
        name="Over-The-Shoulder",
        emotion="perspective, connection",
        use_case="dialogue between characters",
        framing_guide="Back of one head, face of other",
        typical_lens="50-85mm"
    ),
    "POV": ShotDefinition(
        code="POV",
        name="Point-of-View",
        emotion="immersion, subjectivity",
        use_case="character perspective",
        framing_guide="What character sees",
        typical_lens="varies"
    ),
}


# Emotion to shot mapping for auto-selection
EMOTION_SHOT_MAP: dict[str, list[str]] = {
    "emotional": ["CU", "ECU", "MCU"],
    "intimate": ["CU", "MCU"],
    "tense": ["MWS", "CU", "OTS"],
    "action": ["WS", "FS", "TRACK"],
    "establishing": ["EWS", "WS"],
    "dialogue": ["MS", "MCU", "OTS"],
    "revelation": ["ECU", "CU"],
    "isolation": ["EWS", "WS"],
    "confrontation": ["MWS", "OTS", "CU"],
    "peaceful": ["WS", "MS"],
}

# Scene type to shot sequence patterns
SCENE_PATTERNS: dict[str, list[str]] = {
    "intro": ["EWS", "WS", "MS"],           # Wide to medium progression
    "dialogue": ["MS", "OTS", "CU", "OTS"], # Standard coverage pattern
    "action": ["WS", "FS", "CU", "WS"],     # Context → action → detail → context
    "emotional": ["MS", "MCU", "CU", "ECU"], # Progressive intimacy
    "reveal": ["WS", "MS", "CU", "ECU"],    # Build to detail
    "chase": ["WS", "TRACK", "POV", "CU"],  # Dynamic sequence
}


def auto_select_shot(
    scene_type: str,
    emotion: Optional[str] = None,
    beat_position: str = "middle"  # "opening", "middle", "climax", "closing"
) -> str:
    """
    Auto-select appropriate shot based on scene context.
    
    Args:
        scene_type: Type of scene (dialogue, action, emotional, etc.)
        emotion: Optional emotional tone override
        beat_position: Position in scene arc
        
    Returns:
        Shot code (e.g., "MS", "CU")
    """
    # If emotion specified, prioritize that
    if emotion and emotion.lower() in EMOTION_SHOT_MAP:
        shots = EMOTION_SHOT_MAP[emotion.lower()]
        # Select based on beat position
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
    
    # Default to medium shot
    return "MS"


def get_shot_definition(code: str) -> Optional[ShotDefinition]:
    """Get full shot definition by code."""
    return SHOT_TAXONOMY.get(code.upper())


def suggest_camera_movement(
    shot_code: str,
    scene_energy: str = "normal"  # "low", "normal", "high"
) -> CameraMovement:
    """
    Suggest camera movement based on shot type and scene energy.
    
    Args:
        shot_code: Shot type code
        scene_energy: Energy level of scene
        
    Returns:
        Suggested camera movement
    """
    if scene_energy == "high":
        return CameraMovement.HANDHELD if shot_code in ["CU", "MCU"] else CameraMovement.TRACKING
    elif scene_energy == "low":
        return CameraMovement.STATIC
    else:
        # Normal energy - subtle movement
        if shot_code in ["CU", "ECU"]:
            return CameraMovement.PUSH_IN
        elif shot_code in ["EWS", "WS"]:
            return CameraMovement.PAN_RIGHT
        else:
            return CameraMovement.STATIC


if __name__ == "__main__":
    # Quick test
    print("Shot Taxonomy Test")
    print("=" * 40)
    
    for code, definition in SHOT_TAXONOMY.items():
        print(f"{code}: {definition.name}")
        print(f"  Emotion: {definition.emotion}")
        print(f"  Use: {definition.use_case}")
        print()
    
    print("\nAuto-selection tests:")
    print(f"  Dialogue scene, opening: {auto_select_shot('dialogue', beat_position='opening')}")
    print(f"  Emotional scene, climax: {auto_select_shot('emotional', beat_position='climax')}")
    print(f"  Action scene, middle: {auto_select_shot('action', beat_position='middle')}")
