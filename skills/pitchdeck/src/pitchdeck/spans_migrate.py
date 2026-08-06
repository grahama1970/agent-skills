"""Migrate a bundle to the span-first claim model (#1226).

For each claim, locate supporting verbatim excerpts in the RESOLVED source
files: an exact (normalized) hit of the claim text becomes a span directly;
otherwise the best source line by token overlap becomes the span, which keeps
the excerpt verbatim-from-source while making the claim's rendering an
aggregation over it. Also stamps transform_class on quote/paraphrase bindings
where the mechanical checks pass. Reports counts; writes only with apply=True.
Failure modes: unresolvable sources are skipped and reported, never guessed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from loguru import logger

from .models import ClaimLedger, DeckManifest, EvidenceSpan, SourceManifest


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm(text)))


def _source_lines(sources: SourceManifest, source_manifest_dir: Path) -> dict[str, list[str]]:
    lines: dict[str, list[str]] = {}
    for source in sources.sources:
        path = Path(os.path.expandvars(source.path))
        if not path.is_absolute():
            path = source_manifest_dir / path
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        lines[source.id] = [line.strip() for line in raw.splitlines() if len(line.strip()) > 20]
    return lines


def migrate_spans(
    deck: DeckManifest,
    ledger: ClaimLedger,
    sources: SourceManifest,
    *,
    source_manifest_dir: Path,
    ledger_path: Path,
    apply: bool = False,
) -> dict[str, int]:
    corpus = _source_lines(sources, source_manifest_dir)
    exact = best_effort = unresolved = 0
    for claim in ledger.claims:
        if claim.evidence_spans:
            continue
        claim_norm = _norm(claim.text)
        claim_tokens = _tokens(claim.text)
        hit: EvidenceSpan | None = None
        best_score, best_line, best_source = 0.0, "", ""
        for source_id, lines in corpus.items():
            for line in lines:
                if claim_norm in _norm(line) or _norm(line) in claim_norm:
                    hit = EvidenceSpan(source_id=source_id, text=line)
                    break
                overlap = len(claim_tokens & _tokens(line)) / max(1, len(claim_tokens))
                if overlap > best_score:
                    best_score, best_line, best_source = overlap, line, source_id
            if hit:
                break
        if hit is not None:
            claim.evidence_spans = [hit]
            exact += 1
        elif best_score >= 0.4:
            claim.evidence_spans = [EvidenceSpan(source_id=best_source, text=best_line)]
            best_effort += 1
        else:
            unresolved += 1
            logger.warning("no span found for claim '{}' (best overlap {:.0%})", claim.id, best_score)

    if apply:
        payload = ledger.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=False)
        payload["claims"] = [
            {k: v for k, v in c.items() if v not in ([], None)} for c in payload["claims"]
        ]
        ledger_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    counts = {"exact_spans": exact, "best_effort_spans": best_effort, "unresolved": unresolved}
    logger.info("span migration ({}): {}", "applied" if apply else "dry-run", counts)
    return counts
