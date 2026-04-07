"""
Memory-first, persona-guided discovery for all discover-* skills.

Provides shared context-gathering, scoring, and storage so that
discover-books, discover-movies, discover-music, and discover-talent
all query memory and respect the Horus persona before external API calls.
"""
from __future__ import annotations

import json
import os
import glob as _glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from .memory_client import MemoryClient, MemoryScope, RecallResult, LearnResult
from .taxonomy import (
    ContentType,
    get_bridge_attributes,
    get_episodic_associations,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERSONA_STATES_DIR = Path(
    os.environ.get(
        "PERSONA_STATES_DIR",
        str(Path(__file__).resolve().parent.parent.parent.parent / "memory" / "persona" / "states"),
    )
)

_DEFAULT_PERSONA_STATE: Dict[str, float] = {
    "arrogance": 0.7,
    "resentment": 0.6,
    "weariness": 0.5,
    "suspicion": 0.5,
    "grandiosity": 0.6,
    "fatigue_level": 0.3,
}

# Bridge names (canonical)
_BRIDGES = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth", "Intimacy"]

# Default scopes per content type
_SCOPE_DEFAULTS: Dict[str, List[MemoryScope]] = {
    ContentType.MUSIC: [MemoryScope.HORUS_LORE, MemoryScope.PERSONA, MemoryScope.OPERATIONAL],
    ContentType.MOVIE: [MemoryScope.HORUS_LORE, MemoryScope.PERSONA, MemoryScope.OPERATIONAL],
    ContentType.BOOK: [MemoryScope.HORUS_LORE, MemoryScope.PERSONA, MemoryScope.RESEARCH, MemoryScope.DOCUMENTS],
}
_SCOPE_DEFAULTS_FALLBACK = [MemoryScope.HORUS_LORE, MemoryScope.PERSONA]


__all__ = [
    "DiscoveryContext",
    "ScoredResult",
    "gather_context",
    "score_results",
    "store_discoveries",
    "load_persona_state",
    "persona_bridge_weights",
]

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DiscoveryContext:
    """Context assembled from memory + persona before any external API calls."""

    memory_hits: Dict[str, RecallResult] = field(default_factory=dict)
    persona_state: Dict[str, float] = field(default_factory=dict)
    bridge_weights: Dict[str, float] = field(default_factory=dict)
    episodic_anchors: List[str] = field(default_factory=list)
    prior_titles: Set[str] = field(default_factory=set)
    query: str = ""

    @property
    def total_hits(self) -> int:
        return sum(len(r.items) for r in self.memory_hits.values())

    def memory_summary(self) -> str:
        """One-line summary for CLI display."""
        parts = []
        for scope, result in self.memory_hits.items():
            if result.items:
                parts.append(f"{scope}:{len(result.items)}")
        if not parts:
            return ""
        return f"Memory: {', '.join(parts)} prior items"


@dataclass
class ScoredResult:
    """A discovery result with persona-guided scoring."""

    item: Dict[str, Any]
    raw_score: float = 0.0
    bridge_alignment: float = 0.0
    episodic_resonance: float = 0.0
    memory_reinforcement: float = 0.0
    novelty: float = 1.0
    final_score: float = 0.0
    bridge_tags: List[str] = field(default_factory=list)
    episodic_associations: List[str] = field(default_factory=list)
    worth_remembering: bool = False


# ---------------------------------------------------------------------------
# Persona state
# ---------------------------------------------------------------------------

def load_persona_state() -> Dict[str, float]:
    """Load the most recent Horus persona state from JSON files."""
    try:
        candidates = list(_PERSONA_STATES_DIR.glob("horus_persona_*.json"))
        if not candidates:
            logger.debug("No persona state files found, using defaults")
            return dict(_DEFAULT_PERSONA_STATE)

        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        with open(latest) as f:
            state = json.load(f)
        logger.debug("Loaded persona state from {}", latest.name)
        return state
    except Exception as e:
        logger.debug("Failed to load persona state: {}", e)
        return dict(_DEFAULT_PERSONA_STATE)


def persona_bridge_weights(state: Dict[str, float]) -> Dict[str, float]:
    """
    Derive per-bridge weights from persona emotional state.

    High resentment  -> Corruption resonates
    High arrogance   -> Precision resonates
    High weariness   -> Fragility resonates
    High suspicion   -> Stealth resonates
    Honor/loyalty    -> Loyalty resonates
    Low weariness    -> Resilience resonates
    """
    resentment = state.get("resentment", 0.5)
    arrogance = state.get("arrogance", 0.5)
    grandiosity = state.get("grandiosity", 0.5)
    weariness = state.get("weariness", 0.5)
    suspicion = state.get("suspicion", 0.5)
    honor = state.get("honor_sense", 0.2)
    protective = state.get("protective_instinct", 0.1)

    loneliness = state.get("loneliness", 0.3)
    vulnerability = state.get("vulnerability", 0.3)

    weights = {
        "Precision": 0.5 + 0.3 * arrogance + 0.2 * grandiosity,
        "Resilience": 0.5 + 0.3 * (1.0 - weariness) + 0.2 * honor,
        "Fragility": 0.5 + 0.4 * weariness + 0.1 * (1.0 - arrogance),
        "Corruption": 0.5 + 0.3 * resentment + 0.2 * suspicion,
        "Loyalty": 0.5 + 0.4 * honor + 0.1 * protective,
        "Stealth": 0.5 + 0.4 * suspicion + 0.1 * weariness,
        "Intimacy": 0.5 + 0.3 * loneliness + 0.2 * vulnerability,
    }

    # Normalize to 0.0-1.0
    max_w = max(weights.values()) or 1.0
    return {k: round(v / max_w, 3) for k, v in weights.items()}


# ---------------------------------------------------------------------------
# Context gathering (Phase 1: memory-first)
# ---------------------------------------------------------------------------

def gather_context(
    query: str,
    content_type: ContentType,
    scopes: Optional[List[MemoryScope]] = None,
    k_per_scope: int = 3,
) -> DiscoveryContext:
    """
    Query memory across relevant scopes and load persona state.

    Call this BEFORE making external API calls so discovery is
    informed by what is already known and what the persona prefers.
    """
    effective_scopes = scopes or _SCOPE_DEFAULTS.get(content_type, _SCOPE_DEFAULTS_FALLBACK)

    # Multi-scope recall
    memory_hits: Dict[str, RecallResult] = {}
    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL, use_python_api=True)
        for scope in effective_scopes:
            try:
                result = client.recall(query, scope=scope, k=k_per_scope)
                if result.found:
                    memory_hits[scope.value if hasattr(scope, "value") else str(scope)] = result
            except Exception as e:
                logger.debug("Recall failed for scope {}: {}", scope, e)
    except Exception as e:
        logger.debug("Memory client unavailable: {}", e)

    # Persona state + bridge weights
    state = load_persona_state()
    weights = persona_bridge_weights(state)

    # Episodic anchors from memory hits
    episodic: List[str] = []
    for result in memory_hits.values():
        for item in result.items:
            tags = item.get("tags", [])
            # Look for episodic association tags
            for tag in tags:
                if "_" in tag and tag[0].isupper():
                    episodic.append(tag)

    # Prior titles (for novelty detection)
    prior_titles: Set[str] = set()
    for result in memory_hits.values():
        for item in result.items:
            problem = item.get("problem", "")
            # Extract title from "Discovered movie: Title" format
            if ":" in problem:
                title = problem.split(":", 1)[1].strip().lower()
                prior_titles.add(title)
            # Also add the raw problem text
            prior_titles.add(problem.lower())

    ctx = DiscoveryContext(
        memory_hits=memory_hits,
        persona_state=state,
        bridge_weights=weights,
        episodic_anchors=list(set(episodic)),
        prior_titles=prior_titles,
        query=query,
    )
    logger.debug(
        "Discovery context: {} memory hits, bridges={}, episodes={}",
        ctx.total_hits,
        [b for b, w in sorted(weights.items(), key=lambda x: -x[1])[:3]],
        episodic[:3],
    )
    return ctx


# ---------------------------------------------------------------------------
# Scoring (Phase 3: persona-weighted reranking)
# ---------------------------------------------------------------------------

def _item_text(item: Dict[str, Any]) -> str:
    """Build searchable text from a result item."""
    parts = []
    for key in ("title", "name", "artist", "author", "description", "overview", "biography"):
        val = item.get(key, "")
        if val:
            parts.append(str(val))
    # Include genre/subject/tag lists
    for key in ("subjects", "genres", "tags", "genre_names"):
        val = item.get(key, [])
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
    return " ".join(parts)


def score_results(
    results: List[Dict[str, Any]],
    context: DiscoveryContext,
    content_type: ContentType,
    raw_score_key: str = "popularity",
) -> List[ScoredResult]:
    """
    Score and rerank API results using persona + memory context.

    Scoring weights:
      bridge_alignment: 0.30  (persona bridge preference match)
      raw_score:        0.25  (original API ranking signal)
      novelty:          0.20  (not already in memory)
      episodic:         0.15  (lore event resonance)
      reinforcement:    0.10  (mentioned in prior memory)
    """
    scored: List[ScoredResult] = []

    for item in results:
        text = _item_text(item)
        title = item.get("title", item.get("name", "")).lower()

        # 1. Extract bridges for this item
        bridges = get_bridge_attributes(text, content_type=content_type)

        # 2. Bridge alignment with persona weights
        if bridges:
            alignment = sum(context.bridge_weights.get(b, 0.5) for b in bridges)
            alignment = min(alignment / len(bridges), 1.0)
        else:
            alignment = 0.0

        # 3. Episodic resonance
        episodes = get_episodic_associations(bridges, text)
        anchor_set = set(context.episodic_anchors)
        resonance = min(len(set(episodes) & anchor_set) * 0.3, 1.0) if anchor_set else 0.0

        # 4. Memory reinforcement
        reinforcement = 0.0
        for result in context.memory_hits.values():
            for mem_item in result.items:
                problem = mem_item.get("problem", "").lower()
                if title and (title in problem or problem in title):
                    reinforcement = min(reinforcement + 0.3, 1.0)

        # 5. Novelty (not already discovered)
        novelty = 0.0 if title in context.prior_titles else 1.0

        # 6. Raw score (normalize to 0-1)
        raw = item.get(raw_score_key, 0)
        if isinstance(raw, (int, float)):
            raw_norm = min(raw / 100.0, 1.0) if raw > 0 else 0.5
        else:
            raw_norm = 0.5

        # 7. Combined score
        final = (
            0.30 * alignment
            + 0.25 * raw_norm
            + 0.20 * novelty
            + 0.15 * resonance
            + 0.10 * reinforcement
        )

        scored.append(ScoredResult(
            item=item,
            raw_score=raw_norm,
            bridge_alignment=round(alignment, 4),
            episodic_resonance=round(resonance, 4),
            memory_reinforcement=round(reinforcement, 4),
            novelty=novelty,
            final_score=round(final, 4),
            bridge_tags=bridges,
            episodic_associations=episodes,
            worth_remembering=alignment > 0.5 and novelty > 0.5,
        ))

    scored.sort(key=lambda s: s.final_score, reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Storage (Phase 4: persist interesting discoveries)
# ---------------------------------------------------------------------------

def store_discoveries(
    scored: List[ScoredResult],
    content_type: ContentType,
    scope: MemoryScope = MemoryScope.HORUS_LORE,
    max_store: int = 3,
) -> int:
    """
    Store top-scoring novel discoveries back to memory.

    Returns number of items successfully stored.
    """
    worth = [s for s in scored if s.worth_remembering][:max_store]
    if not worth:
        return 0

    stored = 0
    try:
        client = MemoryClient(scope=scope, use_python_api=True)
        for s in worth:
            title = s.item.get("title", s.item.get("name", "Unknown"))
            problem = f"Discovered {content_type.value}: {title}"
            solution = json.dumps({
                "item": {k: v for k, v in s.item.items() if isinstance(v, (str, int, float, bool, list))},
                "bridges": s.bridge_tags,
                "episodes": s.episodic_associations,
                "score": s.final_score,
            }, default=str)
            tags = ["discovery", content_type.value] + s.bridge_tags
            try:
                result = client.learn(problem=problem, solution=solution, scope=scope, tags=tags)
                if result.success:
                    stored += 1
            except Exception as e:
                logger.debug("Failed to store discovery '{}': {}", title, e)
    except Exception as e:
        logger.debug("Memory client unavailable for storage: {}", e)

    if stored:
        logger.info("Stored {}/{} discoveries to memory (scope={})", stored, len(worth), scope)
    return stored
