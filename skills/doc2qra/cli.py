#!/usr/bin/env python3
"""doc2qra: Convert documents into QRA pairs with summaries.

Converts PDF, URL, or text into Question-Reasoning-Answer pairs
with a document summary. Stores to memory for later recall.

Usage:
    python -m doc2qra --file paper.pdf --scope research
    python -m doc2qra --url https://example.com/doc --scope web
    python -m doc2qra --file paper.pdf --summary-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

# Use relative imports within the package
from .config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_GROUNDING_THRESHOLD,
    DEFAULT_MAX_SECTION_CHARS,
)
from .memory_ops import store_qa
from .pdf_handler import read_file
from .qra_generator import (
    extract_qa_heuristic,
    extract_qra_batch,
    extract_qra_llm,
    generate_summary,
    _fallback_heuristic_extraction,
)
from .grounding import validate_and_filter_qras
from .text_handler import (
    build_sections,
    extract_code_blocks,
    parse_code_with_treesitter,
)
from .url_handler import fetch_url
from .utils import iter_with_progress, log, status_panel


# =============================================================================
# Main Distill Logic
# =============================================================================


def distill(
    *,
    url: str = None,
    text: str = None,
    file_path: str = None,
    scope: str = "research",
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS,
    dry_run: bool = False,
    no_llm: bool = False,
    extract_code: bool = True,
    use_treesitter: bool = False,
    mode: str = "fast",
    show_preflight: bool = False,
    batch: bool = True,
    concurrency: int = DEFAULT_CONCURRENCY,
    validate_grounding: bool = True,
    grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD,
    context: str = None,
    context_file: str = None,
    sections_only: bool = False,
    summary_only: bool = False,
) -> Dict[str, Any]:
    """Convert document into Q&A pairs with summary and store in memory.

    Args:
        url: URL to fetch and distill
        text: Raw text to distill
        file_path: File path to read and distill
        scope: Memory scope to store in
        max_section_chars: Maximum characters per section
        dry_run: If True, preview without storing
        no_llm: If True, use heuristic extraction only
        extract_code: If True, extract code blocks separately
        use_treesitter: If True, parse code with treesitter
        mode: PDF extraction mode - "fast", "accurate", or "auto"
        show_preflight: If True, show PDF preflight assessment
        batch: If True, use parallel batch LLM calls
        concurrency: Max parallel LLM requests
        validate_grounding: If True, filter ungrounded QRAs
        grounding_threshold: Minimum similarity score for grounding
        context: Domain context/persona for focused extraction
        context_file: File path to read context from
        sections_only: If True, only extract sections
        summary_only: If True, only generate document summary

    Returns:
        Dict with summary, QRA pairs, and storage stats
    """
    # Load context from file if specified
    if context_file:
        context = Path(context_file).read_text(encoding="utf-8").strip()

    # Get content
    if url:
        content = fetch_url(url)
        source = urlparse(url).netloc + urlparse(url).path[:30]
    elif file_path:
        content = read_file(file_path, mode=mode, show_preflight=show_preflight)
        source = Path(file_path).name
    elif text:
        content = text
        source = "text"
    else:
        raise ValueError("Must provide --url, --file, or --text")

    if not content.strip():
        return {"stored": 0, "source": source, "error": "Empty content"}

    # Show initial status
    status_info = {
        "Source": source,
        "Content size": f"{len(content):,} chars",
        "Mode": mode,
        "Scope": scope,
    }
    if context:
        status_info["Context"] = (context[:40] + "...") if len(context) > 40 else context
    status_panel("doc2qra Starting", status_info)

    # Generate document summary (always, unless sections_only)
    summary = ""
    if not sections_only:
        log("Generating document summary...", style="bold blue")
        summary = generate_summary(content, context=context)
        if summary:
            log(f"Summary generated: {len(summary)} chars", style="green")

    # Handle summary-only mode
    if summary_only:
        status_panel("Summary Generated", {
            "Source": source,
            "Summary length": f"{len(summary)} chars",
        })
        return {
            "summary": summary,
            "source": source,
            "scope": scope,
        }

    # Extract code blocks first (before section splitting)
    code_qa: List[Dict[str, Any]] = []
    if extract_code:
        code_blocks = extract_code_blocks(content)
        log(f"Found {len(code_blocks)} code blocks")

        for idx, block in enumerate(iter_with_progress(code_blocks, desc="Parsing code blocks")):
            language = block["language"]
            code = block["code"]

            # Optionally parse with treesitter for richer extraction
            symbols = []
            if use_treesitter and language not in ("text", "output", ""):
                symbols = parse_code_with_treesitter(code, language)

            if symbols:
                # Create Q&A for each symbol
                for sym in symbols:
                    if sym.get("kind") in ("function", "class", "method"):
                        problem = f"[{source}][{language}] What does {sym['kind']} `{sym['name']}` do?"
                        solution = f"```{language}\n{sym.get('content', sym.get('signature', code[:500]))}\n```"
                        if sym.get("docstring"):
                            solution = f"{sym['docstring']}\n\n{solution}"
                        code_qa.append({
                            "problem": problem,
                            "solution": solution,
                            "type": "code",
                            "language": language,
                            "symbol": sym["name"],
                            "kind": sym["kind"],
                            "source": source,
                        })
            else:
                # Store code block as-is
                problem = f"[{source}][{language}] Code example"
                if len(code) < 100:
                    problem = f"[{source}][{language}] {code.split(chr(10))[0][:60]}"
                solution = f"```{language}\n{code}\n```"
                code_qa.append({
                    "problem": problem,
                    "solution": solution,
                    "type": "code",
                    "language": language,
                    "source": source,
                })

        log(f"{len(code_qa)} code Q&A pairs created")

    # Build sections (respects document structure)
    sections = build_sections(content, max_section_chars=max_section_chars)
    log(f"Split into {len(sections)} sections")

    # If sections_only, return early with just the sections
    if sections_only:
        status_panel("Sections Extracted", {
            "Source": source,
            "Sections": len(sections),
            "Code blocks": len(code_qa) if extract_code else 0,
        })
        sections_data = [
            {"title": title, "content": sect_content, "index": idx}
            for idx, (title, sect_content) in enumerate(sections)
        ]
        return {
            "sections": sections_data,
            "section_count": len(sections),
            "code_blocks": len(code_qa) if extract_code else 0,
            "source": source,
        }

    # Extract Q&A from each section
    all_qa: List[Dict[str, Any]] = []

    if no_llm or os.getenv("DISTILL_NO_LLM"):
        # Heuristic mode - sequential
        log("Extracting QRA using heuristic method")
        for idx, (section_title, section_content) in enumerate(iter_with_progress(sections, desc="Extracting QRA")):
            qa_pairs = extract_qa_heuristic(section_content, source=source, section_title=section_title)
            for qa in qa_pairs:
                qa["section_idx"] = idx
                qa["section_title"] = section_title
                qa["source"] = source
                qa["type"] = "text"
                all_qa.append(qa)
    elif batch:
        # Batch mode - parallel LLM calls via scillm
        log(f"Extracting QRA using batch LLM (concurrency={concurrency})", style="bold blue")
        try:
            all_qa = asyncio.run(
                extract_qra_batch(sections, source=source, concurrency=concurrency, timeout=60, context=context)
            )
        except Exception as e:
            import traceback
            log(f"Batch extraction error: {e}", style="red")
            log(f"Traceback: {traceback.format_exc()[:500]}", style="dim")
            log("Falling back to heuristic extraction", style="yellow")
            all_qa = _fallback_heuristic_extraction(sections, source)
    else:
        # Sequential LLM mode
        log("Extracting QRA using sequential LLM")
        for idx, (section_title, section_content) in enumerate(iter_with_progress(sections, desc="Extracting QRA")):
            qa_pairs = extract_qra_llm(section_content, source=source, section_title=section_title)
            for qa in qa_pairs:
                qa["section_idx"] = idx
                qa["section_title"] = section_title
                qa["source"] = source
                qa["type"] = "text"
                all_qa.append(qa)

    # Combine text and code Q&A
    all_qa.extend(code_qa)
    log(f"{len(all_qa)} total Q&A pairs extracted", style="bold")

    # Grounding validation - filter out hallucinated QRAs
    if validate_grounding and all_qa:
        all_qa = validate_and_filter_qras(
            all_qa, sections,
            validate_grounding=True,
            grounding_threshold=grounding_threshold
        )

    # Store or dry-run
    stored = 0
    if dry_run:
        log(f"DRY RUN - would store {len(all_qa)} pairs", style="yellow")
    else:
        log(f"Storing {len(all_qa)} pairs to scope '{scope}'")
        for qa in iter_with_progress(all_qa, desc="Storing to memory"):
            tags = ["distilled", source.split("/")[0] if "/" in source else source]
            if qa.get("type") == "code":
                tags.append("code")
                if qa.get("language"):
                    tags.append(qa["language"])
            if store_qa(qa["problem"], qa["solution"], scope, tags=tags):
                stored += 1

    # Final summary
    status_panel("doc2qra Complete", {
        "Summary": f"{len(summary)} chars" if summary else "N/A",
        "Extracted": f"{len(all_qa)} Q&A pairs",
        "Stored": f"{stored}" if not dry_run else "(dry run)",
        "Sections": len(sections),
        "Code blocks": len(code_qa) if extract_code else 0,
        "Scope": scope,
    })

    return {
        "summary": summary,
        "stored": stored,
        "extracted": len(all_qa),
        "sections": len(sections),
        "code_blocks": len(code_qa) if extract_code else 0,
        "text_qa": len(all_qa) - len(code_qa) if extract_code else len(all_qa),
        "source": source,
        "scope": scope,
        "qra_pairs": all_qa if dry_run else all_qa[:5],  # Sample in non-dry-run
    }


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Distill PDF/URL/text into Q&A pairs for memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file paper.pdf --scope research
  %(prog)s --file paper.pdf --context "ML researcher" --dry-run
  %(prog)s --url https://example.com/doc --scope web

Environment variables for tuning (optional):
  DISTILL_CONCURRENCY      Parallel LLM requests (default: 6)
  DISTILL_GROUNDING_THRESH Grounding similarity threshold (default: 0.6)
  DISTILL_NO_GROUNDING     Set to 1 to skip grounding validation
  DISTILL_PDF_MODE         PDF mode: fast, accurate, auto (default: fast)
"""
    )

    # === Essential flags (agent-facing) ===
    parser.add_argument("--file", dest="file_path", help="PDF, markdown, or text file to distill")
    parser.add_argument("--url", help="URL to fetch and distill")
    parser.add_argument("--text", help="Raw text to distill")
    parser.add_argument("--scope", default="research", help="Memory scope (default: research)")
    parser.add_argument("--context", help="Domain focus, e.g. 'ML researcher' or 'security expert'")
    parser.add_argument("--dry-run", action="store_true", help="Preview Q&A without storing to memory")
    parser.add_argument("--json", action="store_true", help="Output as JSON (includes summary)")
    parser.add_argument("--sections-only", action="store_true",
                        help="Only extract sections (no Q&A generation)")
    parser.add_argument("--summary-only", action="store_true",
                        help="Only generate document summary (no Q&A)")

    # === Hidden expert flags (use env vars instead) ===
    parser.add_argument("--context-file", dest="context_file", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=["fast", "accurate", "auto"],
                        default=os.getenv("DISTILL_PDF_MODE", "fast"), help=argparse.SUPPRESS)
    parser.add_argument("--preflight", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-section-chars", type=int, default=DEFAULT_MAX_SECTION_CHARS, help=argparse.SUPPRESS)
    parser.add_argument("--no-llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-code", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--treesitter", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--batch", dest="batch", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--no-batch", dest="batch", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--concurrency", type=int,
                        default=int(os.getenv("DISTILL_CONCURRENCY", str(DEFAULT_CONCURRENCY))), help=argparse.SUPPRESS)
    parser.add_argument("--validate-grounding", dest="validate_grounding", action="store_true",
                        default=not os.getenv("DISTILL_NO_GROUNDING"), help=argparse.SUPPRESS)
    parser.add_argument("--no-validate-grounding", dest="validate_grounding",
                        action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--grounding-threshold", type=float,
                        default=float(os.getenv("DISTILL_GROUNDING_THRESH", str(DEFAULT_GROUNDING_THRESHOLD))),
                        help=argparse.SUPPRESS)

    args = parser.parse_args()

    if not any([args.url, args.text, args.file_path]):
        parser.error("Must provide --url, --file, or --text")

    try:
        result = distill(
            url=args.url,
            text=args.text,
            file_path=args.file_path,
            scope=args.scope,
            max_section_chars=args.max_section_chars,
            dry_run=args.dry_run,
            no_llm=args.no_llm,
            extract_code=not args.no_code,
            use_treesitter=args.treesitter,
            mode=args.mode,
            show_preflight=args.preflight,
            batch=args.batch,
            concurrency=args.concurrency,
            validate_grounding=args.validate_grounding,
            grounding_threshold=args.grounding_threshold,
            context=args.context,
            context_file=args.context_file,
            sections_only=args.sections_only,
            summary_only=args.summary_only,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        elif args.summary_only:
            # Summary-only output
            print(f"Source: {result['source']}")
            print(f"\n{'='*60}")
            print("SUMMARY")
            print('='*60)
            print(result.get("summary", "No summary generated"))
        elif args.sections_only:
            # Sections-only output
            print(f"Extracted: {result['section_count']} sections from {result['source']}")
            if result.get("sections"):
                print("\nSections:")
                for sec in result["sections"][:5]:
                    title = sec.get("title", "(untitled)")[:50]
                    content_preview = sec.get("content", "")[:60].replace("\n", " ")
                    print(f"  [{sec['index']}] {title}")
                    print(f"      {content_preview}...")
                if len(result["sections"]) > 5:
                    print(f"  ... and {len(result['sections']) - 5} more")
        else:
            # Full output with summary and QRAs
            print(f"Extracted: {result['extracted']} Q&A pairs from {result['sections']} sections")
            print(f"Stored: {result['stored']} pairs in scope '{result['scope']}'")
            print(f"Source: {result['source']}")

            # Show summary
            if result.get("summary"):
                print(f"\n{'='*60}")
                print("SUMMARY")
                print('='*60)
                print(result["summary"])

            # Show sample QRAs
            if result.get("qra_pairs"):
                print(f"\n{'='*60}")
                print("SAMPLE Q&A")
                print('='*60)
                for qa in result["qra_pairs"][:2]:
                    print(f"  Q: {qa['problem'][:80]}...")
                    print(f"  A: {qa['solution'][:80]}...")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
