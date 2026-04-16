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

from loguru import logger

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import typer

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

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
from .persona_gate import resolve_persona_context, select_persona_by_bridges
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


def _infer_collection(scope: str, source: str) -> str:
    """Infer taxonomy collection from scope/source context."""
    scope_map = {
        "brandon_bailey": "sparta",
        "sparta": "sparta",
        "security": "sparta",
        "threat_intel": "sparta",
        "horus_lore": "lore",
        "horus": "lore",
    }
    return scope_map.get(scope, "operational")


def _trigger_edge_proposal(scope: str) -> None:
    """Trigger embedding generation and edge proposal for new content."""
    try:
        since = str(int(time.time()) - 300)
        subprocess.run(
            ["memory-agent", "embed", "--scope", scope, "--updated-since", since],
            capture_output=True, timeout=120,
        )
        subprocess.run(
            ["memory-agent", "propose", "--scope", scope, "--updated-since", since],
            capture_output=True, timeout=120,
        )
    except Exception as e:
        logger.debug("doc2qra memory propose failed: {}", e)


def distill(
    *,
    url: str = None,
    text: str = None,
    file_path: str = None,
    source_title: str = None,
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
    persona: str = None,
) -> Dict[str, Any]:
    """Convert document into Q&A pairs with summary and store in memory.

    Args:
        url: URL to fetch and distill
        text: Raw text to distill
        file_path: File path to read and distill
        source_title: Human-readable title for source tracking
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
        persona: Persona name for QRA quality gating

    Returns:
        Dict with summary, QRA pairs, storage stats, and persona_verdict
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

    # Source tracking
    source_id = hashlib.sha256(source.encode()).hexdigest()[:12]
    if not source_title:
        source_title = Path(file_path).stem if file_path else source

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

    # Extract document-level taxonomy EARLY — needed for persona routing
    doc_taxonomy: Dict[str, Any] = {"bridge_tags": [], "collection_tags": {}}
    if summary and not sections_only:
        try:
            from taxonomy.taxonomy import extract_taxonomy
            collection_hint = _infer_collection(scope, source)
            doc_taxonomy = extract_taxonomy(
                text=summary[:3000],
                collection=collection_hint,
                fast=False,
            )
            bridge_tags = doc_taxonomy.get("bridge_tags", [])
            if bridge_tags:
                log(f"Taxonomy bridge tags: {bridge_tags}", style="green")
        except Exception as e:
            logger.debug("doc2qra taxonomy extraction failed: {}", e)

    # Persona → Context bridge: resolve persona from taxonomy, derive context
    # This is what makes different personas read the same book differently.
    # taxonomy bridges → persona_router → persona profile → extraction context
    if not context and not sections_only:
        # Step 1: If no persona given, try to auto-select via taxonomy bridges
        if not persona:
            bridge_tags = doc_taxonomy.get("bridge_tags", [])
            if bridge_tags:
                auto_persona = select_persona_by_bridges(bridge_tags)
                if auto_persona:
                    persona = auto_persona
                    log(f"Auto-selected persona '{persona}' from taxonomy bridges {bridge_tags}", style="cyan")

        # Step 2: Resolve persona → context for the LLM extraction prompt
        if persona:
            persona_context = resolve_persona_context(persona)
            if persona_context:
                context = persona_context
                log(f"Persona-derived context: {context[:60]}...", style="cyan")

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

    # Transcripts: process as single section (no chunking)
    # Detected by _extract_transcript_text() output: title + "Channel:" metadata header
    _is_transcript = (
        file_path
        and len(content) < 100_000  # Under 100K chars fits in one LLM call
        and "\nChannel: " in content[:500]
        and "\nDuration: " in content[:500]
    )
    if _is_transcript:
        sections = [(source_title or source, content)]
        log(f"Transcript detected — single section ({len(content):,} chars)", style="cyan")
    else:
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
        # Direct batch mode via DeepSeek (cascade disabled — missing task spec causes failures)
        log(f"Extracting QRA via direct batch (concurrency={concurrency})", style="bold blue")
        try:
            all_qa = asyncio.run(
                extract_qra_batch(sections, source=source, concurrency=concurrency, timeout=60, context=context)
            )
        except Exception as e:
            log(f"Batch extraction error: {e}", style="red")
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

    # Persona quality gate
    persona_verdict = None
    if all_qa:
        try:
            from .persona_gate import select_persona, gate_qras, log_shadow_feedback
            chosen_persona = persona
            if not chosen_persona:
                summary_hint = summary[:200] if summary else ""
                chosen_persona = select_persona(scope, summary_hint)
            if chosen_persona:
                gate_result = gate_qras(all_qa, chosen_persona, scope)
                persona_verdict = gate_result
                if gate_result.get("accepted"):
                    log(f"Persona gate ({chosen_persona}): {gate_result['verdict']} — "
                        f"{len(gate_result['accepted'])}/{len(all_qa)} accepted", style="green")
                    all_qa = gate_result["accepted"]
                if gate_result.get("says"):
                    log(f"Persona says: {gate_result['says']}", style="dim")
                log_shadow_feedback(chosen_persona, all_qa, gate_result["verdict"])
        except ImportError:
            pass  # persona_gate not available yet
        except Exception as e:
            log(f"Persona gate skipped: {e}", style="yellow")

    # Per-QRA taxonomy extraction (fast keyword mode — no LLM cost)
    # Each QRA gets its own bridge tags from its content, plus document-level tags
    doc_bridge_tags = doc_taxonomy.get("bridge_tags", [])
    try:
        from taxonomy.taxonomy import extract_keywords
        _has_taxonomy = True
    except ImportError:
        _has_taxonomy = False
        extract_keywords = None

    # Store or dry-run
    stored = 0
    monitor = TaskClient("doc2qra", total=len(all_qa)) if TaskClient and not dry_run and all_qa else None
    if dry_run:
        log(f"DRY RUN - would store {len(all_qa)} pairs", style="yellow")
    else:
        log(f"Storing {len(all_qa)} pairs to scope '{scope}'")
        for qa in iter_with_progress(all_qa, desc="Storing to memory"):
            tags = ["distilled", source.split("/")[0] if "/" in source else source]
            # Document-level bridge tags
            tags.extend(doc_bridge_tags)
            # Per-QRA bridge tags from content (fast keyword extraction)
            if _has_taxonomy:
                qa_text = f"{qa['problem']} {qa['solution']}"
                qra_bridges = extract_keywords(qa_text[:2000])
                for bt in qra_bridges:
                    if bt not in tags:
                        tags.append(bt)
            # Source tracking tags (queryable via BM25)
            tags.append(f"source_id:{source_id}")
            if source_title:
                tags.append(f"source_title:{source_title}")
            if qa.get("type") == "code":
                tags.append("code")
                if qa.get("language"):
                    tags.append(qa["language"])
            if store_qa(qa["problem"], qa["solution"], scope, tags=tags):
                stored += 1
            if monitor:
                monitor.update(item=qa["problem"][:60])

        if monitor:
            monitor.finish()

        # Trigger embedding + edge proposal for new content
        if stored > 0:
            log("Triggering edge proposal for new content...", style="dim")
            _trigger_edge_proposal(scope)

    # Final summary
    status_panel("doc2qra Complete", {
        "Summary": f"{len(summary)} chars" if summary else "N/A",
        "Extracted": f"{len(all_qa)} Q&A pairs",
        "Stored": f"{stored}" if not dry_run else "(dry run)",
        "Sections": len(sections),
        "Code blocks": len(code_qa) if extract_code else 0,
        "Scope": scope,
    })

    result = {
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
    if persona_verdict:
        result["persona_verdict"] = persona_verdict
    return result


# =============================================================================
# CLI
# =============================================================================


app = typer.Typer(help="Distill PDF/URL/text into Q&A pairs for memory")

# Subcommands that callers can invoke explicitly
_SUBCOMMANDS = {"distill", "recall-source", "--help", "-h"}


@app.command("distill")
def main(
    # Essential flags (agent-facing)
    file_path: str = typer.Option(None, "--file", help="PDF, markdown, or text file to distill"),
    url: str = typer.Option(None, "--url", help="URL to fetch and distill"),
    text: str = typer.Option(None, "--text", help="Raw text to distill"),
    source_title: str = typer.Option(None, "--source-title", help="Human-readable title for source tracking"),
    scope: str = typer.Option("research", "--scope", help="Memory scope (default: research)"),
    context: str = typer.Option(None, "--context", help="Domain focus, e.g. 'ML researcher' or 'security expert'"),
    persona: str = typer.Option(None, "--persona", help="Persona name for QRA quality gating"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview Q&A without storing to memory"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON (includes summary)"),
    sections_only: bool = typer.Option(False, "--sections-only", help="Only extract sections (no Q&A generation)"),
    summary_only: bool = typer.Option(False, "--summary-only", help="Only generate document summary (no Q&A)"),
    # Expert flags (hidden in argparse, now exposed with defaults from env vars)
    context_file: str = typer.Option(None, "--context-file", hidden=True),
    mode: str = typer.Option(os.getenv("DISTILL_PDF_MODE", "fast"), "--mode", hidden=True, help="PDF mode: fast, accurate, auto"),
    preflight: bool = typer.Option(False, "--preflight", hidden=True),
    max_section_chars: int = typer.Option(DEFAULT_MAX_SECTION_CHARS, "--max-section-chars", hidden=True),
    no_llm: bool = typer.Option(False, "--no-llm", hidden=True),
    no_code: bool = typer.Option(False, "--no-code", hidden=True),
    treesitter: bool = typer.Option(False, "--treesitter", hidden=True),
    batch: bool = typer.Option(True, "--batch/--no-batch", hidden=True),
    concurrency: int = typer.Option(
        int(os.getenv("DISTILL_CONCURRENCY", str(DEFAULT_CONCURRENCY))), "--concurrency", hidden=True
    ),
    validate_grounding: bool = typer.Option(
        not os.getenv("DISTILL_NO_GROUNDING"), "--validate-grounding/--no-validate-grounding", hidden=True
    ),
    grounding_threshold: float = typer.Option(
        float(os.getenv("DISTILL_GROUNDING_THRESH", str(DEFAULT_GROUNDING_THRESHOLD))),
        "--grounding-threshold", hidden=True,
    ),
) -> None:
    """Distill PDF/URL/text into Q&A pairs for memory."""
    if not any([url, text, file_path]):
        print("Must provide --url, --file, or --text", file=sys.stderr)
        raise typer.Exit(1)

    try:
        result = distill(
            url=url,
            text=text,
            file_path=file_path,
            source_title=source_title,
            scope=scope,
            max_section_chars=max_section_chars,
            dry_run=dry_run,
            no_llm=no_llm,
            extract_code=not no_code,
            use_treesitter=treesitter,
            mode=mode,
            show_preflight=preflight,
            batch=batch,
            concurrency=concurrency,
            validate_grounding=validate_grounding,
            grounding_threshold=grounding_threshold,
            context=context,
            context_file=context_file,
            sections_only=sections_only,
            summary_only=summary_only,
            persona=persona,
        )

        if json_output:
            print(json.dumps(result, indent=2))
        elif summary_only:
            # Summary-only output
            print(f"Source: {result['source']}")
            print(f"\n{'='*60}")
            print("SUMMARY")
            print('='*60)
            print(result.get("summary", "No summary generated"))
        elif sections_only:
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

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command("recall-source")
def recall_source(
    source_title: str = typer.Option(..., "--source-title", help="Source document title to recall QRAs from"),
    scope: str = typer.Option("", "--scope", help="Memory scope"),
    k: int = typer.Option(20, "--k", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Recall all QRAs from a specific source document."""
    query = f"source_title:{source_title}"
    cmd = ["memory-agent", "recall", "--q", query, "--k", str(k)]
    if scope:
        cmd.extend(["--scope", scope])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"Recall failed: {result.stderr}", file=sys.stderr)
            raise typer.Exit(1)

        if json_output:
            print(result.stdout)
        else:
            try:
                data = json.loads(result.stdout)
                items = data.get("items", [])
                print(f"Found {len(items)} QRAs from source '{source_title}'")
                for i, item in enumerate(items, 1):
                    problem = item.get("problem", "")[:80]
                    tags = item.get("tags", [])
                    bridge = [t for t in tags if t in {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}]
                    print(f"  {i}. {problem}")
                    if bridge:
                        print(f"     Bridge: {', '.join(bridge)}")
            except json.JSONDecodeError:
                print(result.stdout)
    except subprocess.TimeoutExpired:
        print("Recall timed out", file=sys.stderr)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
