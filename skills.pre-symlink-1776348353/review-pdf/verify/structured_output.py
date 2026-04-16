"""Structured document output writer for non-PDF extractable formats.

Parses JSON output from structured extractors (DOCX, HTML, PPTX, etc.)
and writes to the pipeline directory structure expected by downstream
scoring (00_profile_detector/profile.json and 11_json_exporter/structural.json).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any, Dict

from loguru import logger


def _write_structured_output(
    stdout: str, run_dir: Path, doc_path: Path
) -> bool:
    """Parse structured extractor JSON output and write to pipeline dirs.

    The structured extractor (DOCX, HTML, etc.) outputs JSON to stdout
    instead of writing to the pipeline directory structure. This function
    creates the expected 00_profile_detector/profile.json and
    11_json_exporter/structural.json so the scoring pipeline can find them.

    Returns True if files were written successfully.
    """
    try:
        data = _json.loads(stdout.strip())
    except (ValueError, TypeError):
        return False

    if not data.get("success"):
        return False

    document = data.get("document", {})
    if not document:
        return False

    # Write profile.json (minimal S00-compatible profile)
    profile_dir = run_dir / "00_profile_detector"
    profile_dir.mkdir(parents=True, exist_ok=True)
    metadata = document.get("metadata", {})
    _sections = document.get("sections", [])
    _tables = document.get("tables", [])
    _figures = document.get("figures", [])
    _blocks = document.get("blocks", [])
    _fmt = doc_path.suffix.lower().lstrip(".")
    _file_size_mb = 0.0
    try:
        _file_size_mb = round(doc_path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        pass
    profile = {
        "file": str(doc_path.resolve()),
        "source_file": str(doc_path.resolve()),
        "format": doc_path.suffix.lower(),
        "page_count": metadata.get("page_count") or 0,
        "file_size_mb": _file_size_mb,
        "domain": "structured",
        "detected_preset": f"{_fmt}_structured",
        "is_scanned": False,
        "estimated_timeout_seconds": 60,
        "timeout_source": "structured_default",
        "preset_match": {"matched": "structured", "confidence": 1.0},
        "hierarchy": {
            "estimated_sections": len(_sections),
            "has_structure": True,
        },
        "elements": {
            "tables": bool(_tables or any(
                b.get("type", "").lower() == "table" for b in _blocks
            )),
            "figures": bool(_figures or any(
                b.get("type", "").lower() in ("figure", "image") for b in _blocks
            )),
            "formulas": any(
                b.get("type", "").lower() in ("equation", "formula", "math") for b in _blocks
            ),
            "requirements": False,
            "estimated_table_count": len(_tables) or sum(
                1 for b in _blocks if b.get("type", "").lower() == "table"
            ),
            "estimated_figure_count": len(_figures) or sum(
                1 for b in _blocks if b.get("type", "").lower() in ("figure", "image")
            ),
            "estimated_section_count": len(_sections) or sum(
                1 for b in _blocks if b.get("type", "").lower() in ("heading", "title")
            ),
            "text_block_count": sum(
                1 for b in _blocks if b.get("type", "").lower() in ("text", "paragraph")
            ),
        },
        "layout": {"style": "structured", "columns": 1},
        "context": {
            "total_blocks": len(_blocks),
            "format_type": _fmt,
        },
        "route": "structured",
    }
    (profile_dir / "profile.json").write_text(
        _json.dumps(profile, indent=2), encoding="utf-8"
    )

    # Write structural.json (the full extraction result)
    structural_dir = run_dir / "11_json_exporter"
    structural_dir.mkdir(parents=True, exist_ok=True)

    # Build structural.json in the expected format:
    # list of flattened content items with _key, object_type, text_content, etc.
    items = []
    source_file = str(doc_path.resolve())

    # Strategy 1: top-level "blocks" (DOCX/PPTX provider format)
    blocks = document.get("blocks", [])
    current_section = ""
    section_idx = 0
    for bidx, block in enumerate(blocks):
        block_type = block.get("type", "text").lower()
        text = block.get("content", block.get("text", ""))
        if not text:
            continue
        # Track section titles from heading blocks
        if block_type in ("heading", "title"):
            current_section = text
            section_idx += 1
        obj_type = "section" if block_type in ("heading", "title") else (
            "table" if block_type == "table" else "text"
        )
        items.append({
            "_key": f"b{bidx}",
            "object_type": obj_type,
            "text_content": text,
            "section_id": str(section_idx),
            "section_title": current_section,
            "page_num": block.get("page", 0),
            "source_pdf": source_file,
        })

    # Strategy 2: "sections" with nested "blocks" (alternative provider format)
    if not items:
        sections = document.get("sections", [])
        for idx, section in enumerate(sections):
            title = section.get("title", section.get("heading", ""))
            sub_blocks = section.get("blocks", [])
            for sbidx, block in enumerate(sub_blocks):
                block_type = block.get("block_type", block.get("type", "Text"))
                text = block.get("text", block.get("content", ""))
                if not text:
                    continue
                items.append({
                    "_key": f"s{idx}_b{sbidx}",
                    "object_type": "text" if block_type in ("Text", "Paragraph") else block_type.lower(),
                    "text_content": text,
                    "section_id": str(idx),
                    "section_title": title,
                    "page_num": block.get("page", 0),
                    "source_pdf": source_file,
                })

    # Strategy 3: "pages" with nested "blocks"
    if not items:
        pages = document.get("pages", [])
        for pidx, page in enumerate(pages):
            page_blocks = page.get("blocks", [])
            for pbidx, block in enumerate(page_blocks):
                text = block.get("text", block.get("content", ""))
                if not text:
                    continue
                items.append({
                    "_key": f"p{pidx}_b{pbidx}",
                    "object_type": block.get("block_type", block.get("type", "text")).lower(),
                    "text_content": text,
                    "section_id": str(pidx),
                    "section_title": "",
                    "page_num": pidx,
                    "source_pdf": source_file,
                })

    # Strategy 4: full_text fallback
    if not items and document.get("full_text"):
        items.append({
            "_key": "full_text",
            "object_type": "text",
            "text_content": document["full_text"],
            "section_id": "0",
            "section_title": metadata.get("title", ""),
            "page_num": 0,
            "source_pdf": source_file,
        })

    # Group items into sections for S11 structural.json format
    # (analyze_s11_structural expects "sections" -> "elements")
    section_groups: dict = {}
    for item in items:
        sid = item["section_id"]
        if sid not in section_groups:
            section_groups[sid] = {
                "title": item.get("section_title", ""),
                "elements": [],
            }
        section_groups[sid]["elements"].append({
            "type": item["object_type"],
            "content": item["text_content"],
            "page": item.get("page_num", 0),
            "sort_key": len(section_groups[sid]["elements"]),
        })

    structural = {
        "source_file": str(doc_path.resolve()),
        "format": doc_path.suffix.lower(),
        "metadata": metadata,
        "sections": list(section_groups.values()),
        "items": items,
        "item_count": len(items),
    }
    (structural_dir / "structural.json").write_text(
        _json.dumps(structural, indent=2), encoding="utf-8"
    )

    print(
        f"review-pdf structured_output_written "
        f"profile={profile_dir / 'profile.json'} "
        f"structural_items={len(items)} "
        f"doc={doc_path}",
        flush=True,
    )
    return True
