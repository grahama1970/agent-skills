"""Data structures and shared configuration for SPARTA conversation simulation.

Defines Turn, Tier1Result, SessionGrade, StressSession dataclasses and
module-level constants/imports shared across the conversation subsystem.
"""

from __future__ import annotations

import os
import re as _re_mod
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True))

# Ensure graph_memory is importable
# graph_memory lives in the memory project, not pi-mono
_memory_src = str(Path(__file__).resolve().parents[4].parent / "memory" / "src")
if not Path(_memory_src).exists():
    # Fallback: try relative to workspace root
    _memory_src = str(Path(__file__).resolve().parents[5] / "memory" / "src")
if _memory_src not in sys.path:
    sys.path.insert(0, _memory_src)

# scillm path
_scillm_path = str(
    Path(__file__).resolve().parents[4].parent
    / "pi-mono"
    / ".pi"
    / "skills"
    / "scillm"
)
if _scillm_path not in sys.path:
    sys.path.insert(0, _scillm_path)

# pi-mono skills path (for /episodic-archiver, /assistant)
PI_MONO_SKILLS = Path(__file__).resolve().parent.parent.parent

# Response quality utilities (entity extraction/validation only — keyword scanning BANNED)
try:
    from sparta_stress_test.response_quality import (
        validate_entities,
        extract_entities,
    )
    _HAS_QUALITY_UTILS = True
except ImportError:
    _HAS_QUALITY_UTILS = False

# /assistant cascade (Tier 0 → 0.5 → 2 GPT rationale)
try:
    _assistant_path = str(PI_MONO_SKILLS / "assistant")
    if _assistant_path not in sys.path:
        sys.path.insert(0, _assistant_path)
    from assistant import classify as _assistant_classify
    _HAS_ASSISTANT = True
except ImportError:
    _HAS_ASSISTANT = False

# Episodic recall for self-grading loop
try:
    from graph_memory.agent import recall as _episodic_recall
    _HAS_EPISODIC = True
except ImportError:
    _HAS_EPISODIC = False

# ControlCatalog from /extract-controls (Tier 1 fast lookup)
# The script lives in the memory project, not pi-mono
_BACKFILL_SCRIPT = str(
    Path(__file__).resolve().parents[4].parent / "memory"
    / "scripts"
    / "backfill_chunk_control_edges.py"
)
if not Path(_BACKFILL_SCRIPT).exists():
    # Fallback: try pi-mono path (legacy)
    _BACKFILL_SCRIPT = str(
        Path(__file__).resolve().parents[4]
        / "scripts"
        / "backfill_chunk_control_edges.py"
    )
try:
    if not Path(_BACKFILL_SCRIPT).exists():
        raise FileNotFoundError(f"Backfill script not found at {_BACKFILL_SCRIPT}")
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("backfill_chunk_control_edges", _BACKFILL_SCRIPT)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    ControlCatalog = _mod.ControlCatalog
    extract_candidates = _mod.extract_candidates
    _HAS_CONTROL_CATALOG = True
except Exception as _cc_err:
    logger.debug(f"ControlCatalog not available: {_cc_err}")
    _HAS_CONTROL_CATALOG = False

# QRA bridge for promotion
try:
    from graph_memory.qra_bridge import QRABridge
    _HAS_QRA_BRIDGE = True
except ImportError:
    _HAS_QRA_BRIDGE = False

# Bridge extraction for QRA promotion
try:
    from graph_memory.lessons.store import extract_bridges_fast
    _HAS_BRIDGES = True
except ImportError:
    _HAS_BRIDGES = False

# Skill slash-command detection
SKILL_SLASH_PATTERN = _re_mod.compile(r'(?:^|\s)/([a-z][a-z0-9-]+)')

# Adversarial injection rate for personas
ADVERSARIAL_RATE = 0.15

# Self-grading improvement loop config (Brandon's inner monologue)
SELF_GRADE_MAX_ITERATIONS = 2  # Clarify-first reduces need for brute-force retries
SELF_GRADE_TARGET_COMPOSITE = 0.90  # A+ threshold — Brandon must be satisfied

# Outer conversation loop config (persona must ALSO grade A)
OUTER_LOOP_MAX_ROUNDS = int(os.environ.get("CONVO_MAX_ROUNDS", 5))
OUTER_LOOP_TARGET = 0.80   # A grade threshold — realistic with lean4 unavailable
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

# Results directory
SESSIONS_DIR = Path(__file__).resolve().parent.parent / "results" / "sessions"


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
    traceability_report: str = ""  # Markdown report for SPARTA answer turns


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
                    "traceability_report": t.traceability_report,
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
                "qra_citations_verified": self.grade.qra_citations_verified,
                "qra_citations_total": self.grade.qra_citations_total,
                "reasoning_sound": self.grade.reasoning_sound,
                "taxonomy_correct": self.grade.taxonomy_correct,
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


# --------------------------------------------------------------------------- #
# LLM helpers (reuse from question_miner)
# --------------------------------------------------------------------------- #


def _call_scillm(system: str, user_prompt: str, max_tokens: int = 1024, json_mode: bool = True) -> str:
    """Call /scillm via batch.quick_completion (the skill's programmatic API).

    Uses CHUTES_API_BASE/CHUTES_API_KEY/CHUTES_MODEL_ID from .env.
    Has built-in Chutes error hook (503 → OpenRouter fallback).
    """
    try:
        from batch import quick_completion
    except ImportError:
        logger.warning("/scillm batch.quick_completion not importable")
        return "{}" if json_mode else ""

    return quick_completion(
        prompt=user_prompt,
        system=system,
        json_mode=json_mode,
        max_tokens=max_tokens,
        temperature=0.4,
        timeout=60,
    )


def _get_db() -> Any:
    from graph_memory.arango_client import get_db

    return get_db()
