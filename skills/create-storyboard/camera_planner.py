"""
Camera Planner for create-storyboard skill.

Takes parsed screenplay scenes and generates a shot plan with
auto-selected camera shots based on scene emotion and beats.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from shot_taxonomy import (
    auto_select_shot, 
    get_shot_definition, 
    suggest_camera_movement,
    ShotDefinition,
    CameraMovement,
    SHOT_TAXONOMY
)


@dataclass
class Shot:
    """A single shot in the storyboard."""
    scene_number: int
    shot_number: int
    shot_code: str  # e.g., "MS", "CU"
    shot_name: str  # e.g., "Medium Shot"
    description: str  # What's happening in this shot
    duration: float  # Estimated duration in seconds
    camera_movement: str  # e.g., "static", "push_in"
    framing_guide: str
    lens_suggestion: str
    emotion: str
    notes: dict  # Lighting, camera notes from screenplay


@dataclass
class ShotPlan:
    """Complete shot plan for a screenplay."""
    title: str
    total_duration: float
    total_shots: int
    shots: list[Shot]
    metadata: dict


def analyze_scene_emotion(scene: dict) -> str:
    """
    Analyze scene content to determine dominant emotion.
    
    Returns one of: emotional, tense, action, dialogue, peaceful, establishing
    """
    elements = scene.get('elements', [])
    notes = scene.get('notes', {})
    heading = scene.get('heading', {})
    
    # Check notes for explicit beats
    beats = notes.get('beats', [])
    for beat in beats:
        beat_lower = beat.lower()
        if 'tension' in beat_lower or 'tense' in beat_lower:
            return 'tense'
        if 'emotion' in beat_lower or 'sad' in beat_lower or 'cry' in beat_lower:
            return 'emotional'
        if 'action' in beat_lower or 'chase' in beat_lower or 'fight' in beat_lower:
            return 'action'
    
    # Analyze elements
    dialogue_count = sum(1 for e in elements if e.get('type') == 'dialogue')
    action_count = sum(1 for e in elements if e.get('type') == 'action')
    
    # Check for action keywords
    action_keywords = ['runs', 'fights', 'chases', 'jumps', 'crashes', 'explodes']
    for elem in elements:
        text = elem.get('text', '').lower()
        if any(kw in text for kw in action_keywords):
            return 'action'
    
    # Check for emotional keywords
    emotional_keywords = ['tears', 'cries', 'hugs', 'kisses', 'whispers', 'trembles']
    for elem in elements:
        text = elem.get('text', '').lower()
        if any(kw in text for kw in emotional_keywords):
            return 'emotional'
    
    # Default based on element ratio
    if dialogue_count > action_count * 2:
        return 'dialogue'
    elif action_count > dialogue_count * 2:
        return 'action'
    elif len(elements) < 3:
        return 'establishing'
    
    return 'dialogue'  # Default


def determine_beat_position(element_index: int, total_elements: int) -> str:
    """Determine position in scene arc."""
    if total_elements == 0:
        return 'middle'
    
    position = element_index / max(1, total_elements - 1)
    
    if position < 0.2:
        return 'opening'
    elif position > 0.8:
        return 'closing'
    elif 0.4 < position < 0.7:
        return 'climax'
    else:
        return 'middle'


def generate_shot_plan(screenplay_data: dict) -> ShotPlan:
    """
    Generate a complete shot plan from parsed screenplay data.
    
    Args:
        screenplay_data: Dict from screenplay_parser
        
    Returns:
        ShotPlan with all shots
    """
    title = screenplay_data.get('title', 'Untitled')
    shots: list[Shot] = []
    total_duration = 0.0
    
    for scene in screenplay_data.get('scenes', []):
        scene_number = scene.get('number', 0)
        elements = scene.get('elements', [])
        notes = scene.get('notes', {})
        heading = scene.get('heading', {})
        
        # Analyze scene emotion
        scene_emotion = analyze_scene_emotion(scene)
        
        # Group elements into shots
        # Rule: Each major beat gets its own shot
        shot_number = 0
        current_shot_elements = []
        
        for i, element in enumerate(elements):
            current_shot_elements.append(element)
            
            # Decide when to create a new shot
            create_shot = False
            
            # New shot on dialogue change
            if element.get('type') == 'dialogue':
                # Check if next element is different character
                if i + 1 < len(elements):
                    next_elem = elements[i + 1]
                    if next_elem.get('type') == 'dialogue':
                        if next_elem.get('character') != element.get('character'):
                            create_shot = True
                else:
                    create_shot = True
            
            # New shot after significant action
            if element.get('type') == 'action':
                text = element.get('text', '')
                if len(text) > 100:  # Long action = separate shot
                    create_shot = True
            
            # Create shot every 3 elements at minimum
            if len(current_shot_elements) >= 3:
                create_shot = True
            
            if create_shot and current_shot_elements:
                shot_number += 1
                beat_position = determine_beat_position(i, len(elements))
                
                # Auto-select shot type
                shot_code = auto_select_shot(
                    scene_type=scene_emotion,
                    emotion=scene_emotion,
                    beat_position=beat_position
                )
                
                shot_def = get_shot_definition(shot_code) or SHOT_TAXONOMY.get('MS')
                camera_movement = suggest_camera_movement(shot_code, 'normal')
                
                # Build description from elements
                description_parts = []
                for elem in current_shot_elements:
                    if elem.get('type') == 'dialogue':
                        description_parts.append(
                            f"{elem.get('character')}: \"{elem.get('text')[:50]}...\""
                            if len(elem.get('text', '')) > 50
                            else f"{elem.get('character')}: \"{elem.get('text')}\""
                        )
                    else:
                        description_parts.append(elem.get('text', '')[:100])
                
                description = ' | '.join(description_parts)
                
                # Estimate duration
                duration = sum(
                    len(e.get('text', '').split()) / 3.0 
                    for e in current_shot_elements
                )
                duration = max(2.0, min(10.0, duration))  # Clamp between 2-10 seconds
                
                shot = Shot(
                    scene_number=scene_number,
                    shot_number=shot_number,
                    shot_code=shot_code,
                    shot_name=shot_def.name if shot_def else shot_code,
                    description=description,
                    duration=duration,
                    camera_movement=camera_movement.value if isinstance(camera_movement, CameraMovement) else str(camera_movement),
                    framing_guide=shot_def.framing_guide if shot_def else "",
                    lens_suggestion=shot_def.typical_lens if shot_def else "50mm",
                    emotion=scene_emotion,
                    notes={
                        'lighting': notes.get('lighting', []),
                        'camera': notes.get('camera', []),
                        'references': notes.get('references', [])
                    }
                )
                shots.append(shot)
                total_duration += duration
                current_shot_elements = []
        
        # Handle remaining elements
        if current_shot_elements:
            shot_number += 1
            shot_code = auto_select_shot(scene_emotion, beat_position='closing')
            shot_def = get_shot_definition(shot_code)
            
            description = ' | '.join(
                e.get('text', '')[:50] for e in current_shot_elements
            )
            duration = max(2.0, scene.get('duration_estimate', 3.0) / max(1, shot_number))
            
            shot = Shot(
                scene_number=scene_number,
                shot_number=shot_number,
                shot_code=shot_code,
                shot_name=shot_def.name if shot_def else shot_code,
                description=description,
                duration=duration,
                camera_movement='static',
                framing_guide=shot_def.framing_guide if shot_def else "",
                lens_suggestion=shot_def.typical_lens if shot_def else "50mm",
                emotion=scene_emotion,
                notes={}
            )
            shots.append(shot)
            total_duration += duration
    
    return ShotPlan(
        title=title,
        total_duration=total_duration,
        total_shots=len(shots),
        shots=shots,
        metadata={
            'scenes_count': len(screenplay_data.get('scenes', [])),
            'auto_generated': True
        }
    )


def shot_plan_to_dict(plan: ShotPlan) -> dict:
    """Convert shot plan to JSON-serializable dict."""
    return {
        'title': plan.title,
        'total_duration': plan.total_duration,
        'total_shots': plan.total_shots,
        'metadata': plan.metadata,
        'shots': [asdict(shot) for shot in plan.shots]
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        # Demo with inline data
        sample_screenplay = {
            "title": "Test Screenplay",
            "scenes": [
                {
                    "number": 1,
                    "heading": {"int_ext": "INT.", "location": "APARTMENT", "time": "NIGHT"},
                    "elements": [
                        {"type": "action", "text": "Sarah enters the dark apartment."},
                        {"type": "dialogue", "character": "SARAH", "text": "Hello? Is anyone here?"},
                        {"type": "action", "text": "She moves cautiously through the room."},
                        {"type": "dialogue", "character": "VOICE", "text": "I've been waiting for you."},
                        {"type": "action", "text": "Sarah spins around, fear in her eyes."}
                    ],
                    "notes": {
                        "lighting": ["Low key, practical desk lamp only"],
                        "camera": ["Start wide, slowly push in"],
                        "beats": ["Tension building"]
                    },
                    "duration_estimate": 15.0
                }
            ]
        }
        
        plan = generate_shot_plan(sample_screenplay)
        print(json.dumps(shot_plan_to_dict(plan), indent=2))
    else:
        # Load from file
        filepath = Path(sys.argv[1])
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        
        screenplay_data = json.loads(filepath.read_text())
        plan = generate_shot_plan(screenplay_data)
        output = json.dumps(shot_plan_to_dict(plan), indent=2)
        
        # Output
        if len(sys.argv) > 2 and sys.argv[2] == "--output":
            output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else filepath.with_name('shot_plan.json')
            output_path.write_text(output)
            print(f"Wrote to {output_path}")
        else:
            print(output)
