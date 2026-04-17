"""
Collaboration module for session state management and question generation.

Manages persistent session state and generates questions for human collaboration.
"""

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from .schemas import (
    SoundDesignSession,
    SoundDesignPhase,
    SFXCue,
    SFXCandidate,
    SFXEvent,
    Question,
    QuestionType,
    session_to_dict,
    dict_to_session,
)


def get_sessions_dir() -> Path:
    """Get the sessions directory, creating if needed."""
    sessions_dir = Path.home() / ".pi" / "create-sound-design" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def generate_session_id() -> str:
    """Generate a unique session ID."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(3)
    return f"sounddesign-{timestamp}-{suffix}"


def save_session(session: SoundDesignSession) -> Path:
    """
    Persist session state as JSON.
    
    Returns path to saved session file.
    """
    session.updated_at = datetime.now().isoformat()
    
    sessions_dir = get_sessions_dir()
    session_path = sessions_dir / f"{session.session_id}.json"
    
    with open(session_path, "w") as f:
        json.dump(session_to_dict(session), f, indent=2)
    
    logger.debug(f"Saved session to {session_path}")
    return session_path


def load_session(session_id: str) -> Optional[SoundDesignSession]:
    """Load a session by ID."""
    sessions_dir = get_sessions_dir()
    session_path = sessions_dir / f"{session_id}.json"
    
    if not session_path.exists():
        logger.warning(f"Session not found: {session_id}")
        return None
    
    try:
        with open(session_path) as f:
            data = json.load(f)
        return dict_to_session(data)
    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        return None


def list_sessions() -> List[Dict]:
    """List all sessions with basic info."""
    sessions_dir = get_sessions_dir()
    sessions = []
    
    for path in sessions_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            sessions.append({
                "session_id": data["session_id"],
                "phase": data["phase"],
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "project_name": data.get("project_name", ""),
                "cue_count": len(data.get("cues", {})),
                "event_count": len(data.get("events", {})),
            })
        except Exception as e:
            logger.warning(f"Failed to read session {path}: {e}")
    
    # Sort by updated_at descending
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session by ID."""
    sessions_dir = get_sessions_dir()
    session_path = sessions_dir / f"{session_id}.json"
    
    if session_path.exists():
        session_path.unlink()
        logger.info(f"Deleted session {session_id}")
        return True
    return False


# Question generation functions

def generate_analysis_questions(cues: List[SFXCue]) -> List[Question]:
    """
    Generate questions to confirm extracted SFX cues.
    
    Groups cues by scene and asks for confirmation.
    """
    questions = []
    
    # Group by scene
    scenes = {}
    for cue in cues:
        if cue.scene_id not in scenes:
            scenes[cue.scene_id] = []
        scenes[cue.scene_id].append(cue)
    
    # Generate confirmation question for each scene
    for scene_id, scene_cues in scenes.items():
        cue_summary = "\n".join([
            f"  - {c.description} ({c.category}, {c.intensity})"
            for c in scene_cues[:5]  # Limit to 5 for readability
        ])
        if len(scene_cues) > 5:
            cue_summary += f"\n  ... and {len(scene_cues) - 5} more"
        
        questions.append(Question(
            id=f"confirm_{scene_id}",
            question_type=QuestionType.CONFIRMATION,
            question=f"Scene {scene_id}: Found {len(scene_cues)} SFX cues:\n{cue_summary}\n\nAre these correct?",
            options=["Yes, proceed", "Add more cues", "Remove some cues", "Skip this scene"],
            default="Yes, proceed",
            phase=SoundDesignPhase.ANALYSIS,
        ))
    
    # Overall confirmation
    questions.append(Question(
        id="analysis_complete",
        question_type=QuestionType.CONFIRMATION,
        question=f"Analysis complete: {len(cues)} total SFX cues across {len(scenes)} scenes.\n\nProceed to sound search?",
        options=["Yes, proceed to search", "Review cues again"],
        default="Yes, proceed to search",
        phase=SoundDesignPhase.ANALYSIS,
    ))
    
    return questions


def generate_search_questions(
    cue: SFXCue,
    candidates: List[SFXCandidate]
) -> List[Question]:
    """
    Generate questions to select preferred sound for a cue.
    """
    questions = []
    
    if not candidates:
        questions.append(Question(
            id=f"no_candidates_{cue.cue_id}",
            question_type=QuestionType.TEXT_INPUT,
            question=f"No sounds found for: {cue.description}\n\nEnter a search term or 'skip' to skip this cue:",
            options=[],
            default="skip",
            cue_id=cue.cue_id,
            phase=SoundDesignPhase.SEARCH,
        ))
        return questions
    
    # Build options from candidates
    options = []
    for i, c in enumerate(candidates[:4]):  # Max 4 options
        option = f"{i + 1}. {c.name} ({c.duration:.1f}s, {c.category})"
        if c.prior_usage_count > 0:
            option += f" [used {c.prior_usage_count}x before]"
        options.append(option)
    options.append("Search again with different terms")
    options.append("Skip this cue")
    
    questions.append(Question(
        id=f"select_{cue.cue_id}",
        question_type=QuestionType.SELECTION,
        question=f"Cue: {cue.description}\nCategory: {cue.category}, Intensity: {cue.intensity}\n\nSelect a sound:",
        options=options,
        default=options[0],  # First candidate
        cue_id=cue.cue_id,
        phase=SoundDesignPhase.SEARCH,
    ))
    
    return questions


def generate_timing_questions(events: List[SFXEvent]) -> List[Question]:
    """
    Generate questions to approve timing and levels.
    """
    questions = []
    
    # Group by scene
    scenes = {}
    for event in events:
        scene_id = event.cue_id.rsplit("_cue_", 1)[0] if "_cue_" in event.cue_id else "scene_01"
        if scene_id not in scenes:
            scenes[scene_id] = []
        scenes[scene_id].append(event)
    
    for scene_id, scene_events in scenes.items():
        event_summary = "\n".join([
            f"  - {e.sfx_id} @ {e.timestamp:.1f}s (vol: {e.volume:.1f}, dur: {e.duration:.1f}s)"
            for e in sorted(scene_events, key=lambda x: x.timestamp)
        ])
        
        questions.append(Question(
            id=f"timing_{scene_id}",
            question_type=QuestionType.APPROVAL,
            question=f"Scene {scene_id} timing:\n{event_summary}\n\nApprove mix?",
            options=["Approve", "Adjust timing", "Adjust volumes", "Remove events"],
            default="Approve",
            phase=SoundDesignPhase.TIMING,
        ))
    
    # Final approval
    questions.append(Question(
        id="timing_complete",
        question_type=QuestionType.APPROVAL,
        question=f"Timing complete: {len(events)} SFX events placed.\n\nProceed to export?",
        options=["Yes, export manifest", "Review timing again"],
        default="Yes, export manifest",
        phase=SoundDesignPhase.TIMING,
    ))
    
    return questions


def generate_export_questions(manifest_path: str) -> List[Question]:
    """Generate final export confirmation."""
    return [Question(
        id="export_complete",
        question_type=QuestionType.CONFIRMATION,
        question=f"Sound design exported to:\n{manifest_path}\n\nSession complete!",
        options=["Done", "Export to another location"],
        default="Done",
        phase=SoundDesignPhase.EXPORT,
    )]


def process_answer(
    session: SoundDesignSession,
    question_id: str,
    answer: str
) -> bool:
    """
    Process an answer and update session state.
    
    Returns True if answer was processed successfully.
    """
    session.answers[question_id] = answer
    
    # Remove the answered question from pending
    session.pending_questions = [
        q for q in session.pending_questions
        if q.id != question_id
    ]
    
    return True


def get_default_answers(questions: List[Question]) -> Dict[str, str]:
    """Get default answers for all questions (for auto-approve mode)."""
    return {q.id: q.default for q in questions}


def should_advance_phase(session: SoundDesignSession) -> bool:
    """Check if all questions for current phase are answered."""
    current_phase = session.phase
    pending_for_phase = [
        q for q in session.pending_questions
        if q.phase == current_phase
    ]
    return len(pending_for_phase) == 0
