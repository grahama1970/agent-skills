"""Typed external and internal records for themes, scenes, and validation receipts.

Inputs are untrusted YAML or SVG-derived data. Pydantic rejects unknown fields and
invalid cross-field timing before render logic receives a record. Failures surface as
validation errors; this module performs no IO.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class StrictModel(BaseModel):
    """Base model that fails closed on unknown fields and is immutable after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Provenance(StrictModel):
    repository: str
    commit: str
    license: str


class CanvasTheme(StrictModel):
    width: int = Field(gt=0, le=10000)
    height: int = Field(gt=0, le=10000)
    view_box: tuple[float, float, float, float]
    background: str
    radius: float = Field(ge=0)


class FontTheme(StrictModel):
    display: tuple[str, ...] = Field(min_length=1)
    mono: tuple[str, ...] = Field(min_length=1)


class PaletteTheme(StrictModel):
    cyan: str
    green: str
    amber: str
    red: str
    orange: str
    white: str
    dark_text: str
    deep_panel: str


class OpacityTheme(StrictModel):
    panel_fill: float = Field(ge=0, le=1)
    soft_panel_accent: float = Field(ge=0, le=1)
    secondary_text: float = Field(ge=0, le=1)
    secondary_border: float = Field(ge=0, le=1)
    halo_peak: float = Field(ge=0, le=1)


class StrokeTheme(StrictModel):
    thin: float = Field(gt=0)
    normal: float = Field(gt=0)
    emphasis: float = Field(gt=0)
    icon: float = Field(gt=0)
    linecap: Literal["butt", "round", "square"]
    linejoin: Literal["arcs", "bevel", "miter", "miter-clip", "round"]


class ShadowTheme(StrictModel):
    text: str
    strong: str


class RadiusTheme(StrictModel):
    canvas: float = Field(ge=0)
    outer_card: float = Field(ge=0)
    card: float = Field(ge=0)
    chip: float = Field(ge=0)
    small: float = Field(ge=0)
    pill: float = Field(ge=0)


class TypographyTheme(StrictModel):
    title_size: float = Field(gt=0)
    heading_size: float = Field(gt=0)
    body_size: float = Field(gt=0)
    supporting_size: float = Field(gt=0)
    caption_size: float = Field(gt=0)
    title_tracking: float
    heading_tracking: float
    caption_tracking: float


class AnimationTheme(StrictModel):
    ambient_cycle_ms: int = Field(gt=0)
    narrative_cycle_ms: int = Field(gt=0)
    hero_cycle_ms: int = Field(gt=0)
    enter_easing: str
    morph_easing: str
    pulse_easing: str


class Theme(StrictModel):
    schema_version: Literal[1]
    name: str = Field(min_length=1)
    provenance: Provenance
    canvas: CanvasTheme
    fonts: FontTheme
    palette: PaletteTheme
    opacity: OpacityTheme
    strokes: StrokeTheme
    shadows: ShadowTheme
    radii: RadiusTheme
    typography: TypographyTheme
    animation: AnimationTheme


AccentName = Literal["cyan", "green", "amber", "red", "orange", "white"]
RecipeName = Literal[
    "fade",
    "fade-slide-x",
    "fade-slide-y",
    "draw-stroke",
    "color-pin",
    "pulse",
    "halo-pulse",
]


class TimelineEvent(StrictModel):
    target: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    recipe: RecipeName
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    delay_ms: int = Field(default=0, ge=0)
    from_x: float = -18
    from_y: float = -18
    peak_opacity: float = Field(default=0.35, ge=0, le=1)
    from_color: str | None = None
    to_color: str | None = None
    color_property: Literal["fill", "stroke"] = "fill"

    @model_validator(mode="after")
    def validate_interval(self) -> "TimelineEvent":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        if self.recipe == "color-pin" and (not self.from_color or not self.to_color):
            raise ValueError("color-pin requires from_color and to_color")
        return self


class Timeline(StrictModel):
    cycle_ms: int = Field(gt=0, le=120000)
    events: tuple[TimelineEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "Timeline":
        outside = [event.target for event in self.events if event.end_ms > self.cycle_ms]
        if outside:
            raise ValueError(f"timeline events exceed cycle_ms: {', '.join(outside)}")
        return self


class SceneMetadata(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)


class ComparisonColumn(StrictModel):
    heading: str = Field(min_length=1, max_length=40)
    accent: AccentName
    items: tuple[str, ...] = Field(min_length=1, max_length=7)


class SourceCard(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    subtitle: str = Field(min_length=1, max_length=120)


class TargetCard(StrictModel):
    number: int = Field(ge=1, le=99)
    heading: str = Field(min_length=1, max_length=40)
    detail: str = Field(min_length=1, max_length=80)
    accent: AccentName


class SceneBase(StrictModel):
    schema_version: Literal[1]
    theme: str = Field(min_length=1)
    metadata: SceneMetadata
    timeline: Timeline | None = None


class PositiveNegativeScene(SceneBase):
    template: Literal["positive-negative"]
    left: ComparisonColumn
    right: ComparisonColumn
    caption: str = Field(min_length=1, max_length=120)


class FanoutAnatomyScene(SceneBase):
    template: Literal["fanout-anatomy"]
    source: SourceCard
    targets: tuple[TargetCard, ...] = Field(min_length=2, max_length=4)
    caption: str = Field(min_length=1, max_length=120)


Scene = Annotated[
    Union[PositiveNegativeScene, FanoutAnatomyScene],
    Field(discriminator="template"),
]
SCENE_ADAPTER = TypeAdapter(Scene)


class Finding(StrictModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str


class BrowserEvidence(StrictModel):
    status: Literal["PASS", "FAIL", "NOT_RUN"]
    loaded: bool
    natural_width: int = 0
    natural_height: int = 0
    animation_observed: bool = False
    changed_pixel_ratio: float = 0.0
    details: str


class ValidationReceipt(StrictModel):
    kind: Literal["readme-svg-validation.v1"] = "readme-svg-validation.v1"
    status: Literal["PASS", "FAIL"]
    tool_version: str
    source_path: str
    source_sha256: str
    deterministic_rebuild: bool | None = None
    theme: str | None = None
    findings: tuple[Finding, ...]
    browser: BrowserEvidence
    proof_scope: str
    does_not_prove: str
    seam_validation: dict[str, str]
