#!/usr/bin/env python3
"""
TOC (Table of Contents) integrity checker.

This module verifies the integrity of TOC extraction by comparing
PDF bookmarks (from S00 profile.json) against extracted sections
(from S11 structural.json or S04 sections.json).

No DuckDB dependency — reads JSON pipeline output directly.
"""
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_toc_check(path: Path) -> Dict[str, Any]:
    """
    Run TOC integrity check on existing pipeline output.

    Compares PDF TOC bookmarks against extracted sections to measure
    extraction quality.

    Args:
        path: Path to pipeline output directory (the run directory)

    Returns:
        Dict with TOC integrity report:
        - success: True/False
        - has_toc: Whether PDF has TOC bookmarks
        - integrity_score: 0.0-1.0 score
        - status: EXCELLENT/GOOD/FAIR/POOR
        - matched: List of matched TOC entries
        - missing: List of unmatched TOC entries
    """
    run_dir = path if path.is_dir() else path.parent

    # Load TOC from S00 profile.json
    toc_entries = _load_toc_from_profile(run_dir)
    if toc_entries is None:
        return {"success": False, "error": f"No profile.json found in {run_dir}"}

    if not toc_entries:
        return {
            "success": True,
            "has_toc": False,
            "message": "PDF has no TOC/bookmarks",
            "integrity_score": None,
        }

    # Load extracted sections from S11 structural.json or S04 sections.json
    sections = _load_sections(run_dir)
    if sections is None:
        return {
            "success": False,
            "error": "No structural.json or sections.json found — run extraction first",
        }

    # Build match report
    matched, missing = _match_toc_to_sections(toc_entries, sections)

    # Calculate integrity score
    total_toc = len(toc_entries)
    matched_count = len(matched)
    integrity_score = round(matched_count / total_toc, 2) if total_toc > 0 else 1.0

    status = _score_to_status(integrity_score)

    return {
        "success": True,
        "has_toc": True,
        "integrity_score": integrity_score,
        "status": status,
        "toc_entries_count": total_toc,
        "sections_count": len(sections),
        "matched_count": matched_count,
        "missing_count": len(missing),
        "matched": matched,
        "missing": missing,
        "message": f"TOC integrity: {status} ({integrity_score:.0%})",
    }


def _load_toc_from_profile(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Load TOC entries from S00 profile.json."""
    profile_path = run_dir / "00_profile_detector" / "profile.json"
    if not profile_path.exists():
        return None

    try:
        data = json.loads(profile_path.read_text())
        toc = data.get("toc", {})
        if not toc.get("has_toc", False):
            return []
        entries = toc.get("entries", [])
        # Normalize to consistent format: {level, title, page}
        return [
            {
                "level": e.get("level", 1),
                "title": e.get("title", ""),
                "page": e.get("page", 0),
            }
            for e in entries
            if e.get("title", "").strip()
        ]
    except Exception:
        return None


def _load_sections(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Load extracted sections from S11 structural.json or S04 sections.json."""
    # Try S11 first (most complete)
    s11_path = run_dir / "11_json_exporter" / "structural.json"
    if s11_path.exists():
        sections = _parse_sections_from_s11(s11_path)
        if sections:
            return sections

    # Fall back to S04
    s04_path = run_dir / "04_section_builder" / "json_output" / "04_sections.json"
    if s04_path.exists():
        sections = _parse_sections_from_s04(s04_path)
        if sections:
            return sections

    return None


def _parse_sections_from_s11(path: Path) -> List[Dict[str, Any]]:
    """Parse sections from S11 structural.json (flattened format)."""
    try:
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else data.get("elements", data.get("sections", []))
        sections = []
        for item in items:
            obj_type = (item.get("object_type") or item.get("type") or "").lower()
            if obj_type == "section" or item.get("section_title"):
                sections.append({
                    "id": item.get("section_id", item.get("id", "")),
                    "title": item.get("section_title", item.get("title", "")),
                    "page_start": item.get("page_num", item.get("page_start", 0)),
                })
        # Deduplicate by title (S11 may have multiple elements per section)
        seen = set()
        unique = []
        for s in sections:
            key = (s["title"] or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
    except Exception:
        return []


def _parse_sections_from_s04(path: Path) -> List[Dict[str, Any]]:
    """Parse sections from S04 04_sections.json (hierarchical format)."""
    try:
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else data.get("sections", [])
        sections = []
        for item in items:
            sections.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "page_start": item.get("page_start", 0),
            })
        return sections
    except Exception:
        return []


def _match_toc_to_sections(
    toc_entries: List[Dict[str, Any]],
    sections: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Match TOC entries to extracted sections using fuzzy matching.

    Returns:
        Tuple of (matched, missing) lists
    """
    matched = []
    missing = []

    for toc in toc_entries:
        best_match = None
        best_score = 0.0

        for sec in sections:
            # Title similarity
            title_sim = SequenceMatcher(
                None,
                toc["title"].lower(),
                (sec["title"] or "").lower()
            ).ratio()

            # Page proximity (within 2 pages = bonus)
            page_diff = abs((toc["page"] or 0) - (sec["page_start"] or 0))
            page_bonus = 0.2 if page_diff <= 2 else 0.0

            score = title_sim + page_bonus

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = {
                    "section_id": sec["id"],
                    "section_title": sec["title"],
                    "score": round(min(score, 1.0), 2),
                }

        if best_match:
            matched.append({
                "toc_title": toc["title"],
                "toc_page": toc["page"],
                "toc_level": toc["level"],
                **best_match,
            })
        else:
            missing.append({
                "toc_title": toc["title"],
                "toc_page": toc["page"],
                "toc_level": toc["level"],
            })

    return matched, missing


def _score_to_status(integrity_score: float) -> str:
    """Convert integrity score to status string."""
    if integrity_score >= 0.9:
        return "EXCELLENT"
    elif integrity_score >= 0.7:
        return "GOOD"
    elif integrity_score >= 0.5:
        return "FAIR"
    else:
        return "POOR"
