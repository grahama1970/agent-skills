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
import re
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
        stdout = result.stdout.strip()
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Robust JSON extraction: look for first { and last }
            try:
                start = stdout.find("{")
                end = stdout.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(stdout[start:end+1])
            except Exception:
                pass
            return stdout
    return ""



def quick_profile_html(html_content: str) -> dict:
    """
    Quick profile check for HTML content to determine if VLM is needed.

    Counts <figure> and <table> tags in HTML to decide whether
    accurate mode (with VLM) should be used.

    Args:
        html_content: HTML string (e.g., from ar5iv.org)

    Returns:
        dict with:
            - needs_vlm: bool - True if paper has significant figures/tables
            - has_figures: int - Count of figure tags
            - has_tables: int - Count of table tags
            - recommendation: str - "fast" or "accurate"
    """
    # Count figure tags (including nested img in figures)
    figure_pattern = re.compile(r'<figure[^>]*>', re.IGNORECASE)
    figures = len(figure_pattern.findall(html_content))

    # Count table tags (data tables, not layout tables)
    table_pattern = re.compile(r'<table[^>]*class="[^"]*ltx_tabular[^"]*"[^>]*>', re.IGNORECASE)
    tables = len(table_pattern.findall(html_content))

    # Fallback: count all table tags if no ltx_tabular found
    if tables == 0:
        all_tables_pattern = re.compile(r'<table[^>]*>', re.IGNORECASE)
        tables = len(all_tables_pattern.findall(html_content))

    # Heuristic: ar5iv HTML includes figure captions and table data,
    # so VLM is only needed for papers with heavy visual content
    # that can't be understood from captions alone.
    # Higher thresholds since ar5iv does good job extracting captions.
    # VLM recommended only for papers where visual analysis is critical.
    needs_vlm = figures > 20 or tables > 10

    recommendation = "accurate" if needs_vlm else "fast"

    return {
        "needs_vlm": needs_vlm,
        "has_figures": figures,
        "has_tables": tables,
        "recommendation": recommendation,
    }


@dataclass
class Paper:
    """Downloaded paper info."""
    arxiv_id: str
    title: str
    authors: list[str]
    pdf_path: str
    abstract: str = ""
    html_url: str = ""
    html_path: str = ""  # Path to downloaded HTML (from ar5iv)


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
    accurate: bool = False  # Force accurate mode (PDF + VLM)

    paper: Paper | None = None
    profile: dict | None = None  # HTML profile result
    qa_pairs: list[QAPair] = field(default_factory=list)
    approved_pairs: list[QAPair] = field(default_factory=list)
    dropped_pairs: list[QAPair] = field(default_factory=list)

    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


def _download_html(arxiv_id: str, output_dir: Path) -> str | None:
    """Download HTML from ar5iv.org."""
    import urllib.request

    # Strip version suffix if present (e.g., 2501.15355v1 -> 2501.15355)
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    url = f"https://ar5iv.org/abs/{base_id}"
    output_path = output_dir / f"{base_id}.html"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arxiv-learn/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            output_path.write_bytes(content)
            return str(output_path)
    except Exception as e:
        _log(f"HTML download failed: {e}", style="yellow")
        return None


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

        # Also download HTML from ar5iv for profile check and fast extraction
        if not session.accurate:
            html_path = _download_html(session.arxiv_id, papers_dir)
            if html_path:
                paper.html_path = html_path
                _log(f"HTML: Downloaded from ar5iv", style="dim")

                # Run quick profile
                html_content = Path(html_path).read_text()
                session.profile = quick_profile_html(html_content)
                _log(f"Profile: {session.profile['has_figures']} figures, {session.profile['has_tables']} tables", style="dim")

        return paper

    raise ValueError("Must provide arxiv ID, search query, or file path")


def stage_2_extract(session: LearnSession) -> dict:
    """
    Stage 2: Extract content using HTML-first routing.

    Routes extraction based on:
    - Default (fast): ar5iv HTML → extractor HTML mode
    - Accurate: PDF → extractor PDF + VLM mode

    Returns:
        dict with format, source, and extraction results
    """
    _log("Extracting content...", style="bold", stage=2)

    if not session.paper:
        raise ValueError("No paper loaded")

    # Determine extraction mode
    use_pdf = session.accurate

    # Check if profile suggests VLM is needed
    if session.profile and session.profile.get("needs_vlm"):
        _log("Profile suggests VLM needed (many figures/tables)", style="yellow")
        use_pdf = True

    # Use HTML if available and not forced to PDF
    if not use_pdf and session.paper.html_path:
        _log("Using HTML extraction (fast mode)", style="green")

        # Dry run: return expected format without running extractor
        if session.dry_run:
            _log("DRY RUN - would extract from HTML", style="yellow")
            return {
                "format": "html",
                "source": "ar5iv",
                "success": True,
                "dry_run": True,
                "full_text": "",
                "char_count": 0,
                "sections": [],
            }

        # Run extractor in HTML mode (auto-detect preset)
        # Note: extractor run.sh takes file as first positional arg, no "extract" subcommand
        extractor_args = [
            session.paper.html_path,
            "--fast",
            "--json",
        ]

        try:
            result = _run_skill("extractor", extractor_args)

            # Extract text from blocks (extractor returns structured blocks, not full_text)
            full_text = ""
            if isinstance(result, dict):
                doc = result.get("document", {})
                blocks = doc.get("blocks", [])
                # Concatenate text from all blocks
                text_parts = []
                for block in blocks:
                    content = block.get("content", "")
                    block_type = block.get("type", "")

                    # Handle different block types - some have dict content
                    if isinstance(content, dict):
                        # Figure blocks: extract caption
                        if block_type == "figure":
                            caption = content.get("caption", "")
                            title = content.get("title", "")
                            if caption:
                                text_parts.append(f"[Figure: {caption}]")
                            elif title:
                                text_parts.append(f"[Figure: {title}]")
                        # Table blocks: skip (usually no extractable text)
                        # List blocks: skip (items are in listitem blocks)
                        continue
                    elif isinstance(content, str) and content.strip():
                        # String content - add with appropriate formatting
                        if block_type == "heading":
                            text_parts.append(f"\n## {content}\n")
                        elif block_type == "listitem":
                            text_parts.append(f"  • {content}")
                        else:
                            text_parts.append(content)
                full_text = "\n".join(text_parts)

            return {
                "format": "html",
                "source": "ar5iv",
                "success": True,
                "full_text": full_text,
                "char_count": len(full_text),
                "sections": [],
            }
        except Exception as e:
            _log(f"HTML extraction failed, falling back to PDF: {e}", style="yellow")
            use_pdf = True

    # PDF extraction with VLM
    _log("Using PDF extraction (accurate mode)", style="cyan")

    # Dry run: return expected format without running extractor
    if session.dry_run:
        _log("DRY RUN - would extract from PDF", style="yellow")
        return {
            "format": "pdf",
            "source": "arxiv",
            "success": True,
            "dry_run": True,
            "full_text": "",
            "char_count": 0,
            "sections": [],
        }

    # Note: extractor run.sh takes file as first positional arg, no "extract" subcommand
    extractor_args = [
        session.paper.pdf_path,
        "--accurate",
        "--json",
    ]

    try:
        result = _run_skill("extractor", extractor_args)

        return {
            "format": "pdf",
            "source": "arxiv",
            "success": True,
            "full_text": result.get("full_text", ""),
            "char_count": len(result.get("full_text", "")),
            "sections": result.get("sections", []),
        }
    except Exception as e:
        raise RuntimeError(f"Extraction failed: {e}")


def _find_context_file(context: str) -> str | None:
    """Find a context file matching the context string."""
    contexts_dir = SCRIPT_DIR / "contexts"
    if not contexts_dir.exists():
        return None

    # Check for exact match or keyword match
    context_lower = context.lower()
    for ctx_file in contexts_dir.glob("*.md"):
        # Exact stem match
        if ctx_file.stem.lower() == context_lower.replace(" ", "_"):
            return str(ctx_file)
        # Keyword match (e.g., "horus" in context matches "horus_tom.md")
        if any(kw in context_lower for kw in ctx_file.stem.lower().split("_")):
            return str(ctx_file)

    return None


def extract_qa_from_text(text: str, scope: str = "research", context: str = "", dry_run: bool = False) -> dict:
    """
    Extract Q&A pairs from extracted text using QRA skill.

    Args:
        text: Full text content (from extractor)
        scope: Memory scope for storage
        context: Domain context for relevance filtering (or context file name)
        dry_run: If True, don't store to memory

    Returns:
        dict with qa_pairs list and metadata
    """
    if not text or len(text) < 100:
        return {
            "success": False,
            "error": "Text too short for Q&A extraction",
            "qa_pairs": [],
        }

    # Write text to temp file for QRA skill
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        f.write(text)
        text_file = f.name

    try:
        # Build QRA command
        args = [
            "--file", text_file,
            "--scope", scope,
            "--json",
        ]

        # Check for context file (rich context) vs simple context string
        if context:
            context_file = _find_context_file(context)
            if context_file:
                _log(f"Using context file: {Path(context_file).name}", style="cyan")
                args.extend(["--context-file", context_file])
            else:
                args.extend(["--context", context])

        if dry_run:
            args.append("--dry-run")

        # Run QRA skill
        result = _run_skill("qra", args)

        # Parse QRA output (note: QRA skill returns "qra_pairs" key)
        if not isinstance(result, dict):
            error_msg = f"QRA returned non-JSON output: {str(result)[:500]}"
            _log(error_msg, style="red")
            return {
                "success": False,
                "error": error_msg,
                "qa_pairs": [],
            }

        qa_pairs = []
        items = result.get("qra_pairs", result.get("items", result.get("qa_pairs", [])))

        for item in items:
            qa_pairs.append({
                "question": item.get("problem", item.get("question", "")),
                "answer": item.get("solution", item.get("answer", "")),
                "reasoning": item.get("reasoning", ""),
                "grounding_score": item.get("grounding_score", 0.0),
            })

        return {
            "success": True,
            "qa_pairs": qa_pairs,
            "extracted": len(qa_pairs),
            "scope": scope,
            "dry_run": dry_run,
        }


    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "qa_pairs": [],
        }

    finally:
        Path(text_file).unlink(missing_ok=True)


def stage_2_distill(session: LearnSession) -> list[QAPair]:
    """Stage 2b: Distill paper into Q&A pairs (legacy mode using distill skill)."""
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
    """Run the full arxiv-learn pipeline with HTML-first extraction."""
    extraction_format = "unknown"
    try:
        # Stage 1: Find paper (also downloads HTML from ar5iv and runs profile)
        session.paper = stage_1_find_paper(session)

        # Stage 2: Extract content using HTML-first routing
        # This replaces the old distill-based extraction for arxiv papers
        extraction_result = stage_2_extract(session)
        extraction_format = extraction_result.get("format", "unknown")
        full_text = extraction_result.get("full_text", "")

        # Stage 2b: Convert extracted text to Q&A pairs
        if full_text:
            qa_result = extract_qa_from_text(
                full_text,
                scope=session.scope,
                context=session.context,
                dry_run=True,  # Don't store yet - we do that in stage 4
            )
            
            if not qa_result.get("success"):
                _log(f"Q&A extraction failed: {qa_result.get('error')}", style="yellow")
                raw_pairs = []
            else:
                raw_pairs = qa_result.get("qa_pairs", [])

            # Convert to QAPair objects
            session.qa_pairs = []
            for idx, qa in enumerate(raw_pairs):
                pair = QAPair(
                    id=f"q{idx+1}",
                    question=qa.get("question", ""),
                    answer=qa.get("answer", ""),
                    reasoning=qa.get("reasoning", ""),
                    grounding_score=qa.get("grounding_score", 0.0),
                )
                session.qa_pairs.append(pair)

            # Fallback to legacy distill if extraction yielded no results but we have text
            if len(session.qa_pairs) == 0 and len(full_text) > 1000:
                _log("HTML extraction yielded text but 0 Q&A pairs. Falling back to legacy distillation.", style="yellow")
                session.qa_pairs = stage_2_distill(session)
            elif len(session.qa_pairs) > 0:
                # Add recommendations
                session.qa_pairs = _add_recommendations(session.qa_pairs, session)
                _log(f"Extracted {len(session.qa_pairs)} Q&A pairs from {extraction_format.upper()}", style="green")
            else:
                _log("No Q&A pairs extracted and text too short for fallback.", style="yellow")

        elif session.dry_run:
            # Dry run: return stub Q&A pairs (estimation based on profile)
            _log("DRY RUN - estimating Q&A pairs", style="yellow")
            estimated = 10 if session.profile else 5  # Estimate based on typical paper
            session.qa_pairs = [
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
            # Fallback to legacy distill if extraction failed
            _log("HTML extraction returned no text, falling back to distill", style="yellow")
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
            "extraction_format": extraction_format,
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
