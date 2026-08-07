"""Executable design contract: four strict versioned schemas (#1275).

Splits the design knowledge that lived as prose + mixed theme JSON into
machine-enforceable models with closed enums and extra=forbid:

- pitchdeck.design_system.v1   — semantic color/font roles, type scale,
  chrome, bullet grammar, accessibility minima (brand identity, no audience
  behavior).
- pitchdeck.deck_profile.v1    — audience behavior: required modules, order,
  tone, notices, recap/appendix devices (no colors, no fonts).
- pitchdeck.composition_recipe.v1 — per-slide composition contracts (roles,
  kinds, density, binding + reveal + fallback rules, exemplar ids) that
  document.py enforces on intent-carrying slides.
- pitchdeck.style_reference.v1 — imported reference-deck measurements with
  provenance and confidence, never auto-promoted to house invariants.

resolve_design() / resolve_profile() produce deterministic Resolved* views
(role -> concrete value) for renderers. Recipes ship as JSON instances in
design/recipes/ (not Python dicts); exemplar ids can be verified against the
best-practices-slide-design style_corpus manifest. Failure modes: unknown
roles, invalid palette refs, unresolved exemplar ids, or unsupported modules
raise at validation — never at render time.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel

RECIPE_DIR = Path(__file__).parent / "design" / "recipes"

HEX = r"^#[0-9a-fA-F]{6}$"


class ColorRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    CANVAS = "canvas"
    INK = "ink"
    MUTED = "muted"
    HIGHLIGHT_WARM = "highlight_warm"
    HIGHLIGHT_GREEN = "highlight_green"
    PROGRAM = "program"
    ALERT = "alert"


class FontRoles(StrictModel):
    heading: str = Field(min_length=1)
    body: str = Field(min_length=1)
    code: str = Field(min_length=1)
    diagram: str = Field(min_length=1)


class TypeScalePt(StrictModel):
    hero: float = Field(gt=0)
    statement_hero: float = Field(gt=0)
    section: float = Field(gt=0)
    title: float = Field(gt=0)
    lead: float = Field(gt=0)
    body: float = Field(gt=0)
    support: float = Field(gt=0)
    caption: float = Field(gt=0)


class HeaderBand(StrictModel):
    fill_role: ColorRole
    title_color: str = Field(pattern=HEX)
    height_frac: float = Field(gt=0.0, le=0.2)


class FooterChrome(StrictModel):
    rule_role: ColorRole
    page_number: bool = True
    distribution_statement: bool = False
    sponsor_strip: bool = False


class MetaphorBadge(StrictModel):
    position: Literal["top-right", "top-left", "none"]
    shape: Literal["circle"] = "circle"
    stroke_role: ColorRole = ColorRole.PRIMARY


class BulletLevel(StrictModel):
    level: int = Field(ge=1, le=3)
    marker: Literal["chevron", "square", "dash"]
    color_role: ColorRole


class Accessibility(StrictModel):
    min_body_pt: float = Field(ge=8.0)
    min_contrast_ratio: float = Field(ge=1.0)


class DesignSystem(StrictModel):
    schema_: Literal["pitchdeck.design_system.v1"] = Field(default="pitchdeck.design_system.v1", alias="schema")
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    mode: Literal["light", "dark"]
    palette: dict[ColorRole, str] = Field(min_length=1)
    fonts: FontRoles
    type_scale_pt: TypeScalePt
    header_band: HeaderBand
    footer: FooterChrome
    badge: MetaphorBadge
    bullet_grammar: list[BulletLevel] = Field(min_length=1)
    accessibility: Accessibility
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def palette_refs_resolve(self) -> "DesignSystem":
        import re

        for role, value in self.palette.items():
            if not re.match(HEX, value):
                raise ValueError(f"palette role '{role.value}' has invalid hex '{value}'")
        for role in (self.header_band.fill_role, self.footer.rule_role, self.badge.stroke_role):
            if role not in self.palette:
                raise ValueError(f"chrome references palette role '{role.value}' that is not defined")
        for level in self.bullet_grammar:
            if level.color_role not in self.palette:
                raise ValueError(f"bullet level {level.level} references undefined palette role '{level.color_role.value}'")
        return self


class Audience(str, Enum):
    CONFERENCE = "conference"
    SBIR = "sbir"
    PROGRAM_REVIEW = "program-review"


KNOWN_MODULES = {
    "cover", "toc", "value_prop", "thesis", "problem_solution", "vision",
    "product_modules", "architecture", "proof", "roadmap", "ask",
    "pipeline_position", "accomplishments_since_last_review", "discussion",
    "boneyard",
}


class ModuleRequirement(StrictModel):
    module: str = Field(min_length=1)
    required: bool = True
    position: Literal["early", "mid", "late", "any"] = "any"

    @model_validator(mode="after")
    def module_known(self) -> "ModuleRequirement":
        if self.module not in KNOWN_MODULES:
            raise ValueError(f"unsupported narrative module '{self.module}' (known: {sorted(KNOWN_MODULES)})")
        return self


class DeckProfile(StrictModel):
    schema_: Literal["pitchdeck.deck_profile.v1"] = Field(default="pitchdeck.deck_profile.v1", alias="schema")
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    audience: Audience
    target_slide_range: tuple[int, int] = (6, 20)
    modules: list[ModuleRequirement] = Field(min_length=1)
    module_order: list[str] = Field(min_length=1)
    evidence_depth: Literal["light", "standard", "deep"] = "standard"
    humor: Literal["off", "low", "high"] = "low"
    boneyard_appendix: bool = True
    distribution_notice_slide: bool = False
    recap_devices: bool = False
    density_words_median_target: int = Field(ge=5, le=80)
    density_words_p90_max: int = Field(ge=10, le=250)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def order_covers_modules(self) -> "DeckProfile":
        unknown = [m for m in self.module_order if m not in KNOWN_MODULES]
        if unknown:
            raise ValueError(f"module_order contains unsupported modules {unknown}")
        required = {m.module for m in self.modules if m.required}
        missing = required - set(self.module_order)
        if missing:
            raise ValueError(f"required modules missing from module_order: {sorted(missing)}")
        return self


class RoleId(str, Enum):
    TITLE = "title"
    MESSAGE = "message"
    CHEVRONS = "chevrons"
    DIAGRAM = "diagram"
    VISUAL = "visual"
    CALLOUT = "callout"
    CAPTION = "caption"
    FOOTER = "footer"


class CompositionRecipe(StrictModel):
    schema_: Literal["pitchdeck.composition_recipe.v1"] = Field(default="pitchdeck.composition_recipe.v1", alias="schema")
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    required_roles: list[RoleId] = Field(min_length=1)
    optional_roles: list[RoleId] = Field(default_factory=list)
    allowed_kinds: list[Literal["text", "image", "svg", "figure", "diagram"]] = Field(min_length=1)
    max_words: int = Field(ge=5, le=200)
    visual_weight_min_frac: float = Field(ge=0.0, le=1.0, default=0.0)
    title_binding_required: bool = True
    numeric_requires_span: bool = True
    reveal_order_matches_narrative: bool = True
    pptx_editable_shapes_required: bool = True
    exemplar_ids: list[str] = Field(min_length=1)
    provenance: dict[str, str] = Field(default_factory=dict)


class StyleObservation(StrictModel):
    value: str = Field(min_length=1)
    count: int = Field(ge=1)


class StyleReference(StrictModel):
    schema_: Literal["pitchdeck.style_reference.v1"] = Field(default="pitchdeck.style_reference.v1", alias="schema")
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    source_sha256: str | None = None
    slide_count: int = Field(ge=1)
    fonts: list[StyleObservation] = Field(default_factory=list)
    colors: list[StyleObservation] = Field(default_factory=list)
    sizes_pt: list[StyleObservation] = Field(default_factory=list)
    words_median: int = Field(ge=0)
    words_p90: int = Field(ge=0)
    patterns: list[str] = Field(default_factory=list)
    confidence: Literal["measured", "estimated", "unsupported"] = "measured"
    provenance: dict[str, str] = Field(default_factory=dict)


class ResolvedDesignSystem(StrictModel):
    """Deterministic renderer view: every role resolved to a concrete value."""

    system_id: str
    colors: dict[str, str]
    heading_font: str
    body_font: str
    code_font: str
    header_band_fill: str
    header_band_title_color: str
    header_band_height_frac: float
    type_scale_pt: TypeScalePt


def resolve_design(system: DesignSystem) -> ResolvedDesignSystem:
    return ResolvedDesignSystem(
        system_id=system.id,
        colors={role.value: value for role, value in sorted(system.palette.items(), key=lambda kv: kv[0].value)},
        heading_font=system.fonts.heading,
        body_font=system.fonts.body,
        code_font=system.fonts.code,
        header_band_fill=system.palette[system.header_band.fill_role],
        header_band_title_color=system.header_band.title_color,
        header_band_height_frac=system.header_band.height_frac,
        type_scale_pt=system.type_scale_pt,
    )


class ResolvedDeckProfile(StrictModel):
    profile_id: str
    audience: Audience
    ordered_required_modules: list[str]
    density_budget: dict[str, int]


def resolve_profile(profile: DeckProfile) -> ResolvedDeckProfile:
    required = {m.module for m in profile.modules if m.required}
    return ResolvedDeckProfile(
        profile_id=profile.id,
        audience=profile.audience,
        ordered_required_modules=[m for m in profile.module_order if m in required],
        density_budget={
            "words_median_target": profile.density_words_median_target,
            "words_p90_max": profile.density_words_p90_max,
        },
    )


def load_recipes(recipe_dir: Path = RECIPE_DIR) -> dict[str, CompositionRecipe]:
    recipes = {}
    for path in sorted(recipe_dir.glob("*.json")):
        recipe = CompositionRecipe.model_validate(json.loads(path.read_text(encoding="utf-8")))
        recipes[recipe.id] = recipe
    if not recipes:
        raise ValueError(f"no composition recipes found in {recipe_dir}")
    return recipes


def verify_exemplars(recipes: dict[str, CompositionRecipe], corpus_manifest: Path) -> None:
    """Recipe exemplar ids must resolve against the hash-pinned corpus (#1274)."""
    corpus = json.loads(corpus_manifest.read_text(encoding="utf-8"))
    known = {entry["id"] for entry in corpus.get("exemplars", [])}
    for recipe in recipes.values():
        for exemplar in recipe.exemplar_ids:
            if not any(k == exemplar or k.startswith(exemplar) for k in known):
                raise ValueError(f"recipe '{recipe.id}' cites unresolved exemplar '{exemplar}'")


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model, name in (
        (DesignSystem, "pitchdeck.design_system.v1"),
        (DeckProfile, "pitchdeck.deck_profile.v1"),
        (CompositionRecipe, "pitchdeck.composition_recipe.v1"),
        (StyleReference, "pitchdeck.style_reference.v1"),
    ):
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(by_alias=True), indent=1), encoding="utf-8")
        written.append(path)
    return written
