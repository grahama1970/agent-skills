"""Apply a single slide text edit through the full fail-closed validation pipeline.

The UI's edit mode posts here (via the Vite dev middleware). The edit is
applied to the deck manifest IN MEMORY, then the whole bundle re-runs
emit_ui_bundle — which runs the same validate_bundle gates as the PPTX build.
Only on PASS are deck YAML and deck.data.json rewritten; a rejected edit
(private leak, forbidden unqualified phrase, over-length field) leaves every
file untouched and raises with the validator's message. Editable fields are
presentation text only: title, message, body items, notes, footer. Claim ids,
visibility, sources, and layout are not editable here — those are ledger and
manifest decisions.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from .models import (
    AssetManifest,
    ClaimLedger,
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SourceManifest,
)

EDITABLE_FIELDS = {"title", "message", "notes", "footer", "layout"}


def _load(bundle_dir: Path, deck_name: str):
    from .io import load_yaml

    source_path = bundle_dir / "source_manifest.resolved.yaml"
    if not source_path.exists():
        source_path = bundle_dir / "source_manifest.yaml"
    return (
        load_yaml(bundle_dir / deck_name, DeckManifest),
        load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger),
        load_yaml(source_path, SourceManifest),
        load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest),
        source_path,
    )


def apply_slide_edit(
    bundle_dir: Path,
    output_dir: Path,
    *,
    slide_id: str,
    field: str,
    value: str,
    deck_name: str = "deck.public.yaml",
) -> OperationReceipt:
    """Edit one slide field, re-validate the whole bundle, and re-emit on PASS."""
    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)

    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"no slide '{slide_id}' in {deck_name}")

    base_field, _, index_part = field.partition(":")
    if base_field == "body":
        new_body = list(slide.body)
        if index_part == "add":
            new_body.append(value)
        elif index_part.startswith("del."):
            index = int(index_part.removeprefix("del."))
            if index >= len(new_body):
                raise ValueError(f"slide '{slide_id}' has no body item {index}")
            del new_body[index]
        elif index_part.isdigit():
            index = int(index_part)
            if index >= len(new_body):
                raise ValueError(f"slide '{slide_id}' has no body item {index}")
            new_body[index] = value
        else:
            raise ValueError("body edits use field 'body:<index>', 'body:add', or 'body:del.<index>'")
        updated_slide = slide.model_copy(update={"body": new_body})
    elif base_field in EDITABLE_FIELDS:
        updated_slide = slide.model_copy(update={base_field: value or None if base_field == "footer" else value})
    else:
        raise ValueError(
            f"field '{field}' is not editable here; editable: {sorted(EDITABLE_FIELDS)} and body:<index>. "
            "Claims, visibility, sources, and layout are ledger/manifest decisions."
        )

    # Pydantic re-validates field constraints (e.g. title<=120, message<=500).
    updated_deck = DeckManifest.model_validate(
        {
            **deck.model_dump(mode="json", by_alias=True),
            "slides": [
                updated_slide.model_dump(mode="json", by_alias=True)
                if s.id == slide_id
                else s.model_dump(mode="json", by_alias=True)
                for s in deck.slides
            ],
        }
    )

    # Full fail-closed pipeline on the edited deck BEFORE anything is written.
    from .ui_emitter import emit_ui_bundle

    receipt, _ = emit_ui_bundle(
        updated_deck,
        ledger,
        sources,
        assets,
        source_manifest_dir=source_path.parent,
        asset_manifest_dir=bundle_dir,
        output_dir=output_dir,
    )

    deck_path = bundle_dir / deck_name
    deck_path.write_text(
        yaml.safe_dump(
            updated_deck.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    logger.info("slide edit applied: {} {} ({} chars); deck re-emitted", slide_id, field, len(value))

    return OperationReceipt(
        schema="readme_to_pitchdeck.slide_edit_receipt.v1",
        operation="apply-edit",
        readiness=Readiness(receipt.readiness),
        mocked=False,
        live=False,
        inputs={"bundle_dir": str(bundle_dir.resolve()), "slide_id": slide_id, "field": field},
        outputs={
            "deck_manifest": str(deck_path.resolve()),
            "deck_data": receipt.outputs["deck_data"],
        },
        counts={"gaps": len(receipt.gaps)},
        gaps=receipt.gaps,
        claims=OperationClaims(
            proves=[
                "The edit passed the same fail-closed bundle validation as a build before any file was written.",
                "deck manifest YAML and deck.data.json were rewritten together.",
            ],
            does_not_prove=[
                "The edited wording is factually accurate or approved for external use.",
            ],
        ),
        seam_validation=SeamValidation(kind="slide_edit_receipt"),
    )


DECK_OPS = {"add_after", "duplicate", "delete", "move_left", "move_right"}


def apply_deck_op(
    bundle_dir: Path,
    output_dir: Path,
    *,
    op: str,
    slide_id: str,
    deck_name: str = "deck.public.yaml",
) -> OperationReceipt:
    """Slide-level operation (add/duplicate/delete/reorder) through the same gates."""
    if op not in DECK_OPS:
        raise ValueError(f"unknown deck op '{op}'; valid: {sorted(DECK_OPS)}")
    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    slides = sorted(deck.slides, key=lambda s: s.order)
    position = next((i for i, s in enumerate(slides) if s.id == slide_id), None)
    if position is None:
        raise ValueError(f"no slide '{slide_id}' in {deck_name}")
    current = slides[position]

    if op in {"add_after", "duplicate"}:
        base = current if op == "duplicate" else current.model_copy(
            update={
                "role": "content",
                "layout": "statement",
                "title": "New slide",
                "message": "Draft content — edit me.",
                "body": [],
                "claim_ids": [],
                "notes": "Added in the deck editor; bind claims before external use.",
                "footer": None,
            }
        )
        suffix = 2
        new_id = f"{current.id}-copy" if op == "duplicate" else "new-slide"
        existing = {s.id for s in slides}
        candidate = new_id
        while candidate in existing:
            candidate = f"{new_id}-{suffix}"
            suffix += 1
        slides.insert(position + 1, base.model_copy(update={"id": candidate}))
    elif op == "delete":
        if len(slides) == 1:
            raise ValueError("cannot delete the last slide")
        del slides[position]
    elif op == "move_left":
        if position == 0:
            raise ValueError("slide is already first")
        slides[position - 1], slides[position] = slides[position], slides[position - 1]
    elif op == "move_right":
        if position == len(slides) - 1:
            raise ValueError("slide is already last")
        slides[position + 1], slides[position] = slides[position], slides[position + 1]

    renumbered = [s.model_copy(update={"order": i + 1}) for i, s in enumerate(slides)]
    updated_deck = DeckManifest.model_validate(
        {
            **deck.model_dump(mode="json", by_alias=True),
            "slides": [s.model_dump(mode="json", by_alias=True) for s in renumbered],
        }
    )

    from .ui_emitter import emit_ui_bundle

    receipt, _ = emit_ui_bundle(
        updated_deck,
        ledger,
        sources,
        assets,
        source_manifest_dir=source_path.parent,
        asset_manifest_dir=bundle_dir,
        output_dir=output_dir,
    )
    deck_path = bundle_dir / deck_name
    deck_path.write_text(
        yaml.safe_dump(
            updated_deck.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    logger.info("deck op applied: {} on {}; {} slides", op, slide_id, len(renumbered))
    return OperationReceipt(
        schema="readme_to_pitchdeck.deck_op_receipt.v1",
        operation="deck-op",
        readiness=Readiness(receipt.readiness),
        mocked=False,
        live=False,
        inputs={"bundle_dir": str(bundle_dir.resolve()), "op": op, "slide_id": slide_id},
        outputs={"deck_manifest": str(deck_path.resolve()), "deck_data": receipt.outputs["deck_data"]},
        counts={"slides": len(renumbered), "gaps": len(receipt.gaps)},
        gaps=receipt.gaps,
        claims=OperationClaims(
            proves=["The slide operation passed full bundle validation before any file was written."],
            does_not_prove=["New or duplicated slides carry reviewed claims — bind and review before external use."],
        ),
        seam_validation=SeamValidation(kind="deck_op_receipt"),
    )
