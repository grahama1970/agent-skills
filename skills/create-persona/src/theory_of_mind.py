#!/usr/bin/env python3
"""
Theory of Mind (ToM) for personas.

Implements Belief-Desire-Intention (BDI) architecture based on Horus persona system:
- User beliefs with confidence decay
- Contradiction detection
- Mood computation from context
- Dynamic persona state

See: ${HOME}/workspace/experiments/memory/persona for reference implementation.
"""

import importlib.util
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .persona import (
    Persona,
    get_persona,
    store_to_memory,
    recall_from_memory,
)

from loguru import logger as log


# =============================================================================
# Federated Taxonomy - Deep Integration
# =============================================================================

# Tier 0 Bridge Attributes (conceptual layer)
BRIDGE_ATTRIBUTES = {
    "Precision": "Calculated, methodical, optimized approaches",
    "Resilience": "Endurance, survival, recovery, fault tolerance",
    "Fragility": "Vulnerability, brittleness, emotional depth, weakness",
    "Corruption": "Taint, moral compromise, hidden decay, malevolence",
    "Loyalty": "Honor, duty, tradition, trust, allegiance",
    "Stealth": "Hidden, subtle, deceptive, mysterious",
}

# Tier 1 Tactical Bridges (derived from D3FEND)
TACTICAL_TO_CONCEPTUAL = {
    "Model": "Precision",
    "Harden": "Resilience",
    "Detect": "Loyalty",
    "Isolate": "Resilience",
    "Restore": "Resilience",
    "Evade": "Stealth",
    "Exploit": "Fragility",
    "Persist": "Corruption",
}

# Import BRIDGE_KEYWORDS from canonical taxonomy (with fallback)
_TAXONOMY_SKILL = Path(__file__).resolve().parent.parent.parent / "taxonomy" / "taxonomy.py"
try:
    _spec = importlib.util.spec_from_file_location("_canonical_taxonomy", _TAXONOMY_SKILL)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    BRIDGE_KEYWORDS = _mod.BRIDGE_KEYWORDS
except Exception:
    # Minimal fallback for offline use
    BRIDGE_KEYWORDS = {
        "Precision": ["optimiz", "efficien", "precis", "algorithm", "calculat", "method"],
        "Resilience": ["error handl", "fault tol", "robust", "redund", "recover", "resili"],
        "Fragility": ["brittle", "technical debt", "legacy", "fragile", "single point"],
        "Corruption": ["bug", "corrupt", "memory leak", "silent fail", "race condition"],
        "Loyalty": ["secur", "auth", "encrypt", "complian", "trust", "access control"],
        "Stealth": ["hidden", "infiltrat", "decept", "evas", "undetect"],
    }


def extract_bridges(text: str, max_bridges: int = 3) -> list[str]:
    """
    Fast keyword-based bridge extraction without LLM.

    Args:
        text: Text to analyze
        max_bridges: Maximum bridges to return

    Returns:
        List of bridge names ordered by relevance
    """
    text_lower = text.lower()
    bridge_scores = {}

    for bridge, keywords in BRIDGE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            bridge_scores[bridge] = score

    # Return top bridges
    sorted_bridges = sorted(bridge_scores.items(), key=lambda x: x[1], reverse=True)
    return [b[0] for b, _ in sorted_bridges[:max_bridges]]


# =============================================================================
# BDI Model
# =============================================================================

@dataclass
class Belief:
    """A belief held by the persona about a user or topic."""
    key: str
    confidence: float  # 0.0 - 1.0
    source: str  # Where this belief came from
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.last_updated:
            self.last_updated = now


@dataclass
class Desire:
    """A goal or desire the persona has in an interaction."""
    key: str
    priority: float  # 0.0 - 1.0
    satisfied: bool = False


@dataclass
class Intention:
    """A planned action or approach."""
    key: str
    active: bool = True


@dataclass
class BDIState:
    """
    Complete BDI state for a persona-user relationship.

    Based on Horus implementation in verify_tom.py.
    """
    persona_name: str
    user_id: str

    # Core BDI components
    beliefs: dict[str, float] = field(default_factory=dict)  # belief_key -> confidence
    desires: list[str] = field(default_factory=list)
    intentions: list[str] = field(default_factory=list)

    # Relationship metrics
    respect_level: float = 0.5  # How much persona respects user
    trust_level: float = 0.5   # How much persona trusts user
    interaction_count: int = 0

    # Mood state
    current_mood: str = "neutral"
    mood_history: list[str] = field(default_factory=list)

    # Edges created
    edges: list[dict] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    last_interaction: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.last_interaction:
            self.last_interaction = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BDIState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# Mood Computation
# =============================================================================

# Mood types available to personas
MOODS = {
    "neutral": "Default state",
    "engaged": "Interested and focused",
    "enthusiastic": "Excited about the topic",
    "dismissive": "Low respect, low interest",
    "amused": "Finding humor in the situation",
    "defensive": "Triggered by sensitive topic",
    "intense": "Highly focused on important topic",
    "contemplative": "Deep thinking mode",
    "critical": "Evaluating with skepticism",
    "supportive": "Encouraging and helpful",
    "wistful": "Dream-touched, lingering on something half-remembered",
    "haunted": "Unsettled by recent dream imagery",
}


def compute_mood(
    bdi_state: BDIState,
    context: Optional[dict] = None,
) -> dict:
    """
    Compute persona mood based on BDI state and context.

    Based on Horus compute_mood_from_beliefs() implementation.

    Args:
        bdi_state: Current BDI state
        context: Additional context (mood_signals, topic_relevance, etc.)

    Returns:
        Dict with mood and optional modifiers
    """
    context = context or {}
    mood_signals = context.get("mood_signals", [])
    topic_relevance = context.get("topic_relevance", 0.5)

    result = {
        "mood": "neutral",
        "defense_active": False,
        "intensity": 0.5,
    }

    # Check for trauma/trigger signals first
    for signal in mood_signals:
        if signal.startswith("trauma_trigger:") or signal.startswith("sensitive_topic:"):
            result["mood"] = "defensive"
            result["defense_active"] = True
            result["intensity"] = 0.9
            return result

    # High topic relevance -> intense focus
    if topic_relevance > 0.8:
        result["mood"] = "intense"
        result["intensity"] = topic_relevance
        return result

    # Check user beliefs for mood modifiers
    is_frustrated = bdi_state.beliefs.get("is_frustrated", 0.0)
    is_curious = bdi_state.beliefs.get("is_curious", 0.0)
    is_confused = bdi_state.beliefs.get("is_confused", 0.0)
    is_expert = bdi_state.beliefs.get("is_expert", 0.0)

    # Frustrated user + low respect = dismissive
    if is_frustrated > 0.6 and bdi_state.respect_level < 0.4:
        result["mood"] = "dismissive"
        result["intensity"] = is_frustrated
        return result

    # Frustrated user + high respect = amused (trying to help)
    if is_frustrated > 0.6 and bdi_state.respect_level > 0.6:
        result["mood"] = "amused"
        result["intensity"] = 0.7
        return result

    # Curious user = engaged
    if is_curious > 0.6:
        result["mood"] = "engaged"
        result["intensity"] = is_curious
        return result

    # Confused user = supportive
    if is_confused > 0.6:
        result["mood"] = "supportive"
        result["intensity"] = 0.7
        return result

    # Expert user = contemplative (peer discussion)
    if is_expert > 0.6:
        result["mood"] = "contemplative"
        result["intensity"] = 0.6
        return result

    # Long interaction history = more engaged
    if bdi_state.interaction_count > 10:
        result["mood"] = "engaged"
        result["intensity"] = min(0.8, 0.5 + bdi_state.interaction_count * 0.02)
        return result

    # Dream mood as low-priority baseline (only if still neutral)
    dream_mood = context.get("dream_mood")
    if dream_mood and dream_mood in MOODS and result["mood"] == "neutral":
        result["mood"] = dream_mood
        result["intensity"] = 0.4
        result["dream_influenced"] = True

    return result


# =============================================================================
# Belief Management
# =============================================================================

def decay_belief_confidence(
    beliefs: dict[str, float],
    decay_rate: float = 0.95,
    min_confidence: float = 0.1,
) -> dict[str, float]:
    """
    Apply time-based decay to belief confidence.

    Old beliefs become less certain over time.

    Args:
        beliefs: Current beliefs dict
        decay_rate: Multiplier per decay cycle (0.95 = 5% decay)
        min_confidence: Floor for confidence values

    Returns:
        Updated beliefs dict
    """
    return {
        key: max(min_confidence, conf * decay_rate)
        for key, conf in beliefs.items()
    }


def detect_contradictions(
    old_beliefs: dict[str, float],
    new_beliefs: dict[str, float],
    threshold: float = 0.4,
) -> list[dict]:
    """
    Detect contradictions between old and new beliefs.

    A contradiction occurs when the same belief key has significantly
    different confidence values.

    Args:
        old_beliefs: Previous beliefs
        new_beliefs: New inferred beliefs
        threshold: Minimum delta to count as contradiction

    Returns:
        List of contradiction dicts with belief, old_value, new_value
    """
    contradictions = []

    for key in set(old_beliefs.keys()) & set(new_beliefs.keys()):
        old_val = old_beliefs[key]
        new_val = new_beliefs[key]

        # Contradiction if confidence swings significantly
        if abs(new_val - old_val) > threshold:
            contradictions.append({
                "belief": key,
                "old_value": old_val,
                "new_value": new_val,
                "delta": new_val - old_val,
            })

    return contradictions


# =============================================================================
# User BDI Inference
# =============================================================================

def infer_user_bdi(
    conversation_history: list[dict],
    persona: Optional[Persona] = None,
) -> dict:
    """
    Infer user's BDI from conversation history.

    Simple heuristic version - can be enhanced with LLM.

    Args:
        conversation_history: List of {role, content} messages
        persona: Persona for context

    Returns:
        Dict with beliefs, desires, intentions
    """
    result = {
        "beliefs": {},
        "desires": [],
        "intentions": [],
    }

    if not conversation_history:
        return result

    # Get user messages
    user_messages = [m["content"] for m in conversation_history if m.get("role") == "user"]
    if not user_messages:
        return result

    combined_text = " ".join(user_messages).lower()

    # Infer beliefs about user
    if "?" in combined_text:
        result["beliefs"]["is_curious"] = 0.7

    if any(w in combined_text for w in ["help", "stuck", "don't understand", "confused"]):
        result["beliefs"]["is_confused"] = 0.7

    if any(w in combined_text for w in ["frustrat", "annoying", "doesn't work", "broken"]):
        result["beliefs"]["is_frustrated"] = 0.7

    if any(w in combined_text for w in ["actually", "technically", "in my experience"]):
        result["beliefs"]["is_expert"] = 0.6

    if any(w in combined_text for w in ["please", "thank", "appreciate"]):
        result["beliefs"]["is_polite"] = 0.7

    # Infer desires
    if "how" in combined_text or "what" in combined_text:
        result["desires"].append("learn")

    if "fix" in combined_text or "solve" in combined_text:
        result["desires"].append("solve_problem")

    if "explain" in combined_text:
        result["desires"].append("understand")

    # Infer intentions
    if "i want to" in combined_text or "i need to" in combined_text:
        result["intentions"].append("accomplish_task")

    if "can you" in combined_text or "could you" in combined_text:
        result["intentions"].append("request_assistance")

    return result


# =============================================================================
# Edge Types (Memory-compliant)
# =============================================================================

ALLOWED_EDGE_TYPES = {
    # Standard edges
    "solves", "mitigates", "duplicates", "uses_tool", "caused_by",
    "verifies", "depends_on", "similar_to", "related", "violates",
    "uses_script", "supersedes", "contradicted_by",
    # Theory of Mind edges
    "observes",       # Persona observes user behavior
    "revises",        # Persona revises a belief
    "trusts",         # Trust relationship
    "respects",       # Respect relationship
    "distrusts",      # Distrust relationship
    "triggers",       # Something triggers a mood/behavior
    "satisfies",      # Action satisfies a desire
    "frustrates",     # Action frustrates a desire
    "lesson_informs_belief",  # A lesson influences a belief
}


def create_bdi_edge(
    from_node: str,
    to_node: str,
    edge_type: str,
    confidence: float = 0.8,
    context: str = "",
) -> dict:
    """
    Create a BDI edge for memory storage.

    Args:
        from_node: Source node (lesson_id, user_id, etc.)
        to_node: Target node (belief_key, persona, etc.)
        edge_type: Type from ALLOWED_EDGE_TYPES
        confidence: Edge confidence
        context: Additional context

    Returns:
        Edge dict for memory storage
    """
    if edge_type not in ALLOWED_EDGE_TYPES:
        log.warning("Unknown edge type: %s", edge_type)

    return {
        "from": from_node,
        "to": to_node,
        "type": edge_type,
        "confidence": confidence,
        "context": context,
        "created_at": datetime.now().isoformat(),
    }


# =============================================================================
# Persona State Management
# =============================================================================

def get_or_create_bdi_state(
    persona_name: str,
    user_id: str,
    scope: str = "personas",
) -> BDIState:
    """
    Get existing BDI state or create new one.

    Args:
        persona_name: Name of the persona
        user_id: User identifier
        scope: Memory scope

    Returns:
        BDIState instance
    """
    # Try to recall existing state
    query = f"BDI State: {persona_name} <-> {user_id}"
    items = recall_from_memory(query, scope, k=1)

    for item in items:
        if persona_name in item.get("problem", "") and user_id in item.get("problem", ""):
            try:
                data = json.loads(item.get("solution", "{}"))
                return BDIState.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                continue

    # Create new state
    return BDIState(persona_name=persona_name, user_id=user_id)


def save_bdi_state(
    state: BDIState,
    scope: str = "personas",
) -> bool:
    """
    Save BDI state to memory.

    Args:
        state: BDIState to save
        scope: Memory scope

    Returns:
        True if successful
    """
    problem = f"BDI State: {state.persona_name} <-> {state.user_id}"
    solution = json.dumps(state.to_dict(), indent=2)
    tags = [
        "bdi_state",
        f"persona:{state.persona_name.lower().replace(' ', '_')}",
        f"user:{state.user_id}",
        f"mood:{state.current_mood}",
    ]

    return store_to_memory(problem, solution, scope, tags)


# =============================================================================
# Interaction Wrapper
# =============================================================================

def wrap_persona_interaction(
    persona_name: str,
    user_id: str,
    conversation_history: list[dict],
    cited_lesson_ids: Optional[list[str]] = None,
    scope: str = "personas",
) -> dict:
    """
    Wrap a persona interaction with BDI updates.

    This is the main integration point - call before generating responses.

    Based on Horus wrap_horus_interaction() implementation.

    Args:
        persona_name: Name of the persona
        user_id: User identifier
        conversation_history: List of {role, content} messages
        cited_lesson_ids: Lesson IDs referenced in the response
        scope: Memory scope

    Returns:
        Dict with mood, contradictions, new_edges, bdi_state
    """
    cited_lesson_ids = cited_lesson_ids or []

    # Get or create BDI state
    bdi_state = get_or_create_bdi_state(persona_name, user_id, scope)

    # Infer current user BDI
    user_bdi = infer_user_bdi(conversation_history)

    # Detect contradictions with old beliefs
    contradictions = detect_contradictions(bdi_state.beliefs, user_bdi["beliefs"])

    # Apply decay to old beliefs
    bdi_state.beliefs = decay_belief_confidence(bdi_state.beliefs)

    # Merge new beliefs (new beliefs override with higher confidence)
    for key, confidence in user_bdi["beliefs"].items():
        old_conf = bdi_state.beliefs.get(key, 0.0)
        bdi_state.beliefs[key] = max(old_conf, confidence)

    # Update desires and intentions
    bdi_state.desires = list(set(bdi_state.desires + user_bdi["desires"]))[-5:]  # Keep last 5
    bdi_state.intentions = user_bdi["intentions"]

    # Increment interaction count
    bdi_state.interaction_count += 1
    bdi_state.last_interaction = datetime.now().isoformat()

    # Compute mood
    persona = get_persona(persona_name, scope)
    mood_context = {
        "topic_relevance": _estimate_topic_relevance(conversation_history, persona),
    }
    mood_result = compute_mood(bdi_state, mood_context)
    bdi_state.current_mood = mood_result["mood"]
    bdi_state.mood_history.append(mood_result["mood"])
    bdi_state.mood_history = bdi_state.mood_history[-10:]  # Keep last 10

    # Create edges for high-confidence new beliefs linked to cited lessons
    new_edges = []
    for lesson_id in cited_lesson_ids:
        for key, confidence in user_bdi["beliefs"].items():
            if confidence > 0.6:
                edge = create_bdi_edge(
                    from_node=lesson_id,
                    to_node=key,
                    edge_type="lesson_informs_belief",
                    confidence=confidence,
                )
                new_edges.append(f"{lesson_id}->{key}")
                bdi_state.edges.append(edge)

    # Save state
    save_bdi_state(bdi_state, scope)

    return {
        "mood": mood_result,
        "contradictions": contradictions,
        "new_edges": new_edges,
        "bdi_state": bdi_state.to_dict(),
    }


def _estimate_topic_relevance(
    conversation_history: list[dict],
    persona: Optional[Persona],
) -> float:
    """Estimate how relevant the conversation topic is to the persona."""
    if not persona or not conversation_history:
        return 0.5

    # Get user messages
    user_text = " ".join(
        m["content"] for m in conversation_history if m.get("role") == "user"
    ).lower()

    # Check expertise overlap
    expertise_matches = sum(
        1 for exp in (persona.expertise or [])
        if exp.lower() in user_text
    )

    # Check domain overlap
    domain_match = 1.0 if persona.domain and persona.domain.lower() in user_text else 0.0

    # Compute relevance
    relevance = min(1.0, (expertise_matches * 0.2) + (domain_match * 0.3) + 0.3)
    return relevance
