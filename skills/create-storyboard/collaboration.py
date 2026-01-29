"""
Collaboration Module for create-storyboard skill.

Provides question generation, session state management, and structured
output for human-agent collaboration during storyboard creation.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any
import uuid


class Phase(str, Enum):
    """Storyboard creation phases."""
    PARSE = "parse"
    CAMERA_PLAN = "camera_plan"
    GENERATE_PANELS = "generate_panels"
    ASSEMBLE = "assemble"
    COMPLETE = "complete"


class QuestionType(str, Enum):
    """Types of questions to ask."""
    EMOTION = "emotion"
    REFERENCE = "reference"
    CAMERA = "camera"
    APPROVAL = "approval"
    CONFIRMATION = "confirmation"


@dataclass
class Question:
    """A question for human/agent clarification."""
    id: str
    scene_number: int
    question_type: QuestionType
    question: str
    options: list[str] = field(default_factory=list)
    default: Optional[str] = None
    context: Optional[str] = None
    
    def to_dict(self) -> dict:
        # Handle both enum and string question_type
        q_type = self.question_type
        if hasattr(q_type, 'value'):
            q_type = q_type.value
        
        return {
            "id": self.id,
            "scene_number": self.scene_number,
            "question_type": q_type,
            "question": self.question,
            "options": self.options,
            "default": self.default,
            "context": self.context
        }


@dataclass
class SessionState:
    """Persisted state for multi-step workflow."""
    session_id: str
    phase: Phase
    screenplay_path: str
    created_at: str
    updated_at: str
    parsed_scenes: Optional[dict] = None
    shot_plan: Optional[dict] = None
    panels: list[str] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    answers: dict = field(default_factory=dict)
    output_path: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        data['phase'] = Phase(data['phase'])
        return cls(**data)


@dataclass
class StoryboardResult:
    """Structured output for agent communication."""
    status: str  # "needs_input", "in_progress", "complete", "error"
    phase: Phase
    session_id: str
    questions: list[Question] = field(default_factory=list)
    partial_results: Optional[dict] = None
    output_files: list[str] = field(default_factory=list)
    message: str = ""
    resume_command: str = ""
    
    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "phase": self.phase.value,
            "session_id": self.session_id,
            "questions": [q.to_dict() for q in self.questions],
            "partial_results": self.partial_results,
            "output_files": self.output_files,
            "message": self.message,
            "resume_command": self.resume_command
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"storyboard-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def save_session(session: SessionState, output_dir: Path) -> Path:
    """Save session state to file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    session.updated_at = datetime.now().isoformat()
    session_path = output_dir / f"session_{session.session_id}.json"
    session_path.write_text(json.dumps(session.to_dict(), indent=2))
    return session_path


def load_session(session_path: Path) -> SessionState:
    """Load session state from file."""
    data = json.loads(session_path.read_text())
    return SessionState.from_dict(data)


def find_session(session_id: str, search_dir: Path) -> Optional[Path]:
    """Find a session file by ID."""
    pattern = f"session_{session_id}.json"
    for path in search_dir.rglob(pattern):
        return path
    # Also try partial match
    for path in search_dir.rglob("session_*.json"):
        if session_id in path.name:
            return path
    return None


def analyze_screenplay_ambiguities(parsed_scenes: dict) -> list[Question]:
    """
    Analyze parsed screenplay for ambiguities that need human clarification.
    
    Returns a list of questions the agent should ask before proceeding.
    """
    questions = []
    scene_count = 0
    
    for scene in parsed_scenes.get('scenes', []):
        scene_num = scene.get('number', scene_count + 1)
        scene_count += 1
        notes = scene.get('notes', {})
        elements = scene.get('elements', [])
        heading = scene.get('heading', {})
        
        # 1. Check for missing emotion/beat markers
        if not notes.get('beats') and len(elements) > 2:
            # Analyze content to suggest likely emotion
            dialogue_count = sum(1 for e in elements if e.get('type') == 'dialogue')
            action_count = sum(1 for e in elements if e.get('type') == 'action')
            
            if dialogue_count > action_count * 2:
                suggested = "dialogue"
            elif action_count > dialogue_count * 2:
                suggested = "action"
            else:
                suggested = "dialogue"  # Default
            
            questions.append(Question(
                id=f"emotion_s{scene_num}",
                scene_number=scene_num,
                question_type=QuestionType.EMOTION,
                question=f"Scene {scene_num} ({heading.get('location', 'Unknown')}) has no emotional beat markers. What is the dominant emotion?",
                options=["tense", "emotional", "action", "dialogue", "peaceful", "contemplative"],
                default=suggested,
                context=f"Scene has {dialogue_count} dialogue lines and {action_count} action blocks."
            ))
        
        # 2. Check for film/reference notes that could use memory lookup
        for ref in notes.get('references', []):
            questions.append(Question(
                id=f"ref_s{scene_num}_{len(questions)}",
                scene_number=scene_num,
                question_type=QuestionType.REFERENCE,
                question=f"Scene {scene_num} references '{ref}'. Should I search /memory for learned techniques from this film?",
                options=["yes_search_memory", "no_skip", "skip_all_references"],
                default="yes_search_memory",
                context=f"The [REF: {ref}] note suggests this scene should emulate a known film."
            ))
        
        # 3. Check for missing camera notes on long scenes
        if not notes.get('camera') and len(elements) > 5:
            questions.append(Question(
                id=f"camera_s{scene_num}",
                scene_number=scene_num,
                question_type=QuestionType.CAMERA,
                question=f"Scene {scene_num} is substantial ({len(elements)} elements) but has no [CAMERA:] notes. Should I auto-select camera shots?",
                options=["auto_select", "use_defaults", "ask_per_shot"],
                default="auto_select",
                context="Without camera guidance, I'll use the shot taxonomy to auto-select based on scene emotion."
            ))
        
        # 4. Check for ambiguous INT/EXT
        if heading.get('int_ext', '').upper() == 'INT/EXT.':
            questions.append(Question(
                id=f"location_s{scene_num}",
                scene_number=scene_num,
                question_type=QuestionType.CONFIRMATION,
                question=f"Scene {scene_num} is marked INT/EXT ({heading.get('location', '')}). Does the scene transition from interior to exterior, or should I treat it as primarily one or the other?",
                options=["interior_primary", "exterior_primary", "transition_both"],
                default="transition_both"
            ))
    
    return questions


def analyze_shot_plan_for_approval(shot_plan: dict) -> list[Question]:
    """
    Analyze shot plan and generate approval questions for unusual choices.
    """
    questions = []
    shots = shot_plan.get('shots', [])
    
    # Group shots by scene
    scenes = {}
    for shot in shots:
        scene_num = shot.get('scene_number', 1)
        if scene_num not in scenes:
            scenes[scene_num] = []
        scenes[scene_num].append(shot)
    
    for scene_num, scene_shots in scenes.items():
        # Check for many close-ups in a row
        consecutive_cu = 0
        for shot in scene_shots:
            code = shot.get('shot_code', '')
            if code in ['CU', 'ECU', 'MCU']:
                consecutive_cu += 1
            else:
                consecutive_cu = 0
            
            if consecutive_cu >= 3:
                questions.append(Question(
                    id=f"approval_cu_s{scene_num}",
                    scene_number=scene_num,
                    question_type=QuestionType.APPROVAL,
                    question=f"Scene {scene_num} has {consecutive_cu}+ consecutive close-ups. This creates an intimate/intense feel. Is this intentional?",
                    options=["approve", "add_wide_shot", "vary_shots"],
                    default="approve"
                ))
                break  # Only ask once per scene
        
        # Check for very long estimated duration
        total_duration = sum(s.get('duration', 0) for s in scene_shots)
        if total_duration > 30:
            questions.append(Question(
                id=f"approval_duration_s{scene_num}",
                scene_number=scene_num,
                question_type=QuestionType.APPROVAL,
                question=f"Scene {scene_num} is estimated at {total_duration:.1f} seconds ({len(scene_shots)} shots). This is quite long. Should I tighten the pacing?",
                options=["keep_as_is", "tighten_timing", "split_scene"],
                default="keep_as_is"
            ))
    
    return questions


def format_questions_for_display(questions: list[Question]) -> str:
    """Format questions for human-readable display."""
    if not questions:
        return "No questions - proceeding with defaults.\n"
    
    lines = [f"\n{'='*60}", "📋 QUESTIONS REQUIRING INPUT", f"{'='*60}\n"]
    
    for i, q in enumerate(questions, 1):
        # Handle both enum and string question_type
        q_type = q.question_type
        if hasattr(q_type, 'value'):
            q_type = q_type.value
        lines.append(f"{i}. [{q_type.upper()}] Scene {q.scene_number}")
        lines.append(f"   {q.question}")
        if q.context:
            lines.append(f"   Context: {q.context}")
        lines.append(f"   Options: {', '.join(q.options)}")
        lines.append(f"   Default: {q.default or 'none'}")
        lines.append("")
    
    lines.append(f"{'='*60}")
    lines.append("To provide answers, use:")
    lines.append("  ./run.sh resume --session <ID> --answers '{\"emotion_s1\": \"tense\", ...}'")
    lines.append(f"{'='*60}\n")
    
    return "\n".join(lines)


def apply_answers_to_scenes(parsed_scenes: dict, answers: dict) -> tuple[dict, list[str]]:
    """
    Apply user answers to modify parsed scene data.
    Returns (modified_scenes, invalid_ids).
    """
    scenes = parsed_scenes.copy()
    invalid_ids = []
    
    # Track which IDs were actually used/valid
    valid_ids = []
    questions = parsed_scenes.get('_questions', []) # Optional cache of current questions
    
    for question_id, answer in answers.items():
        if question_id == '_config': # Internal config, not a question
            continue
            
        parts = question_id.split('_')
        if len(parts) < 2:
            invalid_ids.append(question_id)
            continue
            
        q_type = parts[0]
        # Handle suggestions: suggestion_1, suggestion_s1_...
        scene_num = None
        
        # Try to find scene number in ID
        for part in parts:
            if part.startswith('s') and len(part) > 1:
                try:
                    scene_num = int(part[1:])
                    break
                except ValueError:
                    continue
        
        if scene_num is None:
            # Maybe it's a direct suggestion index: suggestion_0
            try:
                if q_type == 'suggestion':
                    # Logic to find scene from suggestion index if needed
                    pass 
                # For now, if no scene_num, we can't map it easily to parsed_scenes
                invalid_ids.append(question_id)
                continue
            except ValueError:
                invalid_ids.append(question_id)
                continue
        
        # Find the scene and apply
        found = False
        for scene in scenes.get('scenes', []):
            if scene.get('number') == scene_num:
                found = True
                if q_type == 'emotion':
                    scene.setdefault('notes', {})['beats'] = [answer]
                elif q_type == 'camera' and answer == 'auto_select':
                    scene.setdefault('notes', {})['camera'] = ['AUTO']
                elif q_type == 'ref':
                    # Handled by individual reference logic if needed
                    pass
                elif q_type == 'suggestion' and answer == 'approve':
                    # Suggestion approved - could mark for application
                    pass
                break
        
        if not found:
            invalid_ids.append(question_id)
    
    return scenes, invalid_ids
