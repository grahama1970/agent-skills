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

from .revisions import commit_bundle_write
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

EDITABLE_FIELDS = {"title", "message", "notes", "footer", "layout", "transition", "reveal", "hidden"}


def validated_undo(bundle_dir: Path, output_dir: Path, *, deck_name: str = "deck.public.yaml"):
    """Undo with validate-BEFORE-commit (review P0: no blind byte restore).

    Overlays the newest archive onto a temp copy of the bundle, runs the full
    emit_ui_bundle validation there, and only on PASS performs the real CAS
    restore + re-emit. Out-of-band edits, governance files in the archive, and
    validation failures all refuse fail-closed with nothing written.
    """
    import shutil
    from tempfile import TemporaryDirectory

    from .revisions import (
        GOVERNANCE_FILES,
        HISTORY_DIR,
        GovernanceUndoRefused,
        NoHistory,
        check_out_of_band,
        undo_history,
        undo_last_write,
    )
    from .ui_emitter import emit_ui_bundle

    check_out_of_band(bundle_dir)
    available = undo_history(bundle_dir)
    if not available:
        raise NoHistory(f"no archived revisions under {bundle_dir / HISTORY_DIR}; nothing to undo")
    archive = bundle_dir / HISTORY_DIR / str(available[-1])
    with TemporaryDirectory(prefix="deck-undo-") as tmp:
        staging = Path(tmp) / "bundle"
        shutil.copytree(bundle_dir, staging, ignore=shutil.ignore_patterns(HISTORY_DIR))
        for path in sorted(x for x in archive.rglob("*") if x.is_file()):
            rel = path.relative_to(archive)
            if rel.name in GOVERNANCE_FILES:
                raise GovernanceUndoRefused(
                    f"archive contains governance file '{rel}'; approvals are not undoable"
                )
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        deck, ledger, sources, assets, source_path = _load(staging, deck_name)
        emit_ui_bundle(
            deck, ledger, sources, assets,
            source_manifest_dir=source_path.parent, asset_manifest_dir=staging,
            output_dir=Path(tmp) / "ui",
        )  # raises on validation failure — nothing has touched the real bundle
    revision = undo_last_write(bundle_dir)
    deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
    receipt, _ = emit_ui_bundle(
        deck, ledger, sources, assets,
        source_manifest_dir=source_path.parent, asset_manifest_dir=bundle_dir,
        output_dir=output_dir,
    )
    receipt.inputs["restored_revision"] = str(revision)
    return receipt


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


def simulate_edit(
    bundle_dir: Path,
    *,
    slide_id: str,
    field: str | None = None,
    value: str | None = None,
    op: str | None = None,
    target_order: int | None = None,
    deck_name: str = "deck.public.yaml",
) -> dict:
    """Roundtable slice 1: dry-run a mutation through the REAL pipeline.

    Copies the bundle to a temp overlay, applies the edit (or deck op) there —
    which runs the full emit_ui_bundle validation and post-emit machinery —
    and returns {would_pass, gate_codes, error, diff} without touching the
    real bundle. The agent iterates against this until would_pass, then
    applies with the same arguments.
    """
    import difflib
    import re as _re
    import shutil
    from tempfile import TemporaryDirectory

    from .revisions import HISTORY_DIR

    if (field is None) == (op is None):
        raise ValueError("simulate_edit needs exactly one of field= or op=")
    with TemporaryDirectory(prefix="deck-simulate-") as tmp:
        staging = Path(tmp) / "bundle"
        shutil.copytree(bundle_dir, staging, ignore=shutil.ignore_patterns(HISTORY_DIR))
        before = (staging / deck_name).read_text(encoding="utf-8")
        try:
            if field is not None:
                apply_slide_edit(staging, Path(tmp) / "ui", slide_id=slide_id, field=field, value=value or "", deck_name=deck_name)
            else:
                apply_deck_op(staging, Path(tmp) / "ui", op=op or "", slide_id=slide_id, target_order=target_order, deck_name=deck_name)
        except Exception as exc:
            message = str(exc)
            return {
                "would_pass": False,
                "gate_codes": sorted(set(_re.findall(r"[A-Z][A-Z0-9_]{3,}", message))),
                "error": message,
                "diff": "",
            }
        after = (staging / deck_name).read_text(encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=f"{deck_name}@current", tofile=f"{deck_name}@simulated",
            )
        )
        return {"would_pass": True, "gate_codes": [], "error": None, "diff": diff}


def apply_slide_edit(
    bundle_dir: Path,
    output_dir: Path,
    *,
    slide_id: str,
    field: str,
    value: str,
    deck_name: str = "deck.public.yaml",
    expected_revision: int | None = None,
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
    elif base_field == "element":
        op_or_id, _, sub = index_part.partition(":")
        elements = list(slide.elements)
        from .models import FreeformElement

        if op_or_id == "add" and sub == "text":
            new_id = f"text-{len(elements) + 1}"
            existing_ids = {e.id for e in elements}
            counter = 2
            while new_id in existing_ids:
                new_id = f"text-{len(elements) + counter}"
                counter += 1
            elements.append(
                FreeformElement(id=new_id, type="text", x=0.3, y=0.4, w=0.4, h=0.15, text=value or "New text")
            )
        elif op_or_id == "del":
            elements = [e for e in elements if e.id != sub]
            if len(elements) == len(slide.elements):
                raise ValueError(f"no element '{sub}' on slide '{slide_id}'")
        else:
            target = next((e for e in elements if e.id == op_or_id), None)
            if target is None:
                raise ValueError(f"no element '{op_or_id}' on slide '{slide_id}'")
            if sub == "frame":
                parts = [float(part) for part in value.split(",")]
                if len(parts) != 4:
                    raise ValueError("element frame value must be 'x,y,w,h' fractions")
                updated = target.model_copy(update={"x": parts[0], "y": parts[1], "w": parts[2], "h": parts[3]})
            elif sub == "text":
                updated = target.model_copy(update={"text": value})
            elif sub == "size":
                updated = target.model_copy(update={"size_pt": float(value)})
            elif sub == "bold":
                updated = target.model_copy(update={"bold": value == "true"})
            elif sub == "align":
                updated = target.model_copy(update={"align": value})
            elif sub == "entrance":
                updated = target.model_copy(update={"entrance": value})
            elif sub == "entrance-delay":
                updated = target.model_copy(update={"entrance_delay_ms": int(float(value))})
            else:
                raise ValueError(f"unknown element field '{sub}'; use frame|text|size|bold|align|entrance|entrance-delay")
            elements = [updated if e.id == target.id else e for e in elements]
        updated_slide = slide.model_copy(update={"elements": elements})
    elif base_field == "visual" and index_part == "position":
        updated_slide = slide.model_copy(
            update={"visual": slide.visual.model_copy(update={"position": value})}
        )
    elif base_field == "layout" and value == "freeform" and not slide.elements:
        from .models import FreeformElement

        synthesized = [
            FreeformElement(id="title", type="text", x=0.06, y=0.07, w=0.88, h=0.12, text=slide.title, size_pt=34, bold=True),
            FreeformElement(id="message", type="text", x=0.06, y=0.2, w=0.62, h=0.14, text=slide.message, size_pt=20, color="#9be6f0"),
        ]
        for i, line in enumerate(slide.body[:5]):
            synthesized.append(
                FreeformElement(id=f"bullet-{i + 1}", type="text", x=0.06, y=0.38 + i * 0.1, w=0.5, h=0.09, text=line, size_pt=16)
            )
        if slide.visual.asset_id:
            synthesized.append(
                FreeformElement(id="visual", type="asset", x=0.6, y=0.36, w=0.34, h=0.5, asset_id=slide.visual.asset_id)
            )
        updated_slide = slide.model_copy(update={"layout": value, "elements": synthesized})
    elif base_field == "layout" and value != "freeform" and slide.elements:
        # Leaving freeform: stale elements are invisible in typed renderers but
        # would still count as "visible" in validation — a hidden-qualifier hole
        # (WebGPT review P0-2). Clear them so validation matches what renders.
        updated_slide = slide.model_copy(update={"layout": value, "elements": []})
    elif base_field == "transition_duration":
        updated_slide = slide.model_copy(update={"transition_duration_ms": int(float(value))})
    elif base_field == "hidden":
        updated_slide = slide.model_copy(update={"hidden": value == "true"})
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
    logger.info("slide edit applied: {} {} (rev {}); deck re-emitted", slide_id, field, revision)

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


DECK_OPS = {"add_after", "duplicate", "delete", "move_left", "move_right", "move_to"}


def apply_deck_op(
    bundle_dir: Path,
    output_dir: Path,
    *,
    op: str,
    slide_id: str,
    target_order: int | None = None,
    deck_name: str = "deck.public.yaml",
    expected_revision: int | None = None,
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
    elif op == "move_to":
        if target_order is None or not (1 <= target_order <= len(slides)):
            raise ValueError(f"move_to requires --target-order between 1 and {len(slides)}")
        moved = slides.pop(position)
        slides.insert(target_order - 1, moved)

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
    logger.info("deck op applied: {} on {} (rev {}); {} slides", op, slide_id, revision, len(renumbered))
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
