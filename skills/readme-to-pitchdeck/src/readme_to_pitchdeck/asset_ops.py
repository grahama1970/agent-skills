"""Add or clear a slide's visual asset through the fail-closed pipeline.

`add_asset_to_slide` copies a dropped file into the bundle's assets/ dir,
appends a typed AssetSpec (kind inferred from suffix: video for .mp4/.webm,
screenshot otherwise), binds it as the slide's visual, re-runs full bundle
validation, and only on PASS rewrites asset_manifest.yaml + deck YAML +
deck.data.json together. `clear_slide_visual` detaches a slide's visual.
Failure modes: unsupported suffix, missing slide, or validation errors raise
before anything is written.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml
from loguru import logger

from .models import (
    AssetKind,
    AssetManifest,
    AssetSpec,
    AssetStatus,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    Visibility,
    VisualSpec,
    VisualType,
)
from .revisions import commit_bundle_write
from .slide_edit import _load

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
_VIDEO_SUFFIXES = {".mp4", ".webm"}
_MAX_ASSET_BYTES = 100 * 1024 * 1024

# Content sniffing per suffix: a file's bytes must match what its name claims
# (proof-bundle case 14 — a script renamed .png must be rejected on content).
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webm": (b"\x1a\x45\xdf\xa3",),
}


def _verify_asset_content(file_path: Path, suffix: str) -> None:
    size = file_path.stat().st_size
    if size == 0:
        raise ValueError(f"asset file is empty: {file_path}")
    if size > _MAX_ASSET_BYTES:
        raise ValueError(f"asset exceeds {_MAX_ASSET_BYTES // (1024 * 1024)}MB limit: {file_path} ({size} bytes)")
    head = file_path.open("rb").read(64)
    if suffix in _MAGIC:
        if not any(head.startswith(m) for m in _MAGIC[suffix]):
            raise ValueError(f"asset content does not match {suffix} magic bytes: {file_path}")
    elif suffix == ".webp":
        if not (head.startswith(b"RIFF") and head[8:12] == b"WEBP"):
            raise ValueError(f"asset content does not match .webp magic bytes: {file_path}")
    elif suffix == ".mp4":
        if head[4:8] != b"ftyp":
            raise ValueError(f"asset content does not match .mp4 magic bytes (no ftyp box): {file_path}")
    elif suffix == ".svg":
        text = head.decode("utf-8", errors="ignore").lstrip().lower()
        if not (text.startswith("<svg") or text.startswith("<?xml")):
            raise ValueError(f"asset content does not match .svg magic bytes (no svg/xml prolog): {file_path}")


def _write_pair(bundle_dir: Path, deck_name: str, updated_deck, updated_assets, expected_revision: int | None = None) -> None:
    commit_bundle_write(
        bundle_dir,
        {
            bundle_dir / deck_name: yaml.safe_dump(
                updated_deck.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            ),
            bundle_dir / "asset_manifest.yaml": yaml.safe_dump(
                updated_assets.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            ),
        },
        expected_revision=expected_revision,
    )


def _receipt(operation: str, emit_receipt, bundle_dir: Path, extra_inputs: dict[str, str]) -> OperationReceipt:
    return OperationReceipt(
        schema=f"readme_to_pitchdeck.{operation.replace('-', '_')}_receipt.v1",
        operation=operation,
        readiness=Readiness(emit_receipt.readiness),
        mocked=False,
        live=False,
        inputs={"bundle_dir": str(bundle_dir.resolve()), **extra_inputs},
        outputs={"deck_data": emit_receipt.outputs["deck_data"]},
        counts={"gaps": len(emit_receipt.gaps)},
        gaps=emit_receipt.gaps,
        claims=OperationClaims(
            proves=["The asset change passed full bundle validation before any file was written."],
            does_not_prove=["The asset content is accurate, licensed, or approved for external use."],
        ),
        seam_validation=SeamValidation(kind=f"{operation.replace('-', '_')}_receipt"),
    )


def add_asset_to_slide(
    bundle_dir: Path,
    output_dir: Path,
    *,
    slide_id: str,
    file_path: Path,
    alt_text: str,
    deck_name: str = "deck.public.yaml",
) -> OperationReceipt:
    suffix = file_path.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES | _VIDEO_SUFFIXES:
        raise ValueError(
            f"unsupported asset format {suffix}; images: {sorted(_IMAGE_SUFFIXES)}, videos: {sorted(_VIDEO_SUFFIXES)}"
        )
    if not file_path.exists():
        raise ValueError(f"asset file not found: {file_path}")
    if not alt_text.strip():
        raise ValueError("alt_text is required for every asset (accessibility + claim review)")
    _verify_asset_content(file_path, suffix)

    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"no slide '{slide_id}' in {deck_name}")

    stem = re.sub(r"[^a-z0-9-]+", "-", file_path.stem.lower()).strip("-") or "asset"
    asset_id = f"{slide_id}-{stem}"
    existing = {a.id for a in assets.assets}
    counter = 2
    while asset_id in existing:
        asset_id = f"{slide_id}-{stem}-{counter}"
        counter += 1

    assets_dir = bundle_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    stored = assets_dir / f"{asset_id}{suffix}"
    shutil.copyfile(file_path, stored)

    kind = AssetKind.VIDEO if suffix in _VIDEO_SUFFIXES else AssetKind.SCREENSHOT
    new_asset = AssetSpec(
        id=asset_id,
        kind=kind,
        visibility=Visibility(deck.deck.visibility),
        local_path=str(stored.relative_to(bundle_dir)),
        alt_text=alt_text.strip(),
        required=False,
        status=AssetStatus.PRESENT,
    )
    updated_assets = assets.model_copy(update={"assets": [*assets.assets, new_asset]})
    updated_slide = slide.model_copy(
        update={"visual": VisualSpec(type=VisualType.SCREENSHOT, asset_id=asset_id, position=slide.visual.position)}
    )
    from .models import DeckManifest

    updated_deck = DeckManifest.model_validate(
        {
            **deck.model_dump(mode="json", by_alias=True),
            "slides": [
                (updated_slide if s.id == slide_id else s).model_dump(mode="json", by_alias=True)
                for s in deck.slides
            ],
        }
    )

    from .ui_emitter import emit_ui_bundle

    try:
        emit_receipt, _ = emit_ui_bundle(
            updated_deck,
            ledger,
            sources,
            updated_assets,
            source_manifest_dir=source_path.parent,
            asset_manifest_dir=bundle_dir,
            output_dir=output_dir,
        )
    except Exception:
        stored.unlink(missing_ok=True)  # fail closed: no orphan file on rejection
        raise

    _write_pair(bundle_dir, deck_name, updated_deck, updated_assets)
    logger.info("asset '{}' ({}) bound to slide {}", asset_id, kind.value, slide_id)
    return _receipt("asset-add", emit_receipt, bundle_dir, {"slide_id": slide_id, "asset_id": asset_id})


def clear_slide_visual(
    bundle_dir: Path,
    output_dir: Path,
    *,
    slide_id: str,
    deck_name: str = "deck.public.yaml",
) -> OperationReceipt:
    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"no slide '{slide_id}' in {deck_name}")
    from .models import DeckManifest

    updated_slide = slide.model_copy(update={"visual": VisualSpec()})
    updated_deck = DeckManifest.model_validate(
        {
            **deck.model_dump(mode="json", by_alias=True),
            "slides": [
                (updated_slide if s.id == slide_id else s).model_dump(mode="json", by_alias=True)
                for s in deck.slides
            ],
        }
    )
    from .ui_emitter import emit_ui_bundle

    emit_receipt, _ = emit_ui_bundle(
        updated_deck,
        ledger,
        sources,
        assets,
        source_manifest_dir=source_path.parent,
        asset_manifest_dir=bundle_dir,
        output_dir=output_dir,
    )
    _write_pair(bundle_dir, deck_name, updated_deck, assets)
    logger.info("visual cleared on slide {}", slide_id)
    return _receipt("asset-clear", emit_receipt, bundle_dir, {"slide_id": slide_id})
