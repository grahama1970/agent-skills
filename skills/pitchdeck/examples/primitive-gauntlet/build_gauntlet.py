"""Primitive-gauntlet: the #1271 freeze-test document (2026-08-07 review).

One hand-authored document exercising every new primitive under the exact
conditions the review predicted would break first: an outer group with a
deliberately PADDED child frame (python-pptx recalculates group extents from
children — the padding must survive), a rotated nested group, four preset
shapes, a native-mapped library icon, rich text with a warm bold label
prefix / underline / code / local slide link, one exactly-horizontal and one
bent connector with arrowheads and advisory attach hints, a rotated image,
awkward fractional geometry, a data-bearing relationship line and
data-bearing rich runs with claim bindings, explicitly decorative content,
sibling z ties, and NO clipping. Deterministic; any contract violation
raises at construction. A second slide exists solely as the local-link
target.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pitchdeck.document import (
    AttachHint,
    Bbox,
    BasicMark,
    ColorMark,
    DeckDocument,
    DocElement,
    DocElementKind,
    DocEntrance,
    DocSlide,
    DocTextStyle,
    IconSpec,
    LineSpec,
    LinkMark,
    Point,
    RichBlock,
    RichRun,
    RichTextSpec,
    ShapeSpec,
    StrokeSpec,
)
from pitchdeck.models import (
    AssetKind,
    SourceRef,
    AssetSpec,
    AssetStatus,
    BindingKind,
    Claim,
    ClaimRisk,
    ClaimKind,
    ClaimStatus,
    DeckMeta,
    DeckSourcePolicy,
    EvidenceSpan,
    SlideLayout,
    SourceRole,
    SourceSpec,
    TextBinding,
    Visibility,
)

HERE = Path(__file__).parent


def _claims() -> list[Claim]:
    return [
        Claim(
            id="gauntlet-relationship",
            text="Stage one output feeds stage two directly",
            status=ClaimStatus.CANDIDATE,
            risk=ClaimRisk.LOW,
            kind=ClaimKind.PRODUCT,
            visibility=Visibility.PUBLIC,
            source_refs=[SourceRef(source_id="gauntlet-src", section="pipeline")],
            evidence_spans=[EvidenceSpan(source_id="gauntlet-src", text="stage one output feeds stage two directly")],
        ),
        Claim(
            id="gauntlet-emphasis",
            text="The gate fails closed on unproven content",
            status=ClaimStatus.CANDIDATE,
            risk=ClaimRisk.LOW,
            kind=ClaimKind.PRODUCT,
            visibility=Visibility.PUBLIC,
            source_refs=[SourceRef(source_id="gauntlet-src", section="gates")],
            evidence_spans=[EvidenceSpan(source_id="gauntlet-src", text="the gate fails closed on unproven content")],
        ),
    ]


def build() -> DeckDocument:
    png = HERE / "assets" / "gauntlet.png"
    slide_main = DocSlide(
        id="pg-main",
        order=1,
        section="gauntlet",
        layout_origin=SlideLayout.FREEFORM,
        elements=[
            # legacy flat-text title (must stay plain text — compatibility rule)
            DocElement(
                id="title", kind=DocElementKind.TEXT, role="title",
                bbox=Bbox(x=0.0537, y=0.0421, w=0.8811, h=0.09),
                text="Primitive gauntlet", style=DocTextStyle(size_pt=40.0, bold=True),
            ),
            # outer group with a deliberately PADDED local frame
            DocElement(
                id="outer-group", kind=DocElementKind.GROUP,
                bbox=Bbox(x=0.0713, y=0.1637, w=0.5391, h=0.6113),
                child_frame=Bbox(x=0.1, y=0.1, w=0.8, h=0.8),  # padding must survive emission
                children=[
                    DocElement(id="g-rect", kind=DocElementKind.SHAPE, bbox=Bbox(x=0.03, y=0.05, w=0.27, h=0.22),
                               shape=ShapeSpec(preset="rounded_rect", fill_role="canvas", stroke=StrokeSpec(role="primary"))),
                    DocElement(id="g-ellipse", kind=DocElementKind.SHAPE, bbox=Bbox(x=0.63, y=0.05, w=0.29, h=0.22),
                               shape=ShapeSpec(preset="ellipse", stroke=StrokeSpec(role="primary"))),
                    # exactly HORIZONTAL data-bearing connector with attach hints
                    DocElement(id="g-flow", kind=DocElementKind.LINE, bbox=Bbox(x=0.3, y=0.16, w=0.33, h=0.002),
                               line=LineSpec(start=Point(x=0.3, y=0.16), end=Point(x=0.63, y=0.16),
                                             arrow_end=True,
                                             start_hint=AttachHint(element_id="g-rect", connection_site=3),
                                             end_hint=AttachHint(element_id="g-ellipse", connection_site=1)),
                               binding_paths=["element:g-flow"]),
                    # rotated NESTED group with z-tied siblings
                    DocElement(
                        id="nested-group", kind=DocElementKind.GROUP, rotation_deg=8.0,
                        bbox=Bbox(x=0.05, y=0.42, w=0.55, h=0.5),
                        children=[
                            DocElement(id="n-chevron", kind=DocElementKind.SHAPE, z=0,
                                       bbox=Bbox(x=0.02, y=0.1, w=0.42, h=0.33),
                                       shape=ShapeSpec(preset="chevron", fill_role="highlight_warm")),
                            DocElement(id="n-pill", kind=DocElementKind.SHAPE, z=0,  # sibling z TIE: array order wins
                                       bbox=Bbox(x=0.35, y=0.22, w=0.45, h=0.3),
                                       shape=ShapeSpec(preset="pill", fill_role="highlight_green")),
                        ],
                    ),
                    # explicitly decorative icon (native-mapped, editable)
                    DocElement(id="g-icon", kind=DocElementKind.ICON, bbox=Bbox(x=0.68, y=0.5, w=0.24, h=0.4),
                               icon=IconSpec(library_id="shield-check", tint_role="primary")),
                ],
            ),
            # bent connector OUTSIDE the group, decorative
            DocElement(id="bent", kind=DocElementKind.LINE, bbox=Bbox(x=0.62, y=0.2, w=0.2, h=0.24),
                       line=LineSpec(start=Point(x=0.62, y=0.2), end=Point(x=0.82, y=0.44),
                                     route="bent", dash="dashed", arrow_start=True, arrow_end=True)),
            # rich text: warm bold label prefix + plain + underline + code + local link
            DocElement(
                id="rich", kind=DocElementKind.RICH_TEXT,
                bbox=Bbox(x=0.6203, y=0.4629, w=0.3391, h=0.31),
                binding_paths=["element:rich"],
                rich_text=RichTextSpec(blocks=[
                    RichBlock(style_role="body", runs=[
                        RichRun(text="Gate: ", marks=[BasicMark(type="bold"), ColorMark(role="highlight_warm")]),
                        RichRun(text="fails closed on "),
                        RichRun(text="unproven", marks=[BasicMark(type="underline")]),
                        RichRun(text=" content"),
                    ]),
                    RichBlock(style_role="support", bullet_level=1, runs=[
                        RichRun(text="verify_bundle()", marks=[BasicMark(type="code")]),
                        RichRun(text=" — details on the "),
                        RichRun(text="appendix slide", marks=[LinkMark(target_slide_id="pg-appendix")]),
                    ]),
                ]),
                entrance=DocEntrance(effect="rise", fragment_index=0),
            ),
            # rotated image at awkward fractions
            DocElement(id="photo", kind=DocElementKind.IMAGE, rotation_deg=353.5,
                       bbox=Bbox(x=0.6203, y=0.7907, w=0.1523, h=0.1471),
                       asset_id="gauntlet-photo"),
        ],
        bindings=[
            TextBinding(path="element:g-flow", kind=BindingKind.CLAIM_PARAPHRASE,
                        claim_id="gauntlet-relationship", transform_class="inflection"),
            TextBinding(path="element:rich", kind=BindingKind.CLAIM_PARAPHRASE,
                        claim_id="gauntlet-emphasis", transform_class="inflection"),
        ],
        claim_ids=["gauntlet-relationship", "gauntlet-emphasis"],
    )
    slide_target = DocSlide(
        id="pg-appendix", order=2, section="appendix", layout_origin=SlideLayout.APPENDIX,
        elements=[
            DocElement(id="title", kind=DocElementKind.TEXT, role="title",
                       bbox=Bbox(x=0.06, y=0.07, w=0.88, h=0.12),
                       text="Appendix — link target", style=DocTextStyle(size_pt=40.0, bold=True)),
        ],
    )
    return DeckDocument(
        deck=DeckMeta(
            id="primitive-gauntlet", title="Primitive Gauntlet", audience="contract reviewers",
            visibility=Visibility.PUBLIC, source_policy=DeckSourcePolicy.PUBLIC_ONLY,
        ),
        sources=[SourceSpec(id="gauntlet-src", title="Gauntlet fixture source", path="gauntlet.md",
                            visibility=Visibility.PUBLIC, role=SourceRole.PRIMARY)],
        claims=_claims(),
        assets=[AssetSpec(id="gauntlet-photo", kind=AssetKind.SCREENSHOT, visibility=Visibility.PUBLIC,
                          local_path=str(png), alt_text="gauntlet test image", status=AssetStatus.PRESENT)],
        slides=[slide_main, slide_target],
        revision=0,
        provenance={"kind": "primitive-gauntlet", "review": "webgpt-review-1271-2026-08-07"},
    )


def main() -> int:
    assets_dir = HERE / "assets"
    assets_dir.mkdir(exist_ok=True)
    png = assets_dir / "gauntlet.png"
    if not png.exists():
        from PIL import Image

        img = Image.new("RGB", (320, 200), "#065E7C")
        img.save(png)
    document = build()
    out = HERE / "deck.document.json"
    out.write_text(document.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
    total = sum(1 for s in document.slides for _ in __import__("pitchdeck.document", fromlist=["iter_tree"]).iter_tree(s.elements))
    print(f"gauntlet written: {out} | tree elements={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
