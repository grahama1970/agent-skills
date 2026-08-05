from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .io import SkillError, copy_tree_contents, dump_json, load_yaml
from .models import (
    AssetManifest,
    ClaimLedger,
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SourceManifest,
    ValidationReport,
)
from .planner import plan_bundle
from .pptx_builder import build_pptx
from .renderer import render_pptx
from .validation import validate_bundle, validate_pptx

app = typer.Typer(
    no_args_is_help=True,
    help="Compile claim-bound README sources into editable PPTX pitch decks.",
    add_completion=False,
)


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _emit(model, *, json_output: bool = False) -> None:
    payload = model.model_dump(mode="json", exclude_none=True, by_alias=True)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    readiness = payload.get("readiness") or payload.get("overall_readiness") or "PASS"
    typer.echo(f"{payload.get('operation', 'result')}: {readiness}")
    for key, value in payload.get("outputs", {}).items():
        typer.echo(f"  {key}: {value}")
    for gap in payload.get("gaps", []):
        typer.echo(f"  gap: {gap}")


def _abort(exc: Exception) -> None:
    typer.echo(f"ERROR: {exc}", err=True)
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Print the skill version."""
    typer.echo(__version__)


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    """Check Python dependencies and optional Linux render tools without prompting."""
    modules = {
        "typer": "typer",
        "pydantic": "pydantic",
        "yaml": "yaml",
        "pptx": "pptx",
        "PIL": "PIL",
    }
    dependency_status = {
        label: importlib.util.find_spec(module) is not None for label, module in modules.items()
    }
    binaries = {
        "uv": shutil.which("uv"),
        "libreoffice": shutil.which("libreoffice") or shutil.which("soffice"),
        "pdftoppm": shutil.which("pdftoppm"),
        "rsvg-convert": shutil.which("rsvg-convert"),
    }
    optional_modules = {"cairosvg": importlib.util.find_spec("cairosvg") is not None}
    missing_required = [name for name, present in dependency_status.items() if not present]
    gaps = []
    if not binaries["libreoffice"]:
        gaps.append("LibreOffice is unavailable; local PDF/contact-sheet rendering is disabled.")
    if not binaries["pdftoppm"]:
        gaps.append("pdftoppm is unavailable; local slide PNG rendering is disabled.")
    if not binaries["uv"]:
        gaps.append("uv is unavailable; run.sh cannot provision dependencies.")

    readiness = Readiness.NOT_READY if missing_required or not binaries["uv"] else (
        Readiness.USABLE_WITH_GAPS if gaps else Readiness.READY
    )
    receipt = OperationReceipt(
        schema="readme_to_pitchdeck.doctor_receipt.v1",
        operation="doctor",
        readiness=readiness,
        mocked=False,
        live=False,
        inputs={"python": sys.version.split()[0]},
        outputs={
            "dependency_status": json.dumps(dependency_status, sort_keys=True),
            "binary_status": json.dumps(binaries, sort_keys=True),
            "optional_module_status": json.dumps(optional_modules, sort_keys=True),
        },
        counts={
            "required_dependencies": len(dependency_status),
            "missing_required_dependencies": len(missing_required),
        },
        gaps=[*gaps, *[f"Missing required Python module: {name}" for name in missing_required]],
        claims=OperationClaims(
            proves=["The current host was checked for required Python modules and optional render binaries."],
            does_not_prove=["A deck has been planned, built, rendered, or visually approved."],
        ),
        seam_validation=SeamValidation(kind="doctor_receipt"),
    )
    _emit(receipt, json_output=json_output)
    if readiness == Readiness.NOT_READY:
        raise typer.Exit(code=2)


@app.command()
def scaffold(
    profile: Annotated[
        str,
        typer.Option(help="Scaffold profile: generic or sparta-explorer."),
    ] = "generic",
    output_dir: Annotated[Path, typer.Option(help="Destination bundle directory.")] = Path("docs/pitch"),
    force: Annotated[bool, typer.Option(help="Merge and overwrite matching files.")] = False,
) -> None:
    """Copy a source-controlled deck bundle template into a project."""
    try:
        source = (
            _skill_root() / "templates" / "generic"
            if profile == "generic"
            else _skill_root() / "examples" / profile
        )
        if profile not in {"generic", "sparta-explorer"}:
            raise SkillError("Unknown profile. Valid profiles: generic, sparta-explorer")
        copy_tree_contents(source, output_dir, force=force)
        typer.echo(f"scaffold: READY\n  bundle: {output_dir.resolve()}")
    except Exception as exc:
        _abort(exc)


@app.command()
def plan(
    source_manifest: Annotated[Path, typer.Option(help="Path to source_manifest.yaml.")],
    output_dir: Annotated[Path, typer.Option(help="Directory for generated manifests and receipt.")],
    max_slides: Annotated[int, typer.Option(min=6, max=20, help="Maximum public draft slides.")] = 12,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Extract candidate claims/assets and generate a draft public deck manifest."""
    try:
        manifest = load_yaml(source_manifest, SourceManifest)
        receipt = plan_bundle(
            manifest,
            source_manifest_path=source_manifest,
            output_dir=output_dir,
            max_slides=max_slides,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command()
def build(
    deck: Annotated[Path, typer.Option(help="Path to deck manifest YAML.")],
    claim_ledger: Annotated[Path, typer.Option(help="Path to claim ledger YAML.")],
    source_manifest: Annotated[Path, typer.Option(help="Path to source manifest YAML.")],
    asset_manifest: Annotated[Path, typer.Option(help="Path to asset manifest YAML.")],
    output: Annotated[Path, typer.Option(help="Output PPTX path.")],
    draft_watermark: Annotated[
        bool, typer.Option("--draft-watermark", help="Stamp every slide DRAFT — UNAPPROVED CLAIMS.")
    ] = False,
    require_approved_claims: Annotated[
        bool,
        typer.Option(
            "--require-approved-claims/--allow-candidate-claims",
            help="Fail if any referenced claim is not approved.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Validate manifests and compile an editable 16:9 PPTX."""
    try:
        deck_model = load_yaml(deck, DeckManifest)
        claim_model = load_yaml(claim_ledger, ClaimLedger)
        source_model = load_yaml(source_manifest, SourceManifest)
        asset_model = load_yaml(asset_manifest, AssetManifest)
        receipt, _ = build_pptx(
            deck_model,
            claim_model,
            source_model,
            asset_model,
            source_manifest_dir=source_manifest.parent,
            asset_manifest_dir=asset_manifest.parent,
            output_path=output,
            require_approved_claims=require_approved_claims,
            draft_watermark=draft_watermark,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-ui")
def emit_ui(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory for the UI deck bundle.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    require_approved_claims: Annotated[
        bool,
        typer.Option(
            "--require-approved-claims/--allow-candidate-claims",
            help="Fail if any referenced claim is not approved.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Validate the bundle and emit deck.data.json for the React deck renderer in ui/."""
    from .ui_emitter import emit_ui_bundle

    try:
        deck_path = bundle_dir / deck_name
        source_path = bundle_dir / "source_manifest.resolved.yaml"
        if not source_path.exists():
            source_path = bundle_dir / "source_manifest.yaml"
        receipt, _ = emit_ui_bundle(
            load_yaml(deck_path, DeckManifest),
            load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger),
            load_yaml(source_path, SourceManifest),
            load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest),
            source_manifest_dir=source_path.parent,
            asset_manifest_dir=bundle_dir,
            output_dir=output_dir,
            require_approved_claims=require_approved_claims,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-html")
def emit_html_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output: Annotated[Path, typer.Option(help="Output path for the self-contained deck.html.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    max_width: Annotated[int, typer.Option(min=320, max=3840, help="Max inlined image width.")] = 1600,
    quality: Annotated[int, typer.Option(min=30, max=100, help="WebP re-encode quality.")] = 80,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Self-contained interactive HTML deck (assets inlined, no external resources)."""
    from .html_emitter import emit_html

    try:
        source_path = bundle_dir / "source_manifest.resolved.yaml"
        if not source_path.exists():
            source_path = bundle_dir / "source_manifest.yaml"
        receipt = emit_html(
            load_yaml(bundle_dir / deck_name, DeckManifest),
            load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger),
            load_yaml(source_path, SourceManifest),
            load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest),
            source_manifest_dir=source_path.parent,
            asset_manifest_dir=bundle_dir,
            output_path=output,
            max_width=max_width,
            quality=quality,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-md")
def emit_md(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory for deck.md and assets.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """One-way Marp Markdown export; edits belong in the YAML manifests, not deck.md."""
    from .md_emitter import emit_markdown

    try:
        source_path = bundle_dir / "source_manifest.resolved.yaml"
        if not source_path.exists():
            source_path = bundle_dir / "source_manifest.yaml"
        receipt = emit_markdown(
            load_yaml(bundle_dir / deck_name, DeckManifest),
            load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger),
            load_yaml(source_path, SourceManifest),
            load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest),
            source_manifest_dir=source_path.parent,
            asset_manifest_dir=bundle_dir,
            output_dir=output_dir,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="apply-edit")
def apply_edit(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    slide_id: Annotated[str, typer.Option(help="Slide id to edit.")],
    field: Annotated[str, typer.Option(help="title | message | notes | footer | body:<index>")],
    value: Annotated[str, typer.Option(help="New text value.")],
    base_revision: Annotated[int, typer.Option(help="Expected bundle revision (CAS); -1 skips the check.")] = -1,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Edit one slide text field; re-validates the full bundle before writing anything."""
    from .slide_edit import apply_slide_edit

    try:
        receipt = apply_slide_edit(
            bundle_dir, output_dir, slide_id=slide_id, field=field, value=value, deck_name=deck_name,
            expected_revision=None if base_revision < 0 else base_revision,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="undo")
def undo(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Restore the previous committed bundle state (undo of undo = redo), then re-emit the UI bundle."""
    from .revisions import undo_last_write
    from .slide_edit import _load
    from .ui_emitter import emit_ui_bundle

    try:
        revision = undo_last_write(bundle_dir)
        deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
        receipt, _ = emit_ui_bundle(
            deck, ledger, sources, assets,
            source_manifest_dir=source_path.parent, asset_manifest_dir=bundle_dir, output_dir=output_dir,
        )
        receipt.inputs["restored_revision"] = str(revision)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="source-edit")
def source_edit(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    source_file: Annotated[Path, typer.Option(help="File containing the edited deck manifest YAML.")],
    base_revision: Annotated[int, typer.Option(help="Expected bundle revision (CAS); -1 skips the check.")] = -1,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Replace the deck manifest from edited YAML; full validation before writing."""
    from .source_edit import apply_deck_source

    try:
        receipt = apply_deck_source(
            bundle_dir, output_dir, source_yaml=source_file.read_text(encoding="utf-8"), deck_name=deck_name,
            expected_revision=None if base_revision < 0 else base_revision,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="asset-add")
def asset_add(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    slide_id: Annotated[str, typer.Option(help="Slide to attach the asset to.")],
    file: Annotated[Path, typer.Option(help="Image (.png/.jpg/.webp/.svg/.gif) or video (.mp4/.webm) file.")],
    alt: Annotated[str, typer.Option(help="Required alt text for the asset.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Copy a file into the bundle, register it, and bind it as the slide's visual."""
    from .asset_ops import add_asset_to_slide

    try:
        receipt = add_asset_to_slide(
            bundle_dir, output_dir, slide_id=slide_id, file_path=file, alt_text=alt, deck_name=deck_name
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="asset-clear")
def asset_clear(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    slide_id: Annotated[str, typer.Option(help="Slide whose visual should be removed.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Detach a slide's visual (the asset stays registered in the manifest)."""
    from .asset_ops import clear_slide_visual

    try:
        receipt = clear_slide_visual(bundle_dir, output_dir, slide_id=slide_id, deck_name=deck_name)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="bindings-migrate")
def bindings_migrate(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    triage_rest: Annotated[
        str, typer.Option(help="unbound (default, publish stays blocked) or non_claim (human-reviewed fixtures only).")
    ] = "unbound",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Auto-classify content bindings: exact claim text -> claim_quote, qualifier text -> qualifier."""
    import json as _json

    from .bindings_migrate import migrate_bindings

    try:
        counts = migrate_bindings(bundle_dir, deck_name=deck_name, triage_rest=triage_rest)
        typer.echo(_json.dumps(counts) if json_output else f"bindings-migrate: {counts}")
    except Exception as exc:
        _abort(exc)


@app.command(name="deck-op")
def deck_op(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    op: Annotated[str, typer.Option(help="add_after | duplicate | delete | move_left | move_right | move_to")],
    slide_id: Annotated[str, typer.Option(help="Slide id the operation targets.")],
    target_order: Annotated[int, typer.Option(help="Target 1-based position for move_to.")] = 0,
    base_revision: Annotated[int, typer.Option(help="Expected bundle revision (CAS); -1 skips the check.")] = -1,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Slide add/duplicate/delete/reorder; full bundle validation before writing."""
    from .slide_edit import apply_deck_op

    try:
        receipt = apply_deck_op(
            bundle_dir, output_dir, op=op, slide_id=slide_id,
            target_order=target_order or None, deck_name=deck_name,
            expected_revision=None if base_revision < 0 else base_revision,
        )
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-handout")
def emit_handout_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    render_dir: Annotated[Path, typer.Option(help="Directory of rendered slide-N.png images (from `render`).")],
    output: Annotated[Path, typer.Option(help="Output path for the speaker-handout PDF.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Two-slides-per-page A4 speaker handout with wrapped notes (Pillow, server-side)."""
    from .handout_emitter import emit_handout

    try:
        receipt = emit_handout(load_yaml(bundle_dir / deck_name, DeckManifest), render_dir, output)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="memory-sync")
def memory_sync(
    deck_data: Annotated[Path, typer.Option(help="Path to an emitted deck.data.json.")],
    verify_recall: Annotated[
        bool,
        typer.Option("--verify/--no-verify", help="Ask memory to verify storage by immediate recall."),
    ] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Store the emitted deck summary in /memory (ArangoDB) for /memory recall."""
    from .memory_sync import sync_deck_to_memory

    try:
        receipt = sync_deck_to_memory(deck_data, verify=verify_recall)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command(name="visual-sync")
def visual_sync(
    deck_data: Annotated[Path, typer.Option(help="Path to an emitted deck.data.json.")],
    images_dir: Annotated[Path, typer.Option(help="Directory of rendered slide PNGs (from `render`).")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Index slide images into Qdrant (text_mm+image_mm) with memory pointer docs."""
    from .visual_sync import sync_deck_visuals

    try:
        receipt = sync_deck_visuals(deck_data, images_dir)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


@app.command()
def verify(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    pptx: Annotated[Path | None, typer.Option(help="Optional PPTX to structurally verify.")] = None,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    require_approved_claims: Annotated[
        bool,
        typer.Option(
            "--require-approved-claims/--allow-candidate-claims",
            help="Treat candidate claims as an error.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Verify the bundle contract and, optionally, the generated PPTX."""
    try:
        deck_path = bundle_dir / deck_name
        claim_path = bundle_dir / "claim_ledger.yaml"
        source_path = bundle_dir / "source_manifest.resolved.yaml"
        if not source_path.exists():
            source_path = bundle_dir / "source_manifest.yaml"
        asset_path = bundle_dir / "asset_manifest.yaml"

        deck_model = load_yaml(deck_path, DeckManifest)
        claim_model = load_yaml(claim_path, ClaimLedger)
        source_model = load_yaml(source_path, SourceManifest)
        asset_model = load_yaml(asset_path, AssetManifest)
        report = validate_bundle(
            deck_model,
            claim_model,
            source_model,
            asset_model,
            source_manifest_dir=source_path.parent,
            asset_manifest_dir=asset_path.parent,
            require_approved_claims=require_approved_claims,
        )
        pptx_issues = validate_pptx(pptx, len(deck_model.slides)) if pptx else []
        all_issues = [*report.issues, *pptx_issues]
        errors = sum(issue.severity == "error" for issue in all_issues)
        warnings = sum(issue.severity == "warning" for issue in all_issues)
        readiness = (
            Readiness.NOT_READY
            if errors
            else Readiness.USABLE_WITH_GAPS
            if warnings
            else Readiness.READY
        )
        receipt = OperationReceipt(
            schema="readme_to_pitchdeck.verify_receipt.v1",
            operation="verify",
            readiness=readiness,
            mocked=False,
            live=False,
            inputs={
                "bundle_dir": str(bundle_dir.resolve()),
                "deck": str(deck_path.resolve()),
                **({"pptx": str(pptx.resolve())} if pptx else {}),
            },
            outputs={"validation_report": str((bundle_dir / "validation_report.json").resolve())},
            counts={
                "slides": len(deck_model.slides),
                "claims": len(claim_model.claims),
                "assets": len(asset_model.assets),
                "errors": errors,
                "warnings": warnings,
            },
            gaps=[f"{issue.code}: {issue.message}" for issue in all_issues if issue.severity != "info"],
            claims=OperationClaims(
                proves=[
                    "Typed bundle manifests passed or failed according to the emitted validation issues.",
                    *(["The PPTX was reopened and structurally checked."] if pptx else []),
                ],
                does_not_prove=[
                    "The deck is factually or visually approved.",
                    "Source claims match the current codebase or live runtime.",
                ],
            ),
            seam_validation=SeamValidation(kind="verify_receipt"),
        )
        validation_report = ValidationReport(
            readiness=readiness,
            errors=errors,
            warnings=warnings,
            issues=all_issues,
        )
        dump_json(validation_report, bundle_dir / "validation_report.json")
        dump_json(receipt, bundle_dir / "verify_receipt.json")
        _emit(receipt, json_output=json_output)
        if errors:
            raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command()
def render(
    pptx: Annotated[Path, typer.Option(help="PPTX to render.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory for PDF, PNGs, and contact sheet.")],
    dpi: Annotated[int, typer.Option(min=72, max=300, help="PNG render DPI.")] = 120,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Render a PPTX to PDF, per-slide PNGs, and a contact sheet on Linux."""
    try:
        receipt = render_pptx(pptx, output_dir, dpi=dpi)
        _emit(receipt, json_output=json_output)
    except Exception as exc:
        _abort(exc)


if __name__ == "__main__":
    app()
