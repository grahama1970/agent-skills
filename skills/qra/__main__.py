#!/usr/bin/env python3
"""QRA CLI - Thin entry point for Question-Reasoning-Answer extraction.

This is the main CLI interface. Core logic lives in:
- config.py - Constants and configuration
- utils.py - Logging, progress, text processing
- extractor.py - LLM-based Q&A extraction
- validator.py - Grounding validation
- storage.py - Memory storage

Usage:
    python qra.py --file document.md --scope research
    python qra.py --file notes.txt --context "security expert" --dry-run
    python qra.py --from-extractor /path/to/extractor/results --scope research
    cat transcript.txt | python qra.py --scope meetings

Developer hook:
    Set QRA_CHECK_IMPORTS=1 to perform a lightweight import-graph sanity check
    at startup to detect circular imports during development.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Best-effort .env loading
try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

# Ensure qra package is importable
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

# Import modular components
from qra.config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_GROUNDING_THRESHOLD,
    DEFAULT_MAX_SECTION_CHARS,
    SKIP_GROUNDING,
)
from qra.extractor import extract_qra_batch
from qra.storage import batch_store_qras
from qra.utils import build_sections, log, status_panel
from qra.validator import check_grounding

# Extractor adapter (optional, for --from-extractor integration)
_HAS_EXTRACTOR_ADAPTER = False
try:
    from extractor_adapter import load_extractor_sections, get_extractor_metadata

    _HAS_EXTRACTOR_ADAPTER = True
except ImportError:
    pass


# =============================================================================
# Import Graph Sanity Check (Developer Hook)
# =============================================================================


def _check_import_graph() -> bool:
    """Attempt imports in allowed directions to catch circular import issues.

    Only runs if QRA_CHECK_IMPORTS=1 is set in environment.
    This is a development tool, not for production use.

    Returns:
        True if all imports succeed
    """
    import qra.config  # noqa: F401
    import qra.utils  # noqa: F401
    import qra.extractor  # noqa: F401
    import qra.validator  # noqa: F401
    import qra.storage  # noqa: F401

    return True


# Run import check if enabled (before main logic)
if os.getenv("QRA_CHECK_IMPORTS") == "1":
    try:
        _check_import_graph()
    except Exception as _e:
        print(f"[qra] Import graph check failed: {_e}", file=sys.stderr)


# =============================================================================
# Main Extract Function
# =============================================================================


def extract_qra(
    *,
    text: Optional[str] = None,
    file_path: Optional[str] = None,
    extractor_results: Optional[str] = None,
    prebuilt_sections: Optional[List[Tuple[str, str]]] = None,
    scope: str = "research",
    context: Optional[str] = None,
    context_file: Optional[str] = None,
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS,
    dry_run: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    validate_grounding: bool = True,
    grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> Dict[str, Any]:
    """Extract QRA pairs from text.

    Args:
        text: Text content to extract from
        file_path: File to read text from
        extractor_results: Path to extractor results dir (uses Stage 10 output)
        prebuilt_sections: Pre-built sections as [(title, text), ...]
        scope: Memory scope for storage
        context: Domain context/persona for focused extraction
        context_file: Read context from file
        max_section_chars: Max chars per section
        dry_run: Show QRAs without storing
        concurrency: Parallel LLM requests
        validate_grounding: Filter ungrounded answers
        grounding_threshold: Min similarity (0-1)

    Returns:
        Summary dict with extracted QRAs
    """
    # Determine source and get sections
    sections = None
    source = None

    # Priority 1: Extractor results (Stage 10 integration)
    if extractor_results:
        if not _HAS_EXTRACTOR_ADAPTER:
            raise ImportError(
                "extractor_adapter not found. "
                "Ensure extractor_adapter.py is in the same directory."
            )
        sections = load_extractor_sections(
            extractor_results,
            max_section_chars=max_section_chars,
        )
        source = f"extractor:{Path(extractor_results).name}"
        # Try to get metadata for context enrichment
        try:
            meta = get_extractor_metadata(extractor_results)
            if meta and not context:
                preset = meta.get(
                    "preset", meta.get("preset_match", {}).get("matched", "")
                )
                if preset:
                    context = f"Document processed with {preset} preset"
        except Exception:
            pass

    # Priority 2: Pre-built sections (API usage)
    elif prebuilt_sections:
        sections = prebuilt_sections
        source = "prebuilt"

    # Priority 3: File path
    elif file_path:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        source = Path(file_path).name

    # Priority 4: Direct text
    elif text:
        source = "text"

    # Priority 5: Stdin
    else:
        if not sys.stdin.isatty():
            text = sys.stdin.read()
            source = "stdin"
        else:
            raise ValueError(
                "Must provide --text, --file, --from-extractor, or pipe content"
            )

    # Build sections if not already provided
    if sections is None:
        if not text or not text.strip():
            return {"extracted": 0, "stored": 0, "error": "Empty content"}
        sections = build_sections(text, max_section_chars=max_section_chars)

    if not sections:
        return {"extracted": 0, "stored": 0, "error": "No sections found"}

    # Get context from file if specified
    if context_file:
        context = Path(context_file).read_text(encoding="utf-8").strip()

    # Calculate total chars for display
    total_chars = sum(len(s[1]) for s in sections)

    status_panel(
        "QRA Extraction",
        {
            "Source": source,
            "Content": f"{total_chars:,} chars in {len(sections)} sections",
            "Context": (context[:40] + "...") if context else "(none)",
            "Scope": scope,
        },
    )

    log(f"Processing {len(sections)} sections")

    # Extract QRAs
    all_qa = asyncio.run(
        extract_qra_batch(
            sections,
            source=source,
            context=context,
            concurrency=concurrency,
        )
    )

    log(f"Extracted {len(all_qa)} QRAs", style="bold")

    # Grounding validation
    if validate_grounding and all_qa:
        all_qa, kept, filtered = check_grounding(
            all_qa, sections, grounding_threshold
        )
        if filtered > 0:
            log(
                f"Grounding: {kept} kept, {filtered} filtered "
                f"(threshold={grounding_threshold})",
                style="yellow",
            )
        else:
            log(f"Grounding: all {kept} validated", style="green")

    # Store or dry-run
    stored = batch_store_qras(all_qa, scope, source=source, dry_run=dry_run)

    status_panel(
        "QRA Complete",
        {
            "Extracted": len(all_qa),
            "Stored": stored if not dry_run else "(dry run)",
            "Sections": len(sections),
        },
    )

    return {
        "extracted": len(all_qa),
        "stored": stored,
        "sections": len(sections),
        "source": source,
        "scope": scope,
        "qra_pairs": all_qa if dry_run else all_qa[:5],
    }


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract Question-Reasoning-Answer pairs from text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file document.md --scope research
  %(prog)s --file notes.txt --context "security expert" --dry-run
  %(prog)s --from-extractor /path/to/extractor/results --scope research
  cat transcript.txt | %(prog)s --scope meetings

Extractor integration:
  The --from-extractor flag consumes Stage 10 output (10_flattened_data.json)
  from the extractor project, per HAPPYPATH_GUIDE.md specifications.
  This preserves section structure, table/figure descriptions, and metadata.

Environment variables for tuning (optional):
  QRA_CONCURRENCY       Parallel LLM requests (default: 6)
  QRA_GROUNDING_THRESH  Grounding similarity threshold (default: 0.6)
  QRA_NO_GROUNDING      Set to 1 to skip grounding validation
""",
    )

    # === Essential flags (agent-facing) ===
    parser.add_argument(
        "--file", dest="file_path", help="Text/markdown file to extract from"
    )
    parser.add_argument("--text", help="Raw text to extract from")
    parser.add_argument(
        "--from-extractor",
        dest="extractor_results",
        help="Path to extractor results directory (uses Stage 10 output)",
    )
    parser.add_argument(
        "--scope", default="research", help="Memory scope (default: research)"
    )
    parser.add_argument(
        "--context",
        help="Domain focus, e.g. 'ML researcher' or 'security expert'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview QRAs without storing to memory",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    # === Hidden expert flags (use env vars instead) ===
    parser.add_argument(
        "--context-file", dest="context_file", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--max-section-chars",
        type=int,
        default=DEFAULT_MAX_SECTION_CHARS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("QRA_CONCURRENCY", str(DEFAULT_CONCURRENCY))),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--validate-grounding",
        dest="validate_grounding",
        action="store_true",
        default=not SKIP_GROUNDING,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-validate-grounding",
        dest="validate_grounding",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--grounding-threshold",
        type=float,
        default=float(
            os.getenv("QRA_GROUNDING_THRESH", str(DEFAULT_GROUNDING_THRESHOLD))
        ),
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    try:
        result = extract_qra(
            text=args.text,
            file_path=args.file_path,
            extractor_results=args.extractor_results,
            scope=args.scope,
            context=args.context,
            context_file=args.context_file,
            max_section_chars=args.max_section_chars,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            validate_grounding=args.validate_grounding,
            grounding_threshold=args.grounding_threshold,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"Extracted: {result['extracted']} QRAs "
                f"from {result['sections']} sections"
            )
            print(f"Stored: {result['stored']} in scope '{result['scope']}'")
            if result.get("qra_pairs"):
                print("\nSample QRAs:")
                for qra in result["qra_pairs"][:2]:
                    q = qra.get("question", qra.get("problem", ""))[:70]
                    a = qra.get("answer", qra.get("solution", ""))[:70]
                    print(f"  Q: {q}...")
                    print(f"  A: {a}...")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
