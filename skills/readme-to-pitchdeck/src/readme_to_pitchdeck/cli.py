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
