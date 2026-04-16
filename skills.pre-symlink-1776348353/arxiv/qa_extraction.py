#!/usr/bin/env python3
"""Q&A extraction and recommendation for arxiv-learn skill.

Split from extraction.py to stay under 500-line module limit.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from config import (
    MIN_TEXT_LENGTH, GROUNDING_KEEP_THRESHOLD, GROUNDING_REVIEW_THRESHOLD,
    IMPLEMENTATION_DETAIL_PATTERNS, SKILLS_DIR,
)
from utils import log, run_skill, QAPair, LearnSession


def find_context_file(context: str) -> str | None:
    """Find a context file matching the context string."""
    from config import CONTEXTS_DIR

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


def _extract_qa_via_scillm(text: str, scope: str, context: str, dry_run: bool) -> dict:
    """Generate Q&A pairs from text using scillm (Chutes LLM).

    Uses direct Python import of scillm's async completion to avoid shell-out issues.
    Fallback when the QRA skill is unavailable.
    """
    import json as _json
    import asyncio

    # Truncate text to fit context window (approx 25k chars for safety)
    max_chars = 25000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... truncated for context window ...]"

    context_line = f"\nContext/Scope: {scope}"
    if context:
        context_line += f" - {context}"

    prompt = f"""You are an expert knowledge extractor. Extract 8-15 high-quality Question-Reasoning-Answer (QRA) pairs from this academic paper.{context_line}

Rules:
- Questions should be specific, technical, and answerable from the text
- Reasoning should explain the logic connecting question to answer
- Answers should be concise but complete
- Focus on key findings, methods, threats, defenses, and novel contributions
- Skip trivial or boilerplate content

Output ONLY valid JSON in this exact format:
{{"qra_pairs": [
  {{"question": "...", "reasoning": "...", "answer": "...", "grounding_score": 0.8}},
  ...
]}}

Paper text:
{text}"""

    try:
        # Direct import of scillm async completion
        scillm_dir = Path(__file__).parent.parent / "scillm"
        if str(scillm_dir) not in sys.path:
            sys.path.insert(0, str(scillm_dir))

        from batch import _quick_acompletion

        log("Calling scillm for QRA extraction (this may take 30-60s)...", style="dim")

        result_text = asyncio.run(_quick_acompletion(
            prompt=prompt,
            json_mode=True,
            max_tokens=4096,
            temperature=0.2,
            timeout=120,
        ))

        if not result_text:
            return {"qra_pairs": [], "success": False, "error": "scillm returned empty response"}

        # Extract JSON from response
        start = result_text.find("{")
        end = result_text.rfind("}")
        if start != -1 and end != -1:
            parsed = _json.loads(result_text[start:end+1])
            pairs = parsed.get("qra_pairs", [])
            log(f"scillm extracted {len(pairs)} QRA pairs", style="green")
            return {"qra_pairs": pairs, "success": True, "qa_pairs": pairs}
        else:
            return {"qra_pairs": [], "success": False, "error": "No JSON found in scillm response"}

    except Exception as e:
        log(f"scillm QRA extraction failed: {e}", style="red")
        return {"qra_pairs": [], "success": False, "error": str(e)}


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

        # Try QRA skill first, fall back to scillm-based extraction
        try:
            result = run_skill("qra", args)
        except FileNotFoundError:
            log("QRA skill not found, using scillm-based extraction", style="cyan")
            result = _extract_qa_via_scillm(text, scope, context, dry_run)

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
    "find_context_file",
    "extract_qa_from_text",
    "is_implementation_detail",
    "add_recommendations",
    "distill_paper",
]
