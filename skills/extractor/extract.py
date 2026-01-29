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
import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict

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
    generate_batch_report,
    print_assessment_table,
    print_batch_summary,
)
from extractor_skill.memory_integration import learn_to_memory
from extractor_skill.pdf_extractor import (
    extract_pdf_with_collaboration,
    profile_pdf,
    recommend_mode,
)
from extractor_skill.structured_extractor import extract_structured
from extractor_skill.toc_checker import run_toc_check
from extractor_skill.utils import format_error_guidance


def extract(
    filepath: str,
    opts: ExtractionOptions,
) -> Dict[str, Any]:
    """
    Universal extraction entry point. Routes to appropriate extractor.

    Args:
        filepath: Path to document
        opts: Extraction options

    Returns:
        Dict with extraction result
    """
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


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Preset-First Agentic Document Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Collaboration Flow:
  For PDFs without --preset:
  1. Analyzes document with s00_profile_detector
  2. If high-confidence preset match (>=8) -> auto-extracts
  3. If low-confidence -> prompts for preset selection (interactive)
  4. In non-TTY/batch mode -> uses auto mode with warning

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
            print_batch_summary(report)
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
