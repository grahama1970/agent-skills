#!/usr/bin/env python3
"""
Extractor skill - Preset-First Agentic Document Extraction.

Routes documents through the appropriate extraction path:
- PDFs: Full 14-stage pipeline with s00_profile_detector
- Structured (DOCX, HTML, XML): Fast provider path

Usage:
    ./run.sh document.pdf                    # Auto mode with preset detection
    ./run.sh document.pdf --fast             # PyMuPDF only, no LLM
    ./run.sh document.pdf --accurate         # Full LLM enhancement
    ./run.sh document.pdf --preset arxiv     # Force preset (skip detection)
    ./run.sh document.pdf --no-interactive   # Non-interactive batch mode
    ./run.sh document.pdf --profile-only     # Profile only, no extraction
    ./run.sh document.pdf --markdown         # Output markdown to stdout
    ./run.sh document.pdf --out ./results    # Custom output directory
"""
import typer
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Add this directory to sys.path for package imports
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Use package-style imports
from extractor_skill.config import (
    ExtractionOptions,
    IMAGE_FORMATS,
    PIPELINE_FORMATS,
    STRUCTURED_FORMATS,
)
from extractor_skill.batch import (
    BatchProcessor,
    generate_batch_report,
    print_assessment_table,
    print_batch_summary,
)
from extractor_skill.memory_integration import learn_failure_to_memory
from extractor_skill.memory_integration import learn_to_memory
from extractor_skill.pdf_extractor import (
    extract_pdf_with_collaboration,
    profile_pdf,
    recommend_mode,
)
from extractor_skill.structured_extractor import extract_structured
from extractor_skill.toc_checker import run_toc_check
from extractor_skill.utils import format_error_guidance


def _is_youtube_url(s: str) -> bool:
    """Check if string is a YouTube URL."""
    import re
    return bool(re.match(
        r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)',
        s
    ))


def _extract_youtube(url: str) -> Dict[str, Any]:
    """Extract YouTube transcript via /ingest-youtube skill."""
    import subprocess
    import tempfile

    skill_path = Path.home() / ".pi/skills/ingest-youtube"
    if not skill_path.exists():
        return {
            "success": False,
            "error": "YouTube URL detected but /ingest-youtube skill not found",
            "guidance": "Install /ingest-youtube skill to extract YouTube transcripts",
        }

    # Create temp file for transcript output
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["uv", "run", "python", "youtube_transcript.py", "get", "-u", url, "-o", tmp_path],
            cwd=str(skill_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": f"YouTube transcript extraction failed: {result.stderr[:200]}",
                "guidance": "Check if video has captions. Try: /ingest-youtube directly for more options.",
            }

        # Now extract the transcript JSON through normal flow
        from extractor.core.providers.json import JSONProvider
        provider = JSONProvider()
        doc = provider.extract_document(tmp_path)

        return {
            "success": True,
            "mode": "structured",
            "format": "youtube_transcript",
            "source_url": url,
            "document": doc.model_dump(),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "YouTube transcript extraction timed out (120s)",
            "guidance": "Video may be very long. Try /ingest-youtube directly with --no-whisper.",
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _generate_qra(
    filepath: Path,
    result: Dict[str, Any],
    scope: str = "research",
    domain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate QRA pairs via /doc2qra skill.

    If extractor output directory exists, uses --from-extractor for better quality.
    Otherwise falls back to direct file processing.

    Args:
        filepath: Path to the extracted document
        result: Extraction result (may contain output_dir)
        scope: Memory scope for QRA storage
        domain: Optional domain context (e.g., "ML researcher")

    Returns:
        Dict with success status and QRA count
    """
    import subprocess

    doc2qra_path = Path.home() / ".pi/skills/doc2qra/run.sh"
    if not doc2qra_path.exists():
        return {
            "success": False,
            "error": "/doc2qra skill not found",
        }

    # Build command - prefer --from-extractor if we have output directory
    cmd = ["bash", str(doc2qra_path)]
    output_dir = result.get("outputs", {}).get("report", "")
    if output_dir and Path(output_dir).parent.exists():
        # Use extractor results directory
        cmd.extend(["--from-extractor", str(Path(output_dir).parent)])
    else:
        # Fall back to direct file processing
        cmd.extend(["--file", str(filepath)])

    cmd.extend(["--scope", scope, "--json"])
    if domain:
        cmd.extend(["--context", domain])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout for large docs
        )

        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"doc2qra failed: {proc.stderr[:200]}",
            }

        # Parse JSON output
        import json
        qra_result = json.loads(proc.stdout)
        return {
            "success": True,
            "qra_count": qra_result.get("stored", 0),
            "summary": qra_result.get("summary", "")[:200],
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "QRA generation timed out (300s)",
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "Failed to parse doc2qra output",
        }


def extract(
    filepath: str,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """
    Universal extraction entry point. Routes to appropriate extractor.

    Args:
        filepath: Path to document or URL
        opts: Extraction options

    Returns:
        Dict with extraction result
    """
    # Handle YouTube URLs directly
    if _is_youtube_url(filepath):
        return _extract_youtube(filepath)

    path = Path(filepath)

    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {filepath}",
            "guidance": format_error_guidance("file not found", path),
        }

    suffix = path.suffix.lower()

    # Content sniffing: detect YouTube transcript JSON regardless of extension
    # /ingest-youtube outputs {meta, transcript[], full_text} as .md/.txt/.json
    if suffix in {".md", ".txt", ".json"}:
        try:
            from extractor.pipeline.utils.json_utils import load_json_file
            data = load_json_file(str(path))
            if isinstance(data, dict) and ("transcript" in data or "full_text" in data) and "meta" in data:
                # Explicitly use JSONProvider (not extension-based routing)
                from extractor.core.providers.json import JSONProvider
                provider = JSONProvider()
                doc = provider.extract_document(str(path))
                return {
                    "success": True,
                    "mode": "structured",
                    "format": "youtube_transcript",
                    "document": doc.model_dump(),
                }
        except (json.JSONDecodeError, ValueError):
            # Not a YouTube transcript JSON, continue with normal extraction
            pass

    # Route by format
    if suffix in PIPELINE_FORMATS:
        return extract_pdf_with_collaboration(path, opts)
    elif suffix in STRUCTURED_FORMATS or suffix in IMAGE_FORMATS:
        return extract_structured(path)
    else:
        # Try structured extraction as fallback
        return extract_structured(path)


app = typer.Typer(help="Preset-First Agentic Document Extraction")


@app.command()
def main(
    file: Path = typer.Argument(..., help="Document or directory to extract"),
    out: Optional[Path] = typer.Option(None, "-o", "--out", help="Output directory"),
    preset: Optional[str] = typer.Option(None, help="Force preset (skip auto-detection)"),
    # Mode flags (mutually exclusive - enforced in code)
    fast: bool = typer.Option(False, help="Fast mode (no LLM)"),
    accurate: bool = typer.Option(False, help="Accurate mode (with LLM)"),
    offline: bool = typer.Option(False, help="Offline mode (deterministic)"),
    # Output format
    markdown: bool = typer.Option(False, help="Output markdown to stdout"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON (default)"),
    # Collaboration flags
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip interactive prompts, use auto mode"),
    profile_only: bool = typer.Option(False, "--profile-only", help="Run profile detection only, return JSON profile"),
    auto_ocr: Optional[bool] = typer.Option(None, help="Run OCRmyPDF on scanned PDFs before extraction"),
    skip_scanned: bool = typer.Option(False, "--skip-scanned", help="Skip scanned PDFs"),
    auto_decrypt: bool = typer.Option(True, help="Attempt to decrypt encrypted PDFs automatically"),
    decrypt_password: Optional[str] = typer.Option(None, "--decrypt-password", help="Password for decrypting encrypted PDFs"),
    ocr_lang: str = typer.Option("eng", "--ocr-lang", help="OCR language(s) for OCRmyPDF"),
    ocr_deskew: bool = typer.Option(False, "--ocr-deskew", help="Deskew scanned pages during OCR"),
    ocr_force: bool = typer.Option(False, "--ocr-force", help="Force OCR even if text exists"),
    ocr_timeout: int = typer.Option(600, "--ocr-timeout", help="OCRmyPDF timeout in seconds"),
    continue_on_error: bool = typer.Option(False, "--continue-on-error", help="Continue after failures"),
    sections_only: bool = typer.Option(False, "--sections-only", help="Extract sections only"),
    # Batch options
    glob_pattern: str = typer.Option("**/*.pdf", "--glob", help="Glob pattern for directory input"),
    report_format: str = typer.Option("json", "--report", help="Report format for batch mode (json, summary)"),
    # Memory integration
    learn: bool = typer.Option(False, help="Auto-learn extraction summaries to memory"),
    scope: str = typer.Option("documents", help="Memory scope for --learn"),
    # QRA generation
    qra: bool = typer.Option(False, "--qra", help="Generate QRA pairs via /doc2qra after extraction"),
    qra_scope: str = typer.Option("research", "--qra-scope", help="Memory scope for QRA pairs"),
    qra_domain: Optional[str] = typer.Option(None, "--qra-domain", help="Domain focus for QRA generation"),
    # Edge verification
    verify_edges: bool = typer.Option(False, "--verify-edges", help="Run LLM-verified edge creation after extraction"),
    edge_scope: str = typer.Option("intra", "--edge-scope", help="Edge verification scope (intra, cross, both)"),
    # TOC integrity check
    toc_check: bool = typer.Option(False, "--toc-check", help="Run TOC integrity check"),
) -> None:
    """Preset-First Agentic Document Extraction."""
    # Enforce mutually exclusive mode flags
    mode_count = sum([fast, accurate, offline])
    if mode_count > 1:
        print("Error: --fast, --accurate, and --offline are mutually exclusive", file=sys.stderr)
        raise typer.Exit(code=1)

    # Determine mode
    mode = "auto"
    if fast:
        mode = "fast"
    elif accurate:
        mode = "accurate"
    elif offline:
        mode = "offline"

    interactive = not no_interactive

    # Edge verification warning
    if verify_edges:
        print("WARN: --verify-edges is a future feature. Edge verification requires:", file=sys.stderr)
        print("  1. CHUTES_API_KEY environment variable", file=sys.stderr)
        print("  2. scillm package with parallel_acompletions_iter", file=sys.stderr)
        print("  See 02_TASKS.md Task 8 for implementation details.", file=sys.stderr)

    # TOC integrity check mode
    if toc_check:
        result = run_toc_check(file)
        print(json.dumps(result, indent=2))
        raise typer.Exit(code=0 if result.get("success") else 1)

    # Profile-only mode
    if profile_only:
        if file.suffix.lower() != ".pdf":
            print(json.dumps({"error": "--profile-only only works with PDF files"}))
            raise typer.Exit(code=1)

        profile = profile_pdf(file)
        hierarchy = profile.get("hierarchy", {}) if isinstance(profile.get("hierarchy"), dict) else {}
        elements = profile.get("elements", {}) if isinstance(profile.get("elements"), dict) else {}
        toc = profile.get("toc", {}) if isinstance(profile.get("toc"), dict) else {}

        # Flatten for agent consumption
        flat = {
            "file": str(file),
            "preset": profile.get("preset_match", {}).get("matched"),
            "confidence": profile.get("preset_match", {}).get("confidence", 0),
            "needs_new_preset": profile.get("preset_match", {}).get("needs_new_preset", True),
            "page_count": profile.get("page_count", 0),
            "estimated_timeout_seconds": profile.get("estimated_timeout_seconds", 0),
            "timeout_source": profile.get("timeout_source", "unknown"),
            "layout": profile.get("layout", {}).get("style", "single"),
            "tables": elements.get("tables", False),
            "figures": elements.get("figures", False),
            "formulas": elements.get("formulas", False),
            "requirements": elements.get("requirements", False),
            "toc_entry_count": toc.get("entry_count", 0),
            "estimated_table_count": elements.get("estimated_table_count", 0),
            "table_pages": elements.get("table_pages", 0),
            "image_pages": elements.get("image_pages", 0),
            "max_tables_per_page": elements.get("max_tables_per_page", 0),
            "table_pages_drawing": elements.get("table_pages_drawing", 0),
            "estimated_sections": hierarchy.get("estimated_sections", 0),
            "estimated_sections_regex": hierarchy.get("estimated_sections_regex", 0),
            "estimated_sections_font": hierarchy.get("estimated_sections_font", 0),
            "estimated_sections_toc": hierarchy.get("estimated_sections_toc", 0),
            "has_structure": hierarchy.get("has_structure", False),
            "hierarchy": hierarchy,
            "elements": elements,
            "recommended_mode": recommend_mode(profile),
            "route": profile.get("route", "fast"),
        }
        print(json.dumps(flat, indent=2))
        raise typer.Exit(code=0)

    # Build Extraction Options
    opts = ExtractionOptions(
        mode=mode,
        preset=preset,
        output_dir=out,
        return_markdown=markdown,
        interactive=interactive,
        auto_ocr=auto_ocr,
        skip_scanned=skip_scanned,
        ocr_lang=ocr_lang,
        ocr_deskew=ocr_deskew,
        ocr_force=ocr_force,
        ocr_timeout=ocr_timeout,
        continue_on_error=continue_on_error,
        sections_only=sections_only,
        sync_to_memory=learn,
        auto_decrypt=auto_decrypt,
        decrypt_password=decrypt_password,
    )

    # Handle directory input (batch mode)
    if file.is_dir():
        files = sorted(file.rglob(glob_pattern))
        if not files:
            print(json.dumps({"success": False, "error": f"No files matching {glob_pattern}"}))
            raise typer.Exit(code=1)

        # Define extraction function for BatchProcessor
        def extract_file(filepath: Path) -> Dict[str, Any]:
            file_opts = dataclasses.replace(
                opts,
                output_dir=out / filepath.stem if out else None
            )
            result = extract(str(filepath), file_opts)
            result["file"] = str(filepath)
            return result

        # Use BatchProcessor for NDJSON monitoring, quality gates, and learning
        monitor = TaskClient("extractor", total=len(files)) if TaskClient else None
        processor = BatchProcessor(
            files=files,
            extract_fn=extract_file,
            scope=scope,
            continue_on_error=continue_on_error,
            sync_to_memory=learn,
        )
        batch_report = processor.run()
        if monitor:
            # Update monitor with final count after batch completes
            for f in files:
                monitor.update(item=str(f.name))
            monitor.finish()

        # Write report to output dir if specified
        if out:
            batch_report = generate_batch_report(processor.results, out)

        if learn:
            batch_report["memory_learned"] = batch_report["succeeded"]

        if report_format == "summary":
            print_batch_summary(batch_report)
            # Also print JSON to stdout for piping
            print(json.dumps(batch_report, indent=2, default=str))
        else:
            # JSON output
            print(json.dumps(batch_report, indent=2, default=str))

        raise typer.Exit(code=0 if batch_report['failed'] == 0 else 1)

    # Single file
    result = extract(str(file), opts)

    # Print assessment table if available
    if result.get("success") and result.get("assessment"):
        print_assessment_table(result["assessment"])

    # Auto-learn to memory if enabled
    if learn:
        if result.get("success"):
            if learn_to_memory(file, result, scope):
                result["memory_learned"] = True
                print(f"Learned to memory (scope: {scope})", file=sys.stderr)
        else:
            # Learn from failure for pattern recognition
            error_msg = result.get("error", "Unknown error")
            if learn_failure_to_memory(file, error_msg, scope=scope):
                result["failure_learned"] = True
                print(f"Learned failure pattern to memory (scope: {scope})", file=sys.stderr)

    # QRA generation if enabled
    if qra and result.get("success"):
        qra_result = _generate_qra(file, result, qra_scope, qra_domain)
        if qra_result.get("success"):
            result["qra_generated"] = True
            result["qra_count"] = qra_result.get("qra_count", 0)
            print(f"Generated {qra_result['qra_count']} QRA pairs (scope: {qra_scope})", file=sys.stderr)
        else:
            result["qra_error"] = qra_result.get("error", "Unknown error")
            print(f"QRA generation failed: {result['qra_error']}", file=sys.stderr)

    # Output
    if markdown and result.get("markdown"):
        print(result["markdown"])
    else:
        print(json.dumps(result, indent=2, default=str))

    # Print guidance to stderr on failure for interactive users
    if not result.get("success") and result.get("guidance"):
        print(f"\n{result['guidance']}", file=sys.stderr)

    if not result.get("success"):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
