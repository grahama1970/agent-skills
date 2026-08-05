"""Emit a validated UI deck bundle (deck.data.json) for the React renderer in ui/.

The emitter is a second target beside the PPTX builder: both consume the same
typed manifests, and every fail-closed claim gate in validate_bundle runs before
anything is written. The React app is a pure view over the emitted JSON.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import Field

from .models import (
    AssetManifest,
    ClaimLedger,
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SourceManifest,
    StrictModel,
    Visibility,
)
from .validation import validate_bundle


class UiClaimBadge(StrictModel):
    id: str
    status: str
    risk: str
    kind: str
    text: str
    required_qualifier: str | None = None


class UiAsset(StrictModel):
    id: str
    kind: str
    status: str
    alt_text: str
    file: str | None = None
    missing: bool = False


class UiElement(StrictModel):
    id: str
    type: str
    x: float
    y: float
    w: float
    h: float
    text: str | None = None
    size_pt: float = 20.0
    bold: bool = False
    color: str | None = None
    align: str = "left"
    asset: UiAsset | None = None


class UiVisual(StrictModel):
    type: str
    position: str = "right"
    asset: UiAsset | None = None
    items: list[str] = Field(default_factory=list)
    callouts: list[str] = Field(default_factory=list)
    caption: str | None = None


class UiSlide(StrictModel):
    id: str
    order: int
    layout: str
    role: str
    title: str
    message: str
    body: list[str] = Field(default_factory=list)
    visual: UiVisual
    elements: list[UiElement] = Field(default_factory=list)
    transition: str = "slide"
    reveal: str = "stagger_up"
    claims: list[UiClaimBadge] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    footer: str | None = None


class UiDeckBundle(StrictModel):
    schema_: str = Field(
        default="readme_to_pitchdeck.ui_deck_bundle.v1", alias="schema"
    )
    deck_id: str
    title: str
    subtitle: str | None = None
    audience: str
    visibility: str
    theme: str
    slides: list[UiSlide] = Field(min_length=1)
    claim_summary: dict[str, int] = Field(default_factory=dict)
    validation_readiness: str
    validation_gaps: list[str] = Field(default_factory=list)
    seam_validation: SeamValidation = Field(
        default_factory=lambda: SeamValidation(kind="ui_deck_bundle")
    )


def emit_ui_bundle(
    deck: DeckManifest,
    claim_ledger: ClaimLedger,
    source_manifest: SourceManifest,
    asset_manifest: AssetManifest,
    *,
    source_manifest_dir: Path,
    asset_manifest_dir: Path,
    output_dir: Path,
    require_approved_claims: bool = False,
) -> tuple[OperationReceipt, UiDeckBundle]:
    """Validate the bundle, copy referenced assets, and emit deck.data.json."""
    report = validate_bundle(
        deck,
        claim_ledger,
        source_manifest,
        asset_manifest,
        source_manifest_dir=source_manifest_dir,
        asset_manifest_dir=asset_manifest_dir,
        require_approved_claims=require_approved_claims,
    )
    errors = [issue for issue in report.issues if issue.severity == "error"]
    if errors:
        detail = "; ".join(f"{issue.code}: {issue.message}" for issue in errors[:5])
        raise ValueError(f"bundle failed claim/source validation: {detail}")

    claims_by_id = {claim.id: claim for claim in claim_ledger.claims}
    assets_by_id = {asset.id: asset for asset in asset_manifest.assets}

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_out = output_dir / "assets"
    if assets_out.exists():  # remove stale copies so cleared assets stop being served
        shutil.rmtree(assets_out)
    gaps: list[str] = [
        f"{issue.code}: {issue.message}" for issue in report.issues if issue.severity == "warning"
    ]

    def _ui_asset(asset_id: str) -> UiAsset:
        spec = assets_by_id[asset_id]
        file_name: str | None = None
        missing = spec.local_path is None
        if spec.local_path:
            src = (asset_manifest_dir / spec.local_path).resolve()
            if src.exists():
                assets_out.mkdir(parents=True, exist_ok=True)
                file_name = f"{spec.id}{src.suffix}"
                shutil.copyfile(src, assets_out / file_name)
            else:
                missing = True
        if missing:
            gaps.append(f"UI_MISSING_ASSET: asset '{asset_id}' has no local file; MISSING ASSET card will render.")
        return UiAsset(
            id=spec.id,
            kind=spec.kind.value,
            status=spec.status.value,
            alt_text=spec.alt_text,
            file=f"assets/{file_name}" if file_name else None,
            missing=missing,
        )

    ui_slides: list[UiSlide] = []
    for slide in sorted(deck.slides, key=lambda s: s.order):
        visual = UiVisual(
            type=slide.visual.type.value,
            position=slide.visual.position.value,
            asset=_ui_asset(slide.visual.asset_id) if slide.visual.asset_id else None,
            items=slide.visual.items,
            callouts=slide.visual.callouts,
            caption=slide.visual.caption,
        )
        badges = [
            UiClaimBadge(
                id=claim.id,
                status=claim.status.value,
                risk=claim.risk.value,
                kind=claim.kind.value,
                text=claim.text,
                required_qualifier=claim.required_qualifier,
            )
            for claim in (claims_by_id[cid] for cid in slide.claim_ids)
        ]
        ui_elements = [
            UiElement(
                id=element.id,
                type=element.type,
                x=element.x,
                y=element.y,
                w=element.w,
                h=element.h,
                text=element.text,
                size_pt=element.size_pt,
                bold=element.bold,
                color=element.color,
                align=element.align,
                asset=_ui_asset(element.asset_id) if element.asset_id else None,
            )
            for element in slide.elements
        ]
        ui_slides.append(
            UiSlide(
                id=slide.id,
                order=slide.order,
                layout=slide.layout.value,
                role=slide.role,
                title=slide.title,
                message=slide.message,
                body=slide.body,
                visual=visual,
                elements=ui_elements,
                transition=slide.transition.value,
                reveal=slide.reveal.value,
                claims=badges,
                source_ids=sorted({ref.source_id for ref in slide.source_refs}),
                notes=slide.notes,
                footer=slide.footer,
            )
        )

    claim_summary: dict[str, int] = {}
    for claim in claim_ledger.claims:
        claim_summary[claim.status.value] = claim_summary.get(claim.status.value, 0) + 1

    bundle = UiDeckBundle(
        deck_id=deck.deck.id,
        title=deck.deck.title,
        subtitle=deck.deck.subtitle,
        audience=deck.deck.audience,
        visibility=deck.deck.visibility.value,
        theme=deck.deck.theme,
        slides=ui_slides,
        claim_summary=claim_summary,
        validation_readiness=report.readiness.value,
        validation_gaps=gaps,
    )

    from .io import dump_json

    dump_json(bundle, output_dir / "deck.data.json")

    private_leak = deck.deck.visibility == Visibility.PUBLIC and any(
        claims_by_id[cid].visibility == Visibility.PRIVATE
        for slide in deck.slides
        for cid in slide.claim_ids
    )
    if private_leak:  # validate_bundle already errors on this; belt-and-braces.
        raise ValueError("public deck references private claims")

    receipt = OperationReceipt(
        schema="readme_to_pitchdeck.emit_ui_receipt.v1",
        operation="emit-ui",
        readiness=Readiness.USABLE_WITH_GAPS if gaps else Readiness.READY,
        mocked=False,
        live=False,
        inputs={"deck_id": deck.deck.id, "slides": str(len(ui_slides))},
        outputs={
            "deck_data": str((output_dir / "deck.data.json").resolve()),
            "bundle_dir": str(asset_manifest_dir.resolve()),
        },
        counts={
            "slides": len(ui_slides),
            "claims": len(claim_ledger.claims),
            "copied_assets": len(list(assets_out.glob("*"))) if assets_out.exists() else 0,
        },
        gaps=gaps,
        claims=OperationClaims(
            proves=[
                "The UI bundle was emitted from manifests that passed the same fail-closed validation as the PPTX build.",
            ],
            does_not_prove=[
                "The rendered browser deck is visually approved.",
                "Hand edits to emitted JSON after this receipt are detected (re-run emit-ui to re-validate).",
            ],
        ),
        seam_validation=SeamValidation(kind="emit_ui_receipt"),
    )
    dump_json(receipt, output_dir / "emit_ui_receipt.json")
    return receipt, bundle
