"""Agentic-first pdf-lab orchestration.

This module implements the machine-readable pipeline contracts:

1. agent scan JSON: expected elements selected independently from pdf_oxide
2. pdf_oxide JSON: deterministic extraction for those pages
3. comparison JSON: JSON-to-JSON scoring and mismatch diagnostics

The human-facing HTML/UI is intentionally out of scope here. HTML screenshots
are diagnostics; this module owns the convergence data path.
"""

from __future__ import annotations

import asyncio
import base64
import json
import html
import math
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
import pdf_oxide
from dotenv import load_dotenv
from PIL import Image, ImageDraw

load_dotenv()

from lib.forensic import run_preset_scan, run_toc_scan

try:
    from pdf_oxide.page_review_eval.unknown_region_guards import evaluate_unknown_region_candidate
except Exception:  # pragma: no cover - pdf_oxide development tree may not include the guard yet
    evaluate_unknown_region_candidate = None

try:
    from pdf_oxide.page_review_eval.table_fragment_guards import evaluate_table_fragment_candidate
except Exception:  # pragma: no cover - pdf_oxide development tree may not include the guard yet
    evaluate_table_fragment_candidate = None


_UNKNOWN_REGION_SIDEBAR_NOISE = (
    "this publication is available",
    "free of charge",
    "charge from",
    "https://doi.org/10.6028/nist.sp.800",
    "nist.sp.800",
)
_UNKNOWN_REGION_TABLE_CELL_TEXTS = {"date", "type", "assurance", "implemented", "organization-defined"}
_UNKNOWN_REGION_CONTROL_ID_RE = re.compile(r"\b[A-Z]{2,3}-\d+(?:\(\d+\))?\b")


def _unknown_region_norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _unknown_region_best_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [item for item in payload.get("actual_candidates") or [] if isinstance(item, dict)]
    if not candidates:
        return {}

    def score(candidate: dict[str, Any]) -> float:
        try:
            return float(candidate.get("similarity_to_comparison_text") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return max(candidates, key=score)


def _unknown_region_has_sidebar_noise(text: str) -> bool:
    normalized = _unknown_region_norm(text)
    if any(pattern in normalized for pattern in _UNKNOWN_REGION_SIDEBAR_NOISE):
        return True
    return (
        "this publication is" in normalized
        and "available" in normalized
    ) or ("free" in normalized and "charge" in normalized and "from" in normalized)


def _unknown_region_contains_expected(expected_text: str, candidate_text: str) -> bool:
    expected = _unknown_region_norm(expected_text)
    candidate = _unknown_region_norm(candidate_text)
    return bool(expected) and (expected in candidate or candidate in expected)


def _unknown_region_is_table_cell_fragment(expected_type: str, expected_text: str, candidate_text: str) -> bool:
    expected = _unknown_region_norm(expected_text).strip(" :;")
    candidate = _unknown_region_norm(candidate_text)
    if expected_type == "section_header" and expected in _UNKNOWN_REGION_TABLE_CELL_TEXTS:
        return True
    if expected_type == "section_header" and candidate in {"date type", "implemented assurance"}:
        return True
    return expected_type == "section_header" and expected.isdigit() and len(expected) <= 4


def _local_unknown_region_guard(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("preset_id") != "pdf.unknown_region.v1" or payload.get("actual_json"):
        return {"applies": False, "reason": "not an unresolved unknown-region payload"}
    expected = payload.get("expected_json") if isinstance(payload.get("expected_json"), dict) else {}
    expected_type = str(expected.get("type") or "")
    expected_text = str(expected.get("text") or "")
    candidate = _unknown_region_best_candidate(payload)
    candidate_text = str(candidate.get("text") or "")
    try:
        similarity = float(candidate.get("similarity_to_comparison_text") or 0.0)
    except (TypeError, ValueError):
        similarity = 0.0
    text_present = _unknown_region_contains_expected(expected_text, candidate_text) or similarity >= 0.8
    facts = _unknown_region_norm(payload.get("known_visual_facts"))
    deterministic_present = text_present or "target text is present" in facts or "bbox iou failed" in facts

    if _unknown_region_is_table_cell_fragment(expected_type, expected_text, candidate_text):
        subtype = "table_cell_membership_mismatch"
        resolved_type = "table_cell_or_header_fragment"
        reason = "Target text is present but should be reconciled through table/cell membership, not generic unknown-region review."
    elif expected_type == "list_item":
        subtype = "list_item_embedded_in_text_line"
        resolved_type = "list_item"
        reason = "List item text is present inside a broader extracted text line; split/canonicalize the line before model review."
    elif expected_type == "requirement" or _UNKNOWN_REGION_CONTROL_ID_RE.search(expected_text):
        subtype = "requirement_heading_embedded_in_text_line"
        resolved_type = "requirement"
        reason = "Requirement/control identifier text is present inside a broader extracted line; split/canonicalize the line before model review."
    elif _unknown_region_has_sidebar_noise(candidate_text):
        subtype = "sidebar_watermark_bleed"
        resolved_type = expected_type or "paragraph"
        reason = "Candidate contains expected text plus repeated sidebar/watermark/footer noise; remove noise before comparison."
    elif _unknown_region_contains_expected(expected_text, candidate_text):
        subtype = "compound_header_line_split" if expected_type == "section_header" and candidate.get("type") == "section_header" else "canonicalization_text_fragment"
        resolved_type = "section_heading" if subtype == "compound_header_line_split" else (expected_type or "paragraph")
        reason = "Expected text is present in an actual candidate but failed bbox/type canonicalization."
    elif deterministic_present:
        subtype = "deterministic_comparison_miss"
        resolved_type = expected_type or "unknown_region"
        reason = "Deterministic evidence says the target is present, so this should be resolved by comparison/canonicalization first."
    else:
        return {"applies": False, "reason": "no deterministic unknown-region resolution found"}

    return {
        "applies": True,
        "fixture_family": "unknown_region_canonicalization",
        "subtype": subtype,
        "decision": "resolve_deterministically",
        "resolved_type": resolved_type,
        "expected_type": expected_type or None,
        "best_candidate_id": candidate.get("id"),
        "best_candidate_similarity": similarity,
        "model_review_required": False,
        "recommended_fix_layer": "comparison_canonicalization",
        "reason": reason,
    }


def _local_table_fragment_guard(payload: dict[str, Any]) -> dict[str, Any]:
    actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else {}
    if actual.get("type") != "table":
        return {"applies": False, "reason": "candidate is not a table claim"}
    review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
    metrics = review.get("primary_table_metrics") if isinstance(review.get("primary_table_metrics"), dict) else {}
    raw = actual.get("raw") if isinstance(actual.get("raw"), dict) else {}
    row_count = int(raw.get("row_count") or metrics.get("row_count") or 0)
    col_count = int(raw.get("col_count") or metrics.get("col_count") or 0)
    populated = int(raw.get("populated_column_count") or metrics.get("populated_column_count") or 0)
    has_header = bool(raw.get("has_header") if raw.get("has_header") is not None else metrics.get("has_header"))
    facts = _unknown_region_norm(payload.get("known_visual_facts"))
    adjacent_count = len(review.get("adjacent_table_candidates") or [])
    bbox = actual.get("bbox") if isinstance(actual.get("bbox"), list) else None
    thin_bbox = False
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            thin_bbox = float(bbox[3]) - float(bbox[1]) <= 0.035
        except (TypeError, ValueError):
            thin_bbox = False
    applies = (
        row_count == 1
        and col_count >= 8
        and (
            "repeated table-row structure" in facts
            or "extractor bounds bug" in facts
            or "same-page requirement rows" in facts
            or "same-page section rows" in facts
            or adjacent_count > 0
        )
    )
    if not applies:
        return {
            "applies": False,
            "reason": "insufficient evidence for deterministic table fragment routing",
            "row_count_claimed": row_count,
            "col_count_claimed": col_count,
            "populated_column_count": populated,
            "has_header_claimed": has_header,
            "thin_bbox": thin_bbox,
        }
    return {
        "applies": True,
        "fixture_family": "table_split_merge" if adjacent_count else "table_bbox_expansion",
        "subtype": "single_row_table_fragment",
        "decision": "route_to_table_bbox_expansion",
        "resolved_type": "table",
        "classification": "split_merge_issue" if adjacent_count else "partial_extraction",
        "bbox_error_class": "too_tight",
        "model_review_required": False,
        "recommended_fix_layer": "table_extractor_bbox_expansion",
        "reason": "single-row table candidate is a bbox/merge fragment, not a human table/not-table ambiguity",
    }


BBox = list[float]


@dataclass
class AgentScanResult:
    pdf: str
    output_dir: Path
    expected_elements_path: Path
    toc_path: Path
    preset_scan_path: Path
    selected_pages: list[int]
    expected_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "output_dir": str(self.output_dir),
            "expected_elements_path": str(self.expected_elements_path),
            "toc_path": str(self.toc_path),
            "preset_scan_path": str(self.preset_scan_path),
            "selected_pages": self.selected_pages,
            "expected_count": self.expected_count,
        }


@dataclass
class DeterministicExtractionResult:
    pdf: str
    output_dir: Path
    actual_elements_path: Path
    pages: list[int]
    actual_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "output_dir": str(self.output_dir),
            "actual_elements_path": str(self.actual_elements_path),
            "pages": self.pages,
            "actual_count": self.actual_count,
        }


@dataclass
class JsonComparisonResult:
    comparison_path: Path
    accuracy: float
    matched_count: int
    total_expected: int
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_path": str(self.comparison_path),
            "accuracy": self.accuracy,
            "matched_count": self.matched_count,
            "total_expected": self.total_expected,
            "passed": self.passed,
        }


@dataclass
class AgenticExtractResult:
    pdf: str
    output_dir: Path
    expected_elements_path: Path
    actual_elements_path: Path
    comparison_path: Path
    preset_update_plan_path: Path
    summary_path: Path
    accuracy: float
    passed: bool
    iterations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "output_dir": str(self.output_dir),
            "expected_elements_path": str(self.expected_elements_path),
            "actual_elements_path": str(self.actual_elements_path),
            "comparison_path": str(self.comparison_path),
            "preset_update_plan_path": str(self.preset_update_plan_path),
            "summary_path": str(self.summary_path),
            "accuracy": self.accuracy,
            "passed": self.passed,
            "iterations": self.iterations,
        }


@dataclass
class HumanTriageResult:
    extraction_path: Path
    triage_queue_path: Path
    task_count: int
    page_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction_path": str(self.extraction_path),
            "triage_queue_path": str(self.triage_queue_path),
            "task_count": self.task_count,
            "page_count": self.page_count,
        }


def run_agent_scan(
    pdf: Path,
    *,
    output_dir: Path | None = None,
    max_pages: int = 12,
    top_k: int = 3,
    preset_path: Path | None = None,
) -> AgentScanResult:
    """Create the provisional oracle: expected elements on selected pages.

    The scan intentionally selects pages before running pdf_oxide extraction.
    It uses TOC + preset evidence to choose representative pages, then Poppler
    bbox-layout text as the independent element source. A VLM/LLM second pass can
    replace or enrich this expected JSON later without changing the comparator.
    """
    pdf = pdf.expanduser().resolve()
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")

    if output_dir is None:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        output_dir = Path.home() / ".pi" / "pdf-lab" / "agentic-extract" / f"{pdf.stem}-{stamp}"
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    toc_dir = output_dir / "00_toc_scan"
    preset_dir = output_dir / "01_preset_scan"
    toc = run_toc_scan(pdf, output_dir=toc_dir)
    preset_scan_result = run_preset_scan(pdf, output_dir=preset_dir, top_k=top_k, max_rendered=max_pages)

    preset_scan = json.loads(preset_scan_result.preset_scan_path.read_text(encoding="utf-8"))
    selected_pages = _select_agent_pages(preset_scan, max_pages=max_pages)
    expected_elements = _build_expected_elements_with_poppler(pdf, selected_pages)

    family_preset = _load_document_family_preset(preset_path)
    expected_payload = {
        "schema_version": "pdf-lab.expected-elements.v1",
        "source_pdf": str(pdf),
        "created_at": _now_utc(),
        "oracle": {
            "kind": "agent_scan",
            "description": "Provisional expected elements selected by TOC + full preset sweep, materialized from independent bbox-layout scan.",
            "toc_scan": str(toc.toc_path),
            "preset_scan": str(preset_scan_result.preset_scan_path),
            "selected_pages": selected_pages,
        },
        "match_policy": _default_match_policy(),
        "elements": expected_elements,
    }
    _apply_preset_to_expected_payload(expected_payload, family_preset, preset_path)
    expected_path = output_dir / "expected_elements.json"
    expected_path.write_text(json.dumps(expected_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return AgentScanResult(
        pdf=str(pdf),
        output_dir=output_dir,
        expected_elements_path=expected_path,
        toc_path=toc.toc_path,
        preset_scan_path=preset_scan_result.preset_scan_path,
        selected_pages=selected_pages,
        expected_count=len(expected_elements),
    )


def run_pdf_oxide_pages(
    pdf: Path,
    *,
    pages: list[int],
    output_dir: Path,
    preset_path: Path | None = None,
) -> DeterministicExtractionResult:
    """Run deterministic pdf_oxide extraction for selected 1-based pages."""
    pdf = pdf.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preset = _load_document_family_preset(preset_path)

    with _suppress_native_stderr():
        document = pdf_oxide.PdfDocument(str(pdf))
    elements: list[dict[str, Any]] = []
    for page in sorted(set(pages)):
        page_index = page - 1
        width, height = _page_size(pdf, page)
        try:
            with _suppress_native_stderr():
                lines = document.extract_text_lines(page_index)
        except Exception:
            lines = []
        for index, line in enumerate(lines):
            text = str(getattr(line, "text", "") or "").strip()
            if not text:
                continue
            bbox = _normalize_pdf_oxide_bbox(getattr(line, "bbox", None), width, height)
            element_type = _classify_element(text, bbox)
            elements.append(
                {
                    "id": f"actual:p{page}:line:{index}",
                    "page": page,
                    "type": element_type,
                    "bbox": bbox,
                    "text": text,
                    "confidence": 1.0,
                    "source": "pdf_oxide.extract_text_lines",
                    "raw": {
                        "bbox_space": "normalized_top_left_xyxy",
                    },
                }
            )
        try:
            with _suppress_native_stderr():
                tables = document.extract_tables(page_index)
        except Exception:
            tables = []
        for index, table in enumerate(tables):
            safe_table = _json_safe(table)
            bbox = _coerce_table_bbox(safe_table, width, height)
            elements.append(
                {
                    "id": f"actual:p{page}:table:{index}",
                    "page": page,
                    "type": "table",
                    "bbox": bbox,
                    "text": _table_text(safe_table),
                    "confidence": float(safe_table.get("confidence", 1.0)) if isinstance(safe_table, dict) else 1.0,
                    "source": "pdf_oxide.extract_tables",
                    "raw": safe_table,
                }
            )

    if preset:
        elements = _apply_preset_to_actual_elements(elements, preset)

    payload = {
        "schema_version": "pdf-lab.actual-elements.v1",
        "source_pdf": str(pdf),
        "created_at": _now_utc(),
        "engine": "pdf_oxide",
        "document_family_preset": _preset_metadata(preset, preset_path),
        "pages": sorted(set(pages)),
        "elements": elements,
    }
    actual_path = output_dir / "actual_elements.json"
    actual_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return DeterministicExtractionResult(
        pdf=str(pdf),
        output_dir=output_dir,
        actual_elements_path=actual_path,
        pages=sorted(set(pages)),
        actual_count=len(elements),
    )


def compare_expected_actual(
    expected_path: Path,
    actual_path: Path,
    *,
    output_dir: Path,
    target: float = 0.95,
) -> JsonComparisonResult:
    """Compare agent expected elements against deterministic pdf_oxide JSON."""
    expected_payload = json.loads(expected_path.read_text(encoding="utf-8"))
    actual_payload = json.loads(actual_path.read_text(encoding="utf-8"))
    expected_elements = expected_payload.get("elements", [])
    actual_elements = actual_payload.get("elements", [])
    policy = expected_payload.get("match_policy") or _default_match_policy()

    available_actual = list(actual_elements)
    matches: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    for expected in expected_elements:
        best_index = -1
        best_score = -1.0
        best_detail: dict[str, Any] | None = None
        for index, actual in enumerate(available_actual):
            detail = _score_element_match(expected, actual, policy)
            if detail["score"] > best_score:
                best_index = index
                best_score = detail["score"]
                best_detail = detail
        if best_detail and best_detail["matched"]:
            actual = available_actual.pop(best_index)
            matches.append(
                {
                    "expected_id": expected.get("id"),
                    "actual_id": actual.get("id"),
                    "page": expected.get("page"),
                    "score": best_detail["score"],
                    "iou": best_detail["iou"],
                    "text_similarity": best_detail["text_similarity"],
                    "type_compatible": best_detail["type_compatible"],
                }
            )
        else:
            misses.append(
                {
                    "expected_id": expected.get("id"),
                    "page": expected.get("page"),
                    "type": expected.get("type"),
                    "bbox": expected.get("bbox"),
                    "text": expected.get("text"),
                    "best_candidate": best_detail,
                    "reason": _miss_reason(best_detail, policy),
                }
            )

    total = len(expected_elements)
    matched = len(matches)
    accuracy = matched / total if total else 1.0
    comparison = {
        "schema_version": "pdf-lab.comparison.v1",
        "created_at": _now_utc(),
        "target": target,
        "passed": accuracy >= target,
        "accuracy": accuracy,
        "matched_expected_elements": matched,
        "total_expected_elements": total,
        "unmatched_expected_elements": len(misses),
        "unmatched_actual_elements": len(available_actual),
        "policy": policy,
        "subscores": _subscores(matches, expected_elements),
        "matches": matches,
        "misses": misses,
        "unmatched_actual_sample": available_actual[:50],
    }
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = output_dir / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    return JsonComparisonResult(
        comparison_path=comparison_path,
        accuracy=accuracy,
        matched_count=matched,
        total_expected=total,
        passed=accuracy >= target,
    )


def run_agentic_extract(
    pdf: Path,
    *,
    output_dir: Path | None = None,
    target: float = 0.95,
    max_iterations: int = 5,
    max_pages: int = 12,
    top_k: int = 3,
    full_extract: bool = False,
    preset_path: Path | None = None,
) -> AgenticExtractResult:
    """Run the agentic-first JSON convergence skeleton.

    This command creates convergence artifacts and a preset-first update plan.
    It does not blindly rewrite pdf_oxide core code. Core patches are separated
    as exceptional `core_patch_required` items.
    """
    pdf = pdf.expanduser().resolve()
    if output_dir is None:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        output_dir = Path.home() / ".pi" / "pdf-lab" / "agentic-extract" / f"{pdf.stem}-{stamp}"
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    agent_scan = run_agent_scan(pdf, output_dir=output_dir, max_pages=max_pages, top_k=top_k, preset_path=preset_path)
    expected = json.loads(agent_scan.expected_elements_path.read_text(encoding="utf-8"))
    pages = [int(page) for page in expected["oracle"]["selected_pages"]]

    last_actual_path = output_dir / "actual_elements.json"
    last_comparison_path = output_dir / "comparison.json"
    last_comparison: JsonComparisonResult | None = None
    for iteration in range(1, max_iterations + 1):
        iteration_dir = output_dir / f"iteration_{iteration:02d}"
        actual = run_pdf_oxide_pages(pdf, pages=pages, output_dir=iteration_dir, preset_path=preset_path)
        comparison = compare_expected_actual(
            agent_scan.expected_elements_path,
            actual.actual_elements_path,
            output_dir=iteration_dir,
            target=target,
        )
        last_actual_path = actual.actual_elements_path
        last_comparison_path = comparison.comparison_path
        last_comparison = comparison
        if comparison.passed:
            break
        _write_preset_update_plan(comparison.comparison_path, iteration_dir / "preset_update_plan.json", pdf=pdf)

    if last_comparison is None:
        raise RuntimeError("agentic extraction loop did not run")

    preset_update_plan_path = output_dir / "preset_update_plan.json"
    _write_preset_update_plan(last_comparison_path, preset_update_plan_path, pdf=pdf)

    final_extraction_path = None
    if full_extract and last_comparison.passed:
        final_extraction_path = output_dir / "final_extraction.json"
        _extract_full_document_text_lines(pdf, final_extraction_path, preset_path=preset_path)

    summary = {
        "schema_version": "pdf-lab.agentic-extract-summary.v1",
        "source_pdf": str(pdf),
        "created_at": _now_utc(),
        "target": target,
        "passed": last_comparison.passed,
        "accuracy": last_comparison.accuracy,
        "iterations": iteration,
        "expected_elements": str(agent_scan.expected_elements_path),
        "actual_elements": str(last_actual_path),
        "comparison": str(last_comparison_path),
        "preset_update_plan": str(preset_update_plan_path),
        "document_family_preset": str(preset_path.expanduser().resolve()) if preset_path else None,
        "full_extraction": str(final_extraction_path) if final_extraction_path else None,
        "next_step": "Apply reviewed preset_update_plan.json first; only consider core_patch_required for generic extractor bugs." if not last_comparison.passed else "Run final-pass to produce human_triage_queue.json.",
    }
    summary_path = output_dir / "agentic_extract_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return AgenticExtractResult(
        pdf=str(pdf),
        output_dir=output_dir,
        expected_elements_path=agent_scan.expected_elements_path,
        actual_elements_path=last_actual_path,
        comparison_path=last_comparison_path,
        preset_update_plan_path=preset_update_plan_path,
        summary_path=summary_path,
        accuracy=last_comparison.accuracy,
        passed=last_comparison.passed,
        iterations=iteration,
    )
