from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class SourceRole(str, Enum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    EVIDENCE = "evidence"
    DESIGN = "design"


class ClaimKind(str, Enum):
    THESIS = "thesis"
    PRODUCT = "product"
    PROOF = "proof"
    STATUS = "status"
    ROADMAP = "roadmap"
    ASK = "ask"
    NON_CLAIM = "non_claim"
    CANDIDATE = "candidate"


class ClaimRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MANDATORY_NON_CLAIM = "mandatory_non_claim"


class ClaimStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeckSourcePolicy(str, Enum):
    PUBLIC_ONLY = "public_only"
    PUBLIC_AND_PRIVATE = "public_and_private"


class SlideLayout(str, Enum):
    COVER = "cover"
    STATEMENT = "statement"
    SPLIT = "split"
    SCREENSHOT = "screenshot"
    FLOW = "flow"
    THREE_CARDS = "three_cards"
    PROOF_CARDS = "proof_cards"
    ROADMAP = "roadmap"
    COLLABORATION = "collaboration"
    APPENDIX = "appendix"
    FREEFORM = "freeform"


class SlideTransition(str, Enum):
    """Browser-deck slide transition; PPTX export intentionally ignores it."""

    NONE = "none"
    FADE = "fade"
    SLIDE = "slide"
    SLIDE_UP = "slide_up"
    ZOOM = "zoom"


class ContentReveal(str, Enum):
    """Browser-deck content entrance animation for body items."""

    NONE = "none"
    STAGGER_UP = "stagger_up"
    STAGGER_FADE = "stagger_fade"


class VisualPosition(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"


class VisualType(str, Enum):
    NONE = "none"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    NATIVE_DIAGRAM = "native_diagram"
    CARDS = "cards"


class AssetKind(str, Enum):
    SCREENSHOT = "screenshot"
    DIAGRAM = "diagram"
    LOGO = "logo"
    ILLUSTRATION = "illustration"
    PHOTO = "photo"
    VIDEO = "video"
    OTHER = "other"


class AssetStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    PLANNED = "planned"
    STALE = "stale"
    REGENERATE = "regenerate"


class Readiness(str, Enum):
    READY = "READY"
    USABLE_WITH_GAPS = "USABLE_WITH_GAPS"
    NOT_READY = "NOT_READY"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class SeamValidation(StrictModel):
    kind: str = Field(min_length=1)
    status: Literal["PASS"] = "PASS"


class SourceRef(StrictModel):
    source_id: str = Field(min_length=1)
    section: str | None = None
    locator: str | None = None


class SourceSpec(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    visibility: Visibility
    role: SourceRole = SourceRole.PRIMARY
    required: bool = True
    repo: str | None = None
    ref: str | None = None
    content_sha: str | None = None
    include_sections: list[str] = Field(default_factory=list)
    exclude_sections: list[str] = Field(default_factory=list)


class SourcePolicy(StrictModel):
    public_deck_source_ids: list[str] = Field(default_factory=list)
    forbidden_unqualified_claims: list[str] = Field(default_factory=list)
    mandatory_non_claims: list[str] = Field(default_factory=list)


class SourceManifest(StrictModel):
    schema_: Literal["readme_to_pitchdeck.source_manifest.v1"] = Field(
        default="readme_to_pitchdeck.source_manifest.v1", alias="schema"
    )
    project_name: str = Field(min_length=1)
    deck_title: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    sources: list[SourceSpec] = Field(min_length=1)
    policy: SourcePolicy = Field(default_factory=SourcePolicy)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="source_manifest")
    )

    @model_validator(mode="after")
    def validate_unique_sources(self) -> "SourceManifest":
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        known = set(ids)
        unknown = set(self.policy.public_deck_source_ids) - known
        if unknown:
            raise ValueError(
                f"public_deck_source_ids reference unknown sources: {sorted(unknown)}"
            )
        return self


class Claim(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: ClaimKind = ClaimKind.CANDIDATE
    visibility: Visibility
    source_refs: list[SourceRef] = Field(default_factory=list)
    risk: ClaimRisk = ClaimRisk.MEDIUM
    status: ClaimStatus = ClaimStatus.CANDIDATE
    required_qualifier: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_non_claim_shape(self) -> "Claim":
        if self.risk == ClaimRisk.MANDATORY_NON_CLAIM and self.kind != ClaimKind.NON_CLAIM:
            raise ValueError("mandatory_non_claim risk requires kind=non_claim")
        if self.status != ClaimStatus.REJECTED and not self.source_refs:
            raise ValueError("non-rejected claims require at least one source reference")
        if self.risk == ClaimRisk.HIGH and not self.required_qualifier:
            raise ValueError("high-risk claims require required_qualifier")
        return self


class ClaimLedger(StrictModel):
    schema_: Literal["readme_to_pitchdeck.claim_ledger.v1"] = Field(
        default="readme_to_pitchdeck.claim_ledger.v1", alias="schema"
    )
    project_name: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="claim_ledger")
    )

    @model_validator(mode="after")
    def validate_unique_claims(self) -> "ClaimLedger":
        ids = [claim.id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim ids must be unique")
        return self


class AssetSpec(StrictModel):
    id: str = Field(min_length=1)
    kind: AssetKind
    visibility: Visibility
    local_path: str | None = None
    source_url: str | None = None
    required: bool = False
    alt_text: str = Field(min_length=1)
    target_aspect: str = "16:9"
    status: AssetStatus = AssetStatus.PLANNED
    generation_brief: str | None = None
    source_ref: SourceRef | None = None

    @model_validator(mode="after")
    def validate_asset_location(self) -> "AssetSpec":
        if self.status == AssetStatus.PRESENT and not self.local_path:
            raise ValueError("present assets require local_path")
        if self.required and self.status in {AssetStatus.MISSING, AssetStatus.PLANNED}:
            # This is allowed in planning but will fail the build validator.
            return self
        return self


class AssetManifest(StrictModel):
    schema_: Literal["readme_to_pitchdeck.asset_manifest.v1"] = Field(
        default="readme_to_pitchdeck.asset_manifest.v1", alias="schema"
    )
    project_name: str = Field(min_length=1)
    assets: list[AssetSpec] = Field(default_factory=list)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="asset_manifest")
    )

    @model_validator(mode="after")
    def validate_unique_assets(self) -> "AssetManifest":
        ids = [asset.id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("asset ids must be unique")
        return self


class VisualSpec(StrictModel):
    type: VisualType = VisualType.NONE
    asset_id: str | None = None
    position: VisualPosition = VisualPosition.RIGHT
    items: list[str] = Field(default_factory=list)
    callouts: list[str] = Field(default_factory=list)
    caption: str | None = None

    @model_validator(mode="after")
    def validate_visual(self) -> "VisualSpec":
        if self.type in {VisualType.IMAGE, VisualType.SCREENSHOT} and not self.asset_id:
            raise ValueError("image and screenshot visuals require asset_id")
        if self.type == VisualType.NATIVE_DIAGRAM and len(self.items) < 2:
            raise ValueError("native_diagram visuals require at least two items")
        return self


class FreeformElement(StrictModel):
    """Absolutely positioned element; x/y/w/h are fractions of the 16:9 canvas.

    The same fractions drive the browser renderer (x*1920, y*1080) and the
    PPTX builder (x*13.333in, y*7.5in), so geometry round-trips exactly.
    """

    id: str = Field(min_length=1)
    type: Literal["text", "asset"]
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    text: str | None = None
    size_pt: float = Field(default=20.0, ge=8.0, le=96.0)
    bold: bool = False
    color: str | None = None
    align: Literal["left", "center", "right"] = "left"
    asset_id: str | None = None

    @model_validator(mode="after")
    def validate_element(self) -> "FreeformElement":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError(f"element '{self.id}' extends beyond the canvas")
        if self.type == "text" and not (self.text or "").strip():
            raise ValueError(f"text element '{self.id}' has no text")
        if self.type == "asset" and not self.asset_id:
            raise ValueError(f"asset element '{self.id}' has no asset_id")
        return self


class ClaimGuard(StrictModel):
    allowed_claim_ids: list[str] = Field(default_factory=list)
    requires_non_claim_ids: list[str] = Field(default_factory=list)
    forbidden_unqualified: list[str] = Field(default_factory=list)


class SlideSpec(StrictModel):
    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    role: str = Field(min_length=1)
    layout: SlideLayout
    visibility: Visibility
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    body: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    visual: VisualSpec = Field(default_factory=VisualSpec)
    claim_guard: ClaimGuard = Field(default_factory=ClaimGuard)
    elements: list[FreeformElement] = Field(default_factory=list)
    transition: SlideTransition = SlideTransition.SLIDE
    reveal: ContentReveal = ContentReveal.STAGGER_UP
    hidden: bool = False
    notes: str = ""
    footer: str | None = None


class DeckMeta(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subtitle: str | None = None
    audience: str = Field(min_length=1)
    visibility: Visibility
    target_editor: str = "google_slides"
    theme: str = "dark_cyan_evidence"
    source_policy: DeckSourcePolicy
    author: str | None = None


class DeckManifest(StrictModel):
    schema_: Literal["readme_to_pitchdeck.deck_manifest.v1"] = Field(
        default="readme_to_pitchdeck.deck_manifest.v1", alias="schema"
    )
    deck: DeckMeta
    slides: list[SlideSpec] = Field(min_length=1)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="deck_manifest")
    )

    @model_validator(mode="after")
    def validate_deck(self) -> "DeckManifest":
        ids = [slide.id for slide in self.slides]
        orders = [slide.order for slide in self.slides]
        if len(ids) != len(set(ids)):
            raise ValueError("slide ids must be unique")
        if len(orders) != len(set(orders)):
            raise ValueError("slide order values must be unique")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("slide order must be contiguous starting at 1")
        if self.deck.visibility == Visibility.PUBLIC:
            private = [slide.id for slide in self.slides if slide.visibility == Visibility.PRIVATE]
            if private:
                raise ValueError(f"public deck contains private slides: {private}")
        return self


class ValidationIssue(StrictModel):
    severity: Literal["error", "warning", "info"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    slide_id: str | None = None
    claim_id: str | None = None
    source_id: str | None = None
    asset_id: str | None = None


class ValidationReport(StrictModel):
    schema_: Literal["readme_to_pitchdeck.validation_report.v1"] = Field(
        default="readme_to_pitchdeck.validation_report.v1", alias="schema"
    )
    readiness: Readiness
    errors: int = 0
    warnings: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="validation_report")
    )


class OperationClaims(StrictModel):
    proves: list[str] = Field(default_factory=list)
    does_not_prove: list[str] = Field(default_factory=list)


class OperationReceipt(StrictModel):
    schema_: str = Field(min_length=1, alias="schema")
    operation: str = Field(min_length=1)
    readiness: Readiness
    mocked: bool = False
    live: bool = False
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    claims: OperationClaims
    seam_validation: SeamValidation
