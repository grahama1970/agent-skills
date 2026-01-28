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
import sys
import os
import json
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import dataclasses
from dataclasses import dataclass, field

@dataclass
class ExtractionOptions:
    """Consolidated options for the extraction pipeline."""
    mode: str = "auto"
    preset: Optional[str] = None
    output_dir: Optional[Path] = None
    return_markdown: bool = False
    interactive: bool = True
    auto_ocr: Optional[bool] = None
    skip_scanned: bool = False
    ocr_lang: str = "eng"
    ocr_deskew: bool = False
    ocr_force: bool = False
    ocr_timeout: int = 600
    continue_on_error: bool = False
    sections_only: bool = False
    sync_to_memory: bool = True

# Handle Extractor Root detection robustly
if os.environ.get("EXTRACTOR_ROOT"):
    EXTRACTOR_ROOT = Path(os.environ["EXTRACTOR_ROOT"])
else:
    # Attempt to find it relative to this file (working backwards from .pi/skills/extractor/extract.py)
    # File is at pi-mono/.pi/skills/extractor/extract.py
    # Extractor is at pi-mono/ (sibling of .pi) or developer workspace
    potential_root = Path(__file__).resolve().parents[4]
    if (potential_root / "src/extractor").exists():
        EXTRACTOR_ROOT = potential_root
    else:
        # Fallback to local workspace assumptions
        EXTRACTOR_ROOT = Path("/home/graham/workspace/experiments/extractor")

if not EXTRACTOR_ROOT.exists():
    print(f"FATAL: Extractor root not found at {EXTRACTOR_ROOT}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(EXTRACTOR_ROOT / "src"))

# Formats that use the full pipeline
PIPELINE_FORMATS = {".pdf"}

# Formats that use fast structured extraction
STRUCTURED_FORMATS = {".docx", ".html", ".htm", ".xml", ".pptx", ".xlsx", ".md", ".rst", ".epub"}

# Image formats (low parity without VLM, but still supported)
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

# Confidence threshold for auto-extraction
CONFIDENCE_THRESHOLD = 8


def detect_scanned_pdf(filepath: Path) -> Optional[Dict[str, Any]]:
    """Detect if a PDF is scanned (image-based)."""
    try:
        import fitz
        from extractor.pipeline.steps.s02_pymupdf_extractor import _detect_scanned_pdf

        with fitz.open(str(filepath)) as doc:
            return _detect_scanned_pdf(doc)
    except Exception:
        return None


def _docker_image_exists(image: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_ocrmypdf_available() -> Dict[str, Any]:
    """Ensure OCRmyPDF is available (local or docker). Pulls docker image if needed."""
    if shutil.which("ocrmypdf"):
        return {"available": True, "method": "local"}

    if not shutil.which("docker"):
        return {"available": False, "method": "none", "error": "docker_not_found"}

    if _docker_image_exists("extractor-ocr"):
        return {"available": True, "method": "docker", "image": "extractor-ocr"}
    if _docker_image_exists("jbarlow83/ocrmypdf"):
        return {"available": True, "method": "docker", "image": "jbarlow83/ocrmypdf"}

    try:
        pull = subprocess.run(
            ["docker", "pull", "jbarlow83/ocrmypdf"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if pull.returncode == 0:
            return {
                "available": True,
                "method": "docker",
                "image": "jbarlow83/ocrmypdf",
                "pulled": True,
            }
        return {
            "available": False,
            "method": "docker",
            "error": pull.stderr.strip() or pull.stdout.strip() or "pull_failed",
        }
    except Exception as e:
        return {"available": False, "method": "docker", "error": str(e)}


def maybe_prefetch_ocr_resources(filepath: Path) -> None:
    scanned_info = detect_scanned_pdf(filepath)
    if not scanned_info or not scanned_info.get("is_scanned"):
        return

    status = ensure_ocrmypdf_available()
    if status.get("available"):
        if status.get("pulled"):
            print("INFO: Pulled OCRmyPDF docker image for scanned PDF.", file=sys.stderr)
        else:
            print("INFO: OCRmyPDF available for scanned PDF.", file=sys.stderr)
    else:
        print(
            "WARN: Scanned PDF detected but OCRmyPDF not available "
            f"({status.get('error', 'unknown error')}).",
            file=sys.stderr,
        )


def format_error_guidance(error: str, filepath: Path = None, mode: str = None) -> str:
    """Generate actionable guidance based on error type."""
    guidance = []

    error_lower = error.lower()

    # LLM/API errors
    if any(kw in error_lower for kw in ["api", "chutes", "connection", "timeout", "503", "429", "unauthorized"]):
        guidance.extend([
            "Try these solutions:",
            "  1. Check CHUTES_API_KEY environment variable is set",
            "  2. Try --fast mode (no LLM required): ./run.sh file.pdf --fast",
            "  3. Check network connectivity to llm.chutes.ai",
            "  4. If Chutes is overloaded (503), wait and retry",
        ])

    # File/corrupt errors
    elif any(kw in error_lower for kw in ["corrupt", "invalid pdf", "unable to read", "file not found", "permission"]):
        guidance.extend([
            "File may be corrupted or inaccessible:",
            "  1. Verify the file exists and is readable",
            "  2. Try opening the PDF in a viewer to verify it's not corrupt",
            "  3. Check file permissions",
            "  4. If password-protected, the PDF must be unlocked first",
        ])

    # Memory/resource errors
    elif any(kw in error_lower for kw in ["memory", "oom", "killed", "resource"]):
        guidance.extend([
            "Resource limit exceeded:",
            "  1. Try --fast mode to reduce memory usage",
            "  2. Process smaller batches",
            "  3. Increase system memory/swap",
        ])

    # Import/dependency errors
    elif any(kw in error_lower for kw in ["import", "module", "not found", "no module"]):
        guidance.extend([
            "Missing dependency:",
            "  1. Activate the virtual environment: source .venv/bin/activate",
            "  2. Install dependencies: pip install -e .",
            "  3. Check PYTHONPATH includes extractor/src",
        ])

    # Pipeline errors
    elif "pipeline" in error_lower or "stage" in error_lower:
        guidance.extend([
            "Pipeline processing failed:",
            "  1. Try --fast mode: ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check the pipeline logs in output directory",
        ])

    # Generic fallback
    else:
        guidance.extend([
            "Troubleshooting steps:",
            "  1. Try --fast mode (no LLM): ./run.sh file.pdf --fast",
            "  2. Try with explicit preset: ./run.sh file.pdf --preset arxiv",
            "  3. Check CHUTES_API_KEY is set if using LLM features",
            "  4. Run sanity check: ./sanity.sh",
        ])

    return "\n".join(guidance)


# Find memory skill robustly
MEMORY_SKILL_PATH = Path(os.environ.get(
    "MEMORY_SKILL_PATH", 
    EXTRACTOR_ROOT.parent / "pi-mono/.pi/skills/memory/run.sh"
))
if not MEMORY_SKILL_PATH.exists():
    # Attempt local relative path
    MEMORY_SKILL_PATH = Path(__file__).resolve().parents[3] / "memory/run.sh"


def learn_to_memory(filepath: Path, result: Dict[str, Any], scope: str = "documents") -> bool:
    """Auto-learn extraction summary to memory for future recall."""
    if not MEMORY_SKILL_PATH.exists():
        return False

    if not result.get("success"):
        return False

    counts = result.get("counts", {})
    sections = counts.get("sections", 0)
    tables = counts.get("tables", 0)
    figures = counts.get("figures", 0)
    preset = result.get("preset", "auto")

    # Build problem and solution
    problem = f"What is in {filepath.name}?"
    solution_parts = [f"{sections} sections"]
    if tables > 0:
        solution_parts.append(f"{tables} tables")
    if figures > 0:
        solution_parts.append(f"{figures} figures")
    solution_parts.append(f"Preset: {preset}")

    solution = ", ".join(solution_parts)

    try:
        cmd = [
            str(MEMORY_SKILL_PATH),
            "learn",
            "--problem", problem,
            "--solution", solution,
        ]
        if scope:
            cmd.extend(["--scope", scope])

        subprocess.run(cmd, capture_output=True, timeout=30)
        return True
    except Exception:
        return False


def generate_batch_report(results: List[Dict[str, Any]], output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Generate comprehensive batch report with aggregates and downstream integration info."""
    batch_id = datetime.now().isoformat()

    # Categorize results
    succeeded = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    # Aggregate metrics
    total_sections = sum(r.get("counts", {}).get("sections", 0) for r in succeeded)
    total_tables = sum(r.get("counts", {}).get("tables", 0) for r in succeeded)
    total_figures = sum(r.get("counts", {}).get("figures", 0) for r in succeeded)

    # Build result entries
    result_entries = []
    for r in results:
        entry = {
            "file": r.get("file"),
            "status": "success" if r.get("success") else "failed",
        }
        if r.get("success"):
            entry.update({
                "preset": r.get("preset"),
                "mode": r.get("mode"),
                "sections": r.get("counts", {}).get("sections", 0),
                "tables": r.get("counts", {}).get("tables", 0),
                "figures": r.get("counts", {}).get("figures", 0),
                "output_dir": r.get("output_dir"),
                "markdown_path": r.get("outputs", {}).get("markdown"),
            })
        else:
            entry["error"] = r.get("error")
        result_entries.append(entry)

    report = {
        "batch_id": batch_id,
        "total_files": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": result_entries,
        "aggregates": {
            "total_sections": total_sections,
            "total_tables": total_tables,
            "total_figures": total_figures,
        },
        "ready_for": ["doc-to-qra", "edge-verifier", "episodic-archiver"],
    }

    # Write report to file if output_dir provided
    if output_dir:
        report_path = output_dir / "batch_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str))
        report["report_path"] = str(report_path)

    return report


def print_assessment_table(assessment: Dict[str, Any]) -> None:
    """Print a project agent friendly table comparing expected vs actual counts."""
    if not assessment:
        return

    print("\nExtraction Assessment (Stage 00 vs Reality)", file=sys.stderr)
    print("-" * 65, file=sys.stderr)
    print(f"{'Metric':<15} | {'Expected (Pg)':<15} | {'Actual (Count)':<15} | {'Status':<10}", file=sys.stderr)
    print("-" * 65, file=sys.stderr)
    
    for key, data in assessment.items():
        status_icon = "✅" if data.get("status") == "OK" else "❌"
        print(f"{key.capitalize():<15} | {data.get('expected_pages', 0):<15} | {data.get('actual_count', 0):<15} | {status_icon} {data.get('status')}", file=sys.stderr)
    print("-" * 65, file=sys.stderr)


def profile_pdf(filepath: Path) -> Dict[str, Any]:
    """Run s00_profile_detector to analyze PDF without extraction."""
    try:
        from extractor.pipeline.steps.s00_profile_detector import detect_preset
        return detect_preset(filepath)
    except Exception as e:
        return {"error": str(e)}


def format_profile_display(profile: Dict[str, Any], filename: str) -> str:
    """Format profile for human-readable display."""
    lines = [f"\nAnalyzing: {filename}"]

    # Layout and pages
    layout = profile.get("layout", {})
    cols = "multi-column" if layout.get("columns", 1) > 1 else "single-column"
    pages = profile.get("page_count", "?")
    lines.append(f"Detected: {cols} layout, {pages} pages")

    # Elements
    elements = profile.get("elements", {})
    parts = []
    if elements.get("tables"):
        parts.append("tables")
    if elements.get("figures"):
        parts.append("figures")
    if elements.get("formulas"):
        parts.append("formulas")
    if elements.get("requirements"):
        parts.append("requirements")

    if parts:
        lines.append(f"Contains: {', '.join(parts)}")

    return "\n".join(lines)


def get_preset_choices() -> List[Dict[str, Any]]:
    """Get available presets from registry."""
    try:
        from extractor.core.presets import PRESET_REGISTRY
        choices = []
        for name, config in PRESET_REGISTRY.items():
            desc = config.get("description", name)
            choices.append({"name": name, "description": desc})
        return choices
    except Exception:
        return [
            {"name": "arxiv", "description": "Academic papers (2-column, math)"},
            {"name": "requirements_spec", "description": "Engineering specs (REQ-xxx)"},
        ]


def recommend_mode(profile: Dict[str, Any]) -> str:
    """Determine recommended mode based on profile."""
    elements = profile.get("elements", {})
    layout = profile.get("layout", {})

    # Complex documents → accurate mode
    if (elements.get("tables") or elements.get("figures") or
        elements.get("formulas") or layout.get("columns", 1) > 1):
        return "accurate"

    # Simple text → fast mode
    return "fast"


def interactive_preset_prompt(profile: Dict[str, Any], filename: str) -> tuple[str, str]:
    """Show interactive prompt for preset selection. Returns (preset, mode)."""
    import sys

    # Display profile
    print(format_profile_display(profile, filename), file=sys.stderr)

    # Get presets
    presets = get_preset_choices()
    preset_match = profile.get("preset_match", {})
    matched = preset_match.get("matched")

    # Build options
    options = []
    default_idx = 1

    # Add matched preset first if available
    if matched:
        for p in presets:
            if p["name"] == matched:
                options.append(f"{p['name']} - {p['description']} [DETECTED]")
                break
        else:
            options.append(f"{matched} - Detected preset [DETECTED]")

    # Add other presets
    for p in presets:
        if p["name"] != matched:
            options.append(f"{p['name']} - {p['description']}")

    # Always include auto and fast
    options.append("auto - Let pipeline decide")
    options.append("fast - Quick extraction, no LLM")

    print("\nSelect extraction preset:", file=sys.stderr)
    for i, opt in enumerate(options, 1):
        marker = " [RECOMMENDED]" if i == default_idx else ""
        print(f"  [{i}] {opt}{marker}", file=sys.stderr)

    # Get user input
    try:
        choice = input(f"Enter choice [1-{len(options)}] (default: {default_idx}): ").strip()
        if not choice:
            choice_idx = default_idx
        else:
            choice_idx = int(choice)

        if choice_idx < 1 or choice_idx > len(options):
            choice_idx = default_idx

    except (ValueError, EOFError):
        choice_idx = default_idx

    selected = options[choice_idx - 1].split(" - ")[0]

    # Determine mode
    if selected == "fast":
        return None, "fast"
    elif selected == "auto":
        return None, recommend_mode(profile)
    else:
        return selected, recommend_mode(profile)


def extract_structured(filepath: Path) -> Dict[str, Any]:
    """Fast extraction for structured formats (DOCX, HTML, XML, etc.)."""
    try:
        from extractor.core.providers.registry import provider_from_filepath

        provider_cls = provider_from_filepath(str(filepath))
        # All providers now support the standard pattern
        provider = provider_cls()
        doc = provider.extract_document(str(filepath))

        return {
            "success": True,
            "mode": "structured",
            "format": filepath.suffix.lower(),
            "document": doc.model_dump(),
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "format": filepath.suffix.lower(),
            "guidance": format_error_guidance(error_msg, filepath),
        }


def extract_pipeline(
    filepath: Path,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """Full pipeline extraction for PDFs with preset detection."""

    # Build command
    python = str(EXTRACTOR_ROOT / ".venv" / "bin" / "python")
    cmd = [python, "-m", "extractor.pipeline", str(filepath)]

    # Output directory
    if opts.output_dir:
        out_path = Path(opts.output_dir)
    else:
        out_path = Path(tempfile.mkdtemp(prefix="extractor_"))

    cmd.extend(["--out", str(out_path)])

    # Mode flags
    if opts.mode == "fast":
        cmd.extend(["--offline-smoke"])  # Fast deterministic mode
    elif opts.mode == "accurate":
        cmd.extend(["--use-llm"])  # Enable LLM enhancement
    elif opts.mode == "offline":
        cmd.extend(["--offline-smoke"])

    # Flags mapping
    if opts.preset: cmd.extend(["--preset", opts.preset])
    if opts.auto_ocr is True: cmd.append("--auto-ocr")
    elif opts.auto_ocr is False: cmd.append("--no-auto-ocr")
    if opts.skip_scanned: cmd.append("--skip-scanned")
    if opts.ocr_lang: cmd.extend(["--ocr-lang", opts.ocr_lang])
    if opts.ocr_deskew: cmd.append("--ocr-deskew")
    if opts.ocr_force: cmd.append("--ocr-force")
    if opts.ocr_timeout: cmd.extend(["--ocr-timeout", str(opts.ocr_timeout)])
    if opts.continue_on_error: cmd.append("--continue-on-error")
    
    if opts.sections_only:
         cmd.extend([
            "--skip-tables05",
            "--skip-fig-descriptions",
            "--skip-annotator09a",
            "--skip-reqs07",
            "--skip-proving",
            "--skip-export",
         ])
    
    # Sync settings
    if opts.sync_to_memory:
        os.environ["SYNC_TO_MEMORY"] = "1"
    else:
        os.environ["SYNC_TO_MEMORY"] = "0"

    # Run pipeline
    try:
        env = {**os.environ}
        # Ensure PYTHONPATH includes extractor
        env["PYTHONPATH"] = str(EXTRACTOR_ROOT / "src") + ":" + env.get("PYTHONPATH", "")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(EXTRACTOR_ROOT),
            timeout=1800,  # 30 minute timeout for large documents
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Pipeline failed"
            return {
                "success": False,
                "error": error_msg,
                "stdout": result.stdout,
                "command": " ".join(cmd),
                "guidance": format_error_guidance(error_msg, filepath, mode),
            }

        # Gather outputs
        outputs = {}
        counts = {}

        # Markdown output
        md_candidates = [
            out_path / "10_markdown_exporter" / "document.md",
            out_path / "10_markdown_exporter" / f"{filepath.stem}.md",
        ]
        for md_path in md_candidates:
            if md_path.exists():
                outputs["markdown"] = str(md_path)
                break

        # Sections JSON
        sections_path = out_path / "04_section_builder" / "json_output" / "04_sections.json"
        if sections_path.exists():
            outputs["sections"] = str(sections_path)
            try:
                data = json.loads(sections_path.read_text())
                counts["sections"] = len(data.get("sections", []))
            except Exception:
                pass

        # Tables JSON
        tables_path = out_path / "05_table_extractor" / "json_output" / "05_tables.json"
        if tables_path.exists():
            outputs["tables"] = str(tables_path)
            try:
                data = json.loads(tables_path.read_text())
                counts["tables"] = len(data.get("tables", []))
            except Exception:
                pass

        # Figures JSON
        figures_path = out_path / "06_figure_extractor" / "json_output" / "06_figures.json"
        if figures_path.exists():
            outputs["figures"] = str(figures_path)
            try:
                data = json.loads(figures_path.read_text())
                counts["figures"] = len(data.get("figures", []))
            except Exception:
                pass

        # Report
        report_path = out_path / "14_report_generator" / "json_output" / "final_report.json"
        assessment = None
        if report_path.exists():
            outputs["report"] = str(report_path)
            try:
                report_data = json.loads(report_path.read_text())
                assessment = report_data.get("statistics", {}).get("assessment_comparison")
            except Exception:
                pass

        # Manifest
        manifest_path = out_path / "manifest.json"
        if manifest_path.exists():
            outputs["manifest"] = str(manifest_path)

        # Pipeline context (preset info)
        context_path = out_path / "pipeline_context.json"
        preset_name = None
        if context_path.exists():
            try:
                ctx = json.loads(context_path.read_text())
                preset_name = ctx.get("preset_name")
            except Exception:
                pass

        # If markdown requested, read and return it
        markdown_content = None
        if return_markdown and outputs.get("markdown"):
            try:
                markdown_content = Path(outputs["markdown"]).read_text()
            except Exception:
                pass

        response = {
            "success": True,
            "mode": mode,
            "preset": preset_name or preset,
            "output_dir": str(out_path),
            "outputs": outputs,
            "counts": counts,
            "assessment": assessment,
        }
        
        response["quality_signal"] = "UNKNOWN"
        if report_path.exists():
            try:
                report_data = json.loads(report_path.read_text())
                stats = report_data.get("statistics", {})
                response["quality_signal"] = stats.get("quality_signal", "UNKNOWN")
            except Exception:
                pass

        if markdown_content:
            response["markdown"] = markdown_content

        return response

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Pipeline timeout (30 minutes exceeded)",
            "guidance": format_error_guidance("timeout", filepath, mode),
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "guidance": format_error_guidance(error_msg, filepath, mode),
        }


def extract_pdf_with_collaboration(
    filepath: Path,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """Extract PDF with preset collaboration flow.

    Flow:
    1. If preset provided → use it directly
    2. If no preset:
       a. Run s00_profile_detector
       b. If confidence >= 8 → auto-extract
       c. If low confidence:
          - TTY: interactive prompt
          - Non-TTY: auto mode with warning
    """
    if opts.auto_ocr is not False:
        maybe_prefetch_ocr_resources(filepath)

    # If preset explicitly provided, skip detection
    if opts.preset:
        print(f"Using preset: {opts.preset}", file=sys.stderr)
        return extract_pipeline(filepath, opts)

    # Run profile detection
    profile = profile_pdf(filepath)

    if "error" in profile:
        # s00 failed, fall back to auto mode
        print(f"WARN: Profile detection failed: {profile['error']}. Using auto mode.", file=sys.stderr)
        return extract_pipeline(filepath, opts)

    # Check preset match confidence
    preset_match = profile.get("preset_match", {})
    matched_preset = preset_match.get("matched")
    confidence = preset_match.get("confidence", 0)

    # High confidence → auto-extract
    if matched_preset and confidence >= CONFIDENCE_THRESHOLD:
        recommended_mode = recommend_mode(profile)
        print(f"Detected preset: {matched_preset} (confidence: {confidence}). Extracting in {recommended_mode} mode...", file=sys.stderr)
        # Update opts with detection results
        opts.preset = matched_preset
        opts.mode = recommended_mode
        return extract_pipeline(filepath, opts)

    # Low confidence / no match
    is_tty = sys.stdin.isatty() and opts.interactive

    if is_tty:
        # Interactive prompt
        selected_preset, selected_mode = interactive_preset_prompt(profile, filepath.name)
        if selected_preset:
            print(f"Using preset: {selected_preset} in {selected_mode} mode", file=sys.stderr)
        else:
            print(f"Using {selected_mode} mode", file=sys.stderr)
        
        opts.preset = selected_preset
        opts.mode = selected_mode
        return extract_pipeline(filepath, opts)
    else:
        # Non-TTY: auto mode with warning
        auto_mode = recommend_mode(profile)
        print(f"WARN: Non-interactive environment. Using auto ({auto_mode}) mode for: {filepath.name}", file=sys.stderr)
        opts.mode = auto_mode
        return extract_pipeline(filepath, opts)


def extract(
    filepath: str,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """Universal extraction entry point. Routes to appropriate extractor."""
    path = Path(filepath)

    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {filepath}",
            "guidance": format_error_guidance("file not found", path),
        }

    suffix = path.suffix.lower()

    # Route by format
    if suffix in PIPELINE_FORMATS:
        return extract_pdf_with_collaboration(path, opts)
    elif suffix in STRUCTURED_FORMATS or suffix in IMAGE_FORMATS:
        return extract_structured(path)
    else:
        # Try structured extraction as fallback
        return extract_structured(path)


def run_toc_check(path: Path) -> Dict[str, Any]:
    """Run TOC integrity check on existing pipeline output.

    Args:
        path: Path to DuckDB file or pipeline output directory

    Returns:
        Dict with TOC integrity report
    """
    import duckdb
    from difflib import SequenceMatcher

    # Resolve DuckDB path
    if path.is_dir():
        db_path = path / "corpus.duckdb"
        if not db_path.exists():
            db_path = path / "pipeline.duckdb"
    else:
        db_path = path

    if not db_path.exists():
        return {"success": False, "error": f"DuckDB not found: {db_path}"}

    try:
        con = duckdb.connect(str(db_path), read_only=True)

        # Check if toc_entries table exists
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]

        if "toc_entries" not in table_names:
            return {
                "success": True,
                "has_toc": False,
                "message": "No toc_entries table found. PDF may not have bookmarks.",
                "integrity_score": None,
            }

        # Fetch TOC entries and sections
        toc_rows = con.execute(
            "SELECT id, level, title, page FROM toc_entries ORDER BY id"
        ).fetchall()

        section_rows = con.execute(
            "SELECT id, title, page_start FROM sections ORDER BY page_start, id"
        ).fetchall()

        con.close()

        if not toc_rows:
            return {
                "success": True,
                "has_toc": False,
                "message": "PDF has no TOC/bookmarks",
                "integrity_score": None,
            }

        # Build match report
        toc_entries = [{"id": r[0], "level": r[1], "title": r[2], "page": r[3]} for r in toc_rows]
        sections = [{"id": r[0], "title": r[1], "page_start": r[2]} for r in section_rows]

        matched = []
        missing = []

        for toc in toc_entries:
            best_match = None
            best_score = 0.0

            for sec in sections:
                # Title similarity
                title_sim = SequenceMatcher(
                    None,
                    toc["title"].lower(),
                    (sec["title"] or "").lower()
                ).ratio()

                # Page proximity (within 2 pages = bonus)
                page_diff = abs((toc["page"] or 0) - (sec["page_start"] or 0))
                page_bonus = 0.2 if page_diff <= 2 else 0.0

                score = title_sim + page_bonus

                if score > best_score and score >= 0.5:
                    best_score = score
                    best_match = {
                        "section_id": sec["id"],
                        "section_title": sec["title"],
                        "score": round(min(score, 1.0), 2),
                    }

            if best_match:
                matched.append({
                    "toc_title": toc["title"],
                    "toc_page": toc["page"],
                    "toc_level": toc["level"],
                    **best_match,
                })
            else:
                missing.append({
                    "toc_title": toc["title"],
                    "toc_page": toc["page"],
                    "toc_level": toc["level"],
                })

        # Calculate integrity score
        total_toc = len(toc_entries)
        matched_count = len(matched)
        integrity_score = round(matched_count / total_toc, 2) if total_toc > 0 else 1.0

        # Determine status
        if integrity_score >= 0.9:
            status = "EXCELLENT"
        elif integrity_score >= 0.7:
            status = "GOOD"
        elif integrity_score >= 0.5:
            status = "FAIR"
        else:
            status = "POOR"

        return {
            "success": True,
            "has_toc": True,
            "integrity_score": integrity_score,
            "status": status,
            "toc_entries_count": total_toc,
            "sections_count": len(sections),
            "matched_count": matched_count,
            "missing_count": len(missing),
            "matched": matched,
            "missing": missing,
            "message": f"TOC integrity: {status} ({integrity_score:.0%})",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Preset-First Agentic Document Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Collaboration Flow:
  For PDFs without --preset:
  1. Analyzes document with s00_profile_detector
  2. If high-confidence preset match (>=8) → auto-extracts
  3. If low-confidence → prompts for preset selection (interactive)
  4. In non-TTY/batch mode → uses auto mode with warning

Examples:
  %(prog)s paper.pdf                    # Auto mode with preset detection
  %(prog)s paper.pdf --fast             # Quick extraction (no LLM)
  %(prog)s paper.pdf --accurate         # Full LLM enhancement
  %(prog)s paper.pdf --preset arxiv     # Force preset (skip detection)
  %(prog)s paper.pdf --no-interactive   # Skip prompts, use auto mode
  %(prog)s paper.pdf --profile-only     # Profile only, no extraction
  %(prog)s scanned.pdf --auto-ocr       # OCR scanned PDFs (OCRmyPDF)
  %(prog)s report.docx                  # Structured format (fast path)
  %(prog)s ./pdfs/                      # Batch mode for directory
        """,
    )

    parser.add_argument("file", type=Path, help="Document or directory to extract")
    parser.add_argument("--out", "-o", type=Path, help="Output directory")
    parser.add_argument("--preset", help="Force preset (skip auto-detection)")

    # Mode group (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--fast", action="store_true", help="Fast mode (no LLM)")
    mode_group.add_argument("--accurate", action="store_true", help="Accurate mode (with LLM)")
    mode_group.add_argument("--offline", action="store_true", help="Offline mode (deterministic)")

    # Output format
    parser.add_argument("--markdown", action="store_true", help="Output markdown to stdout")
    parser.add_argument("--json", action="store_true", help="Output JSON (default)")

    # Collaboration flags
    parser.add_argument("--no-interactive", action="store_true",
                       help="Skip interactive prompts, use auto mode")
    parser.add_argument("--profile-only", action="store_true",
                       help="Run profile detection only, return JSON profile")
    parser.add_argument("--auto-ocr", dest="auto_ocr", action="store_true", default=None,
                       help="Run OCRmyPDF on scanned PDFs before extraction")
    parser.add_argument("--no-auto-ocr", dest="auto_ocr", action="store_false",
                       help="Disable OCRmyPDF preprocessing for scanned PDFs")
    parser.add_argument("--skip-scanned", action="store_true",
                       help="Skip scanned PDFs (log + write skip manifest)")
    parser.add_argument("--ocr-lang", default="eng",
                       help="OCR language(s) for OCRmyPDF (e.g., eng or eng+deu)")
    parser.add_argument("--ocr-deskew", action="store_true",
                       help="Deskew scanned pages during OCR preprocessing")
    parser.add_argument("--ocr-force", action="store_true",
                       help="Force OCR even if text exists (disables --skip-text)")
    parser.add_argument("--ocr-timeout", type=int, default=600,
                       help="OCRmyPDF timeout in seconds")
    parser.add_argument("--continue-on-error", action="store_true",
                       help="Allow pipeline to continue after failures")
    parser.add_argument("--sections-only", action="store_true",
                       help="Extract sections only (skip tables, figures, requirements, proving)")

    # Batch options
    parser.add_argument("--glob", default="**/*.pdf", help="Glob pattern for directory input")
    parser.add_argument("--report", choices=["json", "summary"], default="json",
                       help="Report format for batch mode")

    # Memory integration
    parser.add_argument("--learn", action="store_true", default=False,
                       help="Auto-learn extraction summaries to memory")
    parser.add_argument("--scope", default="documents",
                       help="Memory scope for --learn (default: documents)")

    # Edge verification (future feature)
    parser.add_argument("--verify-edges", action="store_true", default=False,
                       help="Run LLM-verified edge creation after extraction (requires CHUTES_API_KEY)")
    parser.add_argument("--edge-scope", choices=["intra", "cross", "both"], default="intra",
                       help="Edge verification scope: intra (within doc), cross (across docs), both")

    # TOC integrity check
    parser.add_argument("--toc-check", action="store_true", default=False,
                       help="Run TOC integrity check on existing pipeline output (requires DuckDB)")

    args = parser.parse_args()

    # Determine mode
    mode = "auto"
    if args.fast:
        mode = "fast"
    elif args.accurate:
        mode = "accurate"
    elif args.offline:
        mode = "offline"

    interactive = not args.no_interactive

    # Edge verification warning
    if args.verify_edges:
        print("WARN: --verify-edges is a future feature. Edge verification requires:", file=sys.stderr)
        print("  1. CHUTES_API_KEY environment variable", file=sys.stderr)
        print("  2. scillm package with parallel_acompletions_iter", file=sys.stderr)
        print("  See 02_TASKS.md Task 8 for implementation details.", file=sys.stderr)

    # TOC integrity check mode
    if args.toc_check:
        result = run_toc_check(args.file)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    # Profile-only mode
    if args.profile_only:
        if args.file.suffix.lower() != ".pdf":
            print(json.dumps({"error": "--profile-only only works with PDF files"}))
            sys.exit(1)

        profile = profile_pdf(args.file)

        # Flatten for agent consumption
        flat = {
            "file": str(args.file),
            "preset": profile.get("preset_match", {}).get("matched"),
            "confidence": profile.get("preset_match", {}).get("confidence", 0),
            "needs_new_preset": profile.get("preset_match", {}).get("needs_new_preset", True),
            "page_count": profile.get("page_count", 0),
            "layout": profile.get("layout", {}).get("style", "single"),
            "tables": profile.get("elements", {}).get("tables", False),
            "figures": profile.get("elements", {}).get("figures", False),
            "formulas": profile.get("elements", {}).get("formulas", False),
            "requirements": profile.get("elements", {}).get("requirements", False),
            "recommended_mode": recommend_mode(profile),
            "route": profile.get("route", "fast"),
        }
        print(json.dumps(flat, indent=2))
        sys.exit(0)

    # Build Extraction Options
    opts = ExtractionOptions(
        mode=mode,
        preset=args.preset,
        output_dir=args.out,
        return_markdown=args.markdown,
        interactive=interactive,
        auto_ocr=args.auto_ocr,
        skip_scanned=args.skip_scanned,
        ocr_lang=args.ocr_lang,
        ocr_deskew=args.ocr_deskew,
        ocr_force=args.ocr_force,
        ocr_timeout=args.ocr_timeout,
        continue_on_error=args.continue_on_error,
        sections_only=args.sections_only,
        sync_to_memory=args.learn,
    )

    # Handle directory input (batch mode)
    if args.file.is_dir():
        files = sorted(args.file.rglob(args.glob))
        if not files:
            print(json.dumps({"success": False, "error": f"No files matching {args.glob}"}))
            sys.exit(1)

        results = []
        for i, f in enumerate(files, 1):
            print(f"Processing [{i}/{len(files)}]: {f.name}", file=sys.stderr)
            # Update opts for specific subset if needed
            file_opts = dataclasses.replace(opts, output_dir=args.out / f.stem if args.out else None)
            result = extract(str(f), file_opts)
            results.append({"file": str(f), **result})

        # Generate batch report
        report = generate_batch_report(results, args.out)

        # Auto-learn to memory logic handled via SYNC_TO_MEMORY env in extract_pipeline
        # But we still want to report it
        if args.learn:
            report["memory_learned"] = report["succeeded"]
            print(f"Synced {report['succeeded']} extractions to memory", file=sys.stderr)

        if args.report == "summary":
            # Human-readable summary
            print(f"\nBatch Extraction Complete", file=sys.stderr)
            print(f"========================", file=sys.stderr)
            print(f"Total: {report['total_files']}", file=sys.stderr)
            print(f"Succeeded: {report['succeeded']}", file=sys.stderr)
            print(f"Failed: {report['failed']}", file=sys.stderr)
            print(f"\nAggregates:", file=sys.stderr)
            print(f"  Sections: {report['aggregates']['total_sections']}", file=sys.stderr)
            print(f"  Tables: {report['aggregates']['total_tables']}", file=sys.stderr)
            print(f"  Figures: {report['aggregates']['total_figures']}", file=sys.stderr)
            if report.get("report_path"):
                print(f"\nReport: {report['report_path']}", file=sys.stderr)
            print(f"\nReady for: {', '.join(report['ready_for'])}", file=sys.stderr)
            # Also print JSON to stdout for piping
            print(json.dumps(report, indent=2, default=str))
        else:
            # JSON output
            print(json.dumps(report, indent=2, default=str))

        sys.exit(0 if report['failed'] == 0 else 1)

    # Single file
    result = extract(str(args.file), opts)

    # Print assessment table if available
    if result.get("success") and result.get("assessment"):
        print_assessment_table(result["assessment"])

    # Auto-learn to memory if enabled
    if args.learn and result.get("success"):
        if learn_to_memory(args.file, result, args.scope):
            result["memory_learned"] = True
            print(f"Learned to memory (scope: {args.scope})", file=sys.stderr)

    # Output
    if args.markdown and result.get("markdown"):
        print(result["markdown"])
    else:
        print(json.dumps(result, indent=2, default=str))

    # Print guidance to stderr on failure for interactive users
    if not result.get("success") and result.get("guidance"):
        print(f"\n{result['guidance']}", file=sys.stderr)

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
