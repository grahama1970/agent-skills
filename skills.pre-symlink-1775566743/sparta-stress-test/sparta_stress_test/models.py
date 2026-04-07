"""Data structures and constants for SPARTA conversation simulation.

Defines the core dataclasses (Turn, Tier1Result, SessionGrade, StressSession)
and configuration constants used across the conversation simulation modules.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Skill slash-command detection
SKILL_SLASH_PATTERN = re.compile(r'(?:^|\s)/([a-z][a-z0-9-]+)')

# Adversarial injection rate for personas
ADVERSARIAL_RATE = 0.15

# Self-grading improvement loop config (Brandon's inner monologue)
SELF_GRADE_MAX_ITERATIONS = 2  # Clarify-first reduces need for brute-force retries
SELF_GRADE_TARGET_COMPOSITE = 0.90  # A+ threshold — Brandon must be satisfied

# Outer conversation loop config (persona must ALSO grade A)
OUTER_LOOP_MAX_ROUNDS = int(os.environ.get("CONVO_MAX_ROUNDS", 5))
OUTER_LOOP_TARGET = 0.90   # Persona + Brandon both need 90+
OUTER_LOOP_STALL_TOLERANCE = 0.02  # Stall if composite delta < this for 2 consecutive rounds

# Shadow-LEGO delta logging path
SHADOW_DELTA_PATH = Path(os.environ.get(
    "SHADOW_DELTA_PATH",
    str(Path.home() / ".pi/assistant/shadow_deltas.jsonl"),
))

# Shadow-LEGO /assistant integration paths
SHADOW_JSONL_PATH = Path(os.environ.get(
    "SHADOW_JSONL_PATH",
    str(Path.home() / ".pi/assistant/shadow.jsonl"),
))

# Minimum sample size for statistical significance (95% CI, ±10% margin)
MIN_STRATIFIED_SAMPLE = 50

# pi-mono skills path (for /episodic-archiver, /assistant)
PI_MONO_SKILLS = Path(__file__).resolve().parent.parent.parent

# Results directory
SESSIONS_DIR = Path(__file__).resolve().parent.parent / "results" / "sessions"

# Grade ordering for fuzzy agreement (legacy A/B/C/F)
GRADE_ORDER = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}

# Evidence-based grade ordering (deterministic 4-state)
EVIDENCE_GRADE_ORDER = {"Pass": 0, "Ambiguous": 1, "Fail": 2, "Absurd": 3}


# --------------------------------------------------------------------------- #
# Data structures (following /battle's BattleState pattern)
# --------------------------------------------------------------------------- #


@dataclass
class Turn:
    """A single turn in a stress test conversation."""

    turn_number: int
    speaker: str  # persona name or "SPARTA"
    role: str  # "persona" or "system"
    content: str
    action: str = ""  # QUERY, CLARIFY, NO_MATCH, FOLLOW_UP, ANSWER
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Tier1Result:
    """Fast Tier 1 classification result — pure AQL, no LLM."""

    classification: str  # HAS_QRAS | CONTROL_ONLY | UNKNOWN_ENTITY | NO_ENTITIES | AMBIGUOUS | SKILL_INVOKE | SKILL_SUGGEST
    valid_entities: List[str] = field(default_factory=list)
    qra_counts: Dict[str, int] = field(default_factory=dict)
    unknown_entities: List[str] = field(default_factory=list)
    fuzzy_matches: Dict[str, List[str]] = field(default_factory=dict)
    graph_neighbors: List[str] = field(default_factory=list)
    steer_toward: Optional[str] = None
    skill_refs: List[str] = field(default_factory=list)
    skill_explicit: bool = False


@dataclass
class SessionGrade:
    """Brandon's grade for a full session."""

    composite: float = 0.0
    grade: str = "F"
    scores: Dict[str, float] = field(default_factory=dict)
    tier: int = 0
    source: str = "heuristic"
    rationale: str = ""
    reasoning_sound: Optional[bool] = None
    taxonomy_correct: Optional[bool] = None
    qra_citations_verified: int = 0
    qra_citations_total: int = 0


@dataclass
class StressSession:
    """Full stress test conversation session (like BattleState)."""

    session_id: str
    persona: str  # "Margaret Chen" or "Jennifer Cheung"
    seed_question: Dict[str, Any]  # The original mined question
    turns: List[Turn] = field(default_factory=list)
    grade: Optional[SessionGrade] = None

    # Session metadata
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    adversarial: bool = False  # Was an intentional flaw injected?
    resolution: str = "unknown"  # resolved, no_coverage, partial, ambiguous
    archived: bool = False  # Submitted to /episodic-archiver?

    # QRA lookup results (for grading context)
    qra_results: Dict[str, Any] = field(default_factory=dict)

    # Blame attribution (from /episodic-archiver analysis of failing sessions)
    blame: Optional[Dict[str, Any]] = None

    def add_turn(
        self,
        speaker: str,
        role: str,
        content: str,
        action: str = "",
        metadata: Optional[Dict] = None,
    ) -> Turn:
        turn = Turn(
            turn_number=len(self.turns) + 1,
            speaker=speaker,
            role=role,
            content=content,
            action=action,
            metadata=metadata or {},
        )
        self.turns.append(turn)
        return turn

    def to_transcript(self) -> Dict[str, Any]:
        """Convert to /episodic-archiver transcript format.

        Includes pre-computed 'category' per message so the archiver
        can skip its LLM categorization call (saves ~4000 calls per
        1000-session run).
        """
        messages = []
        for turn in self.turns:
            # Map turn role+action to archiver category
            if turn.role == "persona":
                category = "question"
            elif turn.action == "CLARIFY":
                category = "clarification"
            elif turn.action == "NO_MATCH":
                category = "error"
            else:
                category = "solution"

            messages.append(
                {
                    "from": "User" if turn.role == "persona" else "Agent",
                    "content": turn.content,
                    "timestamp": turn.timestamp,
                    "type": turn.action or "Chat",
                    "category": category,  # Pre-computed, skip LLM
                }
            )
        return {
            "session_id": self.session_id,
            "persona_id": self.persona.lower().replace(" ", "_"),
            "messages": messages,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "session_id": self.session_id,
            "persona": self.persona,
            "seed_question": self.seed_question,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "speaker": t.speaker,
                    "role": t.role,
                    "content": t.content,
                    "action": t.action,
                    "metadata": t.metadata,
                    "timestamp": t.timestamp,
                }
                for t in self.turns
            ],
            "grade": {
                "composite": self.grade.composite,
                "grade": self.grade.grade,
                "scores": self.grade.scores,
                "tier": self.grade.tier,
                "source": self.grade.source,
                "rationale": self.grade.rationale,
            }
            if self.grade
            else None,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "adversarial": self.adversarial,
            "resolution": self.resolution,
            "archived": self.archived,
            "blame": self.blame,
        }


def grades_agree(grade_a: str, grade_b: str) -> bool:
    """Fuzzy agreement: grades within 1 step count as AGREE.

    A+ vs A = AGREE, A vs B = AGREE, B vs C = AGREE.
    A+ vs B = DISAGREE, A vs F = DISAGREE.
    """
    idx_a = GRADE_ORDER.get(grade_a, 4)
    idx_b = GRADE_ORDER.get(grade_b, 4)
    return abs(idx_a - idx_b) <= 1
