"""
Collaboration module for create-cast skill.

Provides:
- Session state management (save/load/find)
- Question generation for each phase
- Answer application
- Progress tracking
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from .schemas import (
    CastingSession, CastingPhase, CastingResult, Question, QuestionType,
    CharacterSpec, CharacterRole
)


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"casting-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def get_sessions_dir() -> Path:
    """Get the sessions storage directory."""
    sessions_dir = Path.home() / ".pi" / "create-cast" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def save_session(session: CastingSession) -> Path:
    """Save session state to file."""
    session.updated_at = datetime.now().isoformat()
    sessions_dir = get_sessions_dir()
    session_path = sessions_dir / f"{session.session_id}.json"
    session_path.write_text(session.to_json())
    return session_path


def load_session(session_id: str) -> Optional[CastingSession]:
    """Load session state from file."""
    sessions_dir = get_sessions_dir()
    session_path = sessions_dir / f"{session_id}.json"
    
    if not session_path.exists():
        # Try partial match
        for path in sessions_dir.glob("*.json"):
            if session_id in path.stem:
                session_path = path
                break
        else:
            return None
    
    try:
        data = json.loads(session_path.read_text())
        return CastingSession.from_dict(data)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error loading session: {e}")
        return None


def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions with summary info."""
    sessions_dir = get_sessions_dir()
    sessions = []
    
    for path in sessions_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            sessions.append({
                "session_id": data.get("session_id"),
                "phase": data.get("phase"),
                "script_path": data.get("script_path"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "character_count": len(data.get("characters", {})),
                "has_error": data.get("error") is not None,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Sort by updated_at descending
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


def create_new_session(script_path: str, output_dir: str = "") -> CastingSession:
    """Create a new casting session."""
    now = datetime.now().isoformat()
    return CastingSession(
        session_id=generate_session_id(),
        phase=CastingPhase.ANALYSIS,
        script_path=script_path,
        created_at=now,
        updated_at=now,
        output_dir=output_dir,
    )


def generate_analysis_questions(session: CastingSession) -> List[Question]:
    """Generate questions for the ANALYSIS phase (Round 1)."""
    questions = []
    characters = list(session.characters.values())
    
    if not characters:
        return []
    
    # 1. Confirm character list
    char_summary = ", ".join(
        f"{c.name} ({c.role.value}, {c.screen_time_estimate:.0f}s)" 
        for c in characters
    )
    questions.append(Question(
        id="confirm_characters",
        question_type=QuestionType.CONFIRMATION,
        question=f"I found {len(characters)} characters: {char_summary}. Is this correct?",
        options=["approve", "add_character", "remove_character", "modify_roles"],
        default="approve",
        phase=CastingPhase.ANALYSIS,
    ))
    
    # 2. Ask about missing physical descriptions for main characters
    for char in characters:
        if char.role in [CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST, CharacterRole.SUPPORTING]:
            if not char.physical.age_range:
                questions.append(Question(
                    id=f"{char.name.lower()}_age",
                    question_type=QuestionType.SELECTION,
                    question=f"{char.name}'s age isn't specified. What age range?",
                    options=["teens", "20s", "early 30s", "late 30s", "40s", "50s+"],
                    character_name=char.name,
                    phase=CastingPhase.ANALYSIS,
                ))
            
            if not char.physical.gender:
                questions.append(Question(
                    id=f"{char.name.lower()}_gender",
                    question_type=QuestionType.SELECTION,
                    question=f"{char.name}'s gender isn't specified. What gender?",
                    options=["male", "female", "non-binary", "ambiguous"],
                    character_name=char.name,
                    phase=CastingPhase.ANALYSIS,
                ))
            
            if not char.physical.build and not char.physical.distinguishing:
                questions.append(Question(
                    id=f"{char.name.lower()}_appearance",
                    question_type=QuestionType.TEXT_INPUT,
                    question=f"Describe {char.name}'s physical appearance (build, hair, distinguishing features):",
                    character_name=char.name,
                    phase=CastingPhase.ANALYSIS,
                ))
    
    return questions


def generate_discovery_questions(session: CastingSession) -> List[Question]:
    """Generate questions for the DISCOVERY phase (Round 2)."""
    questions = []
    
    for char_name, refs in session.reference_inspirations.items():
        if refs:
            ref_names = [r.name for r in refs[:4]]
            questions.append(Question(
                id=f"{char_name.lower()}_reference",
                question_type=QuestionType.SELECTION,
                question=f"For {char_name}, I found these reference actors: {ref_names}. Select one or skip.",
                options=ref_names + ["skip_reference", "describe_instead"],
                character_name=char_name,
                phase=CastingPhase.DISCOVERY,
            ))
    
    # Add option to skip all references
    if session.reference_inspirations:
        questions.append(Question(
            id="skip_all_references",
            question_type=QuestionType.CONFIRMATION,
            question="Skip all reference actors and describe characters from scratch?",
            options=["use_references", "skip_all"],
            default="use_references",
            phase=CastingPhase.DISCOVERY,
        ))
    
    return questions


def generate_generation_questions(session: CastingSession) -> List[Question]:
    """Generate questions for the GENERATION phase (Round 3)."""
    questions = []
    
    for char_name, looks in session.candidate_looks.items():
        if looks:
            look_options = [f"look_{i+1}" for i in range(len(looks))]
            questions.append(Question(
                id=f"{char_name.lower()}_look",
                question_type=QuestionType.SELECTION,
                question=f"Choose a look for {char_name}. Images generated at: {[l.image_path for l in looks]}",
                options=look_options + ["iterate", "describe_different"],
                character_name=char_name,
                phase=CastingPhase.GENERATION,
            ))
    
    return questions


def generate_pack_build_questions(session: CastingSession) -> List[Question]:
    """Generate questions for the PACK_BUILD phase (Round 4)."""
    questions = []
    
    for char_name, pack in session.identity_packs.items():
        if pack.images:
            questions.append(Question(
                id=f"{char_name.lower()}_pack_approve",
                question_type=QuestionType.APPROVAL,
                question=f"Identity pack for {char_name} complete. Images: {list(pack.images.values())}. Approve?",
                options=["approve", "regenerate_front", "regenerate_three_quarter", "regenerate_full_body", "regenerate_all"],
                default="approve",
                character_name=char_name,
                phase=CastingPhase.PACK_BUILD,
            ))
    
    return questions


def generate_voice_questions(session: CastingSession) -> List[Question]:
    """Generate questions for the VOICE phase (Round 5)."""
    questions = []
    
    for char_name, voice in session.voice_assignments.items():
        if voice.model_name:
            questions.append(Question(
                id=f"{char_name.lower()}_voice",
                question_type=QuestionType.APPROVAL,
                question=f"For {char_name}, found voice model '{voice.model_name}'. Use this?",
                options=["approve", "find_different", "queue_training", "skip_voice"],
                default="approve",
                character_name=char_name,
                phase=CastingPhase.VOICE,
            ))
        else:
            questions.append(Question(
                id=f"{char_name.lower()}_voice_missing",
                question_type=QuestionType.SELECTION,
                question=f"No matching voice for {char_name}. Queue for training or skip?",
                options=["queue_training", "skip_voice"],
                default="skip_voice",
                character_name=char_name,
                phase=CastingPhase.VOICE,
            ))
    
    return questions


def apply_answers(session: CastingSession, answers: Dict[str, Any]) -> CastingSession:
    """Apply user answers to session state."""
    session.answers.update(answers)
    
    for question_id, answer in answers.items():
        # Handle character-specific answers
        parts = question_id.split("_")
        
        if question_id == "confirm_characters":
            if answer == "approve":
                pass  # Characters confirmed as-is
            # Other options would trigger re-analysis
            
        elif "_age" in question_id:
            char_name = parts[0].upper()
            if char_name in session.characters:
                session.characters[char_name].physical.age_range = answer
                
        elif "_gender" in question_id:
            char_name = parts[0].upper()
            if char_name in session.characters:
                session.characters[char_name].physical.gender = answer
                
        elif "_appearance" in question_id:
            char_name = parts[0].upper()
            if char_name in session.characters:
                session.characters[char_name].physical.distinguishing = answer
                
        elif "_reference" in question_id:
            char_name = parts[0].upper()
            if char_name in session.reference_inspirations:
                refs = session.reference_inspirations[char_name]
                for ref in refs:
                    ref.selected = (ref.name == answer)
                    
        elif "_look" in question_id:
            char_name = parts[0].upper()
            if char_name in session.candidate_looks:
                looks = session.candidate_looks[char_name]
                try:
                    idx = int(answer.replace("look_", "")) - 1
                    if 0 <= idx < len(looks):
                        looks[idx].selected = True
                except (ValueError, IndexError):
                    pass
                    
        elif "_pack_approve" in question_id:
            if answer == "approve":
                pass  # Pack approved as-is
                
        elif "_voice" in question_id:
            char_name = parts[0].upper()
            if answer == "approve" and char_name in session.voice_assignments:
                pass  # Voice approved
            elif answer == "queue_training" and char_name in session.voice_assignments:
                session.voice_assignments[char_name].needs_training = True
    
    return session


def advance_phase(session: CastingSession) -> CastingSession:
    """Advance to the next phase if current phase is complete."""
    phase_order = [
        CastingPhase.ANALYSIS,
        CastingPhase.DISCOVERY,
        CastingPhase.GENERATION,
        CastingPhase.PACK_BUILD,
        CastingPhase.VOICE,
        CastingPhase.COMPLETE,
    ]
    
    current_idx = phase_order.index(session.phase)
    if current_idx < len(phase_order) - 1:
        session.phase = phase_order[current_idx + 1]
        session.questions = []  # Clear old questions
    
    return session


def build_result(session: CastingSession, auto_approve: bool = False) -> CastingResult:
    """Build a CastingResult from current session state."""
    # Generate questions for current phase
    questions = []
    if session.phase == CastingPhase.ANALYSIS:
        questions = generate_analysis_questions(session)
    elif session.phase == CastingPhase.DISCOVERY:
        questions = generate_discovery_questions(session)
    elif session.phase == CastingPhase.GENERATION:
        questions = generate_generation_questions(session)
    elif session.phase == CastingPhase.PACK_BUILD:
        questions = generate_pack_build_questions(session)
    elif session.phase == CastingPhase.VOICE:
        questions = generate_voice_questions(session)
    
    session.questions = questions
    
    # Determine status
    if session.error:
        status = "error"
    elif session.phase == CastingPhase.COMPLETE:
        status = "complete"
    elif questions and not auto_approve:
        status = "needs_input"
    else:
        status = "in_progress"
    
    # Build resume command
    resume_cmd = f"./run.sh continue --session {session.session_id} --answers '{{...}}'"
    
    # List completed characters
    complete_chars = list(session.identity_packs.keys())
    
    return CastingResult(
        status=status,
        phase=session.phase,
        session_id=session.session_id,
        questions=questions,
        characters_complete=complete_chars,
        message=f"Phase: {session.phase.value}, {len(questions)} questions pending",
        resume_command=resume_cmd,
        error=session.error,
    )


def format_questions_for_display(questions: List[Question]) -> str:
    """Format questions for human-readable display."""
    if not questions:
        return "No questions - proceeding with defaults.\n"
    
    lines = [f"\n{'='*60}", "CASTING QUESTIONS", f"{'='*60}\n"]
    
    for i, q in enumerate(questions, 1):
        q_type = q.question_type.value if hasattr(q.question_type, 'value') else q.question_type
        char_info = f" ({q.character_name})" if q.character_name else ""
        lines.append(f"{i}. [{q_type.upper()}]{char_info}")
        lines.append(f"   {q.question}")
        if q.options:
            lines.append(f"   Options: {', '.join(q.options)}")
        if q.default:
            lines.append(f"   Default: {q.default}")
        lines.append("")
    
    lines.append(f"{'='*60}")
    lines.append("To provide answers, use:")
    lines.append("  ./run.sh continue --session <ID> --answers '{\"question_id\": \"answer\", ...}'")
    lines.append(f"{'='*60}\n")
    
    return "\n".join(lines)
