"""Canonical whole-deck document schema and compiler (#1263).

`pitchdeck.deck_document.v1` is THE strict datastore for an entire deck
before any conversion: meta + theme, sources, claims, assets, and every
slide as absolutely positioned elements — text, image, inline svg, or a
typed figure spec (d3/react-flow/pixi, #1251) — each with a fractional
bbox, z-order, claim bindings, and typed entrance animation. PPTX, HTML,
and the React renderer are emitters FROM this document; nothing renders
content the document does not carry.

compile_document() builds the document from a validated bundle: freeform
slides pass through exactly; semantic layouts compile through the ONE
canonical geometry table below (LAYOUT_GEOMETRY — emitters migrate to it;
until then it is the document's contract, not a mirror of emitter CSS).
Failure modes: unknown layout, out-of-bounds element, or a binding whose
path maps to no element all raise — the document is never emitted partially.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import (
    AssetSpec,
    Claim,
    ContentReveal,
    DeckManifest,
    DeckMeta,
    FreeformElement,
    SlideLayout,
    SlideSpec,
    SlideTransition,
    SourceSpec,
    StrictModel,
    TextBinding,
)

DOCUMENT_SCHEMA = "pitchdeck.deck_document.v1"


class DocElementKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    SVG = "svg"
    FIGURE = "figure"
    DIAGRAM = "diagram"
    GROUP = "group"
    SHAPE = "shape"
    LINE = "line"
    ICON = "icon"
    RICH_TEXT = "rich_text"


class Bbox(StrictModel):
    """Fractional geometry on the 16:9 canvas — x*1920/y*1080 in the browser,
    x*13.333in/y*7.5in in PPTX, so placement round-trips exactly."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def in_bounds(self) -> "Bbox":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("bbox extends beyond the canvas")
        return self


class DocTextStyle(StrictModel):
    size_pt: float = Field(default=20.0, ge=8.0, le=160.0)
    bold: bool = False
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    align: Literal["left", "center", "right"] = "left"
    font: str | None = None


class DocEntrance(StrictModel):
    """Rhetorical animation: reveal order follows the argument, never decoration."""

    effect: Literal["none", "fade", "rise", "zoom"] = "none"
    delay_ms: int = Field(default=0, ge=0, le=5000)
    fragment_index: int | None = Field(default=None, ge=0, description="Click-gated build step; None reveals with the slide.")


class FigureSpec(StrictModel):
    """Typed reference to a generated figure (#1251). Data-bearing figures must
    carry claim bindings on the owning element; decorative ones must not."""

    engine: Literal["d3", "react-flow", "pixi", "mermaid", "webgl"]
    spec_ref: str = Field(min_length=1, description="Path or id of the figure spec artifact.")
    decorative: bool = False


class ShapePreset(str, Enum):
    RECT = "rect"
    ROUNDED_RECT = "rounded_rect"
    ELLIPSE = "ellipse"
    CHEVRON = "chevron"
    PILL = "pill"
    TRIANGLE = "triangle"


class StrokeSpec(StrictModel):
    role: "ColorRoleRef"
    width_pt: float = Field(default=2.0, gt=0, le=24)
    dash: Literal["solid", "dashed", "dotted"] = "solid"


class ShapeSpec(StrictModel):
    """Closed preset geometry — native sp in PPTX, styled by design-system roles."""

    preset: ShapePreset
    fill_role: "ColorRoleRef | None" = None
    stroke: StrokeSpec | None = None


class Point(StrictModel):
    """A point in the PARENT element frame (fractions)."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class AttachHint(StrictModel):
    """ADVISORY editing hint (2026-08-07 review): geometry stays authoritative;
    the PPTX emitter writes stCxn/endCxn only for proven-safe combinations."""

    element_id: str = Field(min_length=1)
    connection_site: int = Field(ge=0, le=8)


class LineSpec(StrictModel):
    """Canonical endpoints in the parent frame; element bbox is DERIVED."""

    start: Point
    end: Point
    route: Literal["straight", "bent", "curved"] = "straight"
    dash: Literal["solid", "dashed", "dotted"] = "solid"
    width_pt: float = Field(default=2.0, gt=0, le=24)
    arrow_start: bool = False
    arrow_end: bool = True
    start_hint: AttachHint | None = None
    end_hint: AttachHint | None = None


class IconSpec(StrictModel):
    """Library reference ONLY (no inline paths): resolves against the
    hash-pinned icon manifest; fallback is a target-profile branch that fails
    closed when editable shapes are required."""

    library_id: str = Field(min_length=1)
    tint_role: "ColorRoleRef" = "primary"


class TextStyleRole(str, Enum):
    HERO = "hero"
    STATEMENT_HERO = "statement_hero"
    SECTION = "section"
    TITLE = "title"
    LEAD = "lead"
    BODY = "body"
    SUPPORT = "support"
    CAPTION = "caption"


class BasicMark(StrictModel):
    type: Literal["bold", "italic", "underline", "code"]


class ColorMark(StrictModel):
    type: Literal["color"] = "color"
    role: "ColorRoleRef"


class LinkMark(StrictModel):
    type: Literal["link"] = "link"
    target_slide_id: str = Field(min_length=1, description="Local slide link only; external URLs deferred.")


RichMark = BasicMark | ColorMark | LinkMark


class RichRun(StrictModel):
    text: str = Field(min_length=1)
    marks: list[RichMark] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_mark_types(self) -> "RichRun":
        types = [m.type for m in self.marks]
        if len(types) != len(set(types)):
            raise ValueError("duplicate mark types on one run")
        return self


class RichBlock(StrictModel):
    style_role: TextStyleRole = TextStyleRole.BODY
    align: Literal["left", "center", "right"] = "left"
    bullet_level: int | None = Field(default=None, ge=1, le=3)
    runs: list[RichRun] = Field(min_length=1)


class RichTextSpec(StrictModel):
    blocks: list[RichBlock] = Field(min_length=1)

    def plain_text(self) -> str:
        """Canonical projection — title equality, density budgets, search, and
        accessibility all read THIS, so rich text can never evade them."""
        return "\n".join("".join(run.text for run in block.runs) for block in self.blocks)


# Color roles referenced from the design system without a hard import cycle.
ColorRoleRef = Literal[
    "primary", "secondary", "canvas", "ink", "muted",
    "highlight_warm", "highlight_green", "program", "alert",
]


class DiagramNode(StrictModel):
    """Editable diagram node: icon + label as separate parts, bbox in fractions
    of the OWNING element's bbox (diagrams reposition as one unit)."""

    id: str = Field(min_length=1)
    bbox: Bbox
    icon: str | None = Field(default=None, description="Icon-library id or sanitized inline SVG path d= data.")
    label: str = Field(min_length=1)
    sublabel: str | None = None
    binding_paths: list[str] = Field(default_factory=list)
    # Scene clusters (#1315): a multi-element illustration is several glyphs of
    # DIFFERENT weights, not a row of identical ringed icons. "principal" is the
    # labeled subject; "support" is a smaller bare glyph in the same scene;
    # "ground" is a baseline/context mark. Default keeps existing documents
    # byte-identical.
    decoration: Literal["ring", "principal", "support", "ground"] = "ring"
    scale: float = Field(default=1.0, gt=0.2, le=2.5, description="Glyph weight within its scene.")

    @model_validator(mode="after")
    def labelled_node_is_bound(self) -> "DiagramNode":
        # A node label is a visible assertion, so it needs provenance for the
        # same reason an edge does (#1328). A blank label is a bare decorative
        # glyph and carries no claim.
        if self.label.strip() and not self.binding_paths:
            raise ValueError(
                f"node '{self.id}': label '{self.label[:40]}' is a visible assertion and requires binding_paths"
            )
        return self


class DiagramEdge(StrictModel):
    """Connectors are first-class and factual by default: a meaningful edge is a
    RELATIONSHIP claim — it needs bindings or an explicit decorative class."""

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    route: Literal["straight", "curve", "dotted-path"] = "straight"
    line_style: Literal["solid", "dashed", "dotted"] = "solid"
    arrowhead: bool = True
    label: str | None = None
    binding_paths: list[str] = Field(default_factory=list)
    decorative: bool = False

    @model_validator(mode="after")
    def factual_or_decorative(self) -> "DiagramEdge":
        # A decorative primitive must be structurally INCAPABLE of asserting.
        # Previously `decorative=True` skipped the binding requirement while the
        # emitter still rendered edge.label, so 'AI' or '42' reached the deck
        # unbound and was then waved through by the old chrome heuristics.
        if self.decorative and (self.label or "").strip():
            raise ValueError(
                f"edge '{self.id}': a decorative edge cannot carry a visible label "
                f"({self.label[:32]!r}); label it and bind it, or drop the text"
            )
        if not self.decorative and not self.binding_paths:
            raise ValueError(
                f"edge '{self.id}': a non-decorative edge asserts a relationship and requires binding_paths"
            )
        return self


# "scene" (#1315) is a multi-element illustration rather than a node graph:
# a labelled subject with smaller supporting glyphs and dotted flow.
DiagramRecipe = Literal["endpoint-bridge", "pipeline", "hub-spoke", "layered-stack", "loop", "before-after", "scene"]


class DiagramGraph(StrictModel):
    """Normalized editable diagram: separate nodes, edges, labels, and groups —
    emitters MUST render these as distinct shapes (never one raster)."""

    recipe: DiagramRecipe
    nodes: list[DiagramNode] = Field(min_length=2)
    edges: list[DiagramEdge] = Field(default_factory=list)
    groups: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def referential(self) -> "DiagramGraph":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate diagram node ids")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError(f"edge '{e.id}' references unknown node")
        for name, members in self.groups.items():
            for m in members:
                if m not in known:
                    raise ValueError(f"group '{name}' references unknown node '{m}'")
        return self


CompositionRecipeId = Literal[
    "cover-brand",
    "statement-thesis",
    "assertion-chevrons-diagram",
    "one-big-diagram",
    "proof-screenshot-callout",
    "roadmap-lanes",
    "roadmap-gates",
    "assertion-chevrons-scene",
]

# Executable house recipes are SCHEMA INSTANCES (pitchdeck.composition_recipe.v1,
# design/recipes/*.json), not Python dicts (#1275). This dict view keeps the
# DocSlide validator contract stable.
def _load_recipe_table() -> dict[str, dict]:
    from .design_system import load_recipes

    return {
        recipe_id: {
            "required_roles": [role.value for role in recipe.required_roles],
            "exemplar": recipe.exemplar_ids[0],
            "max_words": recipe.max_words,
        }
        for recipe_id, recipe in load_recipes().items()
    }


COMPOSITION_RECIPES: dict[str, dict] = _load_recipe_table()


class SlideIntent(StrictModel):
    """The design-representation layer the 2026-08-06 review named as missing:
    what the slide ARGUES and which house composition realizes it — sits between
    claims and bounding boxes, generated pre-materialization, human-reviewable."""

    module: str = Field(min_length=1, description="Narrative module instance, e.g. 'sparta.value-prop'.")
    purpose: str = Field(min_length=1)
    assertion: str = Field(min_length=1, description="The takeaway the slide argues; must be the title element's text.")
    visual_thesis: str = Field(min_length=1, description="What the visual channel shows, or 'none: <reason>'.")
    recipe: CompositionRecipeId
    audience: Literal["conference", "sbir", "program-review"]
    density_budget_words: int = Field(ge=5, le=150)
    reveal_order: list[str] = Field(default_factory=list, description="Element ids in rhetorical build order.")


class DocElement(StrictModel):
    id: str = Field(min_length=1)
    kind: DocElementKind
    bbox: Bbox
    z: int = 0
    role: str | None = Field(default=None, description="Semantic origin (title, message, body:0, visual, caption…).")
    text: str | None = None
    style: DocTextStyle | None = None
    asset_id: str | None = None
    svg: str | None = Field(default=None, description="Inline SVG; validated by the svg_sanitize allowlist gate (#1268).")
    figure: FigureSpec | None = None
    diagram: "DiagramGraph | None" = None
    children: "list[DocElement] | None" = Field(default=None, description="group members; coordinates are fractions of the group's UNROTATED local frame")
    child_frame: "Bbox | None" = Field(default=None, description="chOff/chExt as fractions of the group bbox; preserved so padded frames survive python-pptx extent recalculation")
    shape: ShapeSpec | None = None
    line: LineSpec | None = None
    icon: IconSpec | None = None
    rich_text: RichTextSpec | None = None
    rotation_deg: float | None = Field(default=None, ge=0.0, lt=360.0, description="clockwise, center-anchored; group/shape/image only")
    binding_paths: list[str] = Field(default_factory=list, description="TextBinding.path values this element renders.")
    entrance: DocEntrance = Field(default_factory=DocEntrance)

    @model_validator(mode="after")
    def validate_content(self) -> "DocElement":
        if self.svg is not None:
            from .svg_sanitize import assert_safe

            assert_safe(self.svg)
        # Exact-one payload semantics (2026-08-07 review): each kind NAMES its
        # payload field; every other payload field must be absent. kind=text
        # silently carrying asset_id/svg/diagram is a contract violation, not
        # a curiosity for the emitters to resolve.
        payload_fields = {
            DocElementKind.TEXT: "text",
            DocElementKind.IMAGE: "asset_id",
            DocElementKind.SVG: "svg",
            DocElementKind.FIGURE: "figure",
            DocElementKind.DIAGRAM: "diagram",
            DocElementKind.GROUP: "children",
            DocElementKind.SHAPE: "shape",
            DocElementKind.LINE: "line",
            DocElementKind.ICON: "icon",
            DocElementKind.RICH_TEXT: "rich_text",
        }
        own = payload_fields[self.kind]
        value = getattr(self, own)
        filled = value is not None and (not isinstance(value, str) or bool(value.strip()))
        if not filled:
            raise ValueError(f"element '{self.id}' ({self.kind.value}) is missing its '{own}' payload")
        for kind, field_name in payload_fields.items():
            if field_name != own and getattr(self, field_name) is not None:
                raise ValueError(
                    f"element '{self.id}' ({self.kind.value}) illegally carries '{field_name}' "
                    f"(payload of kind '{kind.value}')"
                )
        if self.kind is DocElementKind.GROUP:
            if self.binding_paths:
                raise ValueError(f"group '{self.id}': bindings live on leaf content, not containers")
            if not self.children:
                raise ValueError(f"group '{self.id}' has no children")
        if self.child_frame is not None and self.kind is not DocElementKind.GROUP:
            raise ValueError(f"element '{self.id}': child_frame is group-only")
        if self.rotation_deg is not None and self.kind not in {
            DocElementKind.GROUP, DocElementKind.SHAPE, DocElementKind.IMAGE
        }:
            raise ValueError(f"element '{self.id}': rotation is group/shape/image-only")
        if self.kind is DocElementKind.LINE and self.line is not None:
            # Endpoints are canonical; bbox is DERIVED (never authored) — a
            # perfectly horizontal connector has zero natural height, which
            # Bbox forbids, so the hull gets an epsilon extent.
            eps = 0.002
            x0, x1 = sorted((self.line.start.x, self.line.end.x))
            y0, y1 = sorted((self.line.start.y, self.line.end.y))
            object.__setattr__(self, "bbox", Bbox(
                x=x0, y=y0,
                w=max(x1 - x0, eps) if x0 + max(x1 - x0, eps) <= 1.0 else 1.0 - x0,
                h=max(y1 - y0, eps) if y0 + max(y1 - y0, eps) <= 1.0 else 1.0 - y0,
            ))
        return self


def iter_tree(elements: "list[DocElement]"):
    """Depth-first traversal of the element tree. All document invariants use
    this (2026-08-07 review): nested children must never escape validation.
    Groups (when present) expose children via the `children` attribute."""
    for element in elements:
        yield element
        children = getattr(element, "children", None)
        if children:
            yield from iter_tree(children)


class DocSlide(StrictModel):
    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    section: str | None = None
    layout_origin: SlideLayout
    elements: list[DocElement] = Field(min_length=1)
    bindings: list[TextBinding] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    transition: SlideTransition = SlideTransition.SLIDE
    transition_duration_ms: int = Field(default=400, ge=200, le=1200)
    reveal: ContentReveal = ContentReveal.STAGGER_UP
    hidden: bool = False
    notes: str = ""
    intent: SlideIntent | None = None

    @model_validator(mode="after")
    def diagram_labels_resolve_to_bindings(self) -> "DocSlide":
        """Every diagram label string must resolve to a real TextBinding (#1328).

        Element-level binding was too coarse: a diagram bound as one unit let a
        label like 'relevance does not cross this gap' reach a slide with no
        string-level provenance. Declaring a binding_path that no TextBinding
        satisfies is the same failure wearing a receipt, so the path must
        resolve, not merely exist."""
        declared = {binding.path for binding in self.bindings}
        for element in iter_tree(self.elements):
            if element.diagram is None:
                continue
            for node in element.diagram.nodes:
                if node.label.strip():
                    missing = [p for p in node.binding_paths if p not in declared]
                    if missing:
                        raise ValueError(
                            f"slide '{self.id}': node '{node.id}' declares unbound path(s) {missing}"
                        )
            for edge in element.diagram.edges:
                if edge.decorative:
                    continue
                missing = [p for p in edge.binding_paths if p not in declared]
                if missing:
                    raise ValueError(
                        f"slide '{self.id}': edge '{edge.id}' declares unbound path(s) {missing}"
                    )
        return self

    @model_validator(mode="after")
    def unique_element_ids(self) -> "DocSlide":
        ids = [e.id for e in iter_tree(self.elements)]
        if len(ids) != len(set(ids)):
            raise ValueError(f"slide '{self.id}' has duplicate element ids (tree-wide)")
        return self

    @model_validator(mode="after")
    def composition_contract(self) -> "DocSlide":
        """Intent-carrying slides must SATISFY their recipe: required roles
        present, assertion IS the title, density inside budget, reveal order
        resolvable. Design stops being advisory exactly here."""
        if self.intent is None:
            return self
        recipe = COMPOSITION_RECIPES[self.intent.recipe]
        roles = {e.role for e in iter_tree(self.elements) if e.role}
        missing = [r for r in recipe["required_roles"] if r not in roles]
        if missing:
            raise ValueError(
                f"slide '{self.id}': recipe '{self.intent.recipe}' requires roles {missing} (exemplar {recipe['exemplar']})"
            )
        title = next((e for e in iter_tree(self.elements) if e.role == "title"), None)
        if title is not None:
            title_text = title.rich_text.plain_text() if title.rich_text else title.text
            if title_text != self.intent.assertion:
                raise ValueError(f"slide '{self.id}': title text must equal the intent assertion")
        words = 0
        for e in iter_tree(self.elements):
            if e.role == "footer":
                continue  # mandatory qualifiers are compliance chrome, not argument density
            if e.kind is DocElementKind.TEXT:
                words += len((e.text or "").split())
            elif e.kind is DocElementKind.RICH_TEXT:
                words += len(e.rich_text.plain_text().split())
        budget = min(self.intent.density_budget_words, recipe["max_words"])
        if words > budget:
            raise ValueError(f"slide '{self.id}': {words} words exceeds density budget {budget}")
        ids = {e.id for e in iter_tree(self.elements)}
        unknown = [i for i in self.intent.reveal_order if i not in ids]
        if unknown:
            raise ValueError(f"slide '{self.id}': reveal_order references unknown elements {unknown}")
        return self


class DeckDocument(StrictModel):
    schema_: Literal["pitchdeck.deck_document.v1"] = Field(default=DOCUMENT_SCHEMA, alias="schema")
    deck: DeckMeta
    sources: list[SourceSpec]
    claims: list[Claim]
    assets: list[AssetSpec]
    slides: list[DocSlide] = Field(min_length=1)
    revision: int = Field(ge=0)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def referential_integrity(self) -> "DeckDocument":
        claim_ids = {c.id for c in self.claims}
        asset_ids = {a.id for a in self.assets}
        for slide in self.slides:
            for cid in slide.claim_ids:
                if cid not in claim_ids:
                    raise ValueError(f"slide '{slide.id}' references unknown claim '{cid}'")
            for el in iter_tree(slide.elements):
                if el.asset_id and el.asset_id not in asset_ids:
                    raise ValueError(f"element '{slide.id}/{el.id}' references unknown asset '{el.asset_id}'")
        return self


# ── Canonical geometry (fractions of the 16:9 canvas) ─────────────────────────
# One table, one owner. Semantic layouts compile through this; freeform slides
# carry their own author-set geometry and bypass it.
_TITLE = Bbox(x=0.06, y=0.07, w=0.88, h=0.12)
_MESSAGE = Bbox(x=0.06, y=0.20, w=0.88, h=0.10)
_BODY_FULL = Bbox(x=0.06, y=0.33, w=0.88, h=0.55)
_BODY_LEFT = Bbox(x=0.06, y=0.33, w=0.42, h=0.55)
_VISUAL_RIGHT = Bbox(x=0.52, y=0.28, w=0.42, h=0.60)

LAYOUT_GEOMETRY: dict[SlideLayout, dict[str, Bbox]] = {
    # cover/statement carry a body block too: bound content must NEVER drop
    # just because the layout is spare (reviewer finding, 2026-08-06).
    SlideLayout.COVER: {
        "title": Bbox(x=0.08, y=0.28, w=0.84, h=0.18),
        "message": Bbox(x=0.08, y=0.48, w=0.70, h=0.14),
        "body": Bbox(x=0.08, y=0.64, w=0.70, h=0.24),
    },
    SlideLayout.STATEMENT: {
        "title": Bbox(x=0.10, y=0.30, w=0.80, h=0.22),
        "message": Bbox(x=0.10, y=0.54, w=0.80, h=0.12),
        "body": Bbox(x=0.10, y=0.68, w=0.80, h=0.22),
    },
    SlideLayout.SPLIT: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_LEFT, "visual": _VISUAL_RIGHT},
    SlideLayout.SCREENSHOT: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_LEFT, "visual": _VISUAL_RIGHT},
    SlideLayout.FLOW: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
    SlideLayout.THREE_CARDS: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
    SlideLayout.PROOF_CARDS: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
    SlideLayout.ROADMAP: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
    SlideLayout.COLLABORATION: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
    SlideLayout.APPENDIX: {"title": _TITLE, "message": _MESSAGE, "body": _BODY_FULL},
}

_TITLE_STYLE = DocTextStyle(size_pt=40.0, bold=True)
_HERO_STYLE = DocTextStyle(size_pt=64.0, bold=True, align="center")
_MESSAGE_STYLE = DocTextStyle(size_pt=24.0)
_BODY_STYLE = DocTextStyle(size_pt=20.0)


def _grid_rows(base: Bbox, count: int, gap: float = 0.02) -> list[Bbox]:
    if count <= 0:
        return []
    row_h = (base.h - gap * (count - 1)) / count
    return [Bbox(x=base.x, y=base.y + i * (row_h + gap), w=base.w, h=row_h) for i in range(count)]


def _freeform_to_doc(element: FreeformElement, index: int) -> DocElement:
    kind = DocElementKind.TEXT if element.type == "text" else DocElementKind.IMAGE
    return DocElement(
        id=element.id,
        kind=kind,
        bbox=Bbox(x=element.x, y=element.y, w=element.w, h=element.h),
        z=index,
        role=f"element:{element.id}",
        text=element.text,
        style=DocTextStyle(size_pt=element.size_pt, bold=element.bold, color=element.color, align=element.align)
        if kind == DocElementKind.TEXT
        else None,
        asset_id=element.asset_id,
        entrance=DocEntrance(effect=element.entrance, delay_ms=element.entrance_delay_ms),
    )


def _compile_slide(slide: SlideSpec, reveal_steps: bool) -> DocSlide:
    elements: list[DocElement] = []
    if slide.layout is SlideLayout.FREEFORM:
        elements = [_freeform_to_doc(e, i) for i, e in enumerate(slide.elements)]
    else:
        geometry = LAYOUT_GEOMETRY[slide.layout]
        title_style = _HERO_STYLE if slide.layout in {SlideLayout.COVER, SlideLayout.STATEMENT} else _TITLE_STYLE
        elements.append(
            DocElement(id="title", kind=DocElementKind.TEXT, bbox=geometry["title"], role="title", text=slide.title, style=title_style)
        )
        elements.append(
            DocElement(id="message", kind=DocElementKind.TEXT, bbox=geometry["message"], role="message", text=slide.message, style=_MESSAGE_STYLE)
        )
        body_base = geometry.get("body")
        if body_base and slide.body:
            for i, (line, bbox) in enumerate(zip(slide.body, _grid_rows(body_base, len(slide.body)))):
                elements.append(
                    DocElement(
                        id=f"body-{i}",
                        kind=DocElementKind.TEXT,
                        bbox=bbox,
                        role=f"body:{i}",
                        text=line,
                        style=_BODY_STYLE,
                        entrance=DocEntrance(effect="rise", fragment_index=i) if reveal_steps else DocEntrance(),
                    )
                )
        visual_base = geometry.get("visual") or _VISUAL_RIGHT
        if slide.visual.asset_id:
            elements.append(
                DocElement(id="visual", kind=DocElementKind.IMAGE, bbox=visual_base, role="visual", asset_id=slide.visual.asset_id)
            )
        elif slide.visual.items or slide.visual.caption:
            # Item/caption visuals (flow steps, callout lists) compile to a text
            # element until diagram primitives land (#1251 populates FIGURE) —
            # bound content must never drop on the way to the document.
            elements.append(
                DocElement(
                    id="visual",
                    kind=DocElementKind.TEXT,
                    bbox=visual_base,
                    role="visual",
                    text="\n".join([*slide.visual.items, *( [slide.visual.caption] if slide.visual.caption else [])]),
                    style=_BODY_STYLE,
                )
            )
        if slide.footer:
            elements.append(
                DocElement(
                    id="footer",
                    kind=DocElementKind.TEXT,
                    bbox=Bbox(x=0.06, y=0.92, w=0.88, h=0.05),
                    role="footer",
                    text=slide.footer,
                    style=DocTextStyle(size_pt=12.0, color=None),
                )
            )
    # Bindings must land on elements: map binding paths onto element roles.
    roles = {e.role for e in elements} | {e.id for e in elements}
    binding_paths: dict[str, list[str]] = {}
    for binding in slide.bindings:
        root = binding.path.split(".")[0]
        # visual.caption / visual.items:<i> render on the visual element.
        target = "visual" if root == "visual" else root
        if target not in roles and binding.path not in roles:
            raise ValueError(
                f"slide '{slide.id}': binding path '{binding.path}' maps to no document element — "
                "the document would silently drop bound content"
            )
        binding_paths.setdefault(target, []).append(binding.path)
    for el in elements:
        el.binding_paths = binding_paths.get(el.role or el.id, [])
    return DocSlide(
        id=slide.id,
        order=slide.order,
        section=slide.role,
        layout_origin=slide.layout,
        elements=elements,
        bindings=slide.bindings,
        claim_ids=slide.claim_ids,
        transition=slide.transition,
        transition_duration_ms=slide.transition_duration_ms,
        reveal=slide.reveal,
        hidden=slide.hidden,
        notes=slide.notes,
    )


def compile_document(bundle_dir: Path, deck_name: str = "deck.public.yaml") -> DeckDocument:
    """Compile a validated bundle into the canonical whole-deck document."""
    from .io import load_yaml
    from .models import AssetManifest, ClaimLedger, SourceManifest
    from .revisions import current_revision

    deck = load_yaml(bundle_dir / deck_name, DeckManifest)
    ledger = load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger)
    assets = load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest)
    source_path = bundle_dir / "source_manifest.resolved.yaml"
    if not source_path.exists():
        source_path = bundle_dir / "source_manifest.yaml"
    sources = load_yaml(source_path, SourceManifest)

    slides = [
        _compile_slide(slide, reveal_steps=slide.reveal is ContentReveal.STEP)
        for slide in deck.slides
    ]
    return DeckDocument(
        deck=deck.deck,
        sources=sources.sources,
        claims=ledger.claims,
        assets=assets.assets,
        slides=slides,
        revision=current_revision(bundle_dir),
        provenance={"bundle_dir": str(bundle_dir.resolve()), "deck_manifest": deck_name},
    )


def export_json_schema() -> dict:
    """The committed JSON Schema artifact is generated, never hand-edited."""
    return DeckDocument.model_json_schema(by_alias=True)


def project_public(document: DeckDocument) -> DeckDocument:
    """Public-output projection (#1266): only what visible public slides reach.

    Statically served outputs must never carry private claims/sources, hidden
    slides, unreferenced records, or local filesystem provenance. Fail-closed:
    projecting a private deck raises; a visible slide referencing a private
    claim raises (belt-and-braces over validate_bundle).
    """
    from .models import Visibility

    if document.deck.visibility is not Visibility.PUBLIC:
        raise ValueError("cannot project a non-public deck for public output")

    slides = [s for s in document.slides if not s.hidden]
    referenced_claims = {cid for s in slides for cid in s.claim_ids}
    referenced_assets = {e.asset_id for s in slides for e in iter_tree(s.elements) if e.asset_id}

    claims = []
    for claim in document.claims:
        if claim.id not in referenced_claims:
            continue
        if claim.visibility is not Visibility.PUBLIC:
            raise ValueError(f"visible slide references private claim '{claim.id}'")
        claims.append(claim)

    sources = []
    for source in document.sources:
        if source.visibility is not Visibility.PUBLIC:
            continue
        # Strip local-path provenance: keep only the basename for display.
        sources.append(source.model_copy(update={"path": Path(source.path).name}))

    assets = []
    for asset in document.assets:
        if asset.id not in referenced_assets:
            continue
        if asset.visibility is not Visibility.PUBLIC:
            raise ValueError(f"visible slide references private asset '{asset.id}'")
        suffix = Path(asset.local_path).suffix if asset.local_path else ""
        assets.append(asset.model_copy(update={"local_path": f"assets/{asset.id}{suffix}" if asset.local_path else None}))

    return DeckDocument(
        deck=document.deck,
        sources=sources,
        claims=claims,
        assets=assets,
        slides=slides,
        revision=document.revision,
        provenance={"projection": "public", "source_revision": str(document.revision)},
    )


def assert_public_document(document: DeckDocument) -> None:
    """Reject a document that is not a safe public projection."""
    from .models import Visibility

    problems: list[str] = []
    if document.provenance.get("projection") != "public":
        problems.append("document is not marked as a public projection")
    for slide in document.slides:
        if slide.hidden:
            problems.append(f"hidden slide '{slide.id}' present")
    for claim in document.claims:
        if claim.visibility is not Visibility.PUBLIC:
            problems.append(f"private claim '{claim.id}' present")
    for source in document.sources:
        if source.visibility is not Visibility.PUBLIC:
            problems.append(f"private source '{source.id}' present")
        if "/" in source.path or source.path.startswith("$"):
            problems.append(f"source '{source.id}' carries path provenance")
    for asset in document.assets:
        if asset.visibility is not Visibility.PUBLIC:
            problems.append(f"private asset '{asset.id}' present")
        if asset.local_path and not asset.local_path.startswith("assets/"):
            problems.append(f"asset '{asset.id}' carries a local filesystem path")
    if problems:
        raise ValueError("not a public projection: " + "; ".join(problems))
