#!/usr/bin/env python3
"""
TOC (Table of Contents) integrity checker.

This module verifies the integrity of TOC extraction by comparing
PDF bookmarks against extracted sections.
"""
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List


def run_toc_check(path: Path) -> Dict[str, Any]:
    """
    Run TOC integrity check on existing pipeline output.

    Compares PDF TOC bookmarks against extracted sections to measure
    extraction quality.

    Args:
        path: Path to DuckDB file or pipeline output directory

    Returns:
        Dict with TOC integrity report:
        - success: True/False
        - has_toc: Whether PDF has TOC bookmarks
        - integrity_score: 0.0-1.0 score
        - status: EXCELLENT/GOOD/FAIR/POOR
        - matched: List of matched TOC entries
        - missing: List of unmatched TOC entries
    """
    import duckdb

    # Resolve DuckDB path
    if path.is_dir():
        db_path = path / "corpus.duckdb"
        if not db_path.exists():
            db_path = path / "pipeline.duckdb"
    else:
        db_path = path

    if not db_path.exists():
        return {"success": False, "error": f"DuckDB not found: {db_path}"}

    try:
        con = duckdb.connect(str(db_path), read_only=True)

        # Check if toc_entries table exists
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]

        if "toc_entries" not in table_names:
            return {
                "success": True,
                "has_toc": False,
                "message": "No toc_entries table found. PDF may not have bookmarks.",
                "integrity_score": None,
            }

        # Fetch TOC entries and sections
        toc_rows = con.execute(
            "SELECT id, level, title, page FROM toc_entries ORDER BY id"
        ).fetchall()

        section_rows = con.execute(
            "SELECT id, title, page_start FROM sections ORDER BY page_start, id"
        ).fetchall()

        con.close()

        if not toc_rows:
            return {
                "success": True,
                "has_toc": False,
                "message": "PDF has no TOC/bookmarks",
                "integrity_score": None,
            }

        # Build match report
        toc_entries = [{"id": r[0], "level": r[1], "title": r[2], "page": r[3]} for r in toc_rows]
        sections = [{"id": r[0], "title": r[1], "page_start": r[2]} for r in section_rows]

        matched, missing = _match_toc_to_sections(toc_entries, sections)

        # Calculate integrity score
        total_toc = len(toc_entries)
        matched_count = len(matched)
        integrity_score = round(matched_count / total_toc, 2) if total_toc > 0 else 1.0

        # Determine status
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

    except Exception as e:
        return {"success": False, "error": str(e)}


def _match_toc_to_sections(
    toc_entries: List[Dict[str, Any]],
    sections: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Match TOC entries to extracted sections using fuzzy matching.

    Args:
        toc_entries: List of TOC entries
        sections: List of extracted sections

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
