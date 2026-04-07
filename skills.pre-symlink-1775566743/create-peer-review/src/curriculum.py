"""Curriculum paper review pipeline for Shadow-LEGO self-improvement.

Downloads arxiv papers via ar5iv HTML (with PDF fallback), segments into
sections matching ReviewEngine.SECTION_KEYS, creates a temporary LaTeX
directory, and runs the full peer review cascade in shadow mode.

This generates the training data that bootstraps the self-improving
cascade: real arxiv papers graded by the teacher produce shadow entries
that train Tier 1.5 reviewer GPTs.
"""

from __future__ import annotations
import os

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from loguru import logger


SKILL_DIR = Path(__file__).parent.parent
SKILLS_DIR = SKILL_DIR.parent
ARXIV_SKILL_DIR = SKILLS_DIR / "arxiv"

# ar5iv renders arxiv papers as accessible HTML
AR5IV_BASE = "https://ar5iv.labs.arxiv.org/html"

# Section mapping: ar5iv heading patterns → ReviewEngine section keys
SECTION_MAP = {
    "abstract": ["abstract"],
    "intro": ["introduction"],
    "related": [
        "related work", "related works", "background",
        "background and related work", "preliminaries",
        "preliminary", "prior work",
    ],
    "design": [
        "design", "system design", "architecture", "method", "methodology",
        "approach", "framework", "proposed method", "our approach",
        "scope and problem statement", "problem statement", "problem formulation",
        "model", "overview", "system overview", "technical approach",
        "how to", "proposed approach", "our method",
    ],
    "impl": [
        "implementation", "system", "experimental setup", "setup",
        "how to use", "strategies", "algorithm", "training",
        "model architecture", "technical details",
    ],
    "eval": [
        "evaluation", "experiments", "results", "experimental results",
        "empirical evaluation", "empirical results", "analysis",
        "case study", "reduces cost", "performance",
        "main results", "ablation",
    ],
    "discussion": [
        "discussion", "conclusion", "conclusions", "limitations",
        "future work", "discussion and conclusion",
        "discussions", "discussions, limitations",
        "broader impact", "ethical considerations",
    ],
}


def _normalize_heading(text: str) -> str:
    """Normalize a heading string for matching."""
    return re.sub(r"^\d+[\.\s]*", "", text.strip().lower()).strip()


def _fetch_ar5iv_html(arxiv_id: str) -> Optional[str]:
    """Fetch ar5iv HTML rendering of an arxiv paper."""
    url = f"{AR5IV_BASE}/{arxiv_id}"
    logger.info(f"Fetching ar5iv HTML: {url}")
    try:
        req = Request(url, headers={"User-Agent": "Shadow-LEGO-Curriculum/1.0"})
        with urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8", errors="replace")
    except (URLError, OSError) as e:
        logger.warning(f"ar5iv fetch failed for {arxiv_id}: {e}")
    return None


def _segment_html_to_sections(html: str) -> dict[str, str]:
    """Extract sections from ar5iv HTML using heading tags.

    ar5iv uses <h2>/<h3> for section headings with <section> wrappers.
    We extract text between consecutive headings and map to our section keys.
    """
    sections: dict[str, str] = {}

    # Extract abstract — ar5iv uses <div class="ltx_abstract">
    abstract_match = re.search(
        r'<div[^>]*class="[^"]*ltx_abstract[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if abstract_match:
        abstract_text = re.sub(r"<[^>]+>", " ", abstract_match.group(1))
        abstract_text = re.sub(r"\s+", " ", abstract_text).strip()
        if abstract_text:
            sections["abstract"] = abstract_text

    # Split on section headings (<h2>, <h3> within <section> tags)
    heading_pattern = re.compile(
        r'<h([23])[^>]*>(.*?)</h\1>',
        re.DOTALL | re.IGNORECASE,
    )
    headings = list(heading_pattern.finditer(html))

    for i, match in enumerate(headings):
        heading_text = re.sub(r"<[^>]+>", "", match.group(2))
        heading_text = re.sub(r"\s+", " ", heading_text).strip()
        normalized = _normalize_heading(heading_text)

        # Find which section key this heading maps to
        section_key = None
        for key, patterns in SECTION_MAP.items():
            if key == "abstract":
                continue  # Already handled
            for pattern in patterns:
                if (normalized == pattern
                    or normalized.startswith(pattern)
                    or pattern in normalized):
                    section_key = key
                    break
            if section_key:
                break

        if not section_key:
            continue

        # Extract text between this heading and the next
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(html)
        chunk = html[start:end]

        # Strip HTML tags, keep text
        text = re.sub(r"<[^>]+>", " ", chunk)
        text = re.sub(r"\s+", " ", text).strip()

        if text and len(text) > 50:
            # Don't overwrite if we already have a longer version
            if section_key not in sections or len(text) > len(sections[section_key]):
                sections[section_key] = text

    return sections


def _create_temp_paper_dir(
    arxiv_id: str,
    sections: dict[str, str],
    title: str = "",
) -> Path:
    """Create a temporary paper directory with .tex files for ReviewEngine."""
    paper_dir = Path(tempfile.mkdtemp(prefix=f"curriculum_{arxiv_id}_"))
    sections_dir = paper_dir / "sections"
    sections_dir.mkdir()

    for key, content in sections.items():
        # Wrap in minimal LaTeX for ReviewEngine compatibility
        tex_content = f"% Section: {key} (arxiv:{arxiv_id})\n"
        tex_content += f"% Auto-extracted from ar5iv for curriculum review\n\n"
        tex_content += _text_to_tex(content)
        (sections_dir / f"{key}.tex").write_text(tex_content)

    # Create minimal references.bib
    bib = f"% Auto-generated for curriculum review of arxiv:{arxiv_id}\n"
    if title:
        bib += f"@article{{{arxiv_id},\n  title={{{title}}},\n  year={{2024}},\n}}\n"
    (paper_dir / "references.bib").write_text(bib)

    return paper_dir


def _text_to_tex(text: str) -> str:
    """Minimal text-to-LaTeX escaping for extracted content."""
    # Escape special LaTeX characters that would break compilation
    for char in ["&", "%", "$", "#", "_"]:
        text = text.replace(char, f"\\{char}")
    # But un-escape the ones we just double-escaped from our own comments
    text = text.replace("\\\\%", "\\%")
    return text


def _fetch_paper_title(arxiv_id: str) -> str:
    """Fetch paper title from Semantic Scholar."""
    try:
        from .exemplar_comparison import ExemplarComparator
        comparator = ExemplarComparator()
        meta = comparator.fetch_s2_metadata(arxiv_id)
        if meta and "title" in meta:
            return meta["title"]
    except Exception as e:
        logger.debug(f"S2 title fetch failed: {e}")
    return f"arxiv:{arxiv_id}"


def _fallback_arxiv_pdf(arxiv_id: str) -> Optional[Path]:
    """Fallback: use /arxiv learn --accurate to extract from PDF.

    Returns path to extracted paper directory, or None on failure.
    """
    logger.info(f"Falling back to /arxiv PDF extraction for {arxiv_id}")
    arxiv_run = ARXIV_SKILL_DIR / "run.sh"
    if not arxiv_run.exists():
        logger.warning(f"/arxiv skill not found at {arxiv_run}")
        return None

    try:
        result = subprocess.run(
            ["bash", str(arxiv_run), "learn", "--accurate", arxiv_id],
            capture_output=True, text=True, timeout=120,
            cwd=str(ARXIV_SKILL_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            # /arxiv learn writes extracted content to a known location
            extract_dir = Path.home() / ".pi" / "arxiv" / arxiv_id
            if extract_dir.exists():
                return extract_dir
    except Exception as e:
        logger.warning(f"/arxiv PDF fallback failed: {e}")

    return None


def review_arxiv(
    arxiv_id: str,
    shadow: bool = True,
    reviewer_ids: Optional[list[str]] = None,
) -> dict:
    """Review an arxiv paper through the Shadow-LEGO cascade.

    Pipeline:
    1. Fetch ar5iv HTML rendering
    2. Segment into sections matching ReviewEngine.SECTION_KEYS
    3. Create temp LaTeX directory
    4. Run ReviewEngine.run_full_review() in shadow mode
    5. Return meta-review dict + cleanup temp dir

    Args:
        arxiv_id: Arxiv paper ID (e.g., "2305.05176")
        shadow: Enable shadow mode for self-improvement data collection
        reviewer_ids: Specific reviewers to use (default: all 4)

    Returns:
        Dict with meta_review, section_count, shadow_entries, paper_title
    """
    from .review_engine import ReviewEngine, MetaReview

    # Normalize arxiv ID (strip version suffix like v1, v2)
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id.strip())

    title = _fetch_paper_title(arxiv_id)
    logger.info(f"Reviewing arxiv paper: {title} ({arxiv_id})")

    # Step 1: Try ar5iv HTML
    html = _fetch_ar5iv_html(arxiv_id)
    paper_dir = None
    fallback_used = False

    if html:
        sections = _segment_html_to_sections(html)
        if len(sections) >= 3:  # Need at least 3 sections for meaningful review
            paper_dir = _create_temp_paper_dir(arxiv_id, sections, title)
            logger.info(f"ar5iv extraction: {len(sections)} sections for {arxiv_id}")
        else:
            logger.warning(
                f"ar5iv only extracted {len(sections)} sections, "
                f"need >=3. Falling back to PDF."
            )

    # Step 2: PDF fallback if ar5iv insufficient
    if paper_dir is None:
        pdf_dir = _fallback_arxiv_pdf(arxiv_id)
        if pdf_dir:
            paper_dir = pdf_dir
            fallback_used = True
        else:
            return {
                "error": f"Could not extract paper {arxiv_id} via ar5iv or PDF",
                "arxiv_id": arxiv_id,
            }

    # Step 3: Run full review
    try:
        engine = ReviewEngine(
            paper_dir=paper_dir,
            reviewer_ids=reviewer_ids,
            shadow_mode=shadow,
        )
        meta = engine.run_full_review()

        # Count sections that were actually reviewed
        reviewed_sections = set()
        for rid, reviewer in engine.reviewers.items():
            pass  # ReviewResult tracks sections internally

        result = {
            "arxiv_id": arxiv_id,
            "title": title,
            "overall_score": meta.overall_score,
            "decision": meta.decision,
            "reviewer_scores": meta.reviewer_scores,
            "section_count": len(list((paper_dir / "sections").glob("*.tex"))),
            "fallback_used": fallback_used,
            "shadow_mode": shadow,
            "meta_review": meta.to_dict(),
        }

        # Get shadow stats if available
        shadow_stats = engine.shadow_report()
        if shadow_stats:
            result["shadow_stats"] = shadow_stats

        # Persist review files for training data harvesting
        persist_dir = Path.home() / ".pi" / "peer_review" / "reviews" / f"arxiv_{arxiv_id}" / "reviews"
        persist_dir.mkdir(parents=True, exist_ok=True)
        reviews_dir = paper_dir / "reviews"
        if reviews_dir.exists():
            for review_file in reviews_dir.glob("*.json"):
                shutil.copy2(review_file, persist_dir / review_file.name)
            logger.info(f"Persisted reviews to {persist_dir}")

        return result

    finally:
        # Cleanup temp directory (but not PDF fallback dirs)
        if not fallback_used and paper_dir and paper_dir.exists():
            if "curriculum_" in paper_dir.name:
                shutil.rmtree(paper_dir, ignore_errors=True)


def review_arxiv_batch(
    arxiv_ids: list[str],
    shadow: bool = True,
    reviewer_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Review multiple arxiv papers sequentially.

    Returns list of results, one per paper.
    """
    results = []
    for i, arxiv_id in enumerate(arxiv_ids, 1):
        logger.info(f"Curriculum review {i}/{len(arxiv_ids)}: {arxiv_id}")
        try:
            result = review_arxiv(arxiv_id, shadow=shadow, reviewer_ids=reviewer_ids)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to review {arxiv_id}: {e}")
            results.append({"arxiv_id": arxiv_id, "error": str(e)})
    return results
