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
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

EXTRACTOR_ROOT = Path("/home/graham/workspace/experiments/extractor")
sys.path.insert(0, str(EXTRACTOR_ROOT / "src"))

# Formats that use the full pipeline
PIPELINE_FORMATS = {".pdf"}

# Formats that use fast structured extraction
STRUCTURED_FORMATS = {".docx", ".html", ".htm", ".xml", ".pptx", ".xlsx", ".md", ".rst", ".epub"}

# Image formats (low parity without VLM, but still supported)
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

# Confidence threshold for auto-extraction
CONFIDENCE_THRESHOLD = 8


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


MEMORY_SKILL_PATH = Path("/home/graham/workspace/experiments/pi-mono/.pi/skills/memory/run.sh")


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
    output_dir: Optional[Path] = None,
    mode: str = "auto",
    preset: Optional[str] = None,
    return_markdown: bool = False,
) -> Dict[str, Any]:
    """Full pipeline extraction for PDFs with preset detection."""

    # Build command
    python = str(EXTRACTOR_ROOT / ".venv" / "bin" / "python")
    cmd = [python, "-m", "extractor.pipeline", str(filepath)]

    # Output directory
    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = Path(tempfile.mkdtemp(prefix="extractor_"))

    cmd.extend(["--out", str(out_path)])

    # Mode flags
    if mode == "fast":
        cmd.extend(["--offline-smoke"])  # Fast deterministic mode
    elif mode == "accurate":
        cmd.extend(["--use-llm"])  # Enable LLM enhancement
    elif mode == "offline":
        cmd.extend(["--offline-smoke"])
    # "auto" is the default - no extra flags needed

    # Preset override (skip s00 auto-detection)
    if preset:
        cmd.extend(["--preset", preset])

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
        if report_path.exists():
            outputs["report"] = str(report_path)

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
        }

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
    output_dir: Optional[Path] = None,
    mode: str = "auto",
    preset: Optional[str] = None,
    return_markdown: bool = False,
    interactive: bool = True,
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
    # If preset explicitly provided, skip detection
    if preset:
        print(f"Using preset: {preset}", file=sys.stderr)
        return extract_pipeline(filepath, output_dir, mode, preset, return_markdown)

    # Run profile detection
    profile = profile_pdf(filepath)

    if "error" in profile:
        # s00 failed, fall back to auto mode
        print(f"WARN: Profile detection failed: {profile['error']}. Using auto mode.", file=sys.stderr)
        return extract_pipeline(filepath, output_dir, mode, None, return_markdown)

    # Check preset match confidence
    preset_match = profile.get("preset_match", {})
    matched_preset = preset_match.get("matched")
    confidence = preset_match.get("confidence", 0)

    # High confidence → auto-extract
    if matched_preset and confidence >= CONFIDENCE_THRESHOLD:
        recommended_mode = recommend_mode(profile)
        print(f"Detected preset: {matched_preset} (confidence: {confidence}). Extracting in {recommended_mode} mode...", file=sys.stderr)
        return extract_pipeline(filepath, output_dir, recommended_mode, matched_preset, return_markdown)

    # Low confidence / no match
    is_tty = sys.stdin.isatty() and interactive

    if is_tty:
        # Interactive prompt
        selected_preset, selected_mode = interactive_preset_prompt(profile, filepath.name)
        if selected_preset:
            print(f"Using preset: {selected_preset} in {selected_mode} mode", file=sys.stderr)
        else:
            print(f"Using {selected_mode} mode", file=sys.stderr)
        return extract_pipeline(filepath, output_dir, selected_mode, selected_preset, return_markdown)
    else:
        # Non-TTY: auto mode with warning
        auto_mode = recommend_mode(profile)
        print(f"WARN: Non-interactive environment. Using auto ({auto_mode}) mode for: {filepath.name}", file=sys.stderr)
        return extract_pipeline(filepath, output_dir, auto_mode, None, return_markdown)


def extract(
    filepath: str,
    output_dir: Optional[str] = None,
    mode: str = "auto",
    preset: Optional[str] = None,
    return_markdown: bool = False,
    interactive: bool = True,
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
    out_path = Path(output_dir) if output_dir else None

    # Route by format
    if suffix in PIPELINE_FORMATS:
        return extract_pdf_with_collaboration(
            path, out_path, mode, preset, return_markdown, interactive
        )
    elif suffix in STRUCTURED_FORMATS or suffix in IMAGE_FORMATS:
        return extract_structured(path)
    else:
        # Try structured extraction as fallback
        return extract_structured(path)


def main():
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

    # Handle directory input (batch mode)
    if args.file.is_dir():
        files = sorted(args.file.rglob(args.glob))
        if not files:
            print(json.dumps({"success": False, "error": f"No files matching {args.glob}"}))
            sys.exit(1)

        results = []
        for i, f in enumerate(files, 1):
            print(f"Processing [{i}/{len(files)}]: {f.name}", file=sys.stderr)
            result = extract(
                str(f),
                output_dir=str(args.out / f.stem) if args.out else None,
                mode=mode,
                preset=args.preset,
                return_markdown=args.markdown,
                interactive=interactive,
            )
            results.append({"file": str(f), **result})

        # Generate batch report
        report = generate_batch_report(results, args.out)

        # Auto-learn to memory if enabled
        if args.learn:
            learned_count = 0
            for r in results:
                if r.get("success"):
                    if learn_to_memory(Path(r["file"]), r, args.scope):
                        learned_count += 1
            report["memory_learned"] = learned_count
            print(f"Learned {learned_count} extractions to memory (scope: {args.scope})", file=sys.stderr)

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
    result = extract(
        str(args.file),
        output_dir=str(args.out) if args.out else None,
        mode=mode,
        preset=args.preset,
        return_markdown=args.markdown,
        interactive=interactive,
    )

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
