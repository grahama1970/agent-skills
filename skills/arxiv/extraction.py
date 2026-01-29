#!/usr/bin/env python3
"""Content extraction for arxiv-learn skill."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from config import (
    CONTEXTS_DIR, VLM_FIGURE_THRESHOLD, VLM_TABLE_THRESHOLD,
    MIN_TEXT_LENGTH, GROUNDING_KEEP_THRESHOLD, GROUNDING_REVIEW_THRESHOLD,
    IMPLEMENTATION_DETAIL_PATTERNS, SKILLS_DIR,
)
from utils import log, run_skill, QAPair, LearnSession


def quick_profile_html(html_content: str) -> dict:
    """Profile HTML to determine if VLM is needed based on figure/table counts."""
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
    needs_vlm = figures > VLM_FIGURE_THRESHOLD or tables > VLM_TABLE_THRESHOLD

    recommendation = "accurate" if needs_vlm else "fast"

    return {
        "needs_vlm": needs_vlm, "has_figures": figures,
        "has_tables": tables, "recommendation": recommendation,
    }


def find_context_file(context: str) -> str | None:
    """Find a context file matching the context string."""
    if not CONTEXTS_DIR.exists():
        return None

    context_lower = context.lower()
    for ctx_file in CONTEXTS_DIR.glob("*.md"):
        # Exact stem match
        if ctx_file.stem.lower() == context_lower.replace(" ", "_"):
            return str(ctx_file)
        # Keyword match (e.g., "horus" in context matches "horus_tom.md")
        if any(kw in context_lower for kw in ctx_file.stem.lower().split("_")):
            return str(ctx_file)
    return None


def extract_from_html(html_path: str, dry_run: bool = False) -> dict:
    """Extract content from HTML file."""
    log("Using HTML extraction (fast mode)", style="green")

    if dry_run:
        log("DRY RUN - would extract from HTML", style="yellow")
        return {
            "format": "html",
            "source": "ar5iv",
            "success": True,
            "dry_run": True,
            "full_text": "",
            "char_count": 0,
            "sections": [],
        }

    # Run extractor in HTML mode
    extractor_args = [
        html_path,
        "--fast",
        "--json",
    ]

    try:
        result = run_skill("extractor", extractor_args)

        # Extract text from blocks
        full_text = ""
        if isinstance(result, dict):
            doc = result.get("document", {})
            blocks = doc.get("blocks", [])
            text_parts = []

            for block in blocks:
                content = block.get("content", "")
                block_type = block.get("type", "")

                # Handle different block types
                if isinstance(content, dict):
                    # Figure blocks: extract caption
                    if block_type == "figure":
                        caption = content.get("caption", "")
                        title = content.get("title", "")
                        if caption:
                            text_parts.append(f"[Figure: {caption}]")
                        elif title:
                            text_parts.append(f"[Figure: {title}]")
                    continue
                elif isinstance(content, str) and content.strip():
                    if block_type == "heading":
                        text_parts.append(f"\n## {content}\n")
                    elif block_type == "listitem":
                        text_parts.append(f"  - {content}")
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
        log(f"HTML extraction failed: {e}", style="yellow")
        raise


def extract_from_pdf(pdf_path: str, dry_run: bool = False) -> dict:
    """Extract content from PDF file."""
    log("Using PDF extraction (accurate mode)", style="cyan")

    if dry_run:
        log("DRY RUN - would extract from PDF", style="yellow")
        return {
            "format": "pdf",
            "source": "arxiv",
            "success": True,
            "dry_run": True,
            "full_text": "",
            "char_count": 0,
            "sections": [],
        }

    extractor_args = [
        pdf_path,
        "--accurate",
        "--json",
    ]

    try:
        result = run_skill("extractor", extractor_args)
        if not isinstance(result, dict):
            raise RuntimeError("Extractor returned non-JSON output")

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


def extract_content(session: LearnSession) -> dict:
    """Extract content using HTML-first routing with PDF fallback."""
    log("Extracting content...", style="bold", stage=2)

    if not session.paper:
        raise ValueError("No paper loaded")

    # Determine extraction mode
    use_pdf = session.accurate

    # Check if profile suggests VLM is needed
    if session.profile and session.profile.get("needs_vlm"):
        log("Profile suggests VLM needed (many figures/tables)", style="yellow")
        use_pdf = True

    # Use HTML if available and not forced to PDF
    if not use_pdf and session.paper.html_path:
        try:
            return extract_from_html(session.paper.html_path, session.dry_run)
        except Exception as e:
            log(f"HTML extraction failed, falling back to PDF: {e}", style="yellow")
            use_pdf = True

    return extract_from_pdf(session.paper.pdf_path, session.dry_run)


def extract_qa_from_text(text: str, scope: str = "research",
                         context: str = "", dry_run: bool = False) -> dict:
    """Extract Q&A pairs from text using QRA skill."""
    if not text or len(text) < MIN_TEXT_LENGTH:
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
            context_file = find_context_file(context)
            if context_file:
                log(f"Using context file: {Path(context_file).name}", style="cyan")
                args.extend(["--context-file", context_file])
            else:
                args.extend(["--context", context])

        if dry_run:
            args.append("--dry-run")

        # Run QRA skill
        result = run_skill("qra", args)

        # Parse QRA output (note: QRA skill returns "qra_pairs" key)
        if not isinstance(result, dict):
            error_msg = f"QRA returned non-JSON output: {str(result)[:500]}"
            log(error_msg, style="red")
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


def is_implementation_detail(pair: QAPair) -> bool:
    """Check if a Q&A is an implementation detail."""
    q_lower = pair.question.lower()

    for pattern in IMPLEMENTATION_DETAIL_PATTERNS:
        if pattern in q_lower:
            return True

    # Skip if answer is mostly numbers
    digits = sum(1 for c in pair.answer if c.isdigit())
    if len(pair.answer) > 0 and digits / len(pair.answer) > 0.5:
        return True

    return False


def add_recommendations(qa_pairs: list[QAPair], session: LearnSession) -> list[QAPair]:
    """Add agent recommendations to Q&A pairs based on context."""
    context_keywords = session.context.lower().split() if session.context else []

    for pair in qa_pairs:
        # Default: keep if grounding score is good
        if pair.grounding_score >= GROUNDING_KEEP_THRESHOLD:
            pair.recommendation = "keep"
            pair.reason = f"Well-grounded (score: {pair.grounding_score:.2f})"
        elif pair.grounding_score >= GROUNDING_REVIEW_THRESHOLD:
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

        # Drop implementation details
        if is_implementation_detail(pair):
            pair.recommendation = "drop"
            pair.reason = "Implementation detail, not generalizable"

    # High-reasoning refinement via Codex if enabled
    if session.high_reasoning:
        qa_pairs = _refine_with_codex(qa_pairs, session)

    return qa_pairs


def _refine_with_codex(qa_pairs: list[QAPair], session: LearnSession) -> list[QAPair]:
    """Refine recommendations using Codex high-reasoning."""
    log("Refining recommendations with Codex gpt-5.2 High Reasoning...", style="cyan")

    try:
        codex_script = SKILLS_DIR / "codex" / "run.sh"
        if not codex_script.exists():
            return qa_pairs

        # Prepare batch recommendation prompt
        items = [
            f"Q: {p.question}\nA: {p.answer[:200]}..."
            for p in qa_pairs if p.recommendation == "keep"
        ]
        if not items:
            return qa_pairs

        prompt = (
            f"Context: {session.context}\n"
            f"Review these extracted Q&A pairs. Decide which ones are TRULY valuable "
            f"for the given context. Identify any that are trivial, redundant, or "
            f"purely numeric/boilerplate.\n\n"
            "ITEMS:\n" + "\n---\n".join(items) + "\n\n"
            "Provide a list of IDs or questions to DROP, with a brief reason."
        )

        res = run_skill("codex", ["reason", prompt])
        log(f"Codex Insight: {str(res)[:500]}...", style="dim")

    except Exception as e:
        log(f"Codex refinement failed: {e}", style="yellow")

    return qa_pairs


def distill_paper(session: LearnSession) -> list[QAPair]:
    """Distill paper into Q&A pairs using legacy distill skill."""
    log("Distilling Q&As...", style="bold", stage=2)

    if not session.paper:
        raise ValueError("No paper loaded")

    # Build distill command
    args = [
        "--file", session.paper.pdf_path,
        "--scope", session.scope,
        "--json",
        "--dry-run",  # Don't store yet
    ]

    if session.context:
        args.extend(["--context", session.context])

    # Run distill
    result = run_skill("distill", args)

    raw_count = result.get("extracted", 0)
    log(f"Extracted: {raw_count} Q&A pairs")

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

    # Add recommendations
    qa_pairs = add_recommendations(qa_pairs, session)

    keep_count = sum(1 for q in qa_pairs if q.recommendation == "keep")
    drop_count = len(qa_pairs) - keep_count

    log(f"With recommendations: {len(qa_pairs)} pairs ({keep_count} keep, {drop_count} drop)", style="green")
    return qa_pairs


__all__ = [
    "quick_profile_html",
    "find_context_file",
    "extract_from_html",
    "extract_from_pdf",
    "extract_content",
    "extract_qa_from_text",
    "is_implementation_detail",
    "add_recommendations",
    "distill_paper",
]
