"""Typed code-edge records for deterministic ingest-code graph artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal


EdgeType = Literal["DEFINES", "IMPORTS", "CALLS", "INHERITS", "IMPLEMENTS"]
EntityType = Literal["file", "symbol"]
ResolutionStatus = Literal["resolved", "candidate", "unresolved"]


def _sha256_id(prefix: str, values: list[str]) -> str:
    basis = "\x1f".join(values)
    return f"{prefix}_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:40]}"


@dataclass(frozen=True)
class CodeEdgeRecord:
    """One static edge occurrence with explicit resolution and traversal state."""

    from_id: str
    from_entity_type: EntityType
    edge_type: EdgeType
    resolution_status: ResolutionStatus
    resolution_method: str
    confidence: float
    provenance: str
    source_path: str
    source_start_line: int
    source_end_line: int
    source_start_column: int
    source_end_column: int
    to_id: str | None = None
    to_entity_type: EntityType | None = None
    active_for_traversal: bool = False
    synthesized_by: str | None = None
    raw_reference: str = ""
    candidate_ids: list[str] = field(default_factory=list)
    candidate_descriptors: list[str] = field(default_factory=list)
    unresolved_reason: str = ""
    attempted_resolution_stages: list[str] = field(default_factory=list)
    legacy_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def edge_id(self) -> str:
        """Return a stable occurrence id bound to endpoints, status, and source span."""
        return _sha256_id(
            "ce",
            [
                self.from_id,
                self.to_id or "",
                self.edge_type,
                self.resolution_status,
                self.resolution_method,
                self.source_path,
                str(self.source_start_line),
                str(self.source_end_line),
                str(self.source_start_column),
                str(self.source_end_column),
                self.raw_reference,
                ",".join(sorted(self.candidate_ids)),
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the edge for JSONL output."""
        record: dict[str, Any] = {
            "edge_id": self.edge_id,
            "from_id": self.from_id,
            "from_entity_type": self.from_entity_type,
            "to_id": self.to_id,
            "to_entity_type": self.to_entity_type,
            "edge_type": self.edge_type,
            "resolution_status": self.resolution_status,
            "resolution_method": self.resolution_method,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "synthesized_by": self.synthesized_by,
            "source_path": self.source_path,
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
            "source_start_column": self.source_start_column,
            "source_end_column": self.source_end_column,
            "active_for_traversal": self.active_for_traversal,
            "raw_reference": self.raw_reference,
            "candidate_ids": sorted(self.candidate_ids),
            "candidate_descriptors": sorted(self.candidate_descriptors),
            "unresolved_reason": self.unresolved_reason,
            "attempted_resolution_stages": list(self.attempted_resolution_stages),
            "status": self.resolution_status,
        }
        record.update(self.legacy_fields)
        return record
