"""Evidence case graph data model.

Node types for CAE (Claims-Arguments-Evidence) trees stored in ArangoDB
via /memory. Aligned to CAE (Adelard), OSCAL (NIST), GSN (ISO 15026).

Inputs: Raw dicts from /memory recall or fresh construction.
Outputs: Serializable dicts for /memory learn and Rich display.
Failures: ValueError on invalid node_type or verdict state.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class GateResult:
    """Result of a single gate check in the decision tree."""

    gate: str  # gate_1_topic, gate_2_entities, etc.
    passed: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimNode:
    """Root of the evidence tree — the question being verified."""

    text: str
    category: str = "auto"
    id: str = field(default_factory=_uuid)
    node_type: str = "claim"
    created_at: str = field(default_factory=_now)
    verdict: str | None = None  # SATISFIED | NOT_SATISFIED | INCONCLUSIVE
    control_ids: list[str] = field(default_factory=list)
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    sub_claims: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyNode:
    """A verification approach — child of ClaimNode."""

    name: str
    skills: list[str] = field(default_factory=list)
    id: str = field(default_factory=_uuid)
    node_type: str = "strategy"
    turns: int = 0
    score: float = 0.0
    visits: int = 0
    wins: int = 0
    uct: float = 0.0
    selected: bool = False
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceNode:
    """A piece of evidence — child of StrategyNode."""

    method: str  # TEST | EXAMINE | COMPUTE (OSCAL vocabulary)
    layer: str  # seal | conformance | analytics | classifier | ...
    collector: str = "deterministic"  # deterministic | statistical | llm
    id: str = field(default_factory=_uuid)
    node_type: str = "evidence"
    result: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    artifact_ref: str = ""
    collected_at: str = field(default_factory=_now)
    control_ids: list[str] = field(default_factory=list)
    gate_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerdictNode:
    """Final judgment — child of ClaimNode, references winning strategy."""

    state: str  # satisfied | not_satisfied | inconclusive
    grade: str  # A+ | A | B | C | F
    score: float
    strategy_id: str
    evidence_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=_uuid)
    node_type: str = "verdict"
    reasoning: str = ""
    grader: dict[str, Any] = field(default_factory=lambda: {"type": "deterministic", "model_id": "", "modified_in_session": False})
    rendered_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def grade_from_score(score: float) -> str:
    """Map score to letter grade."""
    if score >= 0.95:
        return "A+"
    if score >= 0.88:
        return "A"
    if score >= 0.78:
        return "B"
    if score >= 0.65:
        return "C"
    return "F"


def verdict_from_score(score: float) -> str:
    """Map score to verdict state."""
    if score >= 0.88:
        return "satisfied"
    if score >= 0.65:
        return "inconclusive"
    return "not_satisfied"


@dataclass
class DecompositionNode:
    """Sentence decomposition for evidence case analysis.

    Captures the Given/Then structure of a question so the decomposition
    is auditable and persisted alongside ClaimNode.
    """

    question: str
    given_components: list[str] = field(default_factory=list)
    then_components: list[str] = field(default_factory=list)
    component_queries: dict[str, str] = field(default_factory=dict)
    component_entity_types: dict[str, str] = field(default_factory=dict)
    mermaid: str = ""
    id: str = field(default_factory=_uuid)
    node_type: str = "decomposition"
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


NODE_CLASSES = {
    "claim": ClaimNode,
    "strategy": StrategyNode,
    "evidence": EvidenceNode,
    "verdict": VerdictNode,
    "gate_result": GateResult,
    "decomposition": DecompositionNode,
}
