"""compare — Compute delta between pdf_oxide extraction and ground truth.

Given a fixture PDF and its ground_truth.json sidecar, runs pdf_oxide
extraction and compares sections, blocks, tables, figures, and requirements
against the oracle.
"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def compare(fixture_pdf: Path, ground_truth_json: Path, overrides: dict | None = None) -> dict:
    """Run pdf_oxide on fixture_pdf and compare against ground_truth_json.

    Args:
        overrides: Optional extraction overrides from convergence loop.
            Supported keys: body_font_size_override (float), header_ratio_override (float).

    Returns a ComparisonResult dict with deltas per category and an overall score.
    """
    import pdf_oxide

    gt = json.loads(ground_truth_json.read_text())
    doc = pdf_oxide.PdfDocument(str(fixture_pdf))
    ov = overrides or {}

    # Extract ONCE with overrides, share result across all comparisons.
    # This fixes the #1 performance issue: triple extract_document() calls.
    extraction = doc.extract_document(
        body_font_size_override=ov.get("body_font_size_override"),
        header_ratio_override=ov.get("header_ratio_override"),
    )

    # --- Sections (uses extraction result with overrides applied) ---
    section_delta = _compare_sections(doc, gt, extraction=extraction)

    # --- Blocks ---
    block_delta = _compare_blocks(doc, gt, extraction=extraction)

    # --- Tables ---
    table_delta = _compare_tables(doc, gt, extraction=extraction)

    # --- Figures ---
    figure_delta = _compare_figures(doc, gt, extraction=extraction)

    # --- Requirements ---
    requirement_delta = _compare_requirements(doc, gt)

    # --- Profile ---
    profile_delta = _compare_profile(doc, gt, extraction=extraction)

    # --- Overall score (0..1) ---
    overall_score = _compute_overall_score(
        section_delta, block_delta, table_delta,
        figure_delta, requirement_delta, profile_delta,
    )

    return {
        "fixture_id": gt.get("fixture_id", "unknown"),
        "tricks": gt.get("tricks", []),
        "section_delta": section_delta,
        "block_delta": block_delta,
        "table_delta": table_delta,
        "figure_delta": figure_delta,
        "requirement_delta": requirement_delta,
        "profile_delta": profile_delta,
        "overall_score": round(overall_score, 4),
    }


# ---------------------------------------------------------------------------
# Section comparison
# ---------------------------------------------------------------------------

def _compare_sections(doc, gt: dict, extraction: dict | None = None) -> dict:
    """Compare extracted sections against ground truth."""
    gt_sections = gt.get("sections", [])
    assertions = gt.get("assertions", {})
    expected_count = assertions.get("section_count", len(gt_sections))

    # Use sections from the pre-computed extraction (with overrides applied)
    if extraction and "sections" in extraction:
        extracted = extraction.get("sections", [])
    else:
        result = doc.build_flat_sections()
        extracted = result.get("sections", [])
    got_count = len(extracted)

    # Title matching: fuzzy match extracted titles against ground truth titles
    gt_titles = [s["title"] for s in gt_sections]
    ext_titles = [s.get("title", "") or s.get("display_title", "") for s in extracted]

    matched = 0
    unmatched_gt = list(range(len(gt_titles)))
    for ext_title in ext_titles:
        best_idx = -1
        best_ratio = 0.0
        for idx in unmatched_gt:
            ratio = SequenceMatcher(None, ext_title.lower(), gt_titles[idx].lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
        if best_ratio >= 0.6 and best_idx >= 0:
            matched += 1
            unmatched_gt.remove(best_idx)

    over = max(0, got_count - expected_count)
    under = max(0, expected_count - got_count)

    return {
        "expected": expected_count,
        "got": got_count,
        "over": over,
        "under": under,
        "title_matched": matched,
        "title_missed": len(gt_titles) - matched,
        "score": _ratio_score(matched, expected_count),
    }


# ---------------------------------------------------------------------------
# Block comparison
# ---------------------------------------------------------------------------

_BLOCK_TYPE_MAP = {
    # ground truth type -> set of pdf_oxide block_type values that count as match
    "Header": {"Header", "Title"},
    "Text": {"Body", "Text"},
    "Table": {"Table"},
    "Figure": {"Figure"},
    "Equation": {"Equation"},
    "Code": {"Code"},
    "Footnote": {"Footnote", "Footer"},
    "Caption": {"Caption"},
    "TOC": {"TableOfContents", "TOC"},
    "PageNumber": {"PageNumber", "Boilerplate"},
    "Boilerplate": {"Boilerplate"},
    "Requirement": {"Requirement", "Body"},  # requirements often classified as Body
}


def _compare_blocks(doc, gt: dict, extraction: dict | None = None) -> dict:
    """Compare block classifications against ground truth."""
    gt_blocks = gt.get("blocks", [])
    expected_count = len(gt_blocks)

    # Collect all blocks from all pages — prefer shared extraction result
    all_blocks = []
    if extraction and "pages" in extraction:
        for page_idx, page_data in enumerate(extraction.get("pages", [])):
            blocks = page_data if isinstance(page_data, list) else page_data.get("blocks", [])
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        b["page"] = page_idx
                        all_blocks.append(b)
    else:
        for p in range(doc.page_count()):
            blocks = doc.classify_blocks(p)
            for b in blocks:
                b["page"] = p
                all_blocks.append(b)
    actual_count = len(all_blocks)

    # Count ground truth types
    gt_type_counts: dict[str, int] = {}
    for b in gt_blocks:
        t = b.get("type", "Text")
        gt_type_counts[t] = gt_type_counts.get(t, 0) + 1

    # Count extracted types (mapped to GT categories)
    ext_type_counts: dict[str, int] = {}
    for b in all_blocks:
        bt = b.get("block_type", "Body")
        ext_type_counts[bt] = ext_type_counts.get(bt, 0) + 1

    # Type-level matching: for each GT block, check if we have a block on the
    # same page with a compatible type. Use text similarity for disambiguation.
    type_matches = 0
    misclassified = 0
    used_ext = set()

    for gt_block in gt_blocks:
        gt_type = gt_block.get("type", "Text")
        gt_page = gt_block.get("page", 0)
        gt_text = gt_block.get("text", "")[:200]
        acceptable = _BLOCK_TYPE_MAP.get(gt_type, {gt_type})

        # Find best matching extracted block on same page
        best_idx = -1
        best_score = 0.0
        best_type_ok = False

        for i, ext_block in enumerate(all_blocks):
            if i in used_ext:
                continue
            if ext_block.get("page", -1) != gt_page:
                continue
            ext_text = ext_block.get("text", "")[:200]
            if not gt_text and not ext_text:
                sim = 0.5  # both empty, weak match
            elif not gt_text or not ext_text:
                sim = 0.0
            else:
                sim = SequenceMatcher(None, gt_text.lower(), ext_text.lower()).ratio()

            if sim > best_score:
                best_score = sim
                best_idx = i
                best_type_ok = ext_block.get("block_type", "Body") in acceptable

        if best_idx >= 0 and best_score >= 0.3:
            used_ext.add(best_idx)
            if best_type_ok:
                type_matches += 1
            else:
                misclassified += 1

    return {
        "expected": expected_count,
        "actual": actual_count,
        "type_matches": type_matches,
        "misclassified": misclassified,
        "unmatched": expected_count - type_matches - misclassified,
        "gt_type_counts": gt_type_counts,
        "ext_type_counts": ext_type_counts,
        "score": _ratio_score(type_matches, expected_count),
    }


# ---------------------------------------------------------------------------
# Table comparison
# ---------------------------------------------------------------------------

def _compare_tables(doc, gt: dict, extraction: dict | None = None) -> dict:
    """Compare table extraction against ground truth."""
    gt_tables = gt.get("tables", [])
    assertions = gt.get("assertions", {})

    expected_real = assertions.get("table_count", sum(1 for t in gt_tables if t.get("is_real_table")))
    expected_false = assertions.get("false_table_count", sum(1 for t in gt_tables if not t.get("is_real_table")))

    # Use shared extraction result (with overrides applied)
    if extraction is None:
        extraction = doc.extract_document()

    # Count tables from pages data
    extracted_tables = 0
    for page_data in extraction.get("pages", []):
        blocks = page_data if isinstance(page_data, list) else page_data.get("blocks", [])
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict) and b.get("block_type") == "Table":
                    extracted_tables += 1

    # If both expected and extracted are 0, that's a perfect match
    if expected_real == 0 and extracted_tables == 0:
        score = 1.0
    else:
        score = _ratio_score(
            min(extracted_tables, expected_real),
            max(expected_real, 1),
        )

    return {
        "expected_real": expected_real,
        "expected_false": expected_false,
        "extracted": extracted_tables,
        "over": max(0, extracted_tables - expected_real),
        "under": max(0, expected_real - extracted_tables),
        "score": score,
    }


# ---------------------------------------------------------------------------
# Figure comparison
# ---------------------------------------------------------------------------

def _compare_figures(doc, gt: dict, extraction: dict | None = None) -> dict:
    """Compare figure detection against ground truth."""
    gt_figures = gt.get("figures", [])
    assertions = gt.get("assertions", {})
    expected = assertions.get("figure_count", len(gt_figures))

    if extraction is None:
        extraction = doc.extract_document()
    extracted = len(extraction.get("figures", []))

    return {
        "expected": expected,
        "got": extracted,
        "over": max(0, extracted - expected),
        "under": max(0, expected - extracted),
        "score": 1.0 if expected == extracted else _ratio_score(
            min(extracted, expected), max(expected, extracted, 1)
        ),
    }


# ---------------------------------------------------------------------------
# Requirement comparison
# ---------------------------------------------------------------------------

def _compare_requirements(doc, gt: dict) -> dict:
    """Compare requirement detection against ground truth.

    We look for SHALL/MUST/WILL/SHOULD/MAY patterns in extracted text
    and compare against the ground truth requirement list.
    """
    gt_reqs = gt.get("requirements", [])
    assertions = gt.get("assertions", {})
    expected_real = assertions.get("requirement_count", sum(1 for r in gt_reqs if r.get("is_real_requirement")))
    expected_false = assertions.get("false_requirement_count", sum(1 for r in gt_reqs if not r.get("is_real_requirement")))

    if not gt_reqs:
        return {
            "expected_real": 0,
            "expected_false": 0,
            "score": 1.0,
        }

    # Extract full text and scan for requirement-like sentences
    import re
    modal_pattern = re.compile(
        r'\b(shall|must|will|should|may)\b',
        re.IGNORECASE,
    )

    full_text = ""
    for p in range(doc.page_count()):
        page_text = doc.extract_text(p)
        if page_text:
            full_text += page_text + "\n"

    # Split into sentences and find modal matches
    sentences = re.split(r'(?<=[.!?])\s+|\n', full_text)
    modal_sentences = [s.strip() for s in sentences if modal_pattern.search(s) and len(s.strip()) > 20]

    # Match against GT real requirements
    real_gt = [r for r in gt_reqs if r.get("is_real_requirement")]
    matched_real = 0
    for gt_req in real_gt:
        gt_text = gt_req["text"][:200].lower()
        for sent in modal_sentences:
            if SequenceMatcher(None, gt_text, sent[:200].lower()).ratio() >= 0.5:
                matched_real += 1
                break

    return {
        "expected_real": expected_real,
        "expected_false": expected_false,
        "detected_modal_sentences": len(modal_sentences),
        "matched_real": matched_real,
        "score": _ratio_score(matched_real, expected_real) if expected_real > 0 else 1.0,
    }


# ---------------------------------------------------------------------------
# Profile comparison
# ---------------------------------------------------------------------------

def _compare_profile(doc, gt: dict, extraction: dict | None = None) -> dict:
    """Compare document profile against expected_profile."""
    expected_profile = gt.get("expected_profile", {})
    if not expected_profile:
        return {"score": 1.0}

    if extraction is None:
        extraction = doc.extract_document()
    profile = extraction.get("profile", {})

    matches = 0
    total = 0
    details = {}

    for key in ["is_scanned", "has_tables", "has_figures", "has_equations"]:
        if key in expected_profile:
            total += 1
            # Map profile keys (pdf_oxide uses has_images instead of has_figures)
            profile_key = "has_images" if key == "has_figures" else key
            got = profile.get(profile_key, None)
            expected = expected_profile[key]
            match = got == expected
            if match:
                matches += 1
            details[key] = {"expected": expected, "got": got, "match": match}

    return {
        "matches": matches,
        "total": total,
        "details": details,
        "score": _ratio_score(matches, total) if total > 0 else 1.0,
    }


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _ratio_score(numerator: int, denominator: int) -> float:
    """Return numerator/denominator clamped to [0, 1]."""
    if denominator <= 0:
        return 1.0
    return round(min(1.0, max(0.0, numerator / denominator)), 4)


def _compute_overall_score(
    section_delta: dict,
    block_delta: dict,
    table_delta: dict,
    figure_delta: dict,
    requirement_delta: dict,
    profile_delta: dict,
) -> float:
    """Weighted average of category scores."""
    weights = {
        "section": 0.25,
        "block": 0.25,
        "table": 0.15,
        "figure": 0.10,
        "requirement": 0.15,
        "profile": 0.10,
    }
    scores = {
        "section": section_delta.get("score", 0),
        "block": block_delta.get("score", 0),
        "table": table_delta.get("score", 0),
        "figure": figure_delta.get("score", 0),
        "requirement": requirement_delta.get("score", 0),
        "profile": profile_delta.get("score", 0),
    }
    total_weight = sum(weights.values())
    return sum(scores[k] * weights[k] for k in weights) / total_weight
