"""Whole-deck YAML source editing through the fail-closed pipeline.

The dual-pane editor's source pane edits the REAL document model — the deck
manifest YAML — not a lossy Markdown projection. `apply_deck_source` parses the
submitted YAML into the typed DeckManifest (so schema errors surface with
pydantic messages), re-runs full bundle validation via emit_ui_bundle, and only
on PASS rewrites deck YAML + deck.data.json together. A rejected source edit
changes nothing on disk. Claims, geometry, transitions, and sources all survive
because the source pane speaks the canonical schema.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from .models import (
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
)
from .revisions import commit_bundle_write
from .slide_edit import _load


def apply_deck_source(
    bundle_dir: Path,
    output_dir: Path,
    *,
    source_yaml: str,
    deck_name: str = "deck.public.yaml",
    expected_revision: int | None = None,
) -> OperationReceipt:
    """Replace the deck manifest from edited YAML source; validate before writing."""
    try:
        raw = yaml.safe_load(source_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML syntax error: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("deck source must be a YAML mapping (the deck manifest)")

    updated_deck = DeckManifest.model_validate(raw)
    current_deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    # The target's classification is immutable from inside the mutable payload
    # (WebGPT review P0-3): the source pane may edit content, never what kind
    # of deck this surface is allowed to produce.
    for field in ("id", "visibility", "source_policy"):
        before = getattr(current_deck.deck, field)
        after = getattr(updated_deck.deck, field)
        if before != after:
            raise ValueError(
                f"deck.{field} is immutable through the source editor "
                f"({getattr(before, 'value', before)!r} -> {getattr(after, 'value', after)!r}); "
                "create a separate deck manifest for a different classification."
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
    deck_path = bundle_dir / deck_name
    revision = commit_bundle_write(
        bundle_dir,
        {
            deck_path: yaml.safe_dump(
                updated_deck.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            )
        },
        expected_revision=expected_revision,
    )
    logger.info("deck source applied: {} slides (rev {})", len(updated_deck.slides), revision)
    return OperationReceipt(
        schema="pitchdeck.source_edit_receipt.v1",
        operation="source-edit",
        readiness=Readiness(emit_receipt.readiness),
        mocked=False,
        live=False,
        inputs={"bundle_dir": str(bundle_dir.resolve()), "slides": str(len(updated_deck.slides))},
        outputs={"deck_manifest": str(deck_path.resolve()), "deck_data": emit_receipt.outputs["deck_data"]},
        counts={"gaps": len(emit_receipt.gaps)},
        gaps=emit_receipt.gaps,
        claims=OperationClaims(
            proves=["The edited deck source passed schema and full bundle validation before any write."],
            does_not_prove=["The edited content is factually accurate or approved for external use."],
        ),
        seam_validation=SeamValidation(kind="source_edit_receipt"),
    )
