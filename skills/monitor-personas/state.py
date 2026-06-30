#!/usr/bin/env python3
"""
Unified state management for monitor-personas pipeline.

Manages state files for all pipeline stages:
- state.json - Persona check state (existing)
- learned.json - Learned transcript paths (existing)
- extracted.json - Extracted content paths
- classified.json - Stream classification results
- stream_state.json - Intent vs Persona classifications
- gap_tracker.json - Unresolved knowledge gaps
- training_state.json - Training data + model versions
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# Default state directory
DEFAULT_STATE_DIR = Path(os.environ.get(
    "PERSONA_MONITOR_STATE_DIR",
    Path.home() / ".pi/monitor-personas"
))


@dataclass
class PersonaCheckState:
    """State from persona source checking."""
    name: str
    priority: str
    category: str
    scope: str
    youtube_count: int = 0
    ingested_count: int = 0
    new_count: int = 0
    last_checked: str = ""
    sources_checked: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ExtractedContent:
    """State for extracted QRA content."""
    source_path: str
    output_path: str
    qra_count: int
    extracted_at: str
    persona_id: str
    scope: str


@dataclass
class StreamClassification:
    """Classification of content into Intent or Persona streams."""
    content_id: str
    stream: str  # "intent" or "persona"
    confidence: float
    taxonomy_tags: List[str]
    classified_at: str
    persona_id: str


@dataclass
class KnowledgeGap:
    """Unresolved knowledge gap to be researched."""
    gap_id: str
    description: str
    persona_id: str
    discovered_at: str
    status: str  # "pending", "researching", "resolved"
    dogpile_session: Optional[str] = None
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None


@dataclass
class TrainingState:
    """State for persona model training."""
    persona_id: str
    last_trained: Optional[str] = None
    model_version: int = 0
    model_path: Optional[str] = None
    training_samples: int = 0
    last_export_at: Optional[str] = None


@dataclass
class CurateResult:
    """A curated content discovery."""
    title: str
    content_type: str       # movie, book, music, arxiv, security, feed
    bridge: str             # Which bridge or query triggered this
    score: float            # final_score from discover-* or relevance
    persona_id: str
    discovered_at: str
    consumed: bool = False  # Set when ingested downstream
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateManager:
    """Manages all state files for the persona monitoring pipeline."""

    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # State file paths
        self.state_file = self.state_dir / "state.json"
        self.learned_file = self.state_dir / "learned.json"
        self.extracted_file = self.state_dir / "extracted.json"
        self.classified_file = self.state_dir / "classified.json"
        self.stream_state_file = self.state_dir / "stream_state.json"
        self.gap_tracker_file = self.state_dir / "gap_tracker.json"
        self.training_state_file = self.state_dir / "training_state.json"
        self.curate_state_file = self.state_dir / "curate_state.json"
        self.shared_library_file = self.state_dir / "shared_library_state.json"

    def _load_json(self, path: Path, default: Any = None) -> Any:
        """Load JSON file with fallback to default."""
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        return default if default is not None else {}

    def _save_json(self, path: Path, data: Any):
        """Save data as JSON."""
        path.write_text(json.dumps(data, indent=2, default=str))

    # ─────────────────────────────────────────────────────────────────────────
    # Check State (Persona source checking)
    # ─────────────────────────────────────────────────────────────────────────

    def load_check_state(self) -> Dict[str, Any]:
        """Load persona check state."""
        return self._load_json(self.state_file, {"personas": {}, "last_check": None})

    def save_check_state(self, state: Dict[str, Any]):
        """Save persona check state."""
        self._save_json(self.state_file, state)

    def update_persona_check(self, persona_id: str, check_data: Dict[str, Any]):
        """Update check state for a specific persona."""
        state = self.load_check_state()
        state["personas"][persona_id] = {
            **check_data,
            "last_checked": datetime.now().isoformat(),
        }
        state["last_check"] = datetime.now().isoformat()
        self.save_check_state(state)

    # ─────────────────────────────────────────────────────────────────────────
    # Learned State (Transcripts learned to memory)
    # ─────────────────────────────────────────────────────────────────────────

    def load_learned(self) -> Set[str]:
        """Load set of learned transcript paths."""
        data = self._load_json(self.learned_file, [])
        return set(data) if isinstance(data, list) else set()

    def save_learned(self, learned: Set[str]):
        """Save learned transcript paths."""
        self._save_json(self.learned_file, list(learned))

    def mark_learned(self, path: str):
        """Mark a transcript as learned."""
        learned = self.load_learned()
        learned.add(path)
        self.save_learned(learned)

    def is_learned(self, path: str) -> bool:
        """Check if a transcript has been learned."""
        return path in self.load_learned()

    # ─────────────────────────────────────────────────────────────────────────
    # Extracted State (QRA extraction from content)
    # ─────────────────────────────────────────────────────────────────────────

    def load_extracted(self) -> Dict[str, ExtractedContent]:
        """Load extracted content state."""
        data = self._load_json(self.extracted_file, {})
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = ExtractedContent(**value)
        return result

    def save_extracted(self, extracted: Dict[str, ExtractedContent]):
        """Save extracted content state."""
        data = {k: asdict(v) for k, v in extracted.items()}
        self._save_json(self.extracted_file, data)

    def mark_extracted(self, content: ExtractedContent):
        """Mark content as extracted."""
        extracted = self.load_extracted()
        extracted[content.source_path] = content
        self.save_extracted(extracted)

    def is_extracted(self, source_path: str) -> bool:
        """Check if content has been extracted."""
        return source_path in self.load_extracted()

    # ─────────────────────────────────────────────────────────────────────────
    # Stream State (Intent vs Persona classification)
    # ─────────────────────────────────────────────────────────────────────────

    def load_stream_state(self) -> Dict[str, StreamClassification]:
        """Load stream classification state."""
        data = self._load_json(self.stream_state_file, {})
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = StreamClassification(**value)
        return result

    def save_stream_state(self, state: Dict[str, StreamClassification]):
        """Save stream classification state."""
        data = {k: asdict(v) for k, v in state.items()}
        self._save_json(self.stream_state_file, data)

    def classify_stream(
        self,
        content_id: str,
        stream: str,
        confidence: float,
        taxonomy_tags: List[str],
        persona_id: str,
    ):
        """Classify content into Intent or Persona stream."""
        state = self.load_stream_state()
        state[content_id] = StreamClassification(
            content_id=content_id,
            stream=stream,
            confidence=confidence,
            taxonomy_tags=taxonomy_tags,
            classified_at=datetime.now().isoformat(),
            persona_id=persona_id,
        )
        self.save_stream_state(state)

    def get_stream_stats(self) -> Dict[str, int]:
        """Get count of content in each stream."""
        state = self.load_stream_state()
        intent_count = sum(1 for v in state.values() if v.stream == "intent")
        persona_count = sum(1 for v in state.values() if v.stream == "persona")
        return {"intent": intent_count, "persona": persona_count, "total": len(state)}

    # ─────────────────────────────────────────────────────────────────────────
    # Gap Tracker (Unresolved knowledge gaps)
    # ─────────────────────────────────────────────────────────────────────────

    def load_gaps(self) -> Dict[str, KnowledgeGap]:
        """Load knowledge gaps."""
        data = self._load_json(self.gap_tracker_file, {})
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = KnowledgeGap(**value)
        return result

    def save_gaps(self, gaps: Dict[str, KnowledgeGap]):
        """Save knowledge gaps."""
        data = {k: asdict(v) for k, v in gaps.items()}
        self._save_json(self.gap_tracker_file, data)

    def add_gap(self, description: str, persona_id: str) -> str:
        """Add a new knowledge gap."""
        gaps = self.load_gaps()
        gap_id = f"gap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(gaps)}"
        gaps[gap_id] = KnowledgeGap(
            gap_id=gap_id,
            description=description,
            persona_id=persona_id,
            discovered_at=datetime.now().isoformat(),
            status="pending",
        )
        self.save_gaps(gaps)
        return gap_id

    def resolve_gap(self, gap_id: str, resolution: str):
        """Mark a gap as resolved."""
        gaps = self.load_gaps()
        if gap_id in gaps:
            gaps[gap_id].status = "resolved"
            gaps[gap_id].resolved_at = datetime.now().isoformat()
            gaps[gap_id].resolution = resolution
            self.save_gaps(gaps)

    def get_pending_gaps(self) -> List[KnowledgeGap]:
        """Get all pending (unresolved) gaps."""
        gaps = self.load_gaps()
        return [g for g in gaps.values() if g.status == "pending"]

    # ─────────────────────────────────────────────────────────────────────────
    # Training State (Persona model training)
    # ─────────────────────────────────────────────────────────────────────────

    def load_training_state(self) -> Dict[str, TrainingState]:
        """Load training state for all personas."""
        data = self._load_json(self.training_state_file, {})
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = TrainingState(**value)
        return result

    def save_training_state(self, state: Dict[str, TrainingState]):
        """Save training state."""
        data = {k: asdict(v) for k, v in state.items()}
        self._save_json(self.training_state_file, data)

    def update_training(
        self,
        persona_id: str,
        model_path: str,
        training_samples: int,
    ):
        """Update training state after model training."""
        state = self.load_training_state()
        if persona_id not in state:
            state[persona_id] = TrainingState(persona_id=persona_id)

        state[persona_id].last_trained = datetime.now().isoformat()
        state[persona_id].model_version += 1
        state[persona_id].model_path = model_path
        state[persona_id].training_samples = training_samples
        self.save_training_state(state)

    def needs_training(self, persona_id: str, min_new_samples: int = 100) -> bool:
        """Check if persona needs retraining."""
        state = self.load_training_state()
        if persona_id not in state:
            return True

        # Future work: Check if enough new samples since last training
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Curate State (Proactive content discovery)
    # ─────────────────────────────────────────────────────────────────────────

    def load_curate_queue(self) -> List[CurateResult]:
        """Load curate discovery queue."""
        data = self._load_json(self.curate_state_file, [])
        if not isinstance(data, list):
            return []
        results = []
        for item in data:
            if isinstance(item, dict):
                results.append(CurateResult(**item))
        return results

    def save_curate_queue(self, queue: List[CurateResult]):
        """Save curate discovery queue."""
        self._save_json(self.curate_state_file, [asdict(r) for r in queue])

    def add_curate_results(self, results: List[CurateResult]):
        """Append new curate results, deduped by title + persona_id."""
        queue = self.load_curate_queue()
        existing = {(r.title.lower(), r.persona_id) for r in queue}
        added = 0
        for r in results:
            key = (r.title.lower(), r.persona_id)
            if key not in existing:
                queue.append(r)
                existing.add(key)
                added += 1
        if added:
            self.save_curate_queue(queue)
        return added

    def get_curate_summary(self) -> Dict[str, Any]:
        """Get curate queue summary counts by type and persona."""
        queue = self.load_curate_queue()
        by_type: Dict[str, int] = {}
        by_persona: Dict[str, int] = {}
        unconsumed = 0
        for r in queue:
            by_type[r.content_type] = by_type.get(r.content_type, 0) + 1
            by_persona[r.persona_id] = by_persona.get(r.persona_id, 0) + 1
            if not r.consumed:
                unconsumed += 1
        return {
            "total": len(queue),
            "unconsumed": unconsumed,
            "by_type": by_type,
            "by_persona": by_persona,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Shared Library State (Per-persona document processing tracking)
    # ─────────────────────────────────────────────────────────────────────────

    def load_shared_library_state(self) -> Dict[str, Dict[str, str]]:
        """Load shared library processing state.

        Returns dict mapping doc_path -> {persona_id: timestamp}.
        """
        return self._load_json(self.shared_library_file, {})

    def save_shared_library_state(self, state: Dict[str, Dict[str, str]]):
        """Save shared library processing state."""
        self._save_json(self.shared_library_file, state)

    def is_shared_processed(self, doc_path: str, persona_id: str) -> bool:
        """Check if a shared library document has been processed for a persona."""
        state = self.load_shared_library_state()
        return persona_id in state.get(doc_path, {})

    def mark_shared_processed(self, doc_path: str, persona_id: str):
        """Mark a shared library document as processed for a persona."""
        state = self.load_shared_library_state()
        if doc_path not in state:
            state[doc_path] = {}
        state[doc_path][persona_id] = datetime.now().isoformat()
        self.save_shared_library_state(state)

    def get_shared_library_stats(self) -> Dict[str, Any]:
        """Get shared library processing statistics."""
        state = self.load_shared_library_state()
        total_docs = len(state)
        total_processings = sum(len(personas) for personas in state.values())
        return {
            "total_documents": total_docs,
            "total_persona_processings": total_processings,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Summary / Status
    # ─────────────────────────────────────────────────────────────────────────

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get overall pipeline status."""
        check_state = self.load_check_state()
        learned = self.load_learned()
        extracted = self.load_extracted()
        stream_stats = self.get_stream_stats()
        gaps = self.load_gaps()
        training = self.load_training_state()

        curate_summary = self.get_curate_summary()
        shared_stats = self.get_shared_library_stats()

        return {
            "last_check": check_state.get("last_check"),
            "personas_monitored": len(check_state.get("personas", {})),
            "curate_queue": curate_summary,
            "shared_library": shared_stats,
            "transcripts_learned": len(learned),
            "content_extracted": len(extracted),
            "stream_classification": stream_stats,
            "pending_gaps": len([g for g in gaps.values() if g.status == "pending"]),
            "total_gaps": len(gaps),
            "trained_personas": len([t for t in training.values() if t.last_trained]),
        }


# Singleton instance
_state_manager: Optional[StateManager] = None


def get_state_manager(state_dir: Optional[Path] = None) -> StateManager:
    """Get or create the state manager singleton."""
    global _state_manager
    if _state_manager is None or state_dir is not None:
        _state_manager = StateManager(state_dir or DEFAULT_STATE_DIR)
    return _state_manager
