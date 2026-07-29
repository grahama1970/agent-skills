"""Pure source-bearing evidence classification shared by research consumers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return a SHA-256 hex digest for a local file."""
    return sha256(path.read_bytes()).hexdigest()


def classify_source_bearing_record(record: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    """Classify one provider/evidence record without model judgment.

    Source-bearing means the record identifies a retrievable source and binds a
    local retrieval/evaluation artifact hash. Model synthesis, query tailoring,
    ambiguity checks, and codex_knowledge are explicitly non-source-bearing.
    """

    provider = str(record.get("provider") or "").lower()
    source_type = str(record.get("source_type") or "").lower()
    if provider in {"codex_knowledge", "model_synthesis", "synthesis", "query_tailoring", "ambiguity"}:
        return {"source_bearing": False, "reason": "model or interpretation lane"}
    artifact = record.get("retrieval_artifact") or record.get("artifact_path")
    digest = record.get("content_sha256") or record.get("artifact_sha256") or record.get("sha256")
    if not isinstance(artifact, str) or not artifact.strip():
        return {"source_bearing": False, "reason": "missing retrieval artifact"}
    if not isinstance(digest, str) or not digest.strip():
        return {"source_bearing": False, "reason": "missing artifact hash"}
    if base_dir is not None:
        path = Path(artifact)
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists() or not path.is_file():
            return {"source_bearing": False, "reason": "retrieval_artifact does not exist"}
        if sha256_file(path) != digest:
            return {"source_bearing": False, "reason": "artifact hash mismatch"}
    has_identity = any(
        isinstance(record.get(key), str) and record.get(key, "").strip()
        for key in ("url", "repository", "paper_id", "video_id")
    )
    if provider == "github" or source_type == "github_repository":
        has_receipt = bool(record.get("github_search_receipt") or record.get("evaluation_receipt") or record.get("source_bearing"))
        return {
            "source_bearing": bool(has_identity and has_receipt),
            "reason": "github evaluation receipt bound" if has_identity and has_receipt else "missing github-search evaluation receipt",
        }
    if source_type in {"web_page", "paper", "video", "feed_snapshot"} or provider in {
        "brave",
        "brave_questions",
        "arxiv",
        "youtube",
        "feeds",
    }:
        return {
            "source_bearing": bool(has_identity or source_type == "feed_snapshot"),
            "reason": "source identity and artifact hash bound" if has_identity or source_type == "feed_snapshot" else "missing source identity",
        }
    return {"source_bearing": False, "reason": "unsupported source class"}


def summarize_source_bearing_records(records: list[dict[str, Any]], *, base_dir: Path | None = None) -> dict[str, Any]:
    """Summarize source-bearing records for downstream gates."""

    source_records = []
    model_synthesis_present = False
    errors = []
    for record in records:
        provider = str(record.get("provider") or "").lower()
        model_synthesis_present = model_synthesis_present or provider in {"codex_knowledge", "model_synthesis", "synthesis"}
        classified = classify_source_bearing_record(record, base_dir=base_dir)
        if classified["source_bearing"]:
            source_records.append(record)
        elif record.get("ok") is True or record.get("source_bearing") is True:
            errors.append(classified["reason"])
    return {
        "source_bearing_provider_count": len({record.get("provider") for record in source_records}),
        "source_bearing_evidence_count": len(source_records),
        "model_synthesis_present": model_synthesis_present,
        "research_evidence_sufficient": bool(source_records),
        "errors": sorted(set(errors)),
    }
