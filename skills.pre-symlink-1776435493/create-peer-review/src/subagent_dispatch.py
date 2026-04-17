"""Parallel peer review dispatch via scillm.

Sends all reviewer personas concurrently to the scillm API proxy.
Each persona reviews the full paper in parallel, then results are
parsed back into ReviewResult objects.

Shadow logging preserves every response as a teacher label
for Tier 1.5 GPT training.
"""

from __future__ import annotations
import os

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx
from loguru import logger

if TYPE_CHECKING:
    from .review_engine import ReviewResult, SectionReview
    from .reviewer_personas import ReviewerPersona

# ---------------------------------------------------------------------------
# scillm API configuration
# ---------------------------------------------------------------------------
SCILLM_API_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_API_KEY = "sk-dev-proxy-123"
SCILLM_MODEL = "text"


def run_parallel_review(
    reviewers: dict[str, "ReviewerPersona"],
    section_keys: list[str],
    load_section_fn,
    load_references_fn,
    reviews_dir: Path,
    paper_dir: Path,
) -> list["ReviewResult"]:
    """Dispatch all reviewer personas concurrently via scillm.

    Args:
        reviewers: Dict of reviewer_id -> ReviewerPersona.
        section_keys: List of section keys to review.
        load_section_fn: Callable(section_key) -> str content.
        load_references_fn: Callable() -> str references.
        reviews_dir: Directory to save review JSONs.
        paper_dir: Path to paper directory.

    Returns:
        List of ReviewResult, one per reviewer persona.
    """
    from .review_engine import (
        ReviewResult, SectionReview, RubricScore, _extract_json_from_response,
    )

    logger.info("Parallel review via scillm API")

    # Load all section content once (shared across reviewers)
    sections: dict[str, str] = {}
    for key in section_keys:
        content = load_section_fn(key)
        if content.strip():
            sections[key] = content
    references = load_references_fn()

    def _review_one_persona(reviewer_id: str) -> ReviewResult:
        reviewer = reviewers[reviewer_id]
        system_prompt = reviewer.build_system_prompt()

        section_block = "\n\n".join(
            f"=== SECTION: {key} ===\n{content}"
            for key, content in sections.items()
        )

        user_prompt = f"""PAPER SECTIONS TO REVIEW:

{section_block}

REFERENCES:
{references[:3000]}

Review ALL sections above. For each section, provide a structured JSON review.
Return a JSON object with this structure:
{{
  "sections": {{
    "<section_key>": {{
      "scores": {{"soundness": <1-4>, "technical_novelty": <1-4>, "empirical_novelty": <1-4>, "significance": <1-4>, "clarity": <1-4>, "presentation": <1-4>}},
      "overall_score": <1-10>,
      "confidence": <1-5>,
      "strengths": ["..."],
      "weaknesses": ["..."],
      "questions": ["..."],
      "suggestions": ["..."]
    }}
  }},
  "summary": "<2-3 sentence overall assessment>",
  "major_issues": ["..."],
  "minor_issues": ["..."]
}}

CRITICAL: This is round 14. Focus on SUBSTANTIVE issues — methodology gaps,
missing experiments, unsupported claims, structural problems. NOT copywriting.
Every weakness must be actionable with a specific fix."""

        t0 = time.monotonic()
        try:
            resp = httpx.post(
                SCILLM_API_URL,
                headers={"Authorization": f"Bearer {SCILLM_API_KEY}"},
                json={
                    "model": SCILLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 8192,
                    "temperature": 0.3,
                },
                timeout=600,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

            if resp.status_code != 200:
                logger.error(f"scillm {reviewer_id} HTTP {resp.status_code}")
                return _fallback_review(reviewer_id, reviewer, paper_dir, elapsed_ms)

            data = resp.json()
            raw_response = data["choices"][0]["message"]["content"]
            cost_usd = data.get("usage", {}).get("total_tokens", 0) * 0.000001
            return _parse_response(
                reviewer_id, reviewer, raw_response, elapsed_ms,
                sections, cost_usd, paper_dir,
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(f"scillm {reviewer_id} failed: {e}")
            return _fallback_review(reviewer_id, reviewer, paper_dir, elapsed_ms)

    # Dispatch all reviewers in parallel
    reviews: list[ReviewResult] = []
    with ThreadPoolExecutor(max_workers=len(reviewers)) as pool:
        futures = {
            pool.submit(_review_one_persona, rid): rid
            for rid in reviewers
        }
        for future in as_completed(futures):
            rid = futures[future]
            try:
                result = future.result()
                result.save(reviews_dir)
                reviews.append(result)
                logger.info(
                    f"  {rid}: score={result.overall_score:.1f}, "
                    f"decision={result.decision}"
                )
            except Exception as e:
                logger.error(f"  {rid} failed: {e}")

    return reviews


def _parse_response(
    reviewer_id: str,
    reviewer: "ReviewerPersona",
    raw_response: str,
    elapsed_ms: float,
    sections: dict[str, str],
    cost_usd: float,
    paper_dir: Path,
) -> "ReviewResult":
    """Parse scillm JSON response into a ReviewResult."""
    from .review_engine import (
        ReviewResult, SectionReview, RubricScore, _extract_json_from_response,
    )

    result = ReviewResult(
        reviewer_id=reviewer_id,
        reviewer_name=reviewer.name,
        paper_dir=str(paper_dir),
    )

    parsed = _extract_json_from_response(raw_response)

    if parsed and "sections" in parsed:
        for section_key, section_data in parsed["sections"].items():
            if not isinstance(section_data, dict):
                continue
            sr = SectionReview(
                section_key=section_key,
                reviewer_id=reviewer_id,
                latency_ms=elapsed_ms / max(len(sections), 1),
                tier_used=2.0,
                confidence=float(section_data.get("confidence", 3.0)),
            )
            if "scores" in section_data:
                sr.scores = RubricScore.from_dict(section_data["scores"])
            if "overall_score" in section_data:
                sr.overall_score = float(section_data["overall_score"])
            sr.strengths = section_data.get("strengths", [])
            sr.weaknesses = section_data.get("weaknesses", [])
            sr.questions = section_data.get("questions", [])
            sr.suggestions = section_data.get("suggestions", [])
            result.section_reviews.append(sr)

        result.summary = parsed.get("summary", "")
        result.major_issues = parsed.get("major_issues", [])
        result.minor_issues = parsed.get("minor_issues", [])
    else:
        sr = SectionReview(
            section_key="full_paper",
            reviewer_id=reviewer_id,
            latency_ms=elapsed_ms,
            tier_used=2.0,
            confidence=3.0,
        )
        sr.scores = RubricScore(
            soundness=2.5, technical_novelty=2.5, empirical_novelty=2.5,
            significance=2.5, clarity=2.5, presentation=2.5,
        )
        sr.overall_score = sr.scores.weighted_signal()
        sr.weaknesses = [f"Raw review (JSON parse failed): {raw_response[:500]}"]
        result.section_reviews.append(sr)

    result.tier_distribution = {"tier_2.0": len(result.section_reviews)}
    result.compute_overall(reviewer.rubric_weights)

    _log_shadow(reviewer_id, parsed or {}, cost_usd)

    return result


def _fallback_review(
    reviewer_id: str,
    reviewer: "ReviewerPersona",
    paper_dir: Path,
    elapsed_ms: float,
) -> "ReviewResult":
    """Create a minimal ReviewResult when scillm call fails."""
    from .review_engine import ReviewResult, SectionReview

    result = ReviewResult(
        reviewer_id=reviewer_id,
        reviewer_name=reviewer.name,
        paper_dir=str(paper_dir),
    )
    sr = SectionReview(
        section_key="full_paper",
        reviewer_id=reviewer_id,
        latency_ms=elapsed_ms,
        tier_used=-1,
        confidence=1.0,
    )
    sr.weaknesses = ["Review failed — no structured feedback available"]
    result.section_reviews.append(sr)
    result.compute_overall()
    return result


def _log_shadow(
    reviewer_id: str, parsed: dict, cost_usd: float,
) -> None:
    """Log response as shadow data for Tier 1.5 training."""
    from .cascade_integration import SHADOW_FILE

    try:
        entry = {
            "tier": 2,
            "name": "scillm_teacher",
            "reviewer_id": reviewer_id,
            "teacher_result": parsed,
            "cost_usd": cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": "peer_review_paper",
            "scope": "peer_review",
        }
        SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SHADOW_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Shadow log failed: {e}")
