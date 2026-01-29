#!/usr/bin/env python3
"""
Arxiv-Learn - End-to-end pipeline for extracting knowledge from arxiv papers.

Pipeline: Find -> Distill -> Interview -> Store -> Schedule Edges

This is the thin CLI entry point that orchestrates the modular components.

Usage:
    python arxiv_learn.py 2601.08058 --scope memory --context "agent systems"
    python arxiv_learn.py --search "intent-aware memory retrieval" --scope memory
    python arxiv_learn.py --file paper.pdf --scope research
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Ensure local imports work
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# =============================================================================
# Module Imports
# =============================================================================

from config import (
    SKILLS_DIR,
    STATE_DIR,
    PIPELINE_STAGES,
    MIN_FALLBACK_TEXT_LENGTH,
)
from utils import (
    log,
    run_skill,
    Paper,
    QAPair,
    LearnSession,
    Monitor,
)
from download import (
    download_html,
    download_paper,
    load_local_paper,
)
from extraction import (
    quick_profile_html,
    extract_content,
    extract_qa_from_text,
    add_recommendations,
    distill_paper,
)
from memory_storage import (
    run_interview,
    store_to_memory,
    schedule_edge_verification,
)

# =============================================================================
# Pipeline Stages
# =============================================================================

def stage_1_find_paper(session: LearnSession) -> Paper:
    """Stage 1: Find and download the paper."""
    log("Finding paper...", style="bold", stage=1)

    # Use local file if provided
    if session.file_path:
        return load_local_paper(session.file_path)

    # Search for paper if query provided
    if session.search_query:
        log(f"Searching: {session.search_query}")
        result = run_skill("arxiv", [
            "search", "-q", session.search_query, "-n", "5", "--smart"
        ])
        items = result.get("items", [])
        if not items:
            raise ValueError(f"No papers found for: {session.search_query}")

        paper_info = items[0]
        session.arxiv_id = paper_info["id"]
        log(f"Found: {paper_info['title'][:60]}...", style="cyan")

    # Download by arxiv ID
    if session.arxiv_id:
        paper = download_paper(
            session.arxiv_id,
            include_html=not session.accurate,
        )
        if not paper:
            raise RuntimeError(f"Failed to download: {session.arxiv_id}")

        # Profile HTML if available
        if paper.html_path and not session.accurate:
            html_content = Path(paper.html_path).read_text()
            session.profile = quick_profile_html(html_content)
            log(f"Profile: {session.profile['has_figures']} figures, {session.profile['has_tables']} tables", style="dim")

        return paper

    raise ValueError("Must provide arxiv ID, search query, or file path")


def stage_2_extract_and_distill(session: LearnSession) -> list[QAPair]:
    """Stage 2: Extract content and generate Q&A pairs."""
    # Extract content
    extraction_result = extract_content(session)
    session.extraction_format = extraction_result.get("format", "")
    full_text = extraction_result.get("full_text", "")

    # Convert text to Q&A pairs
    if full_text:
        qa_result = extract_qa_from_text(
            full_text,
            scope=session.scope,
            context=session.context,
            dry_run=True,  # Don't store yet
        )

        if not qa_result.get("success"):
            log(f"Q&A extraction failed: {qa_result.get('error')}", style="yellow")
            raw_pairs = []
        else:
            raw_pairs = qa_result.get("qa_pairs", [])

        # Convert to QAPair objects
        qa_pairs = []
        for idx, qa in enumerate(raw_pairs):
            pair = QAPair(
                id=f"q{idx+1}",
                question=qa.get("question", ""),
                answer=qa.get("answer", ""),
                reasoning=qa.get("reasoning", ""),
                grounding_score=qa.get("grounding_score", 0.0),
            )
            qa_pairs.append(pair)

        # Fallback to legacy distill if extraction yielded no results
        if len(qa_pairs) == 0 and len(full_text) > MIN_FALLBACK_TEXT_LENGTH:
            log("HTML extraction yielded text but 0 Q&A pairs. Falling back to legacy distillation.", style="yellow")
            return distill_paper(session)
        elif len(qa_pairs) > 0:
            qa_pairs = add_recommendations(qa_pairs, session)
            log(f"Extracted {len(qa_pairs)} Q&A pairs from {extraction_result.get('format', 'unknown').upper()}", style="green")
            return qa_pairs
        else:
            log("No Q&A pairs extracted and text too short for fallback.", style="yellow")
            return []

    elif session.dry_run:
        # Dry run stub
        log("DRY RUN - estimating Q&A pairs", style="yellow")
        estimated = 10 if session.profile else 5
        return [
            QAPair(
                id=f"q{i+1}",
                question=f"[DRY RUN] Sample question {i+1}",
                answer=f"[DRY RUN] Sample answer {i+1}",
                recommendation="keep",
                reason="Dry run stub",
            )
            for i in range(estimated)
        ]
    else:
        # Fallback to legacy distill
        log("HTML extraction returned no text, falling back to distill", style="yellow")
        return distill_paper(session)

# =============================================================================
# Main Pipeline
# =============================================================================

def run_pipeline(session: LearnSession) -> dict:
    """Run the full arxiv-learn pipeline with HTML-first extraction.

    Args:
        session: Configured LearnSession

    Returns:
        dict with pipeline results
    """
    # Initialize monitor
    monitor = None
    if Monitor:
        state_file = STATE_DIR / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        monitor = Monitor(
            name=f"arxiv-{session.arxiv_id or 'search'}",
            total=PIPELINE_STAGES,
            desc=f"Learning from arXiv: {session.arxiv_id or session.search_query}",
            state_file=str(state_file)
        )
        # Register task with global monitor
        try:
            subprocess.run([
                "python3", str(SKILLS_DIR / "task-monitor" / "monitor.py"),
                "register",
                "--name", f"arxiv-{session.arxiv_id or 'search'}",
                "--state", str(state_file),
                "--total", str(PIPELINE_STAGES),
                "--desc", f"Arxiv Learn: {session.arxiv_id or session.search_query}"
            ], capture_output=True, check=False)
        except Exception:
            pass

    try:
        # Stage 1: Find paper
        if monitor:
            monitor.update(0, item="Finding paper")
        session.paper = stage_1_find_paper(session)
        if monitor:
            monitor.update(1, item="Found paper")

        # Stage 2: Extract and distill
        if monitor:
            monitor.set_description(f"Extracting: {session.paper.title[:30]}...")
            monitor.update(0, item="Extracting Content")
        session.qa_pairs = stage_2_extract_and_distill(session)
        if monitor:
            monitor.update(1, item="Content Extracted")

        # Stage 3: Interview
        if monitor:
            monitor.update(0, item="Interviewing")
        session.approved_pairs, session.dropped_pairs = run_interview(session)
        if monitor:
            monitor.update(1, item="Interview Complete")

        # Stage 4: Store
        if monitor:
            monitor.update(0, item="Storing Knowledge")
        stored = store_to_memory(session)
        if monitor:
            monitor.update(1, item="Stored")

        # Stage 5: Schedule edges
        if monitor:
            monitor.update(0, item="Verifying Edges")
        verified = schedule_edge_verification(session)
        if monitor:
            monitor.update(1, item="Verified")

        session.completed_at = time.time()

        # Summary
        log("")
        title = session.paper.title if session.paper else "Unknown"
        log(f"Done! {len(session.approved_pairs)} learnings from \"{title[:50]}\"", style="bold green")

        return {
            "success": True,
            "paper": {
                "arxiv_id": session.arxiv_id,
                "title": session.paper.title if session.paper else "",
                "pdf_path": session.paper.pdf_path if session.paper else "",
            },
            "extraction_format": session.extraction_format,
            "extracted": len(session.qa_pairs),
            "approved": len(session.approved_pairs),
            "dropped": len(session.dropped_pairs),
            "stored": stored,
            "verified": verified,
            "scope": session.scope,
            "duration_seconds": session.completed_at - session.started_at,
        }

    except Exception as e:
        log(f"Pipeline failed: {e}", style="bold red")
        return {
            "success": False,
            "error": str(e),
        }

# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Arxiv paper to verified memory knowledge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 2601.08058 --scope memory --context "agent systems"
  %(prog)s --search "intent-aware memory retrieval" --scope memory
  %(prog)s --file paper.pdf --scope research --dry-run
"""
    )

    # Paper source (positional or flags)
    parser.add_argument("arxiv_id", nargs="?", help="Arxiv paper ID (e.g., 2601.08058)")
    parser.add_argument("--search", "-s", help="Search query to find paper")
    parser.add_argument("--file", "-f", help="Local PDF file")

    # Required
    parser.add_argument("--scope", required=True, help="Memory scope for storage")

    # Optional
    parser.add_argument("--context", "-c", help="Domain context for relevance filtering")
    parser.add_argument("--mode", "-m", choices=["auto", "html", "tui"], default="auto",
                        help="Interview mode")
    parser.add_argument("--dry-run", action="store_true", help="Preview without storing")
    parser.add_argument("--skip-interview", action="store_true",
                        help="Auto-accept agent recommendations (no human review)")
    parser.add_argument("--max-edges", type=int, default=20,
                        help="Max inline edge verifications (default: 20)")
    parser.add_argument("--accurate", action="store_true",
                        help="Force accurate mode (PDF + VLM extraction)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not any([args.arxiv_id, args.search, args.file]):
        parser.error("Must provide arxiv ID, --search query, or --file path")

    session = LearnSession(
        arxiv_id=args.arxiv_id or "",
        search_query=args.search or "",
        file_path=args.file or "",
        scope=args.scope,
        context=args.context or "",
        mode=args.mode,
        dry_run=args.dry_run,
        skip_interview=args.skip_interview,
        max_edges=args.max_edges,
        accurate=args.accurate,
    )

    result = run_pipeline(session)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print("\nPipeline complete!")
            print(f"  Extracted: {result['extracted']} Q&A pairs")
            print(f"  Approved:  {result['approved']}")
            print(f"  Stored:    {result['stored']}")
            print(f"  Verified:  {result['verified']} edges")
            print(f"  Duration:  {result['duration_seconds']:.1f}s")
        else:
            print(f"\nPipeline failed: {result['error']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
