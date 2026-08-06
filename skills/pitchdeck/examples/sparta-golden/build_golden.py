"""Golden six-slide Sparta conference mini-arc (#1262 vertical slice).

Hand-authored DeckDocument proving the composition contract BEFORE any
generator exists (webgpt review, 2026-08-06): every slide carries a
SlideIntent + house CompositionRecipe, every visible string binds to the
REAL sparta-explorer claim ledger, and the architecture/problem slides
carry hand-authored editable DiagramGraphs (separate nodes, labeled bound
edges) — never rasters. Deterministic: rebuilding writes byte-identical
output. Failure modes: any contract violation (missing role, assertion/
title mismatch, over-budget density, unbound non-decorative edge) raises
at construction — the golden document cannot exist in a broken state.
"""

from __future__ import annotations

import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1] / "sparta-explorer"

from pitchdeck.document import (  # noqa: E402
    Bbox,
    DeckDocument,
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    DocElement,
    DocElementKind,
    DocEntrance,
    DocSlide,
    DocTextStyle,
    SlideIntent,
)
from pitchdeck.io import load_yaml  # noqa: E402
from pitchdeck.models import (  # noqa: E402
    AssetManifest,
    BindingKind,
    ClaimLedger,
    ContentReveal,
    DeckManifest,
    SlideLayout,
    SourceManifest,
    TextBinding,
)

TEAL = "#065E7C"
INK = "#292929"

TITLE_STYLE = DocTextStyle(size_pt=40.0, bold=True, color=TEAL, font="Calibri")
HERO_STYLE = DocTextStyle(size_pt=64.0, bold=True, align="center", color=TEAL, font="Calibri")
CHEVRON_STYLE = DocTextStyle(size_pt=22.0, color=INK, font="Calibri")
CAPTION_STYLE = DocTextStyle(size_pt=14.0, color="#595959", font="Calibri")


def _binding(path: str, kind: BindingKind, claim_id: str | None = None, transform: str | None = None) -> TextBinding:
    return TextBinding(path=path, kind=kind, claim_id=claim_id, transform_class=transform)


def _text(el_id: str, role: str, bbox: Bbox, text: str, style: DocTextStyle, *, paths: list[str] | None = None, fragment: int | None = None) -> DocElement:
    return DocElement(
        id=el_id,
        kind=DocElementKind.TEXT,
        bbox=bbox,
        role=role,
        text=text,
        style=style,
        binding_paths=paths or [],
        entrance=DocEntrance(effect="rise", fragment_index=fragment) if fragment is not None else DocEntrance(),
    )


def build() -> DeckDocument:
    deck = load_yaml(BUNDLE / "deck.public.yaml", DeckManifest)
    ledger = load_yaml(BUNDLE / "claim_ledger.yaml", ClaimLedger)
    assets = load_yaml(BUNDLE / "asset_manifest.yaml", AssetManifest)
    source_path = BUNDLE / "source_manifest.resolved.yaml"
    if not source_path.exists():
        source_path = BUNDLE / "source_manifest.yaml"
    sources = load_yaml(source_path, SourceManifest)

    slides: list[DocSlide] = []

    # 1 — cover (recipe: cover-brand, exemplar cybersummit-01)
    slides.append(
        DocSlide(
            id="g1-cover",
            order=1,
            section="cover",
            layout_origin=SlideLayout.COVER,
            intent=SlideIntent(
                module="sparta.cover",
                purpose="Brand the talk in five seconds",
                assertion="Sparta Explorer",
                visual_thesis="Brand mark only; the tagline carries the claim",
                recipe="cover-brand",
                audience="conference",
                density_budget_words=24,
                reveal_order=[],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.08, y=0.30, w=0.84, h=0.18), "Sparta Explorer", HERO_STYLE),
                _text(
                    "message",
                    "message",
                    Bbox(x=0.08, y=0.52, w=0.84, h=0.12),
                    "Inspectable space-cyber assurance",
                    DocTextStyle(size_pt=28.0, align="center", color="#595959", font="Calibri"),
                    paths=["message"],
                ),
                DocElement(
                    id="brandmark",
                    kind=DocElementKind.IMAGE,
                    bbox=Bbox(x=0.44, y=0.70, w=0.12, h=0.18),
                    role="visual",
                    asset_id="sparta-helmet-mark",
                ),
            ],
            bindings=[_binding("message", BindingKind.NON_CLAIM)],
            claim_ids=[],
        )
    )

    # 2 — thesis (recipe: statement-thesis, exemplar reqml-12)
    thesis = "One evidence thread, from framework guidance to human decision"
    slides.append(
        DocSlide(
            id="g2-thesis",
            order=2,
            section="thesis",
            layout_origin=SlideLayout.STATEMENT,
            intent=SlideIntent(
                module="sparta.value-prop",
                purpose="State the single idea the talk argues",
                assertion=thesis,
                visual_thesis="none: the statement IS the slide (reqml-12 pattern)",
                recipe="statement-thesis",
                audience="conference",
                density_budget_words=20,
                reveal_order=[],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.08, y=0.36, w=0.84, h=0.28), thesis, HERO_STYLE, paths=["title"]),
            ],
            bindings=[
                _binding("title", BindingKind.CLAIM_PARAPHRASE, "sparta-public-one-thread", "generalization"),
            ],
            claim_ids=["sparta-public-one-thread"],
        )
    )

    # 3 — problem (recipe: assertion-chevrons-diagram, exemplar cybersummit-18)
    problem = "Relevance is not support"
    slides.append(
        DocSlide(
            id="g3-problem",
            order=3,
            section="problem",
            layout_origin=SlideLayout.FREEFORM,
            reveal=ContentReveal.STEP,
            intent=SlideIntent(
                module="sparta.problem",
                purpose="Make the failure visceral before the solution",
                assertion=problem,
                visual_thesis="Endpoint bridge: retrieval reaches relevance; only governed evidence reaches support",
                recipe="assertion-chevrons-diagram",
                audience="conference",
                density_budget_words=60,
                reveal_order=["chevron-0", "chevron-1", "diagram"],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.06, y=0.07, w=0.88, h=0.12), problem, TITLE_STYLE, paths=["title"]),
                _text(
                    "chevron-0",
                    "chevrons",
                    Bbox(x=0.06, y=0.22, w=0.88, h=0.07),
                    "> Search, embeddings, and graph traversal find relevant material",
                    CHEVRON_STYLE,
                    paths=["element:chevron-0"],
                    fragment=0,
                ),
                _text(
                    "chevron-1",
                    "chevrons",
                    Bbox(x=0.06, y=0.30, w=0.88, h=0.07),
                    "> Relevance alone cannot establish that evidence supports a conclusion",
                    CHEVRON_STYLE,
                    paths=["element:chevron-1"],
                    fragment=1,
                ),
                DocElement(
                    id="diagram",
                    kind=DocElementKind.DIAGRAM,
                    bbox=Bbox(x=0.10, y=0.42, w=0.80, h=0.46),
                    role="diagram",
                    entrance=DocEntrance(effect="fade", fragment_index=2),
                    binding_paths=["element:diagram"],
                    diagram=DiagramGraph(
                        recipe="endpoint-bridge",
                        nodes=[
                            DiagramNode(
                                id="retrieval",
                                bbox=Bbox(x=0.02, y=0.25, w=0.30, h=0.50),
                                icon="search",
                                label="Retrieval",
                                sublabel="search · embeddings · graph",
                                binding_paths=["element:diagram"],
                            ),
                            DiagramNode(
                                id="support",
                                bbox=Bbox(x=0.66, y=0.25, w=0.32, h=0.50),
                                icon="shield-check",
                                label="Established support",
                                sublabel="governed evidence · authorized people",
                                binding_paths=["element:diagram"],
                            ),
                        ],
                        edges=[
                            DiagramEdge(
                                id="cannot-cross",
                                source="retrieval",
                                target="support",
                                route="dotted-path",
                                line_style="dashed",
                                label="relevance does not cross this gap",
                                binding_paths=["element:diagram"],
                            ),
                        ],
                    ),
                ),
            ],
            bindings=[
                _binding("title", BindingKind.CLAIM_PARAPHRASE, "sparta-public-relevance-not-support", "generalization"),
                _binding("element:chevron-0", BindingKind.CLAIM_PARAPHRASE, "sparta-public-relevance-not-support", "inflection"),
                _binding("element:chevron-1", BindingKind.CLAIM_PARAPHRASE, "sparta-public-relevance-not-support", "inflection"),
                _binding("element:diagram", BindingKind.CLAIM_PARAPHRASE, "sparta-public-relevance-not-support", "generalization"),
            ],
            claim_ids=["sparta-public-relevance-not-support"],
        )
    )

    # 4 — architecture (recipe: one-big-diagram, exemplar cybersummit-12)
    arch = "Guidance, evidence, and review stay on one inspectable thread"
    slides.append(
        DocSlide(
            id="g4-architecture",
            order=4,
            section="architecture",
            layout_origin=SlideLayout.FREEFORM,
            reveal=ContentReveal.STEP,
            intent=SlideIntent(
                module="sparta.how",
                purpose="Show the mechanism as one pipeline",
                assertion=arch,
                visual_thesis="Pipeline: framework guidance -> program evidence -> human review, model navigates but never decides",
                recipe="one-big-diagram",
                audience="conference",
                density_budget_words=45,
                reveal_order=["diagram"],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.06, y=0.07, w=0.88, h=0.12), arch, TITLE_STYLE, paths=["title"]),
                DocElement(
                    id="diagram",
                    kind=DocElementKind.DIAGRAM,
                    bbox=Bbox(x=0.06, y=0.26, w=0.88, h=0.62),
                    role="diagram",
                    binding_paths=["element:diagram"],
                    diagram=DiagramGraph(
                        recipe="pipeline",
                        nodes=[
                            DiagramNode(id="guidance", bbox=Bbox(x=0.00, y=0.30, w=0.26, h=0.40), icon="book", label="Framework guidance", binding_paths=["element:diagram"]),
                            DiagramNode(id="evidence", bbox=Bbox(x=0.37, y=0.30, w=0.26, h=0.40), icon="database", label="Program evidence", binding_paths=["element:diagram"]),
                            DiagramNode(id="review", bbox=Bbox(x=0.74, y=0.30, w=0.26, h=0.40), icon="users", label="Human review", binding_paths=["element:diagram"]),
                        ],
                        edges=[
                            DiagramEdge(id="g-e", source="guidance", target="evidence", label="traced to", binding_paths=["element:diagram"]),
                            DiagramEdge(id="e-r", source="evidence", target="review", label="decided by", binding_paths=["element:diagram"]),
                        ],
                        groups={"thread": ["guidance", "evidence", "review"]},
                    ),
                ),
            ],
            bindings=[
                _binding("title", BindingKind.CLAIM_PARAPHRASE, "sparta-public-thesis", "generalization"),
                _binding("element:diagram", BindingKind.CLAIM_PARAPHRASE, "sparta-public-model-boundary", "generalization"),
            ],
            claim_ids=["sparta-public-thesis", "sparta-public-model-boundary"],
        )
    )

    # 5 — proof (recipe: proof-screenshot-callout, exemplar cybersummit-04)
    proof = "The working surfaces exist on a prepared host today"
    slides.append(
        DocSlide(
            id="g5-proof",
            order=5,
            section="proof",
            layout_origin=SlideLayout.SCREENSHOT,
            intent=SlideIntent(
                module="sparta.proof",
                purpose="Show, not tell: the real investigation surface",
                assertion=proof,
                visual_thesis="Threat Matrix screenshot as primary evidence",
                recipe="proof-screenshot-callout",
                audience="conference",
                density_budget_words=60,
                reveal_order=[],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.06, y=0.07, w=0.88, h=0.12), proof, TITLE_STYLE, paths=["title"]),
                DocElement(
                    id="visual",
                    kind=DocElementKind.IMAGE,
                    bbox=Bbox(x=0.34, y=0.24, w=0.60, h=0.62),
                    role="visual",
                    asset_id="sparta-threat-matrix",
                ),
                _text(
                    "callout",
                    "callout",
                    Bbox(x=0.06, y=0.24, w=0.25, h=0.40),
                    "> Global Posture\n> Threat Matrix\n> Sparta Chat",
                    CHEVRON_STYLE,
                    paths=["element:callout"],
                ),
                _text("caption", "caption", Bbox(x=0.34, y=0.88, w=0.60, h=0.05), "Prepared-host capture; verify freshness before reuse", CAPTION_STYLE, paths=["element:caption"]),
            ],
            bindings=[
                _binding("title", BindingKind.CLAIM_PARAPHRASE, "sparta-public-working-surfaces", "generalization"),
                _binding("element:callout", BindingKind.CLAIM_PARAPHRASE, "sparta-public-working-surfaces", "truncation"),
                _binding("element:caption", BindingKind.NON_CLAIM),
            ],
            claim_ids=["sparta-public-working-surfaces"],
        )
    )

    # 6 — roadmap (recipe: roadmap-lanes, exemplar cybersummit-33)
    roadmap = "Open gates before wider release"
    slides.append(
        DocSlide(
            id="g6-roadmap",
            order=6,
            section="roadmap",
            layout_origin=SlideLayout.ROADMAP,
            reveal=ContentReveal.STEP,
            intent=SlideIntent(
                module="sparta.roadmap",
                purpose="Name what remains, honestly",
                assertion=roadmap,
                visual_thesis="none: gate list carries the content; each gate is a build step",
                recipe="roadmap-lanes",
                audience="conference",
                density_budget_words=70,
                reveal_order=["chevron-0", "chevron-1", "chevron-2"],
            ),
            elements=[
                _text("title", "title", Bbox(x=0.06, y=0.07, w=0.88, h=0.12), roadmap, TITLE_STYLE, paths=["title"]),
                _text("chevron-0", "chevrons", Bbox(x=0.06, y=0.26, w=0.88, h=0.10), "> Independent corpus review", CHEVRON_STYLE, paths=["element:chevron-0"], fragment=0),
                _text("chevron-1", "chevrons", Bbox(x=0.06, y=0.38, w=0.88, h=0.10), "> Response-route convergence", CHEVRON_STYLE, paths=["element:chevron-1"], fragment=1),
                _text("chevron-2", "chevrons", Bbox(x=0.06, y=0.50, w=0.88, h=0.10), "> QRA reasoning and reuse", CHEVRON_STYLE, paths=["element:chevron-2"], fragment=2),
            ],
            bindings=[
                _binding("title", BindingKind.CLAIM_PARAPHRASE, "sparta-public-open-gates", "generalization"),
                _binding("element:chevron-0", BindingKind.CLAIM_QUOTE, "sparta-public-open-gates", "truncation"),
                _binding("element:chevron-1", BindingKind.CLAIM_QUOTE, "sparta-public-open-gates", "truncation"),
                _binding("element:chevron-2", BindingKind.CLAIM_QUOTE, "sparta-public-open-gates", "truncation"),
            ],
            claim_ids=["sparta-public-open-gates"],
        )
    )

    return DeckDocument(
        deck=deck.deck,
        sources=sources.sources,
        claims=ledger.claims,
        assets=assets.assets,
        slides=slides,
        revision=0,
        provenance={
            "kind": "golden-slice",
            "bundle_dir": "examples/sparta-explorer",
            "review": "webgpt-review-2026-08-06",
        },
    )


def main() -> int:
    out = Path(__file__).parent / "deck.document.json"
    document = build()
    out.write_text(document.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
    total_words = sum(
        len((e.text or "").split()) for s in document.slides for e in s.elements
    )
    print(
        f"golden document written: {out}\n"
        f"slides={len(document.slides)} elements={sum(len(s.elements) for s in document.slides)} "
        f"words={total_words} diagrams={sum(1 for s in document.slides for e in s.elements if e.kind.value == 'diagram')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
