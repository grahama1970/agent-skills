#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "pymupdf>=1.25.0",
#   "loguru>=0.7.0",
# ]
# ///
"""Generate annotated PDFs from pipeline run data by PDF stem.

Auto-discovers run directories and invokes the extractor's render_annotated_pdf
tool. Supports single stem, batch from blacklist, and JSON manifest output.

Examples:
    uv run --script annotate_from_stem.py nasa_20210017388
    uv run --script annotate_from_stem.py nasa_20210017388 --png --out /tmp/annotated.pdf
    uv run --script annotate_from_stem.py --batch-blacklist --out-dir /tmp/failures/
    uv run --script annotate_from_stem.py --batch-blacklist --manifest-only
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import fitz
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True, add_completion=False)

import os

_SKILLS_DIR = Path(__file__).resolve().parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
EXTRACTOR_ROOT = _SKILLS_DIR.parent.parent.parent / "extractor"
RENDER_TOOL = "extractor.pipeline.tools.render_annotated_pdf"

EXTRACTED_RUNS_NVME = _SKILLS_DIR / "review-pdf" / "extracted_runs_staging"
EXTRACTED_RUNS_HDD = _EMBRY_STORAGE / "skills/review-pdf/extracted_runs"
CORPUS_ROOT = _EMBRY_STORAGE / "extractor_corpus"
BLACKLIST_PATH = _SKILLS_DIR / "learn-datalake" / "state" / "failed_pdf_blacklist.jsonl"
DEFAULT_OUT_DIR = Path("/tmp/annotated_pdfs")


def _find_run_dir(stem: str) -> Optional[Path]:
    """Find extraction run directory by stem."""
    for runs_dir in (EXTRACTED_RUNS_NVME, EXTRACTED_RUNS_HDD):
        if not runs_dir.is_dir():
            continue
        for entry in runs_dir.iterdir():
            if entry.name.startswith(stem):
                target = entry.resolve() if entry.is_symlink() else entry
                if target.is_dir():
                    return target
    return None


def _find_pdf(stem: str, run_dir: Optional[Path] = None) -> Optional[Path]:
    """Find original PDF by stem."""
    # Check profile.json first
    if run_dir:
        profile_path = run_dir / "00_profile_detector" / "profile.json"
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text())
                pdf_path = Path(profile.get("file", ""))
                if pdf_path.exists():
                    return pdf_path
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
    # Fallback: search corpus
    for pdf in CORPUS_ROOT.rglob(f"{stem}.pdf"):
        if pdf.is_file():
            return pdf
    return None


def _find_clean_pdf(run_dir: Path) -> Optional[Path]:
    """Find the Stage 01 clean PDF in the run directory."""
    s01_dir = run_dir / "01_annotation_processor"
    if s01_dir.is_dir():
        for f in s01_dir.iterdir():
            if f.name.endswith("_clean.pdf") and f.is_file():
                return f
    return None


def _collect_agent_notes(run_dir: Path, stem: str) -> list[dict]:
    """Collect extraction diagnostic notes from pipeline run data."""
    notes: list[dict] = []

    def _load(p: Path):
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    # Profile preset_match errors (S00)
    profile = _load(run_dir / "00_profile_detector" / "profile.json")
    if profile:
        pm = profile.get("preset_match", {})
        errors = pm.get("errors", [])
        if errors:
            notes.append({
                "severity": "warning",
                "source": "S00 Profile Detector",
                "message": f"Extraction risks: {', '.join(errors)}",
            })
        conf = pm.get("confidence", 100)
        if isinstance(conf, (int, float)) and conf < 10:
            notes.append({
                "severity": "warning",
                "source": "S00 Profile Detector",
                "message": f"Low preset confidence ({conf})",
            })

    # Suspicious headers (S03)
    s03 = _load(run_dir / "03_suspicious_headers" / "json_output" / "03_verified_blocks.json")
    if s03:
        susp_count = s03.get("suspicious_block_count", 0)
        if susp_count > 0:
            notes.append({
                "severity": "warning",
                "source": "S03 Suspicious Headers",
                "message": f"{susp_count} suspicious header blocks",
            })

    # Layout audit (S04a)
    audit = _load(run_dir / "04a_layout_audit" / "json_output" / "04a_layout_audit.json")
    if audit:
        error_count = audit.get("errors", 0)
        total_checks = audit.get("sections_checked", 0)
        if error_count > 0:
            checks = audit.get("checks", [])
            reasons: dict[str, int] = {}
            for c in checks:
                if not c.get("ok", True):
                    r = c.get("reason", "unknown")
                    reasons[r] = reasons.get(r, 0) + 1
            top = ", ".join(f"{r} ({n})" for r, n in sorted(reasons.items(), key=lambda x: -x[1])[:3])
            sev = "error" if error_count > total_checks * 0.3 else "warning"
            notes.append({
                "severity": sev,
                "source": "S04a Layout Audit",
                "message": f"{error_count}/{total_checks} checks failed: {top}",
            })

    # Scanned PDF
    scanned = _load(run_dir / "scanned_pdf.json")
    if scanned and scanned.get("is_scanned"):
        notes.append({
            "severity": "warning",
            "source": "PDF Classification",
            "message": f"Scanned PDF (text ratio: {scanned.get('text_ratio', 0):.1%})",
        })

    # Blacklist
    if BLACKLIST_PATH.exists():
        for line in BLACKLIST_PATH.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("stem") == stem:
                    notes.append({
                        "severity": "error",
                        "source": "Blacklist",
                        "message": f"Blacklisted: {entry.get('reason', 'unknown')}",
                    })
                    break
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

    # Missing stages
    for stage_dir, output, label in [
        ("02_marker_extractor", "json_output/02_marker_blocks.json", "S02 blocks"),
        ("05_table_extractor", "json_output/05_tables.json", "S05 tables"),
        ("06_figure_extractor", "json_output/06_figures.json", "S06 figures"),
    ]:
        sp = run_dir / stage_dir
        if sp.is_dir() and not (sp / output).exists():
            notes.append({"severity": "error", "source": label, "message": f"{label} ran but produced no output"})

    severity_order = {"error": 0, "warning": 1, "info": 2}
    notes.sort(key=lambda n: severity_order.get(n.get("severity", "info"), 3))
    return notes


def _stamp_notes_on_pdf(pdf_path: Path, notes: list[dict], stem: str) -> None:
    """Append a notes page to the annotated PDF with agent diagnostic notes."""
    if not notes:
        return

    doc = fitz.open(str(pdf_path))

    # Create a new page at the end (letter size)
    page = doc.new_page(width=612, height=792)

    # Title
    y = 40
    page.insert_text(
        fitz.Point(40, y), "Extraction Agent Notes",
        fontsize=16, fontname="helv", color=(0.1, 0.1, 0.1),
    )
    y += 8
    page.insert_text(
        fitz.Point(40, y + 14), f"PDF: {stem}",
        fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4),
    )
    y += 30

    # Severity colors
    sev_colors = {
        "error": (0.8, 0.1, 0.1),
        "warning": (0.7, 0.5, 0.0),
        "info": (0.2, 0.4, 0.7),
    }

    for note in notes:
        if y > 740:
            page = doc.new_page(width=612, height=792)
            y = 40

        sev = note.get("severity", "info")
        color = sev_colors.get(sev, (0.3, 0.3, 0.3))

        # Severity badge
        badge = sev.upper()
        page.insert_text(
            fitz.Point(40, y + 10), badge,
            fontsize=8, fontname="hebo", color=color,
        )

        # Source and message
        source = note.get("source", "")
        msg = note.get("message", "")
        page.insert_text(
            fitz.Point(90, y + 10), f"{source}: {msg}",
            fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15),
        )
        y += 18

    # Draw separator line under title
    page_first = doc[-len(notes) if len(notes) > 0 else -1]  # not needed, just save
    doc.save(str(pdf_path), incremental=True, encryption=0)
    doc.close()


def _annotate_one(
    stem: str,
    out: Optional[Path] = None,
    export_png: bool = False,
    png_dpi: int = 144,
) -> Optional[Path]:
    """Generate annotated PDF for a single stem. Returns output path or None."""
    run_dir = _find_run_dir(stem)
    if run_dir is None:
        logger.warning(f"No run directory found for stem={stem}")
        return None

    # Prefer clean PDF, fall back to original
    pdf = _find_clean_pdf(run_dir) or _find_pdf(stem, run_dir)
    if pdf is None:
        logger.warning(f"No PDF found for stem={stem}")
        return None

    if out is None:
        out = DEFAULT_OUT_DIR / f"{stem}_annotated.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", RENDER_TOOL, "from-run",
        "--pdf", str(pdf),
        "--run-dir", str(run_dir),
        "--out", str(out),
    ]
    if export_png:
        cmd.extend(["--export-pages", "--png-dpi", str(png_dpi)])

    env = {
        **dict(__import__("os").environ),
        "PYTHONPATH": str(EXTRACTOR_ROOT / "src"),
    }

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"Annotation failed for {stem}: {result.stderr[:300]}")
        return None

    # Stamp agent notes onto the annotated PDF
    agent_notes = _collect_agent_notes(run_dir, stem)
    if agent_notes:
        try:
            _stamp_notes_on_pdf(out, agent_notes, stem)
            logger.info(f"Stamped {len(agent_notes)} agent note(s) onto {out.name}")
        except Exception as exc:
            logger.warning(f"Failed to stamp notes: {exc}")

    logger.info(f"Annotated: {out}")
    return out


@app.command()
def annotate(
    stem: str = typer.Argument(None, help="PDF stem to annotate"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output PDF path"),
    png: bool = typer.Option(False, "--png", help="Also export per-page PNGs"),
    dpi: int = typer.Option(144, "--dpi", help="PNG export DPI"),
    batch_blacklist: bool = typer.Option(
        False, "--batch-blacklist", help="Annotate all blacklisted PDFs"
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Output directory for batch mode"
    ),
    manifest_only: bool = typer.Option(
        False, "--manifest-only", help="Only print JSON manifest, don't generate PDFs"
    ),
    limit: int = typer.Option(0, "--limit", help="Limit batch to N PDFs (0=all)"),
) -> None:
    """Generate annotated PDFs from extraction pipeline run data."""
    if batch_blacklist:
        _batch_blacklist(out_dir or DEFAULT_OUT_DIR, manifest_only, png, dpi, limit)
        return

    if stem is None:
        typer.echo("Error: provide a stem or use --batch-blacklist", err=True)
        raise typer.Exit(code=1)

    result = _annotate_one(stem, out, png, dpi)
    if result is None:
        typer.echo(f"Failed to annotate {stem}", err=True)
        raise typer.Exit(code=1)

    typer.echo(str(result))


def _batch_blacklist(
    out_dir: Path,
    manifest_only: bool,
    export_png: bool,
    dpi: int,
    limit: int,
) -> None:
    """Annotate all blacklisted PDFs."""
    if not BLACKLIST_PATH.exists():
        typer.echo("No blacklist found")
        raise typer.Exit(code=1)

    stems: list[str] = []
    for line in BLACKLIST_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            stems.append(entry["stem"])
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    if limit > 0:
        stems = stems[:limit]

    logger.info(f"Batch annotating {len(stems)} blacklisted PDFs")

    if manifest_only:
        manifest = []
        for stem in stems:
            run_dir = _find_run_dir(stem)
            pdf = _find_pdf(stem, run_dir) if run_dir else None
            manifest.append({
                "stem": stem,
                "run_dir": str(run_dir) if run_dir else None,
                "pdf_path": str(pdf) if pdf else None,
                "has_run_dir": run_dir is not None,
                "has_pdf": pdf is not None and pdf.exists(),
            })
        typer.echo(json.dumps(manifest, indent=2))
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    for stem in stems:
        out = out_dir / f"{stem}_annotated.pdf"
        result = _annotate_one(stem, out, export_png, dpi)
        if result:
            success += 1

    logger.info(f"Batch complete: {success}/{len(stems)} annotated → {out_dir}")


if __name__ == "__main__":
    app()
