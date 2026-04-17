"""
Core schemas for create-sound-design skill.

Defines dataclasses for SFX cues, events, sessions, and results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class SoundDesignPhase(Enum):
    """Phases of the sound design workflow."""
    ANALYSIS = "analysis"      # Parse script/storyboard for SFX cues
    SEARCH = "search"          # Query sfx-catalog for matching sounds
    TIMING = "timing"          # Place sounds at timestamps with volume/pan
    EXPORT = "export"          # Generate manifest and record usage
    COMPLETE = "complete"      # All done


class QuestionType(Enum):
    """Types of questions for collaboration."""
    CONFIRMATION = "confirmation"  # Yes/No confirmation
    SELECTION = "selection"        # Select from options
    TEXT_INPUT = "text_input"      # Free text input
    APPROVAL = "approval"          # Approve or reject


@dataclass
class SFXCue:
    """A sound effect cue extracted from script/storyboard."""
    cue_id: str                          # "scene_01_cue_003"
    scene_id: str                        # "scene_01"
    description: str                     # "door creaks open slowly"
    category: str                        # "foley", "ambient", "impact", etc.
    timestamp_hint: Optional[float] = None  # Approx position in scene (seconds)
    duration_hint: Optional[float] = None   # Expected length (seconds)
    intensity: str = "moderate"          # "subtle", "moderate", "prominent"
    source_line: str = ""                # Original script line


@dataclass
class SFXCandidate:
    """A candidate sound from sfx-catalog search."""
    sfx_id: str                    # ID from sfx-catalog
    name: str                      # Display name
    path: str                      # File path
    duration: float                # Audio duration in seconds
    category: str                  # Category from catalog
    similarity_score: float        # Semantic similarity to cue
    prior_usage_count: int = 0     # Times used before (from memory)
    description: str = ""          # Description from catalog


@dataclass
class SFXEvent:
    """A placed sound effect event in the timeline."""
    event_id: str                  # Unique ID
    cue_id: str                    # Links to SFXCue
    sfx_id: str                    # From sfx-catalog
    sfx_path: str                  # Local path to audio file
    timestamp: float               # Start time in scene (seconds)
    duration: float                # Playback duration (seconds)
    volume: float = 0.6            # 0.0-1.0
    pan: float = 0.0               # -1.0 (left) to 1.0 (right)
    fade_in: float = 0.1           # Fade duration (seconds)
    fade_out: float = 0.1          # Fade duration (seconds)


@dataclass
class Question:
    """A question for human collaboration."""
    id: str                                # Unique question ID
    question_type: QuestionType            # Type of question
    question: str                          # Text to display
    options: List[str] = field(default_factory=list)  # Possible answers
    default: str = ""                      # Auto-approve value
    cue_id: Optional[str] = None           # Which cue this is about
    phase: SoundDesignPhase = SoundDesignPhase.ANALYSIS


@dataclass
class SceneSoundDesign:
    """Sound design spec for a single scene."""
    scene_id: str
    duration: float                        # Scene duration in seconds
    events: List[SFXEvent] = field(default_factory=list)
    has_dialogue: bool = False
    has_music: bool = False


@dataclass
class SoundDesignSession:
    """Session state for sound design workflow."""
    session_id: str                        # "sounddesign-YYYYMMDD-HHMMSS-xxxxxx"
    phase: SoundDesignPhase                # Current workflow phase
    script_path: str                       # Path to script JSON
    storyboard_path: Optional[str] = None  # Path to storyboard YAML
    created_at: str = ""                   # ISO timestamp
    updated_at: str = ""                   # ISO timestamp
    output_dir: str = ""                   # Output directory

    # State per phase
    cues: Dict[str, SFXCue] = field(default_factory=dict)
    candidates: Dict[str, List[SFXCandidate]] = field(default_factory=dict)
    events: Dict[str, SFXEvent] = field(default_factory=dict)
    scenes: Dict[str, SceneSoundDesign] = field(default_factory=dict)

    # Metadata
    project_name: str = ""
    episode: Optional[str] = None
    bridge_attributes: List[str] = field(default_factory=list)

    # Collaboration state
    pending_questions: List[Question] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class SoundDesignResult:
    """Result returned from sound design operations."""
    status: str                            # "complete", "needs_input", "error"
    phase: SoundDesignPhase
    session_id: str
    questions: List[Question] = field(default_factory=list)

    # Output (when complete)
    scenes: Dict[str, SceneSoundDesign] = field(default_factory=dict)
    manifest_path: str = ""                # JSON manifest for Assemble
    memory_ids: List[str] = field(default_factory=list)  # Stored usage records
    event_count: int = 0                   # Total SFX events placed

    # For error reporting
    error: Optional[str] = None
    resume_command: str = ""               # Command to resume session


def session_to_dict(session: SoundDesignSession) -> Dict[str, Any]:
    """Convert session to JSON-serializable dict."""
    return {
        "session_id": session.session_id,
        "phase": session.phase.value,
        "script_path": session.script_path,
        "storyboard_path": session.storyboard_path,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "output_dir": session.output_dir,
        "cues": {k: vars(v) for k, v in session.cues.items()},
        "candidates": {
            k: [vars(c) for c in v] 
            for k, v in session.candidates.items()
        },
        "events": {k: vars(v) for k, v in session.events.items()},
        "scenes": {
            k: {
                "scene_id": v.scene_id,
                "duration": v.duration,
                "events": [vars(e) for e in v.events],
                "has_dialogue": v.has_dialogue,
                "has_music": v.has_music,
            }
            for k, v in session.scenes.items()
        },
        "project_name": session.project_name,
        "episode": session.episode,
        "bridge_attributes": session.bridge_attributes,
        "pending_questions": [
            {
                "id": q.id,
                "question_type": q.question_type.value,
                "question": q.question,
                "options": q.options,
                "default": q.default,
                "cue_id": q.cue_id,
                "phase": q.phase.value,
            }
            for q in session.pending_questions
        ],
        "answers": session.answers,
        "error": session.error,
    }


def dict_to_session(data: Dict[str, Any]) -> SoundDesignSession:
    """Convert dict back to SoundDesignSession."""
    session = SoundDesignSession(
        session_id=data["session_id"],
        phase=SoundDesignPhase(data["phase"]),
        script_path=data["script_path"],
        storyboard_path=data.get("storyboard_path"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        output_dir=data.get("output_dir", ""),
        project_name=data.get("project_name", ""),
        episode=data.get("episode"),
        bridge_attributes=data.get("bridge_attributes", []),
        answers=data.get("answers", {}),
        error=data.get("error"),
    )

    # Reconstruct cues
    for k, v in data.get("cues", {}).items():
        session.cues[k] = SFXCue(**v)

    # Reconstruct candidates
    for k, v in data.get("candidates", {}).items():
        session.candidates[k] = [SFXCandidate(**c) for c in v]

    # Reconstruct events
    for k, v in data.get("events", {}).items():
        session.events[k] = SFXEvent(**v)

    # Reconstruct scenes
    for k, v in data.get("scenes", {}).items():
        scene = SceneSoundDesign(
            scene_id=v["scene_id"],
            duration=v["duration"],
            has_dialogue=v.get("has_dialogue", False),
            has_music=v.get("has_music", False),
        )
        scene.events = [SFXEvent(**e) for e in v.get("events", [])]
        session.scenes[k] = scene

    # Reconstruct questions
    for q in data.get("pending_questions", []):
        session.pending_questions.append(Question(
            id=q["id"],
            question_type=QuestionType(q["question_type"]),
            question=q["question"],
            options=q.get("options", []),
            default=q.get("default", ""),
            cue_id=q.get("cue_id"),
            phase=SoundDesignPhase(q["phase"]),
        ))

    return session
