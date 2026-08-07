"""Executable deterministic design lint (#1279 layer 1; best-practices-slide-design rules as code).

Runs the DETERMINISTIC subset of the design skill over a deck.document.json:
DESIGN_* findings with typed codes, exit 1 on any finding. This is the floor,
not the verdict — the agent-judgment critique (layer 2) and the agentic-evals
harness with seeded defects (layer 3) sit above it, and the human taste
oracle (layer 4) stays final. Checks: DENSITY_BUDGET, BAND_OVERFLOW (banded
recipes must fit a one-line title), MIDWORD_TRUNCATION (bound text must be a
word-boundary prefix of its claim text), MISSING_VISUAL (recipe demands a
visual channel), DIAGRAM_SHARE (one-big-diagram slides need >=30% visual
area), REVEAL_MISMATCH.
"""

from __future__ import annotations

import json
from pathlib import Path

from .document import DeckDocument, DocElementKind, iter_tree

BANDED_TITLE_MAX_WORDS = 10


def lint_document(document: DeckDocument) -> list[dict]:
    findings: list[dict] = []
    claims = {c.id: c for c in document.claims}

    def finding(code: str, slide_id: str, detail: str) -> None:
        findings.append({"code": f"DESIGN_{code}", "slide": slide_id, "detail": detail})

    for slide in document.slides:
        if slide.intent is None:
            continue
        tree = list(iter_tree(slide.elements))
        recipe = slide.intent.recipe
        # role=="footer" is mandatory qualifier chrome, excluded from density
        # (same rule as deck_document density accounting).
        words = sum(len((e.text or "").split()) for e in tree if e.kind is DocElementKind.TEXT and e.role != "footer")
        words += sum(len(e.rich_text.plain_text().split()) for e in tree if e.kind is DocElementKind.RICH_TEXT)
        if words > slide.intent.density_budget_words:
            finding("DENSITY_BUDGET", slide.id, f"{words} words > budget {slide.intent.density_budget_words}")
        banded = recipe not in {"cover-brand", "statement-thesis"}
        title = next((e for e in tree if e.role == "title"), None)
        if banded and title and len((title.text or "").split()) > BANDED_TITLE_MAX_WORDS:
            finding("BAND_OVERFLOW", slide.id, f"banded title runs {len(title.text.split())} words (max {BANDED_TITLE_MAX_WORDS}) — use a tightened assertion RENDERING")
        # bound text must truncate its claim at a word boundary
        bindings = {b.path: b for b in slide.bindings}
        for element in tree:
            if element.kind is not DocElementKind.TEXT or not element.text:
                continue
            for path in element.binding_paths:
                binding = bindings.get(path)
                if binding is None or binding.claim_id not in claims or binding.transform_class != "truncation":
                    continue
                shown = element.text.lstrip("> ").rstrip("…").strip()
                source = claims[binding.claim_id].text
                if shown and shown not in source:
                    continue  # not a literal excerpt; other transforms judge it
                if shown and shown in source:
                    end = source.find(shown) + len(shown)
                    if end < len(source) and source[end] not in " .,;:—-":
                        finding("MIDWORD_TRUNCATION", slide.id, f"'{element.id}' cuts claim mid-word: …{shown[-18:]!r}")
        visual = [e for e in tree if e.kind in {DocElementKind.DIAGRAM, DocElementKind.IMAGE, DocElementKind.ICON, DocElementKind.SVG}]
        if not visual and not (slide.intent.visual_thesis or "").startswith("none:"):
            finding("MISSING_VISUAL", slide.id, "no visual channel and no declared 'none: <reason>'")
        if recipe in {"one-big-diagram", "assertion-chevrons-diagram"}:
            share = sum(e.bbox.w * e.bbox.h for e in visual)
            if share < 0.30:
                finding("DIAGRAM_SHARE", slide.id, f"visual share {share:.2f} < 0.30")
        if bool(slide.intent.reveal_order) != (slide.reveal.value == "step"):
            finding("REVEAL_MISMATCH", slide.id, "reveal_order and reveal mode disagree")
    return findings


def lint_file(path: Path) -> tuple[list[dict], int]:
    document = DeckDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))
    findings = lint_document(document)
    return findings, (1 if findings else 0)
