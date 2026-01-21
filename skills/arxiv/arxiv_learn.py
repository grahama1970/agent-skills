#!/usr/bin/env python3
"""
Arxiv-Learn - End-to-end pipeline for extracting knowledge from arxiv papers.

Pipeline: Find → Distill → Interview → Store → Schedule Edges

Usage:
    python arxiv_learn.py 2601.08058 --scope memory --context "agent systems"
    python arxiv_learn.py --search "intent-aware memory retrieval" --scope memory
    python arxiv_learn.py --file paper.pdf --scope research
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Resolve skill directories
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent

# Add skills dir to path for imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Best-effort .env loading
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass


def _log(msg: str, style: str = None, stage: int = None):
    """Log message with optional stage prefix."""
    prefix = f"[{stage}/5]" if stage else "[arxiv-learn]"
    try:
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"{prefix} {msg}", style=style)
    except ImportError:
        print(f"{prefix} {msg}", file=sys.stderr)


def _run_skill(skill_name: str, args: list[str], capture: bool = True) -> dict | str:
    """Run a skill script and return output."""
    skill_dir = SKILLS_DIR / skill_name
    run_script = skill_dir / "run.sh"

    if not run_script.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    cmd = ["bash", str(run_script)] + args
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=600,  # 10 min timeout
        env={**os.environ, "PYTHONPATH": f"{SKILLS_DIR}:{os.environ.get('PYTHONPATH', '')}"},
    )

    if result.returncode != 0:
        raise RuntimeError(f"{skill_name} failed: {result.stderr[:500]}")

    if capture:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
    return ""


@dataclass
class Paper:
    """Downloaded paper info."""
    arxiv_id: str
    title: str
    authors: list[str]
    pdf_path: str
    abstract: str = ""
    html_url: str = ""


@dataclass
class QAPair:
    """A distilled Q&A pair with agent recommendation."""
    id: str
    question: str
    answer: str
    reasoning: str = ""
    section_title: str = ""
    recommendation: str = "keep"  # keep, drop
    reason: str = ""  # Why agent recommends this
    grounding_score: float = 0.0
    stored: bool = False
    lesson_id: str = ""

    def to_interview_question(self) -> dict:
        """Convert to interview question format."""
        return {
            "id": self.id,
            "text": f"Q: {self.question}\nA: {self.answer}",
            "type": "yes_no_refine",
            "recommendation": self.recommendation,
            "reason": self.reason,
        }


@dataclass
class LearnSession:
    """Session state for the arxiv-learn pipeline."""
    arxiv_id: str = ""
    search_query: str = ""
    file_path: str = ""
    scope: str = "research"
    context: str = ""
    mode: str = "auto"
    dry_run: bool = False
    skip_interview: bool = False
    max_edges: int = 20

    paper: Paper | None = None
    qa_pairs: list[QAPair] = field(default_factory=list)
    approved_pairs: list[QAPair] = field(default_factory=list)
    dropped_pairs: list[QAPair] = field(default_factory=list)

    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


def stage_1_find_paper(session: LearnSession) -> Paper:
    """Stage 1: Find and download the paper."""
    _log("Finding paper...", style="bold", stage=1)

    # Use local file if provided
    if session.file_path:
        path = Path(session.file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {session.file_path}")
        _log(f"Using local file: {path.name}", style="green")
        return Paper(
            arxiv_id="local",
            title=path.stem,
            authors=[],
            pdf_path=str(path),
        )

    # Search for paper if query provided
    if session.search_query:
        _log(f"Searching: {session.search_query}")
        result = _run_skill("arxiv", [
            "search", "-q", session.search_query, "-n", "5", "--smart"
        ])
        items = result.get("items", [])
        if not items:
            raise ValueError(f"No papers found for: {session.search_query}")

        # Use first result (could add interactive selection later)
        paper_info = items[0]
        session.arxiv_id = paper_info["id"]
        _log(f"Found: {paper_info['title'][:60]}...", style="cyan")

    # Download by arxiv ID
    if session.arxiv_id:
        _log(f"Downloading {session.arxiv_id}...")

        # Get paper metadata
        result = _run_skill("arxiv", ["get", "-i", session.arxiv_id])
        items = result.get("items", [])
        if not items:
            raise ValueError(f"Paper not found: {session.arxiv_id}")

        paper_info = items[0]

        # Download PDF
        with tempfile.TemporaryDirectory() as tmpdir:
            dl_result = _run_skill("arxiv", [
                "download", "-i", session.arxiv_id, "-o", tmpdir
            ])
            pdf_path = dl_result.get("downloaded")
            if not pdf_path:
                raise RuntimeError(f"Failed to download: {session.arxiv_id}")

            # Move to persistent location
            papers_dir = SCRIPT_DIR / "papers"
            papers_dir.mkdir(exist_ok=True)
            final_path = papers_dir / Path(pdf_path).name
            Path(pdf_path).rename(final_path)
            pdf_path = str(final_path)

        paper = Paper(
            arxiv_id=session.arxiv_id,
            title=paper_info.get("title", ""),
            authors=paper_info.get("authors", []),
            pdf_path=pdf_path,
            abstract=paper_info.get("abstract", ""),
            html_url=paper_info.get("html_url", ""),
        )

        _log(f"Title: {paper.title[:60]}...", style="green")
        _log(f"Authors: {', '.join(paper.authors[:3])}", style="dim")

        return paper

    raise ValueError("Must provide arxiv ID, search query, or file path")


def stage_2_distill(session: LearnSession) -> list[QAPair]:
    """Stage 2: Distill paper into Q&A pairs."""
    _log("Distilling Q&As...", style="bold", stage=2)

    if not session.paper:
        raise ValueError("No paper loaded")

    # Build distill command
    args = [
        "--file", session.paper.pdf_path,
        "--scope", session.scope,
        "--json",
        "--dry-run",  # Don't store yet - we'll do that in stage 4
    ]

    if session.context:
        args.extend(["--context", session.context])

    # Run distill
    result = _run_skill("distill", args)

    raw_count = result.get("extracted", 0)
    _log(f"Extracted: {raw_count} Q&A pairs")

    qa_pairs = []
    qa_list = result.get("qa_pairs", [])

    for idx, qa in enumerate(qa_list):
        pair = QAPair(
            id=f"q{idx+1}",
            question=qa.get("problem", ""),
            answer=qa.get("answer", qa.get("solution", "")),
            reasoning=qa.get("reasoning", ""),
            section_title=qa.get("section_title", ""),
            grounding_score=qa.get("grounding_score", 0.0),
        )
        qa_pairs.append(pair)

    # Add agent recommendations based on context
    qa_pairs = _add_recommendations(qa_pairs, session)

    keep_count = sum(1 for q in qa_pairs if q.recommendation == "keep")
    drop_count = len(qa_pairs) - keep_count

    _log(f"With recommendations: {len(qa_pairs)} pairs ({keep_count} keep, {drop_count} drop)", style="green")

    return qa_pairs


def _add_recommendations(qa_pairs: list[QAPair], session: LearnSession) -> list[QAPair]:
    """Add agent recommendations to Q&A pairs based on context."""
    context_keywords = session.context.lower().split() if session.context else []

    for pair in qa_pairs:
        # Default: keep if grounding score is good
        if pair.grounding_score >= 0.7:
            pair.recommendation = "keep"
            pair.reason = f"Well-grounded (score: {pair.grounding_score:.2f})"
        elif pair.grounding_score >= 0.5:
            pair.recommendation = "keep"
            pair.reason = "Moderately grounded, review recommended"
        else:
            pair.recommendation = "drop"
            pair.reason = f"Low grounding score ({pair.grounding_score:.2f})"

        # Boost relevance if matches context
        if context_keywords:
            text = (pair.question + " " + pair.answer).lower()
            matches = sum(1 for kw in context_keywords if kw in text)
            if matches >= 2:
                pair.recommendation = "keep"
                pair.reason = f"Highly relevant to: {session.context}"
            elif matches == 1 and pair.recommendation != "drop":
                pair.reason = f"Relevant to {session.context}; {pair.reason}"

        # Drop implementation details and numbers-only answers
        if _is_implementation_detail(pair):
            pair.recommendation = "drop"
            pair.reason = "Implementation detail, not generalizable"

    return qa_pairs


def _is_implementation_detail(pair: QAPair) -> bool:
    """Check if a Q&A is an implementation detail."""
    q_lower = pair.question.lower()
    a_lower = pair.answer.lower()

    # Skip dataset sizes, hyperparameters, etc.
    detail_patterns = [
        "dataset size", "how many", "what number",
        "learning rate", "batch size", "epoch",
        "table", "figure", "listing",
    ]

    for pattern in detail_patterns:
        if pattern in q_lower:
            return True

    # Skip if answer is mostly numbers
    digits = sum(1 for c in pair.answer if c.isdigit())
    if len(pair.answer) > 0 and digits / len(pair.answer) > 0.5:
        return True

    return False


def stage_3_interview(session: LearnSession) -> tuple[list[QAPair], list[QAPair]]:
    """Stage 3: Human review via interview."""
    _log("Opening interview form...", style="bold", stage=3)

    if session.skip_interview:
        _log("Skipping interview (--skip-interview)", style="yellow")
        approved = [q for q in session.qa_pairs if q.recommendation == "keep"]
        dropped = [q for q in session.qa_pairs if q.recommendation == "drop"]
        return approved, dropped

    # Prepare interview questions
    interview_data = {
        "title": f"Review Q&As from {session.paper.title[:50]}",
        "context": f"Reviewing extracted knowledge for {session.scope} scope",
        "questions": [q.to_interview_question() for q in session.qa_pairs],
    }

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(interview_data, f, indent=2)
        questions_file = f.name

    try:
        # Run interview
        _log(f"Mode: {session.mode}")

        result = _run_skill("interview", [
            "--file", questions_file,
            "--mode", session.mode,
            "--json",
        ])

        responses = result.get("responses", {})

        # Process responses
        approved = []
        dropped = []

        for pair in session.qa_pairs:
            resp = responses.get(pair.id, {})
            decision = resp.get("decision", "skip")

            if decision == "accept":
                # User accepted agent recommendation
                if pair.recommendation == "keep":
                    approved.append(pair)
                else:
                    dropped.append(pair)
            elif decision == "override":
                # User overrode agent recommendation
                if pair.recommendation == "keep":
                    dropped.append(pair)
                else:
                    approved.append(pair)
            else:  # skip
                dropped.append(pair)

            # Check for refinements
            note = resp.get("note")
            if note:
                # User provided refinement - update answer
                pair.answer = note

        _log(f"Accepted: {len(approved)} pairs", style="green")
        _log(f"Dropped: {len(dropped)} pairs", style="dim")

        return approved, dropped

    finally:
        Path(questions_file).unlink(missing_ok=True)


def stage_4_store(session: LearnSession) -> int:
    """Stage 4: Store approved Q&As to memory."""
    _log("Storing to memory...", style="bold", stage=4)

    if session.dry_run:
        _log(f"DRY RUN - would store {len(session.approved_pairs)} pairs", style="yellow")
        return 0

    if not session.approved_pairs:
        _log("No pairs to store", style="yellow")
        return 0

    # Build tags
    tags = ["distilled"]
    if session.arxiv_id and session.arxiv_id != "local":
        tags.append(f"arxiv:{session.arxiv_id}")
    if session.paper:
        # Add author tag (first author surname)
        if session.paper.authors:
            first_author = session.paper.authors[0].split()[-1].lower()
            tags.append(f"author:{first_author}")

    stored = 0
    # Default to env var, or try to find sibling 'memory' workspace
    default_mem = Path(SKILLS_DIR).parent.parent.parent / "memory" 
    memory_root = os.environ.get("MEMORY_ROOT", str(default_mem))
    
    # If explicitly hardcoded fallback is needed for legacy reasons, we keep it as last resort via env
    if not Path(memory_root).exists() and "/home/graham" in memory_root:
        # Fallback to standard location if default logic failed
        pass

    for pair in session.approved_pairs:
        try:
            cmd = [
                "python3", "-m", "graph_memory.agent_cli", "learn",
                "--problem", pair.question,
                "--solution", pair.answer,
                "--scope", session.scope,
            ]
            for tag in tags:
                cmd.extend(["--tag", tag])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "PYTHONPATH": f"{memory_root}/src:{os.environ.get('PYTHONPATH', '')}"},
            )

            if result.returncode == 0:
                # Extract lesson ID from output
                try:
                    output = json.loads(result.stdout)
                    pair.lesson_id = output.get("_key", "")
                except Exception:
                    pass
                pair.stored = True
                stored += 1
        except Exception as e:
            _log(f"Failed to store: {e}", style="red")

    _log(f"Stored: {stored} lessons", style="green")
    _log(f"Scope: {session.scope}", style="dim")
    _log(f"Tags: {', '.join(tags)}", style="dim")

    return stored


def stage_5_schedule_edges(session: LearnSession) -> int:
    """Stage 5: Schedule edge verification for new lessons."""
    _log("Scheduling edge verification...", style="bold", stage=5)

    if session.dry_run:
        _log(f"DRY RUN - would queue {len(session.approved_pairs)} lessons", style="yellow")
        return 0

    # Only process pairs that were stored
    to_verify = [p for p in session.approved_pairs if p.stored and p.lesson_id]

    if not to_verify:
        _log("No lessons to verify", style="yellow")
        return 0

    _log(f"Queued: {len(to_verify)} lessons for verification")

    verified = 0
    inline_limit = min(session.max_edges, len(to_verify))

    for idx, pair in enumerate(to_verify[:inline_limit]):
        try:
            # Run edge verifier for this lesson
            result = subprocess.run([
                "bash", str(SKILLS_DIR / "edge-verifier" / "run.sh"),
                "--source_id", f"lessons/{pair.lesson_id}",
                "--text", f"{pair.question} {pair.answer}",
                "--scope", session.scope,
                "--k", "25",
                "--verify-top", "5",
                "--max-llm", "5",
            ], capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                verified += 1
                _log(f"Verified {idx+1}/{inline_limit}: {pair.question[:40]}...", style="dim")
        except Exception as e:
            _log(f"Verification failed: {e}", style="red")

    remaining = len(to_verify) - verified

    _log(f"Inline verified: {verified} (--max-edges limit)", style="green")
    if remaining > 0:
        _log(f"Remaining: {remaining} (scheduled for batch)", style="yellow")

    return verified


def run_pipeline(session: LearnSession) -> dict:
    """Run the full arxiv-learn pipeline."""
    try:
        # Stage 1: Find paper
        session.paper = stage_1_find_paper(session)

        # Stage 2: Distill
        session.qa_pairs = stage_2_distill(session)

        # Stage 3: Interview
        session.approved_pairs, session.dropped_pairs = stage_3_interview(session)

        # Stage 4: Store
        stored = stage_4_store(session)

        # Stage 5: Schedule edges
        verified = stage_5_schedule_edges(session)

        session.completed_at = time.time()

        # Summary
        _log("")
        title = session.paper.title if session.paper else "Unknown"
        _log(f"Done! {len(session.approved_pairs)} learnings from \"{title[:50]}\"", style="bold green")

        return {
            "success": True,
            "paper": {
                "arxiv_id": session.arxiv_id,
                "title": session.paper.title if session.paper else "",
                "pdf_path": session.paper.pdf_path if session.paper else "",
            },
            "extracted": len(session.qa_pairs),
            "approved": len(session.approved_pairs),
            "dropped": len(session.dropped_pairs),
            "stored": stored,
            "verified": verified,
            "scope": session.scope,
            "duration_seconds": session.completed_at - session.started_at,
        }

    except Exception as e:
        _log(f"Pipeline failed: {e}", style="bold red")
        return {
            "success": False,
            "error": str(e),
        }


def main():
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
    )

    result = run_pipeline(session)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(f"\nPipeline complete!")
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
