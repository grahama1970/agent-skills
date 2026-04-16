from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass(slots=True)
class IntegrityIssue:
    code: str
    severity: Severity
    message: str
    entity_type: str  # document | section | edge
    entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass(slots=True)
class IntegritySummary:
    dataset_name: str
    started_at: datetime
    completed_at: datetime
    documents_count: int
    sections_count: int
    embedding_text_count: int      # 384d MiniLM vectors present
    embedding_visual_count: int    # 2048d Qwen3-VL vectors present
    missing_embeddings_text: int
    missing_embeddings_visual: int
    orphan_chunks: int
    stale_documents: int
    coverage_text: float           # embedding_text / sections
    coverage_visual: float         # embedding_visual / sections
    issues_by_severity: dict[str, int] = field(default_factory=dict)
    edge_counts: dict[str, int] = field(default_factory=dict)  # has_section, has_table, ...

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        d["completed_at"] = self.completed_at.isoformat()
        return d


@dataclass(slots=True)
class RetrievalMetrics:
    num_queries: int
    recall_at_k: dict[int, float] = field(default_factory=dict)
    ndcg_at_k: dict[int, float] = field(default_factory=dict)
    mrr_at_k: dict[int, float] = field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = field(default_factory=dict)
    mean_latency_ms: float | None = None
    p95_latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationReport:
    integrity_summary: IntegritySummary
    integrity_issues: list[IntegrityIssue] = field(default_factory=list)
    retrieval_metrics: RetrievalMetrics | None = None
    visual_verification: dict[str, Any] | None = None  # mean_score, low_confidence
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scope: str = "full"
    dataset_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "scope": self.scope,
            "dataset_metadata": self.dataset_metadata,
            "integrity_summary": self.integrity_summary.to_dict(),
            "integrity_issues": [i.to_dict() for i in self.integrity_issues],
            "retrieval_metrics": self.retrieval_metrics.to_dict() if self.retrieval_metrics else None,
            "visual_verification": self.visual_verification,
        }
