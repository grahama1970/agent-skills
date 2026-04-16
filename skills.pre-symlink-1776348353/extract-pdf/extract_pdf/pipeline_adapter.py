"""Pipeline adapter: convert pdf_oxide output to extractor-compatible directory structure.

Writes S00 (profile), S02 (blocks), S03 (headers), S04 (sections),
S04a (layout audit), S06 (figures) output files that downstream
pipeline stages (S05 tables, S05b/c, S06b VLM, S07+) consume unchanged.

This is the canonical implementation. The extractor project's
s02_pdf_oxide_adapter.py delegates here.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger


def _block_type_map(oxide_type: str) -> str:
    """Map pdf_oxide block_type to S02 pymupdf block_type names."""
    mapping = {
        "Title": "SectionHeader",
        "Header": "SectionHeader",
        "Body": "Text",
        "Equation": "Equation",
        "Boilerplate": "Footer",
        "Caption": "Text",
        "ListItem": "Text",
        "Code": "Text",
        "Footnote": "Footnote",
        "PageNumber": "Footer",
    }
    return mapping.get(oxide_type, "Text")


def _is_header_type(oxide_type: str) -> bool:
    return oxide_type in ("Title", "Header")


def _adapt_blocks(
    pages: List[Dict[str, Any]],
    source_pdf: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """Convert pdf_oxide per-page blocks to flat S02-compatible block list."""
    blocks = []
    block_idx = 0
    suspicious_count = 0

    for page_data in pages:
        page_num = page_data["page"]
        for block in page_data.get("blocks", []):
            bbox = block.get("bbox", [0, 0, 0, 0])
            is_header = _is_header_type(block.get("block_type", "Body"))
            confidence = block.get("confidence", 0.5)

            adapted = {
                "id": f"p{page_num}_b{block_idx}",
                "page": page_num,
                "page_idx": page_num,
                "bbox": bbox,
                "text": block.get("text", ""),
                "block_type": _block_type_map(block.get("block_type", "Body")),
                "font_size": block.get("font_size", 12.0),
                "font_flags": 0,
                "font_color": [0, 0, 0],
                "font_color_bucket": "black",
                "is_header": is_header,
                "header_confidence": confidence if is_header else 0.0,
                "header_level": block.get("header_level"),
                "first_span_font": {
                    "name": block.get("font_name", ""),
                    "size": block.get("font_size", 12.0),
                    "flags": 1 if block.get("is_bold") else 0,
                },
                "header_footer_region": None,
                "is_footnote": block.get("block_type") == "Footnote",
                "is_equation": block.get("block_type") == "Equation",
                "latex_content": None,
            }

            if is_header and confidence < 0.7:
                suspicious_count += 1

            blocks.append(adapted)
            block_idx += 1

    return blocks, suspicious_count


def _adapt_profile(
    profile: Dict[str, Any],
    pdf_path: Path,
    page_count: int,
    duration_ms: int,
) -> Dict[str, Any]:
    """Convert pdf_oxide profile to S00-compatible profile.json format."""
    file_size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 2)

    return {
        "domain": profile.get("domain", "general"),
        "page_count": page_count,
        "file_size_mb": file_size_mb,
        "estimated_timeout_seconds": max(60, page_count * 5),
        "timeout_source": "pdf_oxide_estimate",
        "layout": {
            "columns": profile.get("column_count", 1),
            "style": "double" if profile.get("column_count", 1) > 1 else "single",
        },
        "hierarchy": {
            "estimated_sections": 0,
            "max_depth": 3,
        },
        "elements": {
            "tables": profile.get("has_tables", False),
            "table_pages": 0,
            "estimated_table_count": 0,
            "max_tables_per_page": 0,
            "figures": profile.get("has_images", False),
            "image_pages": 0,
            "formulas": False,
            "requirements": False,
        },
        "preset_match": {
            "matched": profile.get("domain", "general"),
            "score": 0.8,
            "config_name": profile.get("domain", "general"),
        },
        "toc": {
            "has_toc": profile.get("has_toc", False),
            "entry_count": 0,
            "max_depth": 0,
            "entries": [],
        },
        "route": "standard",
        "complexity_score": profile.get("complexity_score", 2.0),
        "thresholds_hit": [],
        "detected_preset": profile.get("domain", "general"),
        "classifier": {},
        "table_style": "none",
        "has_multi_column": profile.get("column_count", 1) > 1,
        "is_scanned": profile.get("is_scanned", False),
        "file": str(pdf_path),
        "timestamp": time.time(),
        "duration_ms": duration_ms,
        "engine": "pdf_oxide",
    }


def _adapt_sections(
    sections: List[Dict[str, Any]],
    blocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert pdf_oxide sections to S04-compatible section list."""
    adapted = []
    for i, sec in enumerate(sections):
        page_start = sec.get("page", 0)
        page_end = sections[i + 1]["page"] if i + 1 < len(sections) else page_start

        sec_blocks = [
            b for b in blocks
            if page_start <= b["page"] <= page_end
        ]

        content_text = " ".join(b["text"] for b in sec_blocks if not b["is_header"])

        adapted.append({
            "id": f"sec_{i}",
            "title": sec.get("title", ""),
            "level": sec.get("level", 1),
            "page_start": page_start,
            "page_end": page_end,
            "parent_id": None,
            "blocks": sec_blocks,
            "bbox": sec_blocks[0]["bbox"] if sec_blocks else [0, 0, 0, 0],
            "content": content_text[:2000],
            "metadata": {
                "is_slide": False,
                "slide_number": 0,
                "block_count": len(sec_blocks),
                "section_number": sec.get("numbering", ""),
                "section_depth": [sec.get("level", 1)],
                "validation_method": "pdf_oxide",
            },
        })

    return adapted


def _adapt_figures(
    figures: List[Dict[str, Any]],
    pdf_path: Path,
    out_dir: Path,
) -> List[Dict[str, Any]]:
    """Convert pdf_oxide figures to S06-compatible figure list."""
    adapted = []
    for i, fig in enumerate(figures):
        fig_id = f"fig_p{fig.get('page', 0)}_{i}"
        adapted.append({
            "figure_id": fig_id,
            "page": fig.get("page", 0),
            "image_path": "",
            "bbox": fig.get("bbox", [0, 0, 0, 0]),
            "ai_description": None,
            "title": fig.get("caption"),
            "title_source": "pdf_oxide" if fig.get("caption") else None,
            "number": fig.get("caption_number"),
            "base_title": fig.get("caption"),
            "normalized_id": f"figure-{i + 1}",
            "context_above": fig.get("context_above", ""),
            "context_below": fig.get("context_below", ""),
            "context_nearby": "",
            "section_id": None,
            "section_title": fig.get("section_title"),
            "metadata": {"engine": "pdf_oxide"},
            "extraction_time": datetime.now(timezone.utc).isoformat(),
        })

    return adapted


def run_pipeline_adapter(
    pdf_path: Path,
    results_dir: Path,
) -> str:
    """Run pdf_oxide extraction and write pipeline-compatible output.

    Writes S00/S02/S03/S04/S04a/S06 directories that downstream stages consume.
    Returns path to the S02-compatible blocks JSON.
    """
    from pdf_oxide import PdfDocument

    pdf_path = Path(pdf_path)
    results_dir = Path(results_dir)

    t0 = time.monotonic()
    logger.info(f"pdf_oxide pipeline: opening {pdf_path.name}")

    doc = PdfDocument(str(pdf_path))
    page_count = doc.page_count()

    result = doc.extract_document()
    extraction_ms = int((time.monotonic() - t0) * 1000)

    pages = result.get("pages", [])
    profile = result.get("profile", {})
    sections_raw = result.get("sections", [])
    figures_raw = result.get("figures", [])

    blocks, suspicious_count = _adapt_blocks(pages, str(pdf_path))
    adapted_profile = _adapt_profile(profile, pdf_path, page_count, extraction_ms)
    adapted_sections = _adapt_sections(sections_raw, blocks)
    adapted_figures = _adapt_figures(figures_raw, pdf_path, results_dir)

    now_iso = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.md5(
        json.dumps([b["text"] for b in blocks], ensure_ascii=False).encode()
    ).hexdigest()

    # --- S00 profile ---
    s00_dir = results_dir / "00_profile_detector"
    s00_dir.mkdir(parents=True, exist_ok=True)
    (s00_dir / "profile.json").write_text(json.dumps(adapted_profile, indent=2))
    logger.info(
        f"S00: domain={adapted_profile['domain']}, "
        f"pages={page_count}, scanned={adapted_profile.get('is_scanned', False)}"
    )

    # pipeline_context.json
    context_data = {
        "preset_name": adapted_profile.get("detected_preset"),
        "config": {},
        "timestamp": time.time(),
        "profile_path": str(s00_dir / "profile.json"),
    }
    (results_dir / "pipeline_context.json").write_text(json.dumps(context_data, indent=2))

    # --- S02 blocks ---
    s02_dir = results_dir / "02_marker_extractor" / "json_output"
    s02_dir.mkdir(parents=True, exist_ok=True)

    s02_output = {
        "timestamp": now_iso,
        "source_pdf": str(pdf_path),
        "status": "Completed",
        "page_count": page_count,
        "block_count": len(blocks),
        "suspicious_block_count": suspicious_count,
        "blocks": blocks,
        "errors_count": 0,
        "warnings_count": 0,
        "diagnostics": {
            "page_count": page_count,
            "total_blocks": len(blocks),
            "figure_count": len(adapted_figures),
            "scanned_pdf_detection": adapted_profile.get("is_scanned", False),
            "document_type": "scanned" if adapted_profile.get("is_scanned") else "native",
        },
        "timings": {"total_ms": extraction_ms},
        "resources": {},
        "predictors_present": {},
        "fallback_mode": False,
        "is_scanned_pdf": adapted_profile.get("is_scanned", False),
        "predictor_mode": "pdf_oxide",
        "blocks_content_hash": content_hash,
    }

    s02_path = s02_dir / "02_marker_blocks.json"
    s02_path.write_text(json.dumps(s02_output, indent=2, ensure_ascii=False))
    logger.info(f"S02: {len(blocks)} blocks in {extraction_ms}ms")

    # --- S03 header validation ---
    s03_dir = results_dir / "03_suspicious_headers" / "json_output"
    s03_dir.mkdir(parents=True, exist_ok=True)

    s03_output = {
        "timestamp": now_iso,
        "source_json": str(s02_path),
        "status": "Completed",
        "blocks": blocks,
        "suspicious_count": suspicious_count,
        "engine": "pdf_oxide",
    }
    s03_path = s03_dir / "03_suspicious_headers.json"
    s03_path.write_text(json.dumps(s03_output, indent=2, ensure_ascii=False))

    # --- S04 sections ---
    s04_dir = results_dir / "04_section_builder" / "json_output"
    s04_dir.mkdir(parents=True, exist_ok=True)

    s04_output = {
        "success": True,
        "timestamp": now_iso,
        "source_json": str(s03_path),
        "source_pdf": str(pdf_path),
        "status": "Completed",
        "section_count": len(adapted_sections),
        "hierarchy_depth": max((s.get("level", 1) for s in adapted_sections), default=0),
        "visual_captures": 0,
        "suspicious_header_analysis": {},
        "sections": adapted_sections,
        "timings": {"total_ms": extraction_ms},
        "engine": "pdf_oxide",
    }
    s04_path = s04_dir / "04_sections.json"
    s04_path.write_text(json.dumps(s04_output, indent=2, ensure_ascii=False))
    logger.info(f"S04: {len(adapted_sections)} sections")

    # --- S04a layout audit ---
    s04a_dir = results_dir / "04a_layout_audit"
    s04a_dir.mkdir(parents=True, exist_ok=True)

    s04a_output = {
        "timestamp": now_iso,
        "status": "Completed",
        "violations": [],
        "engine": "pdf_oxide",
    }
    (s04a_dir / "04a_layout_audit.json").write_text(json.dumps(s04a_output, indent=2))

    # --- S06 figures ---
    s06_dir = results_dir / "06_figure_extractor" / "json_output"
    s06_dir.mkdir(parents=True, exist_ok=True)
    vis_dir = results_dir / "06_figure_extractor" / "visual_output"
    vis_dir.mkdir(parents=True, exist_ok=True)

    s06_output = {
        "timestamp": now_iso,
        "source_json": str(s02_path),
        "source_pdf": str(pdf_path),
        "status": "Completed",
        "figure_count": len(adapted_figures),
        "figures": adapted_figures,
        "engine": "pdf_oxide",
    }
    s06_path = s06_dir / "06_figures.json"
    s06_path.write_text(json.dumps(s06_output, indent=2, ensure_ascii=False))
    logger.info(f"S06: {len(adapted_figures)} figures")

    # --- scanned_pdf.json ---
    scanned_info = {
        "is_scanned": adapted_profile.get("is_scanned", False),
        "detection_method": "pdf_oxide",
    }
    (results_dir / "scanned_pdf.json").write_text(json.dumps(scanned_info, indent=2))

    logger.info(
        f"pdf_oxide pipeline: complete in {extraction_ms}ms - "
        f"{len(blocks)} blocks, {len(adapted_sections)} sections, "
        f"{len(adapted_figures)} figures"
    )

    return str(s02_path)
