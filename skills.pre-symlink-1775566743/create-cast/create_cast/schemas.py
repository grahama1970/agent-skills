"""
Data schemas for create-cast skill.

Defines:
- CharacterSpec: Extracted character information from script
- IdentityPack: Generated identity images for Veo
- VoiceAssignment: Voice model assignment
- CastingSession: Complete session state
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional
import json


class CastingPhase(str, Enum):
    """Casting workflow phases."""
    ANALYSIS = "analysis"         # Round 1: Script analysis
    DISCOVERY = "discovery"       # Round 2: Reference actors
    GENERATION = "generation"     # Round 3: Identity images
    PACK_BUILD = "pack_build"     # Round 4: Full identity pack
    VOICE = "voice"               # Round 5: Voice casting
    COMPLETE = "complete"


class CharacterRole(str, Enum):
    """Character role in the story."""
    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    MINOR = "minor"
    BACKGROUND = "background"


class QuestionType(str, Enum):
    """Types of questions to ask."""
    CONFIRMATION = "confirmation"
    SELECTION = "selection"
    TEXT_INPUT = "text_input"
    APPROVAL = "approval"
    MULTI_SELECT = "multi_select"


@dataclass
class PhysicalDescription:
    """Physical description of a character."""
    age_range: str = ""
    gender: str = ""
    build: str = ""
    hair: str = ""
    skin_tone: str = ""
    distinguishing: str = ""
    outfit_notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PhysicalDescription":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_prompt_descriptors(self) -> List[str]:
        """Convert to list of prompt descriptors for image generation."""
        descriptors = []
        if self.age_range:
            descriptors.append(f"{self.age_range}")
        if self.gender:
            descriptors.append(f"{self.gender}")
        if self.build:
            descriptors.append(f"{self.build} build")
        if self.hair:
            descriptors.append(f"{self.hair} hair")
        if self.skin_tone:
            descriptors.append(f"{self.skin_tone} skin")
        if self.distinguishing:
            descriptors.append(self.distinguishing)
        return descriptors


@dataclass
class CharacterSpec:
    """Complete specification for a character."""
    name: str
    role: CharacterRole
    screen_time_estimate: float = 0.0  # seconds
    physical: PhysicalDescription = field(default_factory=PhysicalDescription)
    personality: List[str] = field(default_factory=list)
    voice_type: str = ""
    dialogue_count: int = 0
    scenes: List[int] = field(default_factory=list)
    bridge_attributes: List[str] = field(default_factory=list)
    raw_mentions: List[str] = field(default_factory=list)  # Original text mentions
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['role'] = self.role.value if isinstance(self.role, CharacterRole) else self.role
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CharacterSpec":
        data = data.copy()
        if 'role' in data:
            data['role'] = CharacterRole(data['role']) if isinstance(data['role'], str) else data['role']
        if 'physical' in data and isinstance(data['physical'], dict):
            data['physical'] = PhysicalDescription.from_dict(data['physical'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ReferenceActor:
    """Reference actor from discover-talent."""
    tmdb_id: int
    name: str
    profile_url: str = ""
    known_for: List[str] = field(default_factory=list)
    selected: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateLook:
    """A generated candidate look for a character."""
    image_path: str
    prompt_used: str
    style_notes: str = ""
    selected: bool = False
    iteration: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdentityPack:
    """Complete identity pack for Veo reference."""
    character_name: str
    images: Dict[str, str] = field(default_factory=dict)  # front, three_quarter, full_body
    prompt_descriptors: List[str] = field(default_factory=list)
    lighting_notes: str = "Neutral studio lighting for Veo reference"
    voice_model: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "IdentityPack":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_yaml(self) -> str:
        """Export as YAML for character_bible.yaml."""
        import yaml
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)


@dataclass
class VoiceAssignment:
    """Voice model assignment for a character."""
    character_name: str
    model_name: str = ""
    model_path: str = ""
    model_type: str = ""  # "rvc", "tts-train", "external"
    needs_training: bool = False
    training_reference: str = ""  # Actor name to train from
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Question:
    """A question for human/agent clarification."""
    id: str
    question_type: QuestionType
    question: str
    options: List[str] = field(default_factory=list)
    default: Optional[str] = None
    context: Optional[str] = None
    character_name: Optional[str] = None
    phase: Optional[CastingPhase] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['question_type'] = self.question_type.value if isinstance(self.question_type, QuestionType) else self.question_type
        d['phase'] = self.phase.value if self.phase and isinstance(self.phase, CastingPhase) else self.phase
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Question":
        data = data.copy()
        if 'question_type' in data:
            data['question_type'] = QuestionType(data['question_type'])
        if 'phase' in data and data['phase']:
            data['phase'] = CastingPhase(data['phase'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CastingSession:
    """Complete session state for multi-round workflow."""
    session_id: str
    phase: CastingPhase
    script_path: str
    created_at: str
    updated_at: str
    output_dir: str = ""
    
    # Round-by-round data
    characters: Dict[str, CharacterSpec] = field(default_factory=dict)
    reference_inspirations: Dict[str, List[ReferenceActor]] = field(default_factory=dict)
    candidate_looks: Dict[str, List[CandidateLook]] = field(default_factory=dict)
    identity_packs: Dict[str, IdentityPack] = field(default_factory=dict)
    voice_assignments: Dict[str, VoiceAssignment] = field(default_factory=dict)
    
    # Questions and answers
    questions: List[Question] = field(default_factory=list)
    answers: Dict[str, Any] = field(default_factory=dict)
    
    # Error tracking
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "phase": self.phase.value,
            "script_path": self.script_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_dir": self.output_dir,
            "characters": {k: v.to_dict() for k, v in self.characters.items()},
            "reference_inspirations": {k: [r.to_dict() for r in v] for k, v in self.reference_inspirations.items()},
            "candidate_looks": {k: [c.to_dict() for c in v] for k, v in self.candidate_looks.items()},
            "identity_packs": {k: v.to_dict() for k, v in self.identity_packs.items()},
            "voice_assignments": {k: v.to_dict() for k, v in self.voice_assignments.items()},
            "questions": [q.to_dict() for q in self.questions],
            "answers": self.answers,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CastingSession":
        data = data.copy()
        data['phase'] = CastingPhase(data['phase'])
        
        # Parse nested objects
        if 'characters' in data:
            data['characters'] = {k: CharacterSpec.from_dict(v) for k, v in data['characters'].items()}
        if 'reference_inspirations' in data:
            data['reference_inspirations'] = {
                k: [ReferenceActor(**r) for r in v] 
                for k, v in data['reference_inspirations'].items()
            }
        if 'candidate_looks' in data:
            data['candidate_looks'] = {
                k: [CandidateLook(**c) for c in v]
                for k, v in data['candidate_looks'].items()
            }
        if 'identity_packs' in data:
            data['identity_packs'] = {k: IdentityPack.from_dict(v) for k, v in data['identity_packs'].items()}
        if 'voice_assignments' in data:
            data['voice_assignments'] = {k: VoiceAssignment(**v) for k, v in data['voice_assignments'].items()}
        if 'questions' in data:
            data['questions'] = [Question.from_dict(q) for q in data['questions']]
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class CastingResult:
    """Structured output for agent communication."""
    status: str  # "needs_input", "in_progress", "complete", "error"
    phase: CastingPhase
    session_id: str
    questions: List[Question] = field(default_factory=list)
    characters_complete: List[str] = field(default_factory=list)
    message: str = ""
    resume_command: str = ""
    error: Optional[str] = None
    partial_results: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "phase": self.phase.value,
            "session_id": self.session_id,
            "questions": [q.to_dict() for q in self.questions],
            "characters_complete": self.characters_complete,
            "message": self.message,
            "resume_command": self.resume_command,
            "error": self.error,
            "partial_results": self.partial_results,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
