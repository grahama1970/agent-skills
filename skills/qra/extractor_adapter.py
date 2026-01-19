#!/usr/bin/env python3
"""
Extractor Adapter for QRA Skill

Converts extractor's Stage 10 canonical output (10_flattened_data.json) into
sections ready for QRA extraction.

Complies with extractor's HAPPYPATH_GUIDE.md:
- Uses Stage 10 as the canonical integration point
- Consumes 10_flattened_data.json (normalized, enriched output)

Usage:
    from extractor_adapter import load_extractor_sections
    sections = load_extractor_sections("/path/to/extractor/results")
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict


def find_stage10_json(results_dir: Path) -> Optional[Path]:
    """Find the Stage 10 flattened JSON in extractor results.

    Searches common locations per HAPPYPATH_GUIDE.md:
    - <results>/10_arangodb_exporter/json_output/10_flattened_data.json
    - <results>/<stem>/10_arangodb_exporter/json_output/10_flattened_data.json
    """
    results_dir = Path(results_dir)

    # Direct path (PDF accurate mode)
    direct = results_dir / "10_arangodb_exporter" / "json_output" / "10_flattened_data.json"
    if direct.exists():
        return direct

    # Nested path (structured formats)
    for subdir in results_dir.iterdir():
        if subdir.is_dir():
            nested = subdir / "10_arangodb_exporter" / "json_output" / "10_flattened_data.json"
            if nested.exists():
                return nested

    return None


def load_extractor_sections(
    results_dir: str,
    include_figures: bool = True,
    include_tables: bool = True,
    max_section_chars: int = 5000,
) -> List[Tuple[str, str]]:
    """Load extractor Stage 10 output as QRA-ready sections.

    Args:
        results_dir: Path to extractor results directory
        include_figures: Include figure descriptions in section text
        include_tables: Include table descriptions in section text
        max_section_chars: Split sections exceeding this limit

    Returns:
        List of (section_title, section_text) tuples ready for QRA extraction
    """
    results_path = Path(results_dir)

    # Find Stage 10 JSON
    stage10_path = find_stage10_json(results_path)
    if not stage10_path:
        raise FileNotFoundError(
            f"Stage 10 output not found in {results_dir}. "
            "Expected: 10_arangodb_exporter/json_output/10_flattened_data.json\n"
            "Run extractor with: python -m src.cli extract <input> <out_dir> --mode accurate"
        )

    # Load Stage 10 data
    with open(stage10_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not entries:
        return []

    # Group entries by section_id
    sections_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "title": "",
        "breadcrumbs": [],
        "level": 0,
        "summary": "",
        "key_concepts": [],
        "text_parts": [],
        "figures": [],
        "tables": [],
    })

    for entry in entries:
        section_id = entry.get("section_id", "unknown")
        sec = sections_map[section_id]

        # Capture section metadata (from first entry)
        if not sec["title"]:
            sec["title"] = entry.get("section_title", "Untitled")
            sec["breadcrumbs"] = entry.get("section_breadcrumbs", [])
            sec["level"] = entry.get("section_level", 0)
            summary_data = entry.get("section_summary", {})
            if isinstance(summary_data, dict):
                sec["summary"] = summary_data.get("summary", "")
                sec["key_concepts"] = summary_data.get("key_concepts", [])

        obj_type = entry.get("object_type", "Text")
        text_content = entry.get("text_content", "")

        if obj_type == "Text":
            sec["text_parts"].append(text_content)
        elif obj_type == "Figure" and include_figures:
            # Extract figure description
            data = entry.get("data", {})
            fig_id = data.get("figure_id", "")
            desc = data.get("ai_description", "")
            if desc and desc != "Description skipped (offline)":
                sec["figures"].append(f"[Figure {fig_id}]: {desc}")
            elif text_content and "Description" not in text_content:
                sec["figures"].append(f"[Figure {fig_id}]: {text_content}")
        elif obj_type == "Table" and include_tables:
            data = entry.get("data", {})
            table_id = data.get("table_id", "")
            desc = data.get("ai_description", "")
            if desc:
                sec["tables"].append(f"[Table {table_id}]: {desc}")
            elif text_content:
                sec["tables"].append(f"[Table {table_id}]: {text_content}")

    # Convert to QRA section format
    result: List[Tuple[str, str]] = []

    for section_id, sec in sections_map.items():
        # Build enriched section text
        parts = []

        # Add breadcrumb context
        if sec["breadcrumbs"]:
            breadcrumb_str = " > ".join(sec["breadcrumbs"])
            parts.append(f"Section: {breadcrumb_str}")

        # Add summary if available (provides context for QRA)
        if sec["summary"]:
            parts.append(f"Summary: {sec['summary']}")

        # Add key concepts
        if sec["key_concepts"]:
            parts.append(f"Key concepts: {', '.join(sec['key_concepts'])}")

        parts.append("")  # Blank line before content

        # Add main text
        parts.extend(sec["text_parts"])

        # Add figure descriptions
        if sec["figures"]:
            parts.append("\n--- Figures ---")
            parts.extend(sec["figures"])

        # Add table descriptions
        if sec["tables"]:
            parts.append("\n--- Tables ---")
            parts.extend(sec["tables"])

        section_text = "\n".join(parts).strip()

        if not section_text:
            continue

        # Split if exceeds max chars
        if len(section_text) <= max_section_chars:
            result.append((sec["title"], section_text))
        else:
            # Split into chunks, preserving title
            chunks = _split_text(section_text, max_section_chars)
            for i, chunk in enumerate(chunks):
                chunk_title = f"{sec['title']} (part {i+1})" if len(chunks) > 1 else sec["title"]
                result.append((chunk_title, chunk))

    return result


def _split_text(text: str, max_chars: int) -> List[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for \n\n
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def get_extractor_metadata(results_dir: str) -> Dict[str, Any]:
    """Get metadata about the extractor run for QRA context.

    Returns:
        Dict with source_file, preset, page_count, etc.
    """
    results_path = Path(results_dir)
    metadata = {}

    # Try to find pipeline metadata
    meta_paths = [
        results_path / "pipeline_metadata.json",
        results_path / "00_profile_detector" / "json_output" / "00_profile.json",
    ]

    for meta_path in meta_paths:
        if meta_path.exists():
            with open(meta_path, "r") as f:
                data = json.load(f)
                metadata.update(data)
                break

    return metadata


if __name__ == "__main__":
    # Self-test with sample extractor output
    import sys

    if len(sys.argv) < 2:
        print("Usage: python extractor_adapter.py <extractor_results_dir>")
        sys.exit(1)

    results_dir = sys.argv[1]

    try:
        sections = load_extractor_sections(results_dir)
        print(f"Loaded {len(sections)} sections from extractor output")
        for title, text in sections[:3]:
            print(f"\n--- {title} ---")
            print(text[:200] + "..." if len(text) > 200 else text)
        print("\nPASS: Extractor adapter working")
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
