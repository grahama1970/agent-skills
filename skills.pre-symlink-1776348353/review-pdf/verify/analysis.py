"""Core extraction analysis for review-pdf.

Purpose:
- parse S00/S11 artifacts and source PDF signals into comparable metrics.

Inputs:
- profile/context/structural JSON artifacts and optional source PDF.

Outputs:
- normalized estimate/actual/source metric dictionaries.

Failure modes:
- missing artifacts produce reduced metrics; callers decide pass/fail policy.
"""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz  # type: ignore
except ImportError:
    fitz = None  # type: ignore[assignment]  # optional — only needed by analyze_pdf_source
from loguru import logger

from .models import MATH_TOKEN_RE
from .utils import safe_json, to_float


def _collect_profiles_with_fd(
    input_path: Path, limit: Optional[int]
) -> Optional[List[Path]]:
    """Use fd for bounded profile discovery; return None when fd is unavailable."""
    cmd = [
        "fd",
        "-p",
        "--hidden",
        "--no-ignore",
        "--follow",
        "--type",
        "file",
        "--glob",
        "**/00_profile_detector/profile.json",
    ]
    if limit is not None and limit > 0:
        cmd.extend(["--max-results", str(limit)])
    cmd.append(str(input_path))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            f"profile discovery timed out under {input_path}; continuing without pre-discovered profiles"
        )
        return []
    if proc.returncode != 0:
        return []
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return [Path(line).resolve() for line in lines]


def collect_profiles(input_path: Path, limit: Optional[int] = None) -> List[Path]:
    """Collect profile.json files from a run dir tree or direct profile path."""
    if input_path.is_file() and input_path.name == "profile.json":
        return [input_path]
    candidate = input_path / "00_profile_detector" / "profile.json"
    if candidate.exists():
        return [candidate]

    fd_results = _collect_profiles_with_fd(input_path, limit=limit)
    if fd_results is not None:
        return sorted(fd_results)

    profiles: List[Path] = []
    for profile_path in input_path.rglob("00_profile_detector/profile.json"):
        profiles.append(profile_path)
        if limit is not None and limit > 0 and len(profiles) >= limit:
            break
    return sorted(profiles)


def resolve_doc_inputs(profile_path: Path) -> Dict[str, Optional[Path]]:
    """Resolve run-local artifact paths from one profile.json path."""
    run_dir = profile_path.parent.parent
    profile = safe_json(profile_path)
    structural_path = run_dir / "11_json_exporter" / "structural.json"
    flattened_path = run_dir / "10_arangodb_exporter" / "json_output" / "10_flattened_data.json"
    sections_path = run_dir / "04_section_builder" / "json_output" / "04_sections.json"
    context_path = run_dir / "pipeline_context.json"
    pdf_path: Optional[Path] = None

    source_pdf = profile.get("file")
    if isinstance(source_pdf, str) and source_pdf:
        candidate = Path(source_pdf)
        if candidate.exists():
            pdf_path = candidate
    if pdf_path is None:
        run_local = sorted(run_dir.glob("*.pdf"))
        if run_local:
            pdf_path = run_local[0]

    return {
        "run_dir": run_dir,
        "profile_path": profile_path,
        "structural_path": structural_path if structural_path.exists() else None,
        "flattened_path": flattened_path if flattened_path.exists() else None,
        "sections_path": sections_path if sections_path.exists() else None,
        "context_path": context_path if context_path.exists() else None,
        "pdf_path": pdf_path,
    }


def _first_not_none(*values, default=0):
    """Return first value that is not None, or default.

    Unlike ``X or Y``, treats 0, False, and empty string as valid values.
    """
    for v in values:
        if v is not None:
            return v
    return default


def extract_s00_estimates(
    profile: Dict[str, Any], context: Dict[str, Any]
) -> Dict[str, Any]:
    """Normalize S00 estimate keys used for S11 fidelity comparison."""
    elements = profile.get("elements", {}) or {}
    hierarchy = profile.get("hierarchy", {}) or {}
    toc = profile.get("toc", {}) or {}
    layout = profile.get("layout", {}) or {}
    return {
        "page_count": int(_first_not_none(
            profile.get("page_count"), context.get("page_count"), default=0)),
        "estimated_sections": int(_first_not_none(
            hierarchy.get("estimated_sections"), context.get("toc_entry_count"), default=0)),
        "estimated_sections_regex": int(_first_not_none(
            hierarchy.get("estimated_sections_regex"), default=0)),
        "estimated_sections_font": int(_first_not_none(
            hierarchy.get("estimated_sections_font"), default=0)),
        "estimated_sections_toc": int(_first_not_none(
            hierarchy.get("estimated_sections_toc"),
            toc.get("entry_count"),
            context.get("toc_entry_count"),
            default=0)),
        "estimated_table_count": int(_first_not_none(
            elements.get("estimated_table_count"),
            context.get("estimated_table_count"),
            default=0)),
        "table_pages": int(_first_not_none(
            elements.get("table_pages"), context.get("table_pages"), default=0)),
        "image_pages": int(_first_not_none(
            elements.get("image_pages"), context.get("image_pages"), default=0)),
        "has_formulas": bool(
            elements.get("formulas")
            if "formulas" in elements
            else context.get("has_formulas", False)
        ),
        "has_tables": bool(elements.get("tables", False)),
        "has_figures": bool(elements.get("figures", False)),
        "has_requirements": bool(elements.get("requirements", False)),
        "domain": str(_first_not_none(
            profile.get("domain"), context.get("domain"), default="unknown")),
        "layout_columns": int(_first_not_none(
            layout.get("columns"), context.get("layout_columns"), default=1)),
        "file_size_mb": float(_first_not_none(
            profile.get("file_size_mb"), context.get("file_size_mb"), default=0)),
        "estimated_timeout_seconds": int(_first_not_none(
            profile.get("estimated_timeout_seconds"),
            context.get("estimated_timeout_seconds"),
            default=0)),
        "detected_preset": str(_first_not_none(
            (profile.get("preset_match") or {}).get("matched"),
            context.get("detected_preset"),
            default="")),
    }


def normalize_type(raw_value: Any) -> str:
    """Normalize element type tokens to canonical labels."""
    token = str(raw_value or "").strip().lower()
    if token in {"fig", "image", "img"}:
        return "figure"
    if token in {"math"}:
        return "equation"
    if token in {"req", "requirements"}:
        return "requirement"
    if token in {"paragraph", "body"}:
        return "text"
    if token in {"footnote", "footer_note"}:
        return "footnote"
    return token or "unknown"


def extract_bbox(meta: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """Extract first available bbox from metadata."""
    for key in ("bbox", "bbox0", "original_rect"):
        bbox = meta.get(key)
        if isinstance(bbox, list) and len(bbox) == 4:
            x0, y0, x1, y1 = [to_float(value, default=float("nan")) for value in bbox]
            if not any(math.isnan(v) for v in (x0, y0, x1, y1)):
                return (x0, y0, x1, y1)
    return None


def extract_page(meta: Dict[str, Any]) -> Optional[int]:
    """Extract page index/number from metadata keys."""
    for key in ("page_idx", "page_index", "page_num", "page"):
        value = meta.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def analyze_ordering_with_bbox(
    positioned_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check y/x ordering per page, with simple multi-column split handling."""
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for item in positioned_items:
        by_page.setdefault(item["page"], []).append(item)

    page_results: Dict[int, Dict[str, Any]] = {}
    total_violations = 0
    multi_col_pages = 0

    for page, items in by_page.items():
        if len(items) < 4:
            page_results[page] = {"multi_col": False, "violations": 0}
            continue

        centers = [item["cx"] for item in items]
        min_x, max_x = min(centers), max(centers)
        span = max_x - min_x
        threshold = max(90.0, span * 0.33)
        split_x = (min_x + max_x) / 2.0
        looks_multi_col = span > threshold and len(items) >= 8
        if looks_multi_col:
            multi_col_pages += 1

        ordered = sorted(items, key=lambda row: (row["sort_order"], row["index"]))
        page_violations = 0
        for prev, curr in zip(ordered, ordered[1:]):
            if looks_multi_col:
                prev_col = 0 if prev["cx"] < split_x else 1
                curr_col = 0 if curr["cx"] < split_x else 1
                if prev_col == curr_col and curr["y0"] + 3.0 < prev["y0"]:
                    page_violations += 1
            elif curr["y0"] + 3.0 < prev["y0"]:
                page_violations += 1

        total_violations += page_violations
        page_results[page] = {
            "multi_col": looks_multi_col,
            "violations": page_violations,
        }

    return {
        "bbox_pages_checked": len(by_page),
        "bbox_multi_col_pages": multi_col_pages,
        "bbox_order_violations": total_violations,
        "bbox_page_results": page_results,
    }


def analyze_s11_structural(structural: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze extracted structure quality and ordering metrics."""
    sections = structural.get("sections", []) or []
    type_counts: Dict[str, int] = {}
    section_count = len(sections)
    empty_sections = 0
    empty_elements = 0
    element_count = 0
    text_length = 0
    sort_order_violations = 0
    unknown_type_count = 0
    section_titles_missing = 0
    content_freq: Dict[str, int] = {}
    positioned_items: List[Dict[str, Any]] = []

    for sec_idx, section in enumerate(sections):
        title = str(section.get("title") or "").strip()
        elements = section.get("elements", []) or []
        if not title:
            section_titles_missing += 1
        if not elements:
            empty_sections += 1

        last_sort: Optional[float] = None
        for el_idx, element in enumerate(elements):
            element_count += 1
            element_type = normalize_type(element.get("type"))
            type_counts[element_type] = type_counts.get(element_type, 0) + 1
            if element_type == "unknown":
                unknown_type_count += 1

            content = element.get("content")
            if isinstance(content, str):
                text_length += len(content)
                normalized = re.sub(r"\s+", " ", content).strip().lower()
                if len(normalized) >= 30:
                    content_freq[normalized] = content_freq.get(normalized, 0) + 1
            elif content is None:
                content = ""

            if not str(content).strip() and not element.get("structured_data"):
                empty_elements += 1

            sort_order = to_float(element.get("sort_order"), default=float("nan"))
            if not math.isnan(sort_order):
                if last_sort is not None and sort_order < last_sort:
                    sort_order_violations += 1
                last_sort = sort_order

            metadata = (
                element.get("metadata")
                if isinstance(element.get("metadata"), dict)
                else {}
            )
            page = extract_page(metadata)
            bbox = extract_bbox(metadata)
            if page is not None and bbox is not None and not math.isnan(sort_order):
                x0, y0, x1, y1 = bbox
                positioned_items.append(
                    {
                        "index": (sec_idx * 100000) + el_idx,
                        "page": page,
                        "sort_order": sort_order,
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1,
                        "cx": (x0 + x1) / 2.0,
                    }
                )

    duplicates = [count for count in content_freq.values() if count > 1]
    duplicate_count = sum(duplicates) - len(duplicates)
    duplicate_count = max(0, duplicate_count)

    ordering_bbox = analyze_ordering_with_bbox(positioned_items)

    # If marker didn't classify any blocks as figure/image, S06 had no input
    # to extract from.  Don't penalize for pipeline input limitations — score
    # as not_available (0.7) instead of fail (0.0).  Same logic for tables.
    _fig_count = type_counts.get("figure", 0) + type_counts.get("image", 0)
    _tbl_count = type_counts.get("table", 0)

    return {
        "section_count": section_count,
        "empty_sections": empty_sections,
        "section_titles_missing": section_titles_missing,
        "element_count": element_count,
        "empty_elements": empty_elements,
        "empty_ratio": empty_elements / max(1, element_count),
        "duplicate_count": duplicate_count,
        "duplicate_ratio": duplicate_count / max(1, element_count),
        "type_counts": type_counts,
        "text_length": text_length,
        "sort_order_violations": sort_order_violations,
        "unknown_type_count": unknown_type_count,
        "figure_extraction_available": _fig_count > 0,
        "table_extraction_available": _tbl_count > 0,
        **ordering_bbox,
    }


def analyze_flattened_data(flattened: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze extraction quality from 10_flattened_data.json format.

    Produces the same metric dict as analyze_s11_structural() so the scoring
    pipeline works identically.  Ordering metrics (sort_order, bbox) are
    unavailable in the flat format and reported as zero.
    """
    # Map object_type -> canonical type
    TYPE_MAP = {
        "Text": "text", "Table": "table", "Figure": "figure",
        "Equation": "equation", "Requirement": "requirement",
    }

    type_counts: Dict[str, int] = {}
    sections_seen: Dict[str, Dict[str, Any]] = {}  # section_id -> info
    element_count = 0
    empty_elements = 0
    text_length = 0
    unknown_type_count = 0
    content_freq: Dict[str, int] = {}

    for entry in flattened:
        element_count += 1
        raw_type = entry.get("object_type", "unknown")
        etype = TYPE_MAP.get(raw_type, raw_type.lower())
        type_counts[etype] = type_counts.get(etype, 0) + 1
        if etype not in TYPE_MAP.values():
            unknown_type_count += 1

        text = entry.get("text_content", "") or ""
        text_length += len(text)
        if not text.strip():
            empty_elements += 1

        normalized = re.sub(r"\s+", " ", text).strip().lower()
        if len(normalized) >= 30:
            content_freq[normalized] = content_freq.get(normalized, 0) + 1

        sid = entry.get("section_id")
        if sid is not None:
            if sid not in sections_seen:
                sections_seen[sid] = {
                    "title": entry.get("section_title", ""),
                    "has_elements": False,
                }
            sections_seen[sid]["has_elements"] = True

    section_count = max(len(sections_seen), 1)
    empty_sections = sum(1 for s in sections_seen.values() if not s["has_elements"])
    section_titles_missing = sum(1 for s in sections_seen.values() if not s["title"])

    duplicates = [c for c in content_freq.values() if c > 1]
    duplicate_count = max(0, sum(duplicates) - len(duplicates))

    _fig_count = type_counts.get("figure", 0) + type_counts.get("image", 0)
    _tbl_count = type_counts.get("table", 0)

    return {
        "section_count": section_count,
        "empty_sections": empty_sections,
        "section_titles_missing": section_titles_missing,
        "element_count": element_count,
        "empty_elements": empty_elements,
        "empty_ratio": empty_elements / max(1, element_count),
        "duplicate_count": duplicate_count,
        "duplicate_ratio": duplicate_count / max(1, element_count),
        "type_counts": type_counts,
        "text_length": text_length,
        "sort_order_violations": 0,  # Not available in flattened format
        "unknown_type_count": unknown_type_count,
        "figure_extraction_available": _fig_count > 0,
        "table_extraction_available": _tbl_count > 0,
        "bbox_pages_checked": 0,
        "bbox_multi_col_pages": 0,
        "bbox_order_violations": 0,
        "bbox_page_results": {},
    }


def analyze_sections_data(sections_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze extraction quality from 04_sections.json format.

    This is the most common artifact — produced by s04_section_builder for
    93%+ of extractions.  Uses 'blocks' (not 'elements') with block_type
    instead of object_type.  Produces the same metric dict as
    analyze_s11_structural() so the scoring pipeline works identically.
    """
    BLOCK_TYPE_MAP = {
        "table": "table", "figure": "figure", "image": "figure",
        "equation": "equation", "math": "equation",
        "requirement": "requirement", "req": "requirement",
    }

    sections = sections_data.get("sections", []) or []
    type_counts: Dict[str, int] = {}
    section_count = len(sections)
    empty_sections = 0
    empty_elements = 0
    element_count = 0
    text_length = 0
    unknown_type_count = 0
    section_titles_missing = 0
    content_freq: Dict[str, int] = {}

    for section in sections:
        title = str(section.get("title") or "").strip()
        blocks = section.get("blocks", []) or section.get("elements", []) or []
        if not title:
            section_titles_missing += 1
        if not blocks:
            empty_sections += 1

        for block in blocks:
            element_count += 1
            raw_type = str(block.get("block_type") or block.get("type") or "").strip().lower()
            etype = BLOCK_TYPE_MAP.get(raw_type, "text")
            type_counts[etype] = type_counts.get(etype, 0) + 1

            text = block.get("text") or block.get("content") or ""
            text_length += len(text)
            if not str(text).strip():
                empty_elements += 1

            normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
            if len(normalized) >= 30:
                content_freq[normalized] = content_freq.get(normalized, 0) + 1

    duplicates = [c for c in content_freq.values() if c > 1]
    duplicate_count = max(0, sum(duplicates) - len(duplicates))

    return {
        "section_count": section_count,
        "empty_sections": empty_sections,
        "section_titles_missing": section_titles_missing,
        "element_count": element_count,
        "empty_elements": empty_elements,
        "empty_ratio": empty_elements / max(1, element_count),
        "duplicate_count": duplicate_count,
        "duplicate_ratio": duplicate_count / max(1, element_count),
        "type_counts": type_counts,
        "text_length": text_length,
        "sort_order_violations": 0,
        "unknown_type_count": unknown_type_count,
        "bbox_pages_checked": 0,
        "bbox_multi_col_pages": 0,
        "bbox_order_violations": 0,
        "bbox_page_results": {},
        # S04 sections artifact does not contain S05 table or S06 figure output.
        # Mark these capabilities as unavailable so the scorer doesn't penalize
        # for missing tables/figures that were never extracted.
        "table_extraction_available": False,
        "figure_extraction_available": False,
    }


def analyze_pdf_source(pdf_path: Optional[Path]) -> Dict[str, Any]:
    """Extract raw source-level signals used for coverage checks."""
    if not pdf_path or not pdf_path.exists():
        return {"available": False}
    if fitz is None:
        logger.debug("fitz (PyMuPDF) not available — skipping PDF source analysis")
        return {"available": False}
    document = fitz.open(pdf_path)
    raw_text_length = 0
    math_symbol_count = 0
    for page in document:
        text = page.get_text("text")
        raw_text_length += len(text)
        math_symbol_count += len(MATH_TOKEN_RE.findall(text))
    return {
        "available": True,
        "page_count": len(document),
        "raw_text_length": raw_text_length,
        "math_symbol_count": math_symbol_count,
        "math_symbol_density": (math_symbol_count / max(1, raw_text_length)),
    }
