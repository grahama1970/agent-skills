from __future__ import annotations

import importlib.util
import json
import os
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


def _asset_sources(bundle_dir: Path) -> dict[str, Path]:
    """Every present bundle asset becomes a digested manifest input (#1384):
    deleting or altering one generated art file fails the chain closed."""
    import os

    import yaml as yaml_mod

    manifest_path = bundle_dir / "asset_manifest.yaml"
    out: dict[str, Path] = {}
    try:
        payload = yaml_mod.safe_load(manifest_path.read_text())
    except OSError:
        return out
    for asset in (payload or {}).get("assets", []):
        local = os.path.expandvars(str(asset.get("local_path", "")))
        if not local:
            continue
        path = Path(local) if Path(local).is_absolute() else bundle_dir / local
        out[f"asset:{asset.get('id')}"] = path
    return out


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
        schema="pitchdeck.doctor_receipt.v1",
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


@app.command(name="record-note")
def record_note_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    slide_id: Annotated[str, typer.Option(help="Slide whose speaker notes receive the narration.")],
    timeout_seconds: Annotated[int, typer.Option(help="Max recording window.")] = 120,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
) -> None:
    """Record narration (RealtimeSTT mic capture, faster-whisper local transcription) into slide notes."""
    import json as json_mod

    from .transcribe import record_note

    try:
        result = record_note(bundle_dir, output_dir, slide_id=slide_id, deck_name=deck_name, timeout_seconds=timeout_seconds)
        typer.echo(json_mod.dumps(result, indent=1))
        raise typer.Exit(0 if result["status"] == "PASS" else 6)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="compile-document")
def compile_document_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output: Annotated[Path, typer.Option(help="Path for the emitted deck.document.json.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
) -> None:
    """Compile the bundle into the canonical whole-deck document (pitchdeck.deck_document.v1)."""
    import json as json_mod

    from .document import compile_document

    try:
        document = compile_document(bundle_dir, deck_name=deck_name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS",
            "schema": "pitchdeck.deck_document.v1",
            "output": str(output.resolve()),
            "slides": len(document.slides),
            "elements": sum(len(s.elements) for s in document.slides),
            "revision": document.revision,
        }, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="render-document")
def render_document_cmd(
    document: Annotated[Path, typer.Option(help="Path to a deck.document.json (pitchdeck.deck_document.v1).")],
    output: Annotated[Path, typer.Option(help="Output HTML path (self-contained).")],
    asset_base: Annotated[Path, typer.Option(help="Base dir for relative asset paths (usually the bundle dir).")],
    theme_template: Annotated[Path | None, typer.Option(help="pitchdeck.theme_template.v1 JSON; default house-light.")] = None,
    preview: Annotated[bool, typer.Option("--preview", help="Allow rendering a preview-stamped document (HTML only, for review).")] = False,
) -> None:
    """Render a canonical deck document to house-native self-contained HTML."""
    import json as json_mod

    from .document import DeckDocument
    from .document_html import render_document_html

    try:
        doc = DeckDocument.model_validate(json_mod.loads(document.read_text(encoding="utf-8")))
        html_text = render_document_html(doc, asset_base=asset_base, theme_template=theme_template, preview=preview)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html_text, encoding="utf-8")
        typer.echo(json_mod.dumps({"status": "PASS", "output": str(output.resolve()), "slides": len(doc.slides)}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="design-lint")
def design_lint_cmd(
    document: Annotated[Path, typer.Option(help="deck.document.json to lint.")],
) -> None:
    """Deterministic DESIGN_* lint over a canonical document (exit 1 on findings)."""
    import json as json_mod

    from .design_lint import lint_file

    try:
        findings, code = lint_file(document)
        typer.echo(json_mod.dumps({"status": "PASS" if code == 0 else "FINDINGS", "findings": findings}, indent=1))
        raise typer.Exit(code)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="compile-voice-profile")
def compile_voice_profile_cmd(
    corpus: Annotated[Path, typer.Option(help="best-practices-slide-design skill dir (contains references/exemplars.yaml).")],
    output: Annotated[Path | None, typer.Option(help="Write voice_profile.v1 JSON here (stdout otherwise).")] = None,
) -> None:
    """Compile the author headline corpus into content-addressed voice_profile.v1 (#1311)."""
    import json as json_mod

    from .voice_profile import compile_voice_profile

    try:
        profile = compile_voice_profile(corpus)
        payload = profile.model_dump(by_alias=True, mode="json")
        payload["content_sha256"] = profile.content_sha256()
        rendered = json_mod.dumps(payload, indent=1, sort_keys=True)
        if output:
            output.write_text(rendered, encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS",
            "exemplars": len(profile.exemplars),
            "coverage_gaps": profile.coverage_gaps,
            "content_sha256": payload["content_sha256"],
            "output": str(output) if output else None,
        }, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="measure-house-spec")
def measure_house_spec_cmd(
    decks: Annotated[Path, typer.Option(help="Directory of the author's real .pptx decks.")],
    output: Annotated[Path | None, typer.Option(help="Write house_spec.v1 JSON here.")] = None,
) -> None:
    """Measure geometry, type scale, and colors from a real deck corpus (#1311)."""
    import json as json_mod

    from .house_spec import measure_house_spec

    try:
        spec = measure_house_spec(decks)
        payload = spec.model_dump(by_alias=True, mode="json")
        if output:
            output.write_text(json_mod.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        typer.echo(json_mod.dumps({"status": "PASS", **payload}, indent=1, sort_keys=True))
    except Exception as exc:
        _abort(exc)


@app.command(name="house-conformance")
def house_conformance_cmd(
    pptx: Annotated[Path, typer.Option(help="Emitted .pptx to measure against corpus invariants.")],
) -> None:
    """Deterministic house-style conformance gate (exit 1 on findings, #1311)."""
    import json as json_mod

    from .house_conformance import check_conformance

    try:
        findings = [f.model_dump(mode="json") for f in check_conformance(pptx)]
        typer.echo(json_mod.dumps(
            {"status": "PASS" if not findings else "FINDINGS", "findings": findings}, indent=1))
        raise typer.Exit(0 if not findings else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="index-house-slides")
def index_house_slides_cmd(
    decks: Annotated[Path, typer.Option(help="Directory of real .pptx decks.")],
    renders: Annotated[Path, typer.Option(help="Directory of rendered slide PNGs.")],
) -> None:
    """Index real slides into Qdrant for nearest-layout retrieval (composes /embedding)."""
    import json as json_mod

    from .layout_retrieval import index_house_slides

    try:
        typer.echo(json_mod.dumps({"status": "PASS", **index_house_slides(decks, renders)}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="find-layout")
def find_layout_cmd(
    query: Annotated[str, typer.Option(help="What the slide needs to do.")],
    limit: Annotated[int, typer.Option(help="Max hits.")] = 3,
) -> None:
    """Retrieve the author's real slides closest to a described need (#1315)."""
    import json as json_mod

    from .layout_retrieval import find_nearest_layout

    try:
        hits = find_nearest_layout(query, limit=limit)
        typer.echo(json_mod.dumps({"status": "PASS", "hits": [
            {k: v for k, v in h.items() if k != "blocks"} for h in hits]}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="variations")
def variations_cmd(
    output_dir: Annotated[Path, typer.Option(help="Where candidates, contact sheet, and receipt go.")],
    prompt: Annotated[str | None, typer.Option(help="Describe the visual you want.")] = None,
    image: Annotated[Path | None, typer.Option(help="Existing image to reinterpret.")] = None,
    table: Annotated[Path | None, typer.Option(help="JSON data file to chart.")] = None,
    count: Annotated[int, typer.Option(min=1, max=8, help="How many candidates.")] = 4,
    title: Annotated[str, typer.Option(help="Chart title (table lane).")] = "Candidate",
    execute: Annotated[bool, typer.Option("--execute", help="Actually produce candidates (default plans only).")] = False,
) -> None:
    """N candidate visuals from a prompt, an image, or a table — one command."""
    import json as json_mod

    from .variations import generate_variations

    try:
        receipt = generate_variations(
            output_dir=output_dir, prompt=prompt, image=image, table=table,
            count=count, title=title, execute=execute,
        )
        typer.echo(json_mod.dumps(receipt, indent=1))
        if receipt.get("status") == "NEEDS_ATTENTION":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="verify-publish")
def verify_publish_cmd(
    pptx: Annotated[Path, typer.Option(help="The FINAL, possibly human-edited .pptx to be delivered.")],
    ledger: Annotated[Path, typer.Option(help="Claim ledger (yaml or json).")],
    approvals: Annotated[Path | None, typer.Option(help="pitchdeck.publish_approvals.v1 JSON: approved renderings, chrome text, disclaimer, stale-owner markers.")] = None,
    template_contract: Annotated[Path | None, typer.Option(help="pitchdeck.template_contract.v1 JSON to check the deck still derives from the approved template.")] = None,
    document: Annotated[Path | None, typer.Option(help="The approved deck.document.json: supplies compiler-emitted assertion atoms so provenance is never hand-enumerated.")] = None,
    build_manifest_path: Annotated[Path | None, typer.Option("--build-manifest", help="Build manifest: the document/pptx must be the exact artifacts the chain recorded.")] = None,
    bundle_dir: Annotated[Path | None, typer.Option(help="Bundle dir (required with --build-manifest to re-digest inputs).")] = None,
    out: Annotated[Path | None, typer.Option(help="Write the publish receipt here.")] = None,
) -> None:
    """Re-prove the DELIVERED pptx: every visible string claim-bound (exit 1 on findings)."""
    import json as json_mod

    from .publish_verify import PublishApprovals, TemplateContract, load_claim_texts, load_claims_by_id, verify_publish

    try:
        approval_model = (
            PublishApprovals.model_validate(json_mod.loads(approvals.read_text(encoding="utf-8")))
            if approvals else PublishApprovals()
        )
        contract_model = (
            TemplateContract.model_validate(json_mod.loads(template_contract.read_text(encoding="utf-8")))
            if template_contract else None
        )
        doc_model = None
        if document is not None:
            from .document import DeckDocument

            doc_model = DeckDocument.model_validate(json_mod.loads(document.read_text(encoding="utf-8")))
        manifest_model = None
        manifest_sources = None
        if build_manifest_path is not None:
            from .build_manifest import BuildManifest

            manifest_model = BuildManifest.model_validate(json_mod.loads(build_manifest_path.read_text(encoding="utf-8")))
            base = bundle_dir or ledger.parent
            manifest_sources = {
                "claim_ledger": base / "claim_ledger.yaml",
                "source_manifest": base / "source_manifest.yaml",
                "asset_manifest": base / "asset_manifest.yaml",
                "canonical_document": document,
            }
            recorded = {i.role: i.path for i in manifest_model.inputs}
            for role in ("approved_outline", "template", "icon_library"):
                if recorded.get(role):
                    manifest_sources[role] = Path(recorded[role])
            for role, path in recorded.items():
                if role.startswith("asset:") and path:
                    manifest_sources[role] = Path(path)
        receipt = verify_publish(
            pptx,
            claim_texts=load_claim_texts(ledger),
            claims_by_id=load_claims_by_id(ledger),
            approvals=approval_model,
            template_contract=contract_model,
            document=doc_model,
            manifest=manifest_model,
            manifest_sources=manifest_sources,
            repo_root=_skill_root().parents[1],
        )
        payload = receipt.model_dump(by_alias=True, mode="json")
        if out:
            out.write_text(json_mod.dumps(payload, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps(payload, indent=1))
        raise typer.Exit(0 if receipt.status == "PASS" else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-document-ui")
def emit_document_ui_cmd(
    document: Annotated[Path, typer.Option(help="deck.document.json (pitchdeck.deck_document.v1).")],
    output_dir: Annotated[Path, typer.Option(help="Directory to write deck.data.json (+ copied assets).")],
    asset_base: Annotated[Path, typer.Option(help="Base dir for relative asset paths.")],
) -> None:
    """Project the canonical document into the React deck payload (one source, three targets)."""
    import json as json_mod
    import shutil as shutil_mod

    from .document import DeckDocument
    from .document_ui import project_document_to_ui

    try:
        doc = DeckDocument.model_validate(json_mod.loads(document.read_text(encoding="utf-8")))
        payload = project_document_to_ui(doc)
        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        copied = 0
        from .io import expand_path

        missing_assets = []
        for asset in doc.assets:
            raw = getattr(asset, "local_path", None)
            if not raw:
                continue
            # expand_path resolves RELATIVE paths against the CWD (that bug
            # silently dropped every bundle-relative asset, #1388) — decide
            # relativity on the raw string, then join against the bundle.
            expanded = os.path.expandvars(str(raw))
            source = Path(expanded) if Path(expanded).is_absolute() else asset_base / expanded
            if source.is_file():
                shutil_mod.copy(source, assets_dir / source.name)
                copied += 1
            else:
                missing_assets.append(f"{asset.id}: {source}")
        if missing_assets:
            raise SkillError("asset copy failed closed — referenced assets not found: "
                             + "; ".join(missing_assets[:5]))
        payload["assets_index"] = [
            {"id": a.id, "kind": getattr(a, "kind", ""), "alt_text": getattr(a, "alt_text", ""),
             "file": f"assets/{Path(os.path.expandvars(str(getattr(a, 'local_path', '') or ''))).name}"}
            for a in doc.assets
        ]
        (output_dir / "deck.data.json").write_text(json_mod.dumps(payload, indent=1), encoding="utf-8")
        (output_dir / "deck.document.json").write_text(document.read_text(encoding="utf-8"), encoding="utf-8")
        (output_dir / "emit_ui_receipt.json").write_text(json_mod.dumps({
            "schema": "pitchdeck.emit_ui_receipt.v1",
            "operation": "emit-document-ui",
            "outputs": {
                "deck_data": str((output_dir / "deck.data.json").resolve()),
                "document_path": str(document.resolve()),
                "asset_base": str(asset_base.resolve()),
                "output_dir": str(output_dir.resolve()),
            },
        }, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS" if payload["validation_readiness"] == "READY" else "USABLE_WITH_GAPS",
            "slides": len(payload["slides"]),
            "elements": sum(len(s["elements"]) for s in payload["slides"]),
            "assets_copied": copied,
            "gaps": payload["validation_gaps"],
            "output": str(output_dir / "deck.data.json"),
        }, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="build-manifest")
def build_manifest_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Bundle with claim_ledger/source_manifest/asset_manifest.")],
    document: Annotated[Path, typer.Option(help="The canonical deck.document.json this build emitted.")],
    outline: Annotated[Path, typer.Option(help="The APPROVED narrative outline.")],
    output: Annotated[Path, typer.Option(help="Where to write the build manifest.")],
    pptx: Annotated[Path | None, typer.Option(help="Delivered pptx to bind into the chain.")] = None,
    house_template: Annotated[Path | None, typer.Option(help="House template the deck inherits from.")] = None,
    verify: Annotated[bool, typer.Option("--verify", help="Re-compute every digest and fail on drift.")] = False,
    allow_dirty: Annotated[bool, typer.Option("--allow-dirty", help="Permit an uncommitted compiler tree.")] = False,
) -> None:
    """Bind every input digest to the delivered artifact (#1332)."""
    import json as json_mod

    from .build_manifest import BuildManifest, build_manifest, verify_manifest

    try:
        repo_root = _skill_root().parents[1]
        sources = {
            "claim_ledger": bundle_dir / "claim_ledger.yaml",
            "source_manifest": bundle_dir / "source_manifest.yaml",
            "asset_manifest": bundle_dir / "asset_manifest.yaml",
            "approved_outline": outline,
            "canonical_document": document,
            "icon_library": _skill_root() / "src" / "pitchdeck" / "design" / "icons" / "manifest.json",
        }
        if house_template is not None:
            sources["template"] = house_template
        sources.update(_asset_sources(bundle_dir))
        if verify:
            existing = BuildManifest.model_validate(json_mod.loads(output.read_text(encoding="utf-8")))
            findings = verify_manifest(existing, repo_root=repo_root, sources=sources,
                                       delivered_pptx=pptx, allow_dirty=allow_dirty)
            typer.echo(json_mod.dumps({
                "status": "PASS" if not findings else "DRIFT",
                "chain_digest": existing.content_digest(),
                "findings": [f.model_dump(mode="json") for f in findings],
            }, indent=1))
            raise typer.Exit(0 if not findings else 1)
        manifest = build_manifest(repo_root=repo_root, sources=sources, delivered_pptx=pptx,
                                  renderers={"libreoffice": shutil.which("soffice") or "absent"})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_mod.dumps(manifest.model_dump(by_alias=True, mode="json"), indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS",
            "chain_digest": manifest.content_digest(),
            "inputs": len(manifest.inputs),
            "reproducible": manifest.compiler.reproducible,
            "output": str(output),
        }, indent=1))
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="house-similarity")
def house_similarity_cmd(
    slides_dir: Annotated[Path, typer.Option(help="Directory of rendered slide PNGs to score.")],
    calibration: Annotated[Path, typer.Option(help="Frozen house_gate_calibration.v1 artifact — the ONLY source of thresholds and the reference histogram (#1379).")] = Path("fixtures/house-gate/calibration.v1.json"),
    render_receipt: Annotated[Path | None, typer.Option(help="Render receipt binding the scored PNGs to the delivered pptx (pptx sha, dpi, per-page hashes). Without it the verdict is UNBOUND.")] = None,
    pptx: Annotated[Path | None, typer.Option(help="The delivered pptx the receipt must describe.")] = None,
    document: Annotated[Path | None, typer.Option(help="deck.document.json — declares the expected visible slide count.")] = None,
    glob: Annotated[str, typer.Option(help="Filename pattern.")] = "*.png",
) -> None:
    """Gate each rendered slide on house style: text-invariant pixel metrics
    (ink coverage + house-palette share, calibrated on the real corpus) plus a
    nearest-real-page embedding floor. The embedding channel alone is text-
    dominated (measured: same-words pages 0.952, same-archetype-different-words
    0.25), so it serves as an anomaly floor, never the style verdict."""
    import base64
    import json as json_mod

    import httpx

    from .house_gate_calibration import HouseGateCalibration, verify_render_receipt
    from .style_metrics import measure
    from .visual_sync import EMBED_URL, HTTP_TIMEOUT, QDRANT_URL

    try:
        cal_payload = json_mod.loads(calibration.read_text())
        recorded_digest = cal_payload.pop("content_digest", None)
        cal = HouseGateCalibration.model_validate(cal_payload)
        if recorded_digest != cal.content_digest():
            raise ValueError(f"calibration artifact digest mismatch: recorded {str(recorded_digest)[:12]}… "
                             f"vs recomputed {cal.content_digest()[:12]}… — the artifact was edited by hand")
        threshold = cal.thresholds.embedding_anomaly_floor
        ink_floor = cal.thresholds.ink_floor
        palette_floor = cal.thresholds.palette_floor
        corpus_hist = cal.cluster_histograms or cal.corpus_palette_histogram
        binding_findings = []
        if render_receipt is not None:
            expected_pages = None
            if document is not None:
                doc = json_mod.loads(document.read_text())
                expected_pages = len([sl for sl in doc["slides"] if not sl.get("hidden")])
            binding_findings = [f.model_dump() for f in verify_render_receipt(
                json_mod.loads(render_receipt.read_text()), renders_dir=slides_dir,
                pptx_path=pptx, expected_pages=expected_pages, calibration=cal)]
        rows = []
        failed = 0
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            for image in sorted(slides_dir.glob(glob)):
                encoded = base64.b64encode(image.read_bytes()).decode()
                vector = client.post(EMBED_URL, json={"image": f"data:image/png;base64,{encoded}"})
                vector.raise_for_status()
                hits = client.post(
                    f"{QDRANT_URL}/collections/pitchdeck_house_slides_v1/points/search",
                    json={"vector": {"name": "image_mm", "vector": vector.json()["embedding"]},
                          "limit": 1, "with_payload": ["deck", "slide_index", "title", "record_path"]})
                hits.raise_for_status()
                hit = hits.json()["result"][0]
                score = hit["score"]
                style = measure(image, corpus_hist=corpus_hist)
                reasons = []
                if score < threshold:
                    reasons.append(f"embedding {score:.3f} < {threshold}")
                if style.ink_fraction < ink_floor:
                    reasons.append(f"ink {style.ink_fraction:.3f} < {ink_floor} (canvas too empty)")
                if style.palette_similarity < palette_floor:
                    reasons.append(f"palette {style.palette_similarity:.3f} < {palette_floor} (off-house color distribution)")
                if reasons:
                    failed += 1
                rows.append({
                    "slide": image.name, "score": round(score, 3),
                    "ink": style.ink_fraction, "palette": style.palette_similarity,
                    "verdict": "PASS" if not reasons else "FAIL", "reasons": reasons,
                    "nearest": f"{hit['payload']['deck']}#{hit['payload']['slide_index']}",
                    "nearest_title": hit["payload"].get("title"),
                    "diff_target": hit["payload"].get("record_path"),
                })
        import statistics as stats_mod
        deck_median = round(stats_mod.median(r["score"] for r in rows), 3) if rows else 0.0
        ok = bool(rows) and failed == 0 and not binding_findings
        typer.echo(json_mod.dumps({
            "status": "HOUSE_NON_ANOMALOUS" if ok else "FAIL",  # anomaly filter, not a positive looks-like-Graham classifier
            "calibration_digest": recorded_digest,
            "binding": ("BOUND" if (render_receipt is not None and not binding_findings)
                         else ("VIOLATED" if binding_findings else "UNBOUND")),
            "binding_findings": binding_findings,
            "threshold": threshold, "ink_floor": ink_floor, "palette_floor": palette_floor,
            "deck_median": deck_median, "failed": failed, "slides": rows,
        }, indent=1))
        if not rows:
            typer.echo("no rendered slides matched — a gate over nothing proves nothing", err=True)
        raise typer.Exit(0 if ok else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="house-structure")
def house_structure_cmd(
    pptx: Annotated[Path, typer.Option(help="Delivered .pptx.")],
    document: Annotated[Path, typer.Option(help="Canonical deck.document.json (role source).")],
) -> None:
    """Archetype-conditioned structural + typography contracts on the delivered file (#1381)."""
    import json as json_mod

    from .house_structure import check_structure

    try:
        findings = check_structure(pptx, document)
        typer.echo(json_mod.dumps({
            "status": "PASS" if not findings else "FINDINGS",
            "findings": [f.model_dump() for f in findings],
        }, indent=1))
        raise typer.Exit(0 if not findings else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="house-deck-gate")
def house_deck_gate_cmd(
    pptx: Annotated[Path, typer.Option(help="Delivered .pptx.")],
    calibration: Annotated[Path, typer.Option(help="deck_gate_calibration.v1 (leave-one-deck-out).")] = Path("fixtures/house-gate/deck-calibration.v1.json"),
    records_dir: Annotated[Path, typer.Option(help="Corpus layout_signature records.")] = Path("/mnt/storage12tb/skills/pitchdeck/outputs/house-slides/records"),
    calibrate_only: Annotated[bool, typer.Option("--calibrate", help="(Re)build the calibration artifact and exit.")] = False,
) -> None:
    """Deck-level structural positive bar, LODO-calibrated (#1382). PASS here is
    DECK_STRUCTURAL_MATCH — positive evidence, distinct from the anomaly floors."""
    import json as json_mod

    from .house_deck_gate import DeckGateCalibration, calibrate, score_deck

    try:
        if calibrate_only:
            cal = calibrate(records_dir)
            payload = json_mod.loads(cal.model_dump_json(by_alias=True))
            payload["content_digest"] = cal.content_digest()
            calibration.parent.mkdir(parents=True, exist_ok=True)
            calibration.write_text(json_mod.dumps(payload, indent=1))
            typer.echo(json_mod.dumps({"status": "PASS", **payload}, indent=1))
            raise typer.Exit(0)
        payload = json_mod.loads(calibration.read_text())
        digest = payload.pop("content_digest", None)
        cal = DeckGateCalibration.model_validate(payload)
        if digest != cal.content_digest():
            raise ValueError("deck-gate calibration digest mismatch — the artifact was edited by hand")
        result = score_deck(pptx, records_dir)
        ok = result["median"] <= cal.median_bar and result["p90"] <= cal.p90_bar
        typer.echo(json_mod.dumps({
            "status": "DECK_STRUCTURAL_MATCH" if ok else "FAIL",
            "median": result["median"], "median_bar": cal.median_bar,
            "p90": result["p90"], "p90_bar": cal.p90_bar,
            "slides": result["slides"], "per_slide": result["per_slide"],
            "fold_medians": cal.fold_medians,
        }, indent=1))
        raise typer.Exit(0 if ok else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="asset-alternates")
def asset_alternates_cmd(
    bundle_dir: Annotated[Path, typer.Option(help="Bundle containing asset_manifest.yaml.")],
    asset_id: Annotated[str, typer.Option(help="Asset to generate alternates for.")],
    count: Annotated[int, typer.Option("-n", "--count", help="How many alternates.")] = 4,
    prompt: Annotated[str | None, typer.Option(help="Extra guidance appended to the asset's generation brief.")] = None,
    example: Annotated[list[Path], typer.Option(help="Example image(s) whose look to describe into the prompt (their alt text / brief is quoted; backends here are text-to-image).")] = [],
    backend: Annotated[str, typer.Option(help="Art backend: claude-svg (Claude authors an SVG scene — on-palette by construction, editable source kept beside the PNG), flux (HF), google (nano banana; needs a valid GEMINI_API_KEY), fal, ollama.")] = "claude-svg",
    select: Annotated[Path | None, typer.Option(help="Adopt this previously generated candidate into the bundle (replaces the asset file; the build-manifest digest chain records the change).")] = None,
    figure: Annotated[str | None, typer.Option(help="Instead of AI art, route to /create-figure with this spec, e.g. 'workflow:Ask,Retrieve,Answer' or 'force-graph:<json>'.")] = None,
    model: Annotated[str | None, typer.Option(help="Model override for the backend (e.g. fal-ai/nano-banana for --backend fal).")] = None,
    reference: Annotated[Path | None, typer.Option(help="Reference image SHOWN to the generator (image-to-image). Defaults to the asset's current file. NO EXCEPTIONS (operator rule 2026-08-12): raster generation without a reference is refused.")] = None,
) -> None:
    """Generate N alternates for a bundle image asset (nano banana / gemini,
    flux) or a /create-figure chart, then adopt one with --select. Every
    candidate lands in outputs/asset-alternates/<asset-id>/ with a receipt;
    adoption rewrites the asset file so the digest chain (#1384) sees it."""
    import datetime as dt
    import json as json_mod
    import os
    import subprocess

    import yaml as yaml_mod

    try:
        manifest_path = bundle_dir / "asset_manifest.yaml"
        payload = yaml_mod.safe_load(manifest_path.read_text())
        asset = next((a for a in payload.get("assets", []) if a.get("id") == asset_id), None)
        if asset is None:
            raise ValueError(f"asset '{asset_id}' not found in {manifest_path}")
        local = os.path.expandvars(str(asset.get("local_path")))
        target = Path(local) if Path(local).is_absolute() else bundle_dir / local

        if select is not None:
            if not select.is_file():
                raise ValueError(f"candidate not found: {select}")
            target.write_bytes(select.read_bytes())
            asset["generation_brief"] = (str(asset.get("generation_brief", "")).split(" [adopted")[0]
                + f" [adopted alternate {select.name} on {dt.date.today().isoformat()}]")
            manifest_path.write_text(yaml_mod.safe_dump(payload, sort_keys=False))
            typer.echo(json_mod.dumps({"status": "ADOPTED", "asset": asset_id,
                                       "file": str(target),
                                       "note": "re-run build-manifest + the eval; the digest chain records this change"}))
            raise typer.Exit(0)

        out_dir = Path("/mnt/storage12tb/skills/pitchdeck/outputs/asset-alternates") / asset_id
        out_dir.mkdir(parents=True, exist_ok=True)
        if select is None and figure is None:
            ref = reference if reference is not None else (target if target.is_file() else None)
            if ref is None or not Path(ref).is_file():
                raise ValueError("NO REFERENCE IMAGE: every generation must be shown its design-source "
                                 "reference (the README figure or the asset's current file). Pass --reference.")
            if backend == "claude-svg":
                pass  # reference is injected into the claude prompt below
            elif backend not in {"google", "fal"}:
                raise ValueError(f"backend '{backend}' cannot consume a reference image; use google, fal, or claude-svg")
        else:
            ref = None
        # With a reference image the reference IS the style authority — a
        # text style-suffix would fight it (observed: cartoon drift, 2026-08-12).
        house = ("Match the attached reference image's visual style, palette, glow treatment, and "
                 "subject register EXACTLY — the output must read as a sibling panel of the reference. "
                 "Wide 16:9 composition, no text or letters.")
        base = str(asset.get("generation_brief") or asset.get("alt_text") or asset_id)
        example_notes = " ".join(f"In the spirit of: {e.stem.replace('-', ' ')}." for e in example)
        full = f"{asset.get('alt_text', '')}. {prompt or base}. {example_notes} {house}"
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
        results = []
        for index in range(count):
            out = out_dir / f"{stamp}-alt{index + 1}.png"
            if backend == "claude-svg" and not figure:
                # The Claude lane is /ask -> Tau DAG -> scillm claude-fable-low
                # (#1387): receipted, full-strength, never `claude -p` (degraded)
                # and never webclaude (a chat tab is not Claude).
                svg_path = out.with_suffix(".svg")
                ask = (f"The attached reference image defines the visual identity — match its palette, "
                       "register, and subject treatment; your SVG must read as a sibling of it. "
                       "Output ONLY an SVG document (no markdown fences, no commentary). "
                       f"A 1280x720 vector illustration derived from that reference: {full} "
                       f"Variation {index + 1}: explore a different composition. "
                       "Root element must be <svg xmlns=... width=1280 height=720>.")
                ask_root = _skill_root().parent / "ask"
                proc = subprocess.run(
                    [str(ask_root / "run.sh"), "tau-dag", ask,
                     "--repo", "local/agent-skills", "--target", f"asset-alt-{asset_id}-{stamp}-{index}",
                     "--immutable-goal", f"one SVG alternate for asset {asset_id}",
                     "--handler", "claude-fable-low",
                     "--attach-file", str(ref),
                     "--execute", "--json"],
                    capture_output=True, text=True, timeout=1800)
                text = ""
                import re as re_mod
                match = re_mod.search(r'"run_dir":\s*"([^"]+)"', proc.stdout or "")
                if match:
                    response = (Path(match.group(1)) / "node-artifacts"
                                / "handler-claude-fable-low" / "response.md")
                    if response.is_file():
                        text = response.read_text(encoding="utf-8")
                if not text:
                    text = proc.stdout
                start, end = text.find("<svg"), text.rfind("</svg>")
                if start >= 0 and end > start:
                    svg_path.write_text(text[start:end + 6])
                    subprocess.run(["rsvg-convert", "-w", "1280", "-h", "720",
                                    str(svg_path), "-o", str(out)],
                                   capture_output=True, timeout=120)
                results.append({"file": str(out), "svg": str(svg_path) if svg_path.exists() else None,
                                "ok": out.is_file(),
                                "error": None if out.is_file() else (proc.stderr or text)[-200:]})
                continue
            if figure:
                kind, _, spec = figure.partition(":")
                cmd = [str(Path.home() / ".claude/skills/create-figure/run.sh"), kind,
                       "--stages" if kind == "workflow" else "--data", spec,
                       "--output", str(out), "--format", "png"]
            else:
                cmd = ["uv", "run", "--script",
                       str(Path.home() / ".claude/skills/create-image/generate.py"), "generate",
                       f"{full} Variation {index + 1}: explore a different composition.",
                       "--output", str(out), "--size", "1280x720", "--backend", backend,
                       "--reference", str(ref)]
                if model:
                    cmd += ["--model", model]
            env = dict(os.environ)
            # key resolution for raster backends: NANO_BANANA_FREE_API_KEY and
            # FAL_API_KEY live in ~/.zshrc; create-image reads GEMINI_API_KEY
            # and FAL_KEY. Resolve without requiring an interactive shell.
            zshrc = Path.home() / ".zshrc"
            if zshrc.is_file():
                for line in zshrc.read_text().splitlines():
                    for src, dst in (("NANO_BANANA_FREE_API_KEY", "GEMINI_API_KEY"),
                                      ("FAL_API_KEY", "FAL_KEY")):
                        # ALWAYS override: the session env may carry the old
                        # revoked key; the zshrc names are authoritative here
                        if src in line and "=" in line:
                            env[dst] = line.split("=", 1)[1].strip().strip('"').split(" #")[0].strip()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env,
                                  cwd=str(Path.home() / ".claude/skills/create-image"))
            results.append({"file": str(out), "ok": out.is_file(),
                            "error": None if out.is_file() else proc.stdout[-200:] + proc.stderr[-200:]})
        receipt = {"schema": "pitchdeck.asset_alternates.v1", "asset": asset_id,
                   "prompt": full, "backend": backend, "reference": str(ref) if ref else None,
                   "candidates": results,
                   "adopt_with": f"./run.sh asset-alternates --bundle-dir {bundle_dir} --asset-id {asset_id} --select <candidate.png>"}
        (out_dir / f"{stamp}-receipt.json").write_text(json_mod.dumps(receipt, indent=1))
        typer.echo(json_mod.dumps(receipt, indent=1))
        raise typer.Exit(0 if all(r["ok"] for r in results) else 1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="document-edit")
def document_edit_cmd(
    document: Annotated[Path, typer.Option(help="Canonical deck.document.json to edit in place.")],
    slide_id: Annotated[str, typer.Option(help="Slide id.")],
    field: Annotated[str, typer.Option(help="element:<id>:frame|text|size|bold|align|asset, or slide hidden.")],
    value: Annotated[str, typer.Option(help="frame: 'x,y,w,h' fractions; asset: asset id; others: literal.")],
    output_dir: Annotated[Path, typer.Option(help="UI public dir to re-project into.")],
    asset_base: Annotated[Path, typer.Option(help="Bundle dir for asset resolution.")],
) -> None:
    """Apply ONE validated edit to the canonical document, then re-project
    deck.data.json (#1388). The document model re-validates on every write —
    a rejected edit changes nothing on disk."""
    import json as json_mod

    from .document import DeckDocument
    from .document_ui import project_document_to_ui

    try:
        doc = DeckDocument.model_validate(json_mod.loads(document.read_text(encoding="utf-8")))
        slide = next((sl for sl in doc.slides if sl.id == slide_id), None)
        if slide is None:
            raise ValueError(f"unknown slide '{slide_id}'")
        parts = field.split(":")
        if parts[0] == "element" and len(parts) == 3:
            element_id, attr = parts[1], parts[2]
            el = next((e for e in slide.elements if e.id == element_id), None)
            if el is None:
                raise ValueError(f"unknown element '{element_id}' on slide '{slide_id}'")
            from .document import Bbox as _Bbox
            if attr == "frame":
                x, y, w, h = (float(v) for v in value.split(","))
                el.bbox = _Bbox(x=x, y=y, w=w, h=h)
            elif attr == "text":
                el.text = value
            elif attr == "asset":
                if not any(a.id == value for a in doc.assets):
                    raise ValueError(f"asset '{value}' is not registered in the document")
                el.asset_id = value
            elif attr in {"size", "bold", "align"}:
                style = el.style or type(el).model_fields["style"].annotation.__args__[0]()
                if attr == "size":
                    style.size_pt = float(value)
                elif attr == "bold":
                    style.bold = value.lower() in {"1", "true", "yes"}
                else:
                    style.align = value
                el.style = style
            else:
                raise ValueError(f"unsupported element attribute '{attr}'")
        else:
            raise ValueError(f"unsupported field '{field}'")
        # full-model revalidation before anything touches disk
        revalidated = DeckDocument.model_validate(json_mod.loads(doc.model_dump_json(by_alias=True)))
        document.write_text(revalidated.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        payload = project_document_to_ui(revalidated)
        existing = json_mod.loads((output_dir / "deck.data.json").read_text(encoding="utf-8"))
        payload["revision"] = int(existing.get("revision", 0)) + 1
        payload["assets_index"] = existing.get("assets_index", [])
        (output_dir / "deck.data.json").write_text(json_mod.dumps(payload, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({"status": "PASS", "slide": slide_id, "field": field,
                                   "revision": payload["revision"]}))
    except Exception as exc:
        _abort(exc)


@app.command(name="theme-edit")
def theme_edit_cmd(
    source: Annotated[Path, typer.Option(help="Server-resolved document or deck YAML.")],
    output_dir: Annotated[Path, typer.Option(help="Emitted UI directory.")],
    request_file: Annotated[Path, typer.Option(help="Bound theme operation request.")],
    storage: Annotated[Path, typer.Option(help="Private theme catalog and undo storage.")],
) -> None:
    from .theme_edit import run
    import json
    try:
        typer.echo(json.dumps(run(source, output_dir, request_file, storage)))
    except Exception as exc:
        _abort(exc)


@app.command(name="selected-edit")
def selected_edit_cmd(
    document: Annotated[Path, typer.Option(help="Canonical document.")],
    output_dir: Annotated[Path, typer.Option(help="Emitted UI directory.")],
    operation: Annotated[str, typer.Option(help="preview, apply or undo.")],
    request_file: Annotated[Path, typer.Option(help="Server-owned selected-element request.")],
) -> None:
    """Validate/apply/undo a revision-bound selected-element proposal."""
    import json as json_mod
    from .selected_edit import run

    try:
        typer.echo(json_mod.dumps(run(document, output_dir, operation, request_file)))
    except Exception as exc:
        _abort(exc)


@app.command(name="document-op")
def document_op_cmd(
    document: Annotated[Path, typer.Option(help="Canonical deck.document.json to edit in place.")],
    output_dir: Annotated[Path, typer.Option(help="UI public dir to re-project into.")],
    asset_base: Annotated[Path, typer.Option(help="Bundle dir for existing relative asset paths.")],
    op: Annotated[str, typer.Option(help="add-text | add-image | add-chart | add-diagram | delete-element | crop | slide-add_after | slide-duplicate | slide-move_left | slide-move_right | slide-delete | slide-hide | slide-show")],
    slide_id: Annotated[str, typer.Option(help="Target slide id.")],
    element_id: Annotated[str | None, typer.Option(help="Element id for delete-element/crop.")] = None,
    text: Annotated[str | None, typer.Option(help="Text for add-text.")] = None,
    file: Annotated[Path | None, typer.Option(help="Image file for add-image.")] = None,
    spec: Annotated[Path | None, typer.Option(help="add-chart: metrics JSON for create-figure; add-diagram: scene YAML for create-svg.")] = None,
    chart_type: Annotated[str, typer.Option(help="add-chart: bar|hbar|pie|line.")] = "bar",
    title: Annotated[str, typer.Option(help="add-chart title.")] = "Figure",
    alt: Annotated[str | None, typer.Option(help="Alt text (required for any image).")] = None,
    bbox: Annotated[str | None, typer.Option(help="x,y,w,h fractions for the new element or the crop window.")] = None,
) -> None:
    """Structural edit on a canonical document: elements, slides, images, crops,
    and agent-generated charts/diagrams via create-figure / create-svg. Full
    re-validation before any write; a rejected op changes nothing."""
    import json as json_mod

    from .document import Bbox as _Bbox
    from .document_ops import apply

    try:
        box = None
        if bbox:
            x, y, w, h = (float(v) for v in bbox.split(","))
            box = _Bbox(x=x, y=y, w=w, h=h)
        result = apply(document, output_dir, asset_base, op, slide_id=slide_id, element_id=element_id, text=text,
                       file=file, spec=spec, chart_type=chart_type, title=title, alt=alt or "", bbox=box)
        typer.echo(json_mod.dumps(result))
    except Exception as exc:
        _abort(exc)


@app.command(name="calibrate-house-gate")
def calibrate_house_gate_cmd(
    output: Annotated[Path, typer.Option(help="Where to write house_gate_calibration.v1 JSON.")] = Path("fixtures/house-gate/calibration.v1.json"),
    pages_dir: Annotated[Path, typer.Option(help="Corpus renders directory.")] = Path("/mnt/storage12tb/skills/pitchdeck/outputs/house-slides"),
) -> None:
    """Build the frozen content-addressed house-gate calibration artifact (#1379)."""
    import json as json_mod

    from .house_gate_calibration import build_calibration

    try:
        cal = build_calibration(pages_dir)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = json_mod.loads(cal.model_dump_json(by_alias=True))
        payload["content_digest"] = cal.content_digest()
        output.write_text(json_mod.dumps(payload, indent=1))
        typer.echo(json_mod.dumps({"status": "PASS", "output": str(output),
                                   "pages": len(cal.pages),
                                   "duplicate_clusters": cal.duplicate_cluster_count,
                                   "thresholds": cal.thresholds.model_dump(),
                                   "content_digest": payload["content_digest"]}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="outline")
def outline_cmd(
    context: Annotated[Path, typer.Option(help="DECK_CONTEXT yaml/json (pitchdeck.deck_context.v1).")],
    bundle_dir: Annotated[Path, typer.Option(help="Bundle containing claim_ledger.yaml.")],
    profile: Annotated[Path, typer.Option(help="deck_profile.v1 JSON.")],
    output: Annotated[Path, typer.Option(help="Where to write narrative_outline.json.")],
    approve_by: Annotated[str | None, typer.Option(help="Approve immediately as this reviewer (records hash-bound approval).")] = None,
) -> None:
    """Two-stage planning: draft (and optionally approve) a claim-routed narrative outline."""
    import json as json_mod

    import yaml as yaml_mod

    from .design_system import DeckProfile
    from .models import ClaimLedger
    from .planning import DeckContext, approve_outline, draft_outline

    try:
        raw = context.read_text(encoding="utf-8")
        data = yaml_mod.safe_load(raw) if context.suffix in {".yaml", ".yml"} else json_mod.loads(raw)
        ctx = DeckContext.model_validate(data)
        ledger = load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger)
        prof = DeckProfile.model_validate(json_mod.loads(profile.read_text(encoding="utf-8")))
        drafted = draft_outline(ctx, ledger, prof)
        if approve_by:
            from datetime import UTC, datetime

            # Bind the LEDGER the approval was given against. Without this the
            # approval carries no ledger digest, so assert_approved() has nothing
            # to compare and a later claim edit silently keeps the approval valid.
            drafted = approve_outline(drafted, approved_by=approve_by,
                                      approved_at=datetime.now(UTC).isoformat(),
                                      ledger=ledger)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drafted.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS",
            "modules": [m.module for m in drafted.modules],
            "questions": [q.code for q in drafted.questions],
            "approved": drafted.approval is not None,
            "output": str(output.resolve()),
        }, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="propose-renderings")
def propose_renderings_cmd(
    outline: Annotated[Path, typer.Option(help="narrative_outline.json to amend (approval is invalidated).")],
    bundle_dir: Annotated[Path, typer.Option(help="Bundle with claim_ledger.yaml (verification source).")],
    proposals: Annotated[Path | None, typer.Option(help="JSON list of {module, claim_id, text, transform_class} agent proposals.")] = None,
    max_words: Annotated[int, typer.Option(help="Band cap for auto truncation candidates.")] = 10,
) -> None:
    """Propose tightened assertion RENDERINGS (candidates only; human approval promotes)."""
    import json as json_mod

    from .models import ClaimLedger
    from .planning import AssertionRendering, NarrativeOutline, propose_truncations, verify_rendering

    try:
        model = NarrativeOutline.model_validate(json_mod.loads(outline.read_text(encoding="utf-8")))
        ledger = load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger)
        claims = {c.id: c.text for c in ledger.claims}
        agent_props = json_mod.loads(proposals.read_text(encoding="utf-8")) if proposals else []
        summary = []
        new_modules = []
        for module in model.modules:
            renderings = list(module.renderings)
            for prop in [p for p in agent_props if p["module"] == module.module]:
                if prop["claim_id"] not in module.candidate_claim_ids:
                    raise ValueError(f"claim '{prop['claim_id']}' is not among module '{module.module}' candidate claims — cross-scope binding refused")
                rendering = verify_rendering(
                    AssertionRendering(claim_id=prop["claim_id"], text=prop["text"], transform_class=prop["transform_class"]),
                    claims[prop["claim_id"]],
                )
                renderings.append(rendering)
                summary.append({"module": module.module, "text": rendering.text, "class": rendering.transform_class, "status": "candidate"})
            if not renderings and module.candidate_claim_ids and len(module.candidate_assertions[0].split()) > max_words:
                for candidate in propose_truncations(claims[module.candidate_claim_ids[0]], max_words=max_words)[:2]:
                    rendering = verify_rendering(
                        AssertionRendering(claim_id=module.candidate_claim_ids[0], text=candidate, transform_class="truncation"),
                        claims[module.candidate_claim_ids[0]],
                    )
                    renderings.append(rendering)
                    summary.append({"module": module.module, "text": rendering.text, "class": rendering.transform_class, "status": "candidate"})
            new_modules.append(module.model_copy(update={"renderings": renderings}))
        amended = model.model_copy(update={"modules": new_modules, "approval": None})
        outline.write_text(amended.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({"status": "PASS", "proposed": summary, "note": "outline approval invalidated; human approval required"}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="approve-rendering")
def approve_rendering_cmd(
    outline: Annotated[Path, typer.Option(help="narrative_outline.json.")],
    module: Annotated[str, typer.Option(help="Module whose rendering to approve.")],
    index: Annotated[int, typer.Option(help="Rendering index within the module.")],
    approved_by: Annotated[str, typer.Option(help="HUMAN approver identity (provenance).")],
) -> None:
    """Approve one assertion rendering (human provenance required)."""
    import json as json_mod

    from .planning import NarrativeOutline

    try:
        model = NarrativeOutline.model_validate(json_mod.loads(outline.read_text(encoding="utf-8")))
        new_modules = []
        hit = None
        for m in model.modules:
            if m.module == module:
                renderings = list(m.renderings)
                renderings[index] = renderings[index].model_copy(update={"status": "approved", "approved_by": approved_by})
                hit = renderings[index]
                m = m.model_copy(update={"renderings": renderings})
            new_modules.append(m)
        if hit is None:
            raise ValueError(f"module '{module}' not found")
        amended = model.model_copy(update={"modules": new_modules, "approval": None})
        outline.write_text(amended.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({"status": "PASS", "approved": {"module": module, "text": hit.text, "by": approved_by},
                                   "note": "outline approval invalidated; re-approve the outline"}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="materialize-outline")
def materialize_outline_cmd(
    outline: Annotated[Path, typer.Option(help="APPROVED narrative_outline.json.")],
    context: Annotated[Path, typer.Option(help="DECK_CONTEXT yaml/json.")],
    bundle_dir: Annotated[Path, typer.Option(help="Bundle with claim_ledger/source_manifest/asset_manifest.")],
    output: Annotated[Path, typer.Option(help="Where to write the materialized deck.document.json.")],
    preview_candidates: Annotated[bool, typer.Option("--preview-candidates", help="PREVIEW ONLY: use candidate renderings; provenance-stamped, never publishable.")] = False,
) -> None:
    """Materialize an APPROVED outline into an intent-carrying deck document (deterministic)."""
    import json as json_mod

    import yaml as yaml_mod

    from .intents import materialize_outline
    from .models import AssetManifest, ClaimLedger, SourceManifest
    from .planning import DeckContext, NarrativeOutline

    try:
        raw = context.read_text(encoding="utf-8")
        ctx = DeckContext.model_validate(yaml_mod.safe_load(raw) if context.suffix in {".yaml", ".yml"} else json_mod.loads(raw))
        out_model = NarrativeOutline.model_validate(json_mod.loads(outline.read_text(encoding="utf-8")))
        ledger = load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger)
        source_path = bundle_dir / "source_manifest.resolved.yaml"
        if not source_path.exists():
            source_path = bundle_dir / "source_manifest.yaml"
        sources = load_yaml(source_path, SourceManifest)
        assets = load_yaml(bundle_dir / "asset_manifest.yaml", AssetManifest)
        document = materialize_outline(out_model, ctx, ledger, sources, assets, use_candidate_renderings=preview_candidates)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
        typer.echo(json_mod.dumps({
            "status": "PASS",
            "slides": [{"id": s.id, "recipe": s.intent.recipe if s.intent else None} for s in document.slides],
            "output": str(output.resolve()),
        }, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="emit-document-pptx")
def emit_document_pptx_cmd(
    document: Annotated[Path, typer.Option(help="Path to a deck.document.json (pitchdeck.deck_document.v1).")],
    output: Annotated[Path, typer.Option(help="Output PPTX path.")],
    asset_base: Annotated[Path, typer.Option(help="Base dir for relative asset paths.")],
    theme_template: Annotated[Path | None, typer.Option(help="pitchdeck.theme_template.v1 JSON.")] = None,
    house_template: Annotated[Path | None, typer.Option(help="House .pptx to inherit theme/master/layouts from (band, logo, footer come free).")] = None,
    disclaimer_owner: Annotated[str | None, typer.Option(help="Owner named in the footer disclaimer; retargets the template's inherited one.")] = None,
    disclaimer_approved_by: Annotated[str | None, typer.Option(help="Who approved the ownership assertion (required with --disclaimer-owner).")] = None,
    brandmark: Annotated[bool, typer.Option("--brandmark", help="Replace the template owner's logo with the grahama.co Gc mark.")] = False,
) -> None:
    """Emit a canonical document as NATIVE editable PPTX (nested groups, shapes, connectors, runs)."""
    import json as json_mod

    from .document import DeckDocument
    from .document_pptx import emit_document_pptx

    try:
        doc = DeckDocument.model_validate(json_mod.loads(document.read_text(encoding="utf-8")))
        disclaimer_text = None
        if disclaimer_owner:
            from .identity import ownership_disclaimer

            if not disclaimer_approved_by:
                raise SkillError("--disclaimer-owner requires --disclaimer-approved-by: "
                                 "ownership is a legal assertion, never a derivation")
            disclaimer_text = ownership_disclaimer(disclaimer_owner, approved_by=disclaimer_approved_by).text
        receipt = emit_document_pptx(doc, output, asset_base=asset_base,
                                     theme_template=theme_template, house_template=house_template,
                                     disclaimer=disclaimer_text, brandmark=brandmark)
        typer.echo(json_mod.dumps({"status": "PASS", **receipt}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="analyze-style")
def analyze_style_cmd(
    pptx: Annotated[Path, typer.Option(help="Reference PPTX to analyze.")],
    output_dir: Annotated[Path, typer.Option(help="Directory for style_reference.json, renders, and receipt.")],
    design_system: Annotated[Path | None, typer.Option(help="design_system.v1 JSON to classify against (signals only).")] = None,
    render: Annotated[bool, typer.Option(help="Render representative slides via LibreOffice.")] = True,
) -> None:
    """Analyze a reference deck into validated pitchdeck.style_reference.v1 data."""
    import json as json_mod

    from .style_analyze import analyze_style

    try:
        receipt = analyze_style(pptx, output_dir, design_system, render=render)
        typer.echo(json_mod.dumps({"status": "PASS", **receipt}, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="record-transcript")
def record_transcript_cmd(
    timeout_seconds: Annotated[int, typer.Option(help="Max recording window.")] = 120,
) -> None:
    """Record one utterance (RealtimeSTT mic, faster-whisper local) and print the transcript JSON.

    Used by the chat well's voice/dictation affordance: the transcript enters the
    chat composer path, never the deck directly — proposals still go through
    simulate + human Apply + compiler validation.
    """
    import json as json_mod

    from .transcribe import record_transcript

    try:
        result = record_transcript(timeout_seconds)
        typer.echo(json_mod.dumps(result, indent=1))
        raise typer.Exit(0 if result["status"] == "PASS" else 6)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="claim-decide")
def claim_decide(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    claim_id: Annotated[str, typer.Option(help="Claim id to decide.")],
    decision: Annotated[str, typer.Option(help="approve | reject")],
    decided_by: Annotated[str, typer.Option(help="Human reviewer identity.")],
    qualifier: Annotated[str, typer.Option(help="Qualifier to attach on approval.")] = "",
    batch: Annotated[bool, typer.Option("--batch", help="Batch context: high-risk/numeric claims refuse.")] = False,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Decide one candidate claim through full validation; appends a replayable audit line."""
    import json as json_mod

    from .claim_decide import decide_claim

    try:
        result = decide_claim(
            bundle_dir, output_dir, claim_id=claim_id, decision=decision,
            decided_by=decided_by, qualifier=qualifier or None, batch=batch, deck_name=deck_name,
        )
        typer.echo(json_mod.dumps(result, indent=1))
    except Exception as exc:
        _abort(exc)


@app.command(name="image-variations")
def image_variations(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    slide_id: Annotated[str, typer.Option(help="Slide to generate visual variations for.")],
    output_dir: Annotated[Path, typer.Option(help="Directory for the plan, variants, and contact sheet.")],
    count: Annotated[int, typer.Option(help="Number of variations.")] = 4,
    execute: Annotated[bool, typer.Option("--execute", help="Run live via codex exec + the imagegen skill (OAuth session; no API key).")] = False,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
) -> None:
    """Compile a theme-aware brief and fan out N image variations (plan always; live with --execute)."""
    import json as json_mod

    from .image_variations import emit_variation_plan, run_variations
    from .slide_edit import _load

    try:
        deck, *_ = _load(bundle_dir, deck_name)
        plan_path = emit_variation_plan(deck, slide_id, output_dir, count=count)
        result = {"plan": str(plan_path)}
        if execute:
            result.update(run_variations(plan_path, output_dir))
        typer.echo(json_mod.dumps(result, indent=1))
        raise typer.Exit(0 if result.get("status") in (None, "PASS") else 5)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="drift")
def drift(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    update: Annotated[bool, typer.Option("--update", help="Refresh the source snapshot after reporting.")] = False,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
) -> None:
    """Living-deck drift check: report changed sources + affected claims/slides; --update refreshes the snapshot."""
    import json as json_mod

    from .drift import check_drift, snapshot_sources
    from .slide_edit import _load

    try:
        deck, ledger, sources, assets, source_path = _load(bundle_dir, deck_name)
        report = check_drift(bundle_dir, deck, ledger, sources, source_path.parent)
        if update:
            snapshot_sources(bundle_dir, sources, source_path.parent)
            report["snapshot_refreshed"] = True
        typer.echo(json_mod.dumps(report, indent=1))
        raise typer.Exit(0 if report["no_op"] or update else 4)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="simulate")
def simulate(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    slide_id: Annotated[str, typer.Option(help="Slide id the mutation targets.")],
    field: Annotated[str, typer.Option(help="Slide field to edit (mutually exclusive with --op).")] = "",
    value: Annotated[str, typer.Option(help="New value for --field.")] = "",
    op: Annotated[str, typer.Option(help="Deck op: add_after|duplicate|delete|move_left|move_right|move_to.")] = "",
    target_order: Annotated[int, typer.Option(help="Target order for move_to.")] = 0,
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
) -> None:
    """Dry-run a mutation through the REAL pipeline: JSON {would_pass, gate_codes, error, diff}; zero writes."""
    import json as json_mod

    from .slide_edit import simulate_edit

    try:
        result = simulate_edit(
            bundle_dir, slide_id=slide_id,
            field=field or None, value=value or None,
            op=op or None, target_order=target_order or None, deck_name=deck_name,
        )
        typer.echo(json_mod.dumps(result, indent=1))
        raise typer.Exit(0 if result["would_pass"] else 3)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@app.command(name="undo")
def undo(
    bundle_dir: Annotated[Path, typer.Option(help="Directory containing the standard bundle manifests.")],
    output_dir: Annotated[Path, typer.Option(help="Output directory holding deck.data.json to refresh.")],
    deck_name: Annotated[str, typer.Option(help="Deck manifest filename inside the bundle.")] = "deck.public.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Restore the previous committed state — validated BEFORE commit; refuses governance/out-of-band."""
    from .slide_edit import validated_undo

    try:
        receipt = validated_undo(bundle_dir, output_dir, deck_name=deck_name)
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
            schema="pitchdeck.verify_receipt.v1",
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
