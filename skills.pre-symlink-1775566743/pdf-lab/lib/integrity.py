"""integrity — datalake integrity checks via httpx to localhost:8601."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from loguru import logger

from .metrics_models import IntegrityIssue, IntegritySummary, Severity

_BASE = "http://localhost:8601"
_TIMEOUT = 30.0

_EDGE_COLLECTIONS = ("has_section", "has_table", "has_figure", "has_requirement")


def _post(path: str, payload: dict) -> dict:
    r = httpx.post(f"{_BASE}{path}", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _count(collection: str) -> int:
    data = _post("/list", {"collection": collection, "k": 1})
    return data.get("total", 0)


def check_integrity(sample_size: int = 100) -> tuple[IntegritySummary, list[IntegrityIssue]]:
    """Run datalake integrity checks, return summary + issues."""
    started = datetime.now(timezone.utc)
    issues: list[IntegrityIssue] = []

    try:
        doc_count = _count("documents")
        sections_total = _count("sections")

        data = _post("/list", {
            "collection": "sections", "k": sample_size,
            "return_fields": ["_key", "title", "embedding", "embedding_visual"],
        })
        rows = data.get("results") or data.get("documents") or []

        has_text = sum(1 for r in rows if r.get("embedding") and len(r["embedding"]) == 384)
        has_visual = sum(1 for r in rows if r.get("embedding_visual") and len(r["embedding_visual"]) == 2048)
        sampled = len(rows) or 1

        for r in rows:
            key = r.get("_key", "?")
            if not r.get("embedding") or len(r.get("embedding", [])) != 384:
                issues.append(IntegrityIssue("missing_embedding_text", Severity.WARN,
                    f"Section {key} missing 384d text embedding", "section", key))
            if not r.get("embedding_visual") or len(r.get("embedding_visual", [])) != 2048:
                issues.append(IntegrityIssue("missing_embedding_visual", Severity.WARN,
                    f"Section {key} missing 2048d visual embedding", "section", key))

        edge_counts: dict[str, int] = {}
        for ec in _EDGE_COLLECTIONS:
            try:
                edge_counts[ec] = _count(ec)
            except Exception:
                edge_counts[ec] = 0

        summary = IntegritySummary(
            dataset_name="datalake", started_at=started,
            completed_at=datetime.now(timezone.utc),
            documents_count=doc_count, sections_count=sections_total,
            embedding_text_count=has_text, embedding_visual_count=has_visual,
            missing_embeddings_text=sampled - has_text,
            missing_embeddings_visual=sampled - has_visual,
            orphan_chunks=0, stale_documents=0,
            coverage_text=has_text / sampled, coverage_visual=has_visual / sampled,
            issues_by_severity={s.value: sum(1 for i in issues if i.severity == s) for s in Severity},
            edge_counts=edge_counts,
        )
        logger.info("integrity check: {} docs, {}/{} text, {}/{} visual",
                     doc_count, has_text, sampled, has_visual, sampled)
        return summary, issues

    except httpx.ConnectError as exc:
        logger.error("memory daemon unreachable: {}", exc)
        issues.append(IntegrityIssue("connection_error", Severity.ERROR,
            f"Cannot reach {_BASE}: {exc}", "edge", None))
        now = datetime.now(timezone.utc)
        return IntegritySummary(
            dataset_name="datalake", started_at=started, completed_at=now,
            documents_count=0, sections_count=0, embedding_text_count=0,
            embedding_visual_count=0, missing_embeddings_text=0,
            missing_embeddings_visual=0, orphan_chunks=0, stale_documents=0,
            coverage_text=0.0, coverage_visual=0.0,
            issues_by_severity={"error": 1}, edge_counts={},
        ), issues


def check_document_integrity(doc_key: str) -> list[IntegrityIssue]:
    """Check a single document for integrity issues."""
    issues: list[IntegrityIssue] = []
    try:
        data = _post("/recall/by-keys", {"collection": "documents", "keys": [doc_key]})
        docs = data.get("documents") or data.get("results") or []
        if not docs:
            issues.append(IntegrityIssue("missing_document", Severity.ERROR,
                f"Document {doc_key} not found", "document", doc_key))
            return issues
        doc = docs[0]
        for field in ("title", "source_url", "extraction_date", "page_count"):
            if not doc.get(field):
                issues.append(IntegrityIssue("missing_field", Severity.WARN,
                    f"Document {doc_key} missing field '{field}'", "document", doc_key,
                    {"field": field}))
    except httpx.ConnectError as exc:
        issues.append(IntegrityIssue("connection_error", Severity.ERROR,
            f"Cannot reach {_BASE}: {exc}", "edge", None))
    return issues
