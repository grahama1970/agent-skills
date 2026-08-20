"""Clause-level provenance over existing lanes (#1476).

The receipt machinery becomes visible product: every substantive card clause
is mapped to the retrieved source spans that actually support it, sources are
digest-stamped at retrieval, and verification RECOMPUTES the anchors from the
filesystem -- a mutated or deleted source renders as invalidated evidence,
never silently retained support. Clauses with no resolvable source are marked
unsourced; no clause borrows another clause's citation.

Deterministic floor: mapping is token overlap between clause and source
excerpt. It can under-claim (a paraphrased clause shows unsourced) but cannot
invent support.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_CLAUSE_SPLIT_RE = re.compile(r"(?:\n#+\s*|\n[-*]\s+|(?<=[.!?])\s+|\n\n)")
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{3,}")
CLAUSE_SUPPORT_THRESHOLD = 0.30


def content_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def stamp_source(source_payload: dict[str, Any]) -> None:
    """Record the cited file's digest at retrieval time (mutation detector)."""

    path = source_payload.get("path")
    if path and Path(path).is_file():
        digest = content_sha256(Path(path))
        if digest:
            source_payload.setdefault("metadata", {})["content_sha256"] = digest


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text)}


def split_clauses(answer: str) -> list[str]:
    clauses = [clause.strip() for clause in _CLAUSE_SPLIT_RE.split(answer or "")]
    return [clause for clause in clauses if len(clause) >= 25][:40]


def map_clauses(answer: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic clause -> source mapping. Each clause cites only sources
    whose own excerpt overlaps it; nothing is inherited card-wide."""

    mapped: list[dict[str, Any]] = []
    # Generated sources (the fast solver's own receipt) are excluded from
    # clause mapping: their excerpt IS the answer, so every clause would
    # trivially self-cite the generator instead of retrieved evidence --
    # observed live before this guard (7/7 clauses "sourced" by the answer).
    source_tokens = [
        (source, _tokens(str(source.get("excerpt") or "")))
        for source in sources
        if (source.get("metadata") or {}).get("mode") != "scillm_fast_path"
        and str(source.get("lane")) not in {"ask", "RetrievalLane.ASK"}
    ]
    for clause in split_clauses(answer):
        clause_tokens = _tokens(clause)
        cites: list[str] = []
        for source, tokens in source_tokens:
            if not clause_tokens or not tokens:
                continue
            overlap = len(clause_tokens & tokens) / len(clause_tokens)
            if overlap >= CLAUSE_SUPPORT_THRESHOLD:
                cites.append(str(source.get("source_id")))
        mapped.append({"clause": clause, "source_ids": cites, "sourced": bool(cites)})
    return mapped


def verify_source(source_payload: dict[str, Any]) -> dict[str, Any]:
    """Recompute this source's anchor from the filesystem, fail closed."""

    source_id = str(source_payload.get("source_id"))
    path_value = source_payload.get("path")
    metadata = source_payload.get("metadata") or {}
    stamped = metadata.get("content_sha256")
    if not path_value:
        return {"source_id": source_id, "state": "not_file_backed", "ok": True}
    path = Path(str(path_value))
    if not path.is_file():
        return {"source_id": source_id, "state": "missing", "ok": False}
    current = content_sha256(path)
    if stamped and current != stamped:
        return {"source_id": source_id, "state": "digest_mismatch", "ok": False,
                "stamped": stamped, "current": current}
    line_start = source_payload.get("line_start")
    anchor_line = None
    if line_start:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if int(line_start) <= len(lines):
            anchor_line = lines[int(line_start) - 1][:200]
        else:
            return {"source_id": source_id, "state": "line_out_of_range", "ok": False}
    return {"source_id": source_id, "state": "verified" if stamped else "unstamped",
            "ok": True, "anchor_line": anchor_line, "current": current}


def card_provenance(card_payload: dict[str, Any]) -> dict[str, Any]:
    """Full provenance readback for one card: chain + verification."""

    sources = card_payload.get("sources") or []
    verification = {v["source_id"]: v for v in (verify_source(s) for s in sources)}
    clauses = map_clauses(str(card_payload.get("answer") or ""), sources)
    for clause in clauses:
        clause["invalidated"] = any(
            not verification.get(source_id, {}).get("ok", True)
            for source_id in clause["source_ids"]
        )
    return {
        "card_id": card_payload.get("card_id"),
        "question_id": card_payload.get("question_id"),
        "question_revision": card_payload.get("question_revision"),
        "clauses": clauses,
        "sources": [
            {
                "source_id": s.get("source_id"),
                "label": s.get("label"),
                "lane": s.get("lane"),
                "path": s.get("path"),
                "line_start": s.get("line_start"),
                "line_end": s.get("line_end"),
                "excerpt": str(s.get("excerpt") or "")[:4_000],
                "verification": verification.get(str(s.get("source_id"))),
            }
            for s in sources
        ],
    }
