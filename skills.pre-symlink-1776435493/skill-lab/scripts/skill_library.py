#!/usr/bin/env python3
"""VOYAGER-style skill library — embedding-indexed successful compositions.

Successful compositions are stored with their embedding (description + outcome).
When generating new candidates, retrieve top-k similar past successes as context.
This is "primordial memory" — successful bonds inform future bond formation.

Reference: Wang et al., "VOYAGER: An Open-Ended Embodied Agent with LLMs"
           https://arxiv.org/abs/2305.16291

Usage:
    from skill_library import SkillLibrary
from loguru import logger
    lib = SkillLibrary.load_or_create()
    lib.add_success(chain, quality, energy, elegance, critique)
    similar = lib.retrieve_similar(chain_description, k=5)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

LIBRARY_FILE = STATE_DIR / "skill_library.json"

# Quality threshold — only top compositions enter the library
MIN_ELEGANCE_PERCENTILE = 0.2  # Top 80% (low bar initially, tighten later)


@dataclass
class LibraryEntry:
    """A successful composition stored in the skill library."""
    chain: list[str]
    description: str       # Human-readable: "extractor → memory → taxonomy"
    quality: float         # Success rate
    energy: float          # Total ATP cost
    elegance_score: float  # Elegance metric
    elegance_grade: str    # brilliant/elegant/adequate/wasteful/bloated
    task_type: str = ""    # extraction/research/security/creation
    critique: str = ""     # LLM-as-judge feedback (Priority 6)
    embedding: list[float] = field(default_factory=list)
    inserted_at: float = 0.0


@dataclass
class SkillLibrary:
    """Embedding-indexed library of successful skill compositions.

    Inspired by VOYAGER's skill library: stores reusable compositions
    indexed by embedding descriptions. When facing new tasks, retrieves
    top-k similar successful compositions as context for mutation.
    """
    entries: list[LibraryEntry] = field(default_factory=list)
    total_offered: int = 0  # Total compositions offered for inclusion
    created_at: float = field(default_factory=time.time)

    def add_success(
        self,
        chain: list[str],
        quality: float,
        energy: float,
        elegance_score: float,
        elegance_grade: str,
        task_type: str = "",
        critique: str = "",
    ) -> bool:
        """Add a successful composition to the library.

        Only accepts compositions above the quality threshold.
        Returns True if added.
        """
        self.total_offered += 1

        # Quality gate — reject wasteful/bloated compositions
        if elegance_grade in ("wasteful", "bloated", "none"):
            return False

        description = " → ".join(chain)

        # Compute embedding if embedding service available
        embedding = _embed_text(description)

        entry = LibraryEntry(
            chain=chain,
            description=description,
            quality=quality,
            energy=energy,
            elegance_score=elegance_score,
            elegance_grade=elegance_grade,
            task_type=task_type,
            critique=critique,
            embedding=embedding,
            inserted_at=time.time(),
        )

        # Deduplicate — if same chain already exists, keep higher elegance
        chain_key = "+".join(chain)
        for i, existing in enumerate(self.entries):
            if "+".join(existing.chain) == chain_key:
                if elegance_score > existing.elegance_score:
                    self.entries[i] = entry
                    return True
                return False

        self.entries.append(entry)

        # Prune if library grows too large (keep top 500 by elegance)
        if len(self.entries) > 500:
            self.entries.sort(key=lambda e: e.elegance_score, reverse=True)
            self.entries = self.entries[:500]

        return True

    def retrieve_similar(
        self,
        query: str | list[str],
        k: int = 5,
        task_type: str | None = None,
    ) -> list[LibraryEntry]:
        """Retrieve top-k similar compositions from the library.

        Uses cosine similarity on embeddings if available,
        falls back to Jaccard similarity on skill sets.
        """
        if not self.entries:
            return []

        # Resolve query
        if isinstance(query, list):
            query_text = " → ".join(query)
            query_skills = set(query)
        else:
            query_text = query
            query_skills = set(query.split(" → "))

        # Filter by task type if specified
        candidates = self.entries
        if task_type:
            typed = [e for e in candidates if e.task_type == task_type]
            if typed:
                candidates = typed

        # Try embedding similarity first
        query_embedding = _embed_text(query_text)
        if query_embedding and any(e.embedding for e in candidates):
            scored = []
            for entry in candidates:
                if entry.embedding:
                    sim = _cosine_similarity(query_embedding, entry.embedding)
                    scored.append((sim, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [entry for _, entry in scored[:k]]

        # Fallback: Jaccard similarity on skill sets
        scored = []
        for entry in candidates:
            entry_skills = set(entry.chain)
            intersection = len(query_skills & entry_skills)
            union = len(query_skills | entry_skills)
            jaccard = intersection / union if union > 0 else 0
            scored.append((jaccard, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:k]]

    def stats(self) -> dict[str, Any]:
        """Summary statistics."""
        if not self.entries:
            return {
                "size": 0,
                "total_offered": self.total_offered,
                "acceptance_rate": 0.0,
            }
        grades = {}
        for e in self.entries:
            grades[e.elegance_grade] = grades.get(e.elegance_grade, 0) + 1
        return {
            "size": len(self.entries),
            "total_offered": self.total_offered,
            "acceptance_rate": round(len(self.entries) / max(1, self.total_offered), 4),
            "grade_distribution": grades,
            "has_embeddings": sum(1 for e in self.entries if e.embedding),
        }

    def save(self, path: Path | None = None) -> None:
        """Persist library to JSON."""
        path = path or LIBRARY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_offered": self.total_offered,
            "created_at": self.created_at,
            "entries": [asdict(e) for e in self.entries],
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load_or_create(cls, path: Path | None = None) -> SkillLibrary:
        """Load existing library or create a new one."""
        path = path or LIBRARY_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            lib = cls(
                total_offered=data.get("total_offered", 0),
                created_at=data.get("created_at", time.time()),
            )
            for entry_data in data.get("entries", []):
                lib.entries.append(LibraryEntry(**entry_data))
            return lib
        except (json.JSONDecodeError, OSError, TypeError):
            return cls()


# ---------------------------------------------------------------------------
# Embedding helpers — use local embedding service if available
# ---------------------------------------------------------------------------

def _embed_text(text: str) -> list[float]:
    """Embed text using the local embedding service.

    Returns empty list if service unavailable (graceful degradation).
    """
    try:
        import httpx
        resp = httpx.post(
            "http://localhost:8602/embed",
            json={"text": text},
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("embedding", [])
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
