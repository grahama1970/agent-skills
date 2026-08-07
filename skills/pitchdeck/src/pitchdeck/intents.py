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
from .document import (
    Bbox,
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

# Module -> ordered recipe preferences. Compatibility is checked in order.
_MODULE_RECIPES: dict[str, list[str]] = {
    "cover": ["cover-brand"],
    "thesis": ["statement-thesis"],
    "value_prop": ["statement-thesis"],
    "problem_solution": ["assertion-chevrons-diagram", "roadmap-lanes"],
    "architecture": ["one-big-diagram"],
    "proof": ["proof-screenshot-callout"],
    "roadmap": ["roadmap-lanes"],
    "ask": ["statement-thesis"],
}

_TITLE_STYLE = DocTextStyle(size_pt=40.0, bold=True)
_HERO_STYLE = DocTextStyle(size_pt=64.0, bold=True, align="center")
_CHEVRON_STYLE = DocTextStyle(size_pt=22.0)
_CAPTION_STYLE = DocTextStyle(size_pt=14.0)


def _compatible(recipe: CompositionRecipe, module: OutlineModule) -> bool:
    roles = set(r.value for r in recipe.required_roles)
    if "diagram" in roles and module.diagram is None:
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


def _assertion_for(module: OutlineModule, deck_title: str) -> tuple[str, str | None]:
    """(assertion text, claim_id) — verbatim candidate, never a label."""
    if module.module == "cover":
        return deck_title, None
    if not module.candidate_assertions:
        raise ValueError(
            f"{PlanningCode.NO_COMPATIBLE_RECIPE}: SOURCELESS_ASSERTION — module '{module.module}' has no bound assertion candidates"
        )
    assertion = module.candidate_assertions[0]
    if assertion.strip().lower().rstrip(".?!") in _LABEL_HEADLINES:
        raise ValueError(f"LABEL_HEADLINE: module '{module.module}' assertion '{assertion}' is a label, not a takeaway")
    return assertion, module.candidate_claim_ids[0]


def _materialize_slide(module: OutlineModule, order: int, recipes, deck_title: str, tagline: str | None = None) -> DocSlide:
    recipe = _resolve_recipe(module, recipes)
    assertion, claim_id = _assertion_for(module, deck_title)
    if assertion.strip().lower().rstrip(".?!") in _LABEL_HEADLINES:
        raise ValueError(f"LABEL_HEADLINE: '{assertion}'")
    text_only_recipes = {"statement-thesis", "cover-brand", "roadmap-lanes"}
    visual_thesis = module.visual_thesis or (
        "none: text lanes carry the content" if recipe.id in text_only_recipes else None
    )
    if visual_thesis is None:
        raise ValueError(f"MISSING_VISUAL_THESIS: module '{module.module}' (recipe {recipe.id})")

    elements: list[DocElement] = []
    bindings: list[TextBinding] = []
    claim_ids: list[str] = list(dict.fromkeys(module.candidate_claim_ids))
    reveal: list[str] = []

    hero = recipe.id in {"cover-brand", "statement-thesis"}
    title_bbox = Bbox(x=0.08, y=0.34, w=0.84, h=0.26) if hero else Bbox(x=0.06, y=0.07, w=0.88, h=0.12)
    elements.append(DocElement(id="title", kind=DocElementKind.TEXT, role="title", bbox=title_bbox,
                               text=assertion, style=_HERO_STYLE if hero else _TITLE_STYLE,
                               binding_paths=["title"] if claim_id else []))
    if claim_id:
        bindings.append(TextBinding(path="title", kind=BindingKind.CLAIM_QUOTE, claim_id=claim_id, transform_class="truncation"))

    if "message" in {r.value for r in recipe.required_roles}:
        message_text = tagline or module.purpose
        elements.append(DocElement(id="message", kind=DocElementKind.TEXT, role="message",
                                   bbox=Bbox(x=0.08, y=0.62, w=0.84, h=0.1), text=message_text,
                                   style=DocTextStyle(size_pt=28.0, align="center", color="#595959"),
                                   binding_paths=["message"]))
        bindings.append(TextBinding(path="message", kind=BindingKind.NON_CLAIM))

    if "chevrons" in {r.value for r in recipe.required_roles}:
        extra = module.candidate_assertions[1:4] or module.candidate_assertions[:1]
        for index, text in enumerate(extra):
            el_id = f"chevron-{index}"
            elements.append(DocElement(
                id=el_id, kind=DocElementKind.TEXT, role="chevrons",
                bbox=Bbox(x=0.06, y=0.22 + index * 0.09, w=0.88, h=0.08),
                text=f"> {text[:90]}", style=_CHEVRON_STYLE,
                binding_paths=[f"element:{el_id}"],
                entrance=DocEntrance(effect="rise", fragment_index=index),
            ))
            source_claim = module.candidate_claim_ids[min(index + 1, len(module.candidate_claim_ids) - 1)]
            bindings.append(TextBinding(path=f"element:{el_id}", kind=BindingKind.CLAIM_QUOTE,
                                        claim_id=source_claim, transform_class="truncation"))
            reveal.append(el_id)

    if "diagram" in {r.value for r in recipe.required_roles}:
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
        elements.append(DocElement(id="visual", kind=DocElementKind.IMAGE, role="visual",
                                   bbox=Bbox(x=0.34, y=0.24, w=0.6, h=0.62), asset_id=module.visual_asset_id))
    if "callout" in {r.value for r in recipe.required_roles}:
        callout_lines = "\n".join(f"> {t[:40]}" for t in module.candidate_assertions[:3])
        elements.append(DocElement(id="callout", kind=DocElementKind.TEXT, role="callout",
                                   bbox=Bbox(x=0.06, y=0.24, w=0.25, h=0.4), text=callout_lines,
                                   style=_CHEVRON_STYLE, binding_paths=["element:callout"]))
        bindings.append(TextBinding(path="element:callout", kind=BindingKind.CLAIM_QUOTE,
                                    claim_id=claim_ids[0], transform_class="truncation"))

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
) -> DeckDocument:
    outline.assert_approved()
    active = [m for m in outline.modules if not m.omitted]
    recipes = load_recipes()
    title = _deck_title(context)
    tagline = context.objective.split("—")[-1].strip() if "—" in context.objective else context.primary_ask
    slides = [
        _materialize_slide(module, order, recipes, title, tagline)
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
            "outline_sha256": outline.content_hash(),
            "context_sha256": outline.context_sha256,
        },
    )


def _deck_title(context: DeckContext) -> str:
    return context.objective.split(".")[0][:100]
