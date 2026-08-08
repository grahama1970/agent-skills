"""Deterministic slide-intent materializer (#1278): approved outline -> DeckDocument.

Consumes an APPROVED narrative outline (hash-verified, questions answered),
the claim ledger, a deck profile, a design system, and the recipe library,
and emits intent-carrying slides through recipe layout constraints — never
hand-authored per-deck coordinates and never free-form LLM rewriting.
Titles are ASSERTION CANDIDATES taken verbatim from bound ledger claims;
default labels ("The problem", "How it works") are rejected with
LABEL_HEADLINE. The recipe resolver picks only COMPATIBLE recipes (a
diagram recipe requires approved diagram data; a proof recipe requires an
asset) and raises NO_COMPATIBLE_RECIPE with the module named when none fit.
Appendix/boneyard slides are the explicit intent-exempt class. Failure
modes are typed: UNAPPROVED_OUTLINE, LABEL_HEADLINE, NO_COMPATIBLE_RECIPE,
MISSING_VISUAL_THESIS, SOURCELESS_ASSERTION.
"""

from __future__ import annotations

from pathlib import Path

from .design_system import CompositionRecipe, DeckProfile, DesignSystem, load_recipes
from .house_spec import HOUSE_BODY_PT, HOUSE_CAPTION_PT
from .document import (
    Bbox,
    DiagramEdge,
    DiagramNode,
    IconSpec,
    DeckDocument,
    DiagramGraph,
    DocElement,
    DocElementKind,
    DocEntrance,
    DocSlide,
    DocTextStyle,
    SlideIntent,
)
from .models import (
    AssetManifest,
    BindingKind,
    ClaimLedger,
    ContentReveal,
    DeckMeta,
    DeckSourcePolicy,
    SlideLayout,
    SourceManifest,
    TextBinding,
    Visibility,
)
from .planning import DeckContext, NarrativeOutline, OutlineModule, PlanningCode

_LABEL_HEADLINES = {
    "the problem", "problem", "solution", "how it works", "architecture",
    "results", "roadmap", "overview", "introduction", "background", "value proposition",
}

# Metaphor badge per module (cybersummit pattern: circular line-icon top-right
# setting the slide's emotional register). Cover carries the brand, no badge.
_MODULE_BADGES: dict[str, str] = {
    "thesis": "compass",
    "value_prop": "lightbulb",
    "problem_solution": "lightbulb",
    "architecture": "route",
    "proof": "monitor",
    "roadmap": "flag",
    "ask": "users",
}

# Module -> ordered recipe preferences. Compatibility is checked in order.
_MODULE_RECIPES: dict[str, list[str]] = {
    "cover": ["cover-brand"],
    "thesis": ["statement-thesis"],
    "value_prop": ["statement-thesis"],
    "problem_solution": ["assertion-chevrons-diagram", "roadmap-lanes"],
    "architecture": ["one-big-diagram"],
    "proof": ["proof-screenshot-callout"],
    "roadmap": ["roadmap-gates", "roadmap-lanes"],
    "ask": ["statement-thesis"],
}

_TITLE_STYLE = DocTextStyle(size_pt=40.0, bold=True)
_HERO_STYLE = DocTextStyle(size_pt=64.0, bold=True, align="center")
_CHEVRON_STYLE = DocTextStyle(size_pt=HOUSE_BODY_PT)
_CAPTION_STYLE = DocTextStyle(size_pt=HOUSE_CAPTION_PT)


def _compatible(recipe: CompositionRecipe, module: OutlineModule) -> bool:
    roles = set(r.value for r in recipe.required_roles)
    if "diagram" in roles and module.diagram is None and recipe.id != "roadmap-gates":
        # roadmap-lanes SYNTHESIZES its gate diagram deterministically from the
        # claim's own verbatim list fragments — no approved diagram data needed.
        return False
    if "visual" in roles and not module.visual_asset_id:
        return False
    return True


def _resolve_recipe(module: OutlineModule, recipes: dict[str, CompositionRecipe]) -> CompositionRecipe:
    for recipe_id in _MODULE_RECIPES.get(module.module, ["statement-thesis"]):
        recipe = recipes[recipe_id]
        if _compatible(recipe, module):
            return recipe
    raise ValueError(
        f"{PlanningCode.NO_COMPATIBLE_RECIPE}: module '{module.module}' has no compatible recipe "
        f"(diagram approved: {module.diagram is not None}, asset: {module.visual_asset_id!r}) — "
        "approve visual content in the outline or choose a text recipe"
    )


def _assertion_for(module: OutlineModule, deck_title: str, *, use_candidate_renderings: bool = False) -> tuple[str, str | None, str]:
    """(assertion text, claim_id, transform) — APPROVED rendering if present,
    else full verbatim claim text. Candidate renderings are used only in
    explicit preview mode (provenance-stamped, never publishable)."""
    if module.module == "cover":
        return deck_title, None, "non_claim"
    if not module.candidate_assertions:
        raise ValueError(
            f"{PlanningCode.NO_COMPATIBLE_RECIPE}: SOURCELESS_ASSERTION — module '{module.module}' has no bound assertion candidates"
        )
    approved = [r for r in module.renderings if r.status == "approved"]
    pool = approved or ([r for r in module.renderings] if use_candidate_renderings else [])
    if pool:
        chosen = pool[0]
        return chosen.text, chosen.claim_id, chosen.transform_class
    assertion = module.candidate_assertions[0]
    if assertion.strip().lower().rstrip(".?!") in _LABEL_HEADLINES:
        raise ValueError(f"LABEL_HEADLINE: module '{module.module}' assertion '{assertion}' is a label, not a takeaway")
    return assertion, module.candidate_claim_ids[0], "verbatim"


def _materialize_slide(module: OutlineModule, order: int, recipes, deck_title: str, tagline: str | None = None, *, use_candidate_renderings: bool = False, qualifiers: dict[str, str] | None = None, context_ask: str | None = None) -> DocSlide:
    recipe = _resolve_recipe(module, recipes)
    assertion, claim_id, transform = _assertion_for(module, deck_title, use_candidate_renderings=use_candidate_renderings)
    if assertion.strip().lower().rstrip(".?!") in _LABEL_HEADLINES:
        raise ValueError(f"LABEL_HEADLINE: '{assertion}'")
    text_only_recipes = {"statement-thesis", "cover-brand", "roadmap-lanes"}
    visual_thesis = module.visual_thesis or (
        "none: text lanes carry the content" if recipe.id in text_only_recipes else ("gate illustration from claim fragments" if recipe.id == "roadmap-gates" else None)
    )
    if visual_thesis is None:
        raise ValueError(f"MISSING_VISUAL_THESIS: module '{module.module}' (recipe {recipe.id})")

    elements: list[DocElement] = []
    bindings: list[TextBinding] = []
    claim_ids: list[str] = list(dict.fromkeys(module.candidate_claim_ids))
    reveal: list[str] = []

    hero = recipe.id in {"cover-brand", "statement-thesis"}
    if recipe.id == "cover-brand":
        # One coherent lockup (visual review): wordmark only, generous leading,
        # tagline on its own clear line — nothing shares a vertical band.
        assertion = assertion.split("\u2014")[0].split("—")[0].strip()
        title_bbox = Bbox(x=0.08, y=0.30, w=0.84, h=0.18)
    elif hero:
        title_bbox = Bbox(x=0.08, y=0.22, w=0.84, h=0.26)
    else:
        title_bbox = Bbox(x=0.06, y=0.07, w=0.88, h=0.12)
    # Slice 2: thesis statement renders centered TEAL (exemplar reqml-12)
    thesis_style = DocTextStyle(size_pt=64.0, bold=True, align="center", color="#065E7C")
    elements.append(DocElement(id="title", kind=DocElementKind.TEXT, role="title", bbox=title_bbox,
                               text=assertion,
                               style=(thesis_style if recipe.id == "statement-thesis" else _HERO_STYLE) if hero else _TITLE_STYLE,
                               binding_paths=["title"] if claim_id else []))
    if recipe.id == "statement-thesis":
        # one large metaphor beneath the assertion (decorative, exemplar pattern)
        elements.append(DocElement(
            id="metaphor", kind=DocElementKind.ICON, role="visual",
            bbox=Bbox(x=0.42, y=0.54, w=0.16, h=0.28),
            icon=IconSpec(library_id="route", tint_role="primary"),
        ))
    if claim_id:
        kind_map = {"truncation": BindingKind.CLAIM_QUOTE, "inflection": BindingKind.CLAIM_QUOTE, "generalization": BindingKind.CLAIM_PARAPHRASE}
        # verbatim fallback = untransformed quote, never falsely labeled truncation
        transform_value = None if transform in {"non_claim", "verbatim"} else transform
        bindings.append(TextBinding(path="title", kind=kind_map.get(transform, BindingKind.CLAIM_QUOTE), claim_id=claim_id,
                                    transform_class=transform_value))

    if "message" in {r.value for r in recipe.required_roles}:
        message_text = (context_ask or tagline or module.purpose) if recipe.id == "cover-brand" else (tagline or module.purpose)
        elements.append(DocElement(id="message", kind=DocElementKind.TEXT, role="message",
                                   bbox=Bbox(x=0.08, y=0.52, w=0.84, h=0.09), text=message_text,
                                   style=DocTextStyle(size_pt=22.0, align="center", color="#595959"),
                                   binding_paths=["message"]))
        bindings.append(TextBinding(path="message", kind=BindingKind.NON_CLAIM))

    if recipe.id == "roadmap-gates":
        # Five-gate closure ILLUSTRATION (visual review slice 2): the claim's
        # own list items become checkpoints on a path ending at the flag.
        import re as _re

        primary = module.candidate_assertions[0]
        lanes = [c.strip().rstrip(".") for c in _re.split(r",| and ", primary) if 2 <= len(c.split()) <= 8][:5]
        lanes = lanes or [primary]
        count = len(lanes)
        nodes = []
        for i, lane in enumerate(lanes):
            nodes.append(DiagramNode(
                id=f"gate-{i}",
                bbox=Bbox(x=0.02 + i * (0.96 / count), y=0.28, w=0.96 / count - 0.02, h=0.44),
                icon="shield-check" if i < count - 1 else "flag",
                label=lane[:60],
                binding_paths=["element:diagram"],
            ))
        edges = [DiagramEdge(id=f"g{i}", source=f"gate-{i}", target=f"gate-{i+1}",
                             line_style="dashed", route="dotted-path",
                             binding_paths=["element:diagram"]) for i in range(count - 1)]
        elements.append(DocElement(
            id="diagram", kind=DocElementKind.DIAGRAM, role="diagram",
            bbox=Bbox(x=0.05, y=0.24, w=0.9, h=0.58),
            diagram=DiagramGraph(recipe="pipeline", nodes=nodes, edges=edges),
            binding_paths=["element:diagram"],
            entrance=DocEntrance(effect="fade"),
        ))
        bindings.append(TextBinding(path="element:diagram", kind=BindingKind.CLAIM_QUOTE,
                                    claim_id=module.candidate_claim_ids[0], transform_class="truncation"))
    elif "chevrons" in {r.value for r in recipe.required_roles}:
        # one COMPLETE supporting takeaway; the diagram is the star (visual review)
        # density-5x5: up to three takeaways, each included ONLY if it fits
        # whole (drop-not-clip; corpus voice is short assertions, and a
        # trailing ellipsis is the strongest machine tell).
        pool = module.candidate_assertions[1:] or module.candidate_assertions[:1]
        extra = [t for t in pool if len(t) <= 110][:3] or [pool[0]]
        for index, text in enumerate(extra):
            el_id = f"chevron-{index}"
            elements.append(DocElement(
                id=el_id, kind=DocElementKind.TEXT, role="chevrons",
                bbox=Bbox(x=0.06, y=0.22 + index * 0.105, w=0.88, h=0.095),
                text=f"> {_truncate_words(text, 220)}", style=_CHEVRON_STYLE,
                binding_paths=[f"element:{el_id}"],
                entrance=DocEntrance(effect="rise", fragment_index=index),
            ))
            source_claim = (module.candidate_claim_ids[0] if recipe.id == "roadmap-lanes"
                            else module.candidate_claim_ids[min(index + 1, len(module.candidate_claim_ids) - 1)])
            bindings.append(TextBinding(path=f"element:{el_id}", kind=BindingKind.CLAIM_QUOTE,
                                        claim_id=source_claim, transform_class="truncation"))
            reveal.append(el_id)

    if "diagram" in {r.value for r in recipe.required_roles} and recipe.id != "roadmap-gates":
        graph = DiagramGraph.model_validate(module.diagram)
        elements.append(DocElement(
            id="diagram", kind=DocElementKind.DIAGRAM, role="diagram",
            bbox=Bbox(x=0.08, y=0.4 if reveal else 0.26, w=0.84, h=0.48 if reveal else 0.6),
            diagram=graph, binding_paths=["element:diagram"],
            entrance=DocEntrance(effect="fade", fragment_index=len(reveal)) if reveal else DocEntrance(),
        ))
        bindings.append(TextBinding(path="element:diagram", kind=BindingKind.CLAIM_PARAPHRASE,
                                    claim_id=claim_id or claim_ids[0], transform_class="generalization"))
        reveal.append("diagram")

    if "visual" in {r.value for r in recipe.required_roles}:
        # Corpus ink-envelope fit: screenshots sit at moderate scale on light
        # canvas in the house style (render-oracle finding, dark product UI).
        elements.append(DocElement(id="visual", kind=DocElementKind.IMAGE, role="visual",
                                   bbox=Bbox(x=0.37, y=0.27, w=0.47, h=0.42), asset_id=module.visual_asset_id))
        elements.append(DocElement(id="visual-caption", kind=DocElementKind.TEXT, role="caption",
                                   bbox=Bbox(x=0.37, y=0.71, w=0.47, h=0.05),
                                   text="Prepared-host capture",
                                   style=_CAPTION_STYLE, binding_paths=["element:visual-caption"]))
        bindings.append(TextBinding(path="element:visual-caption", kind=BindingKind.NON_CLAIM))
    if "callout" in {r.value for r in recipe.required_roles}:
        # ONE complete complementary takeaway (title already carries the primary
        # claim; visual-review rule: complete text, never clipped; budget-safe).
        callout_source = module.candidate_assertions[1:2] or module.candidate_assertions[:1]
        callout_lines = "\n\n".join(f"> {_truncate_words(t, 200)}" for t in callout_source)
        elements.append(DocElement(id="callout", kind=DocElementKind.TEXT, role="callout",
                                   bbox=Bbox(x=0.05, y=0.20, w=0.29, h=0.62), text=callout_lines,
                                   style=_CHEVRON_STYLE, binding_paths=["element:callout"]))
        bindings.append(TextBinding(path="element:callout", kind=BindingKind.CLAIM_QUOTE,
                                    claim_id=claim_ids[0], transform_class="truncation"))

    badge = _MODULE_BADGES.get(module.module)
    if badge:
        from .document import IconSpec as _IconSpec

        elements.append(DocElement(
            id="metaphor-badge", kind=DocElementKind.ICON, role="badge",
            bbox=Bbox(x=0.918, y=0.016, w=0.062, h=0.068),
            icon=_IconSpec(library_id=badge, tint_role="canvas"),
        ))

    # required_qualifier (2026-08-07 review): a claim's mandatory qualifier must
    # be VISIBLE wherever the claim is asserted — rendered as a bound footer.
    required = [q for cid in claim_ids for q in ([qualifiers.get(cid)] if qualifiers else []) if q]
    if required:
        elements.append(DocElement(
            id="qualifier", kind=DocElementKind.TEXT, role="footer",
            bbox=Bbox(x=0.06, y=0.92, w=0.88, h=0.05),
            text=_truncate_words(" · ".join(dict.fromkeys(required)), 260),
            style=DocTextStyle(size_pt=HOUSE_CAPTION_PT, color="#595959"),
            binding_paths=["footer"],
        ))
        bindings.append(TextBinding(path="footer", kind=BindingKind.QUALIFIER, claim_id=claim_ids[0]))

    return DocSlide(
        id=f"m-{module.module.replace('_', '-')}",
        order=order,
        section=module.module,
        layout_origin=SlideLayout.FREEFORM,
        reveal=ContentReveal.STEP if reveal else ContentReveal.STAGGER_UP,
        intent=SlideIntent(
            module=f"outline.{module.module}",
            purpose=module.purpose,
            assertion=assertion,
            visual_thesis=visual_thesis,
            recipe=recipe.id,
            audience="conference",
            density_budget_words=recipe.max_words,
            reveal_order=reveal,
        ),
        elements=elements,
        bindings=bindings,
        claim_ids=claim_ids,
    )


def materialize_outline(
    outline: NarrativeOutline,
    context: DeckContext,
    ledger: ClaimLedger,
    sources: SourceManifest,
    assets: AssetManifest,
    *,
    revision: int = 0,
    use_candidate_renderings: bool = False,
) -> DeckDocument:
    if use_candidate_renderings:
        # PREVIEW ONLY: candidates + possibly-unapproved outline; the document
        # is provenance-stamped and the publish path must refuse it.
        pass
    else:
        outline.assert_approved(ledger)
    active = [m for m in outline.modules if not m.omitted]
    recipes = load_recipes()
    title = _deck_title(context)
    tagline = context.objective.split("—")[-1].strip() if "—" in context.objective else context.primary_ask
    qualifiers = {c.id: c.required_qualifier for c in ledger.claims if getattr(c, "required_qualifier", None)}
    slides = [
        _materialize_slide(module, order, recipes, title, tagline,
                           use_candidate_renderings=use_candidate_renderings, qualifiers=qualifiers,
                           context_ask=context.desired_action)
        for order, module in enumerate(active, start=1)
    ]
    return DeckDocument(
        deck=DeckMeta(
            id=f"outline-{outline.context_sha256[:8]}",
            title=_deck_title(context),
            audience=", ".join(context.audience_roles),
            visibility=context.visibility,
            source_policy=DeckSourcePolicy.PUBLIC_ONLY if context.visibility is Visibility.PUBLIC else DeckSourcePolicy.PUBLIC_AND_PRIVATE,
        ),
        sources=sources.sources,
        claims=ledger.claims,
        assets=assets.assets,
        slides=slides,
        revision=revision,
        provenance={
            "kind": "materialized-outline",
            **({"preview_unapproved_renderings": "true"} if use_candidate_renderings else {}),
            "outline_sha256": outline.content_hash(),
            "context_sha256": outline.context_sha256,
        },
    )


def _deck_title(context: DeckContext) -> str:
    return context.objective.split(".")[0][:100]


def _truncate_words(text: str, limit: int) -> str:
    """Word-boundary truncation — a truncation transform must never cut mid-word."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—-")
    return f"{cut}…"
