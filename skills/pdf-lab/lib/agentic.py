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
from PIL import Image, ImageDraw

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


def run_final_agent_pass(
    extraction_path: Path,
    *,
    output_dir: Path | None = None,
    comparison_path: Path | None = None,
    preset_path: Path | None = None,
    max_tasks: int | None = None,
    second_pass_model: str | None = None,
    second_pass_endpoint: str = "http://localhost:4001/v1/chat/completions",
    second_pass_timeout_s: float = 120.0,
    max_second_pass_cases: int | None = None,
) -> HumanTriageResult:
    """Create the final human triage queue from full deterministic extraction.

    This is intentionally a queue generator, not a UI artifact. The review UI
    should consume `human_triage_queue.json` and render task-first decisions.
    """
    extraction_path = extraction_path.expanduser().resolve()
    if not extraction_path.exists():
        raise FileNotFoundError(f"Full extraction JSON not found: {extraction_path}")
    if output_dir is None:
        output_dir = extraction_path.parent
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    comparison = None
    if comparison_path:
        comparison_path = comparison_path.expanduser().resolve()
        if not comparison_path.exists():
            raise FileNotFoundError(f"Comparison JSON not found: {comparison_path}")
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    preset = _load_document_family_preset(preset_path)
    agent_resolved_findings = _build_agent_resolved_findings(extraction, comparison=comparison)
    tasks = _build_human_triage_tasks(extraction, comparison=comparison)
    if max_tasks is not None:
        tasks = tasks[: max(0, int(max_tasks))]

    second_pass_prompt_cases = _write_second_pass_prompt_artifacts(
        output_dir,
        extraction=extraction,
        comparison=comparison,
        findings=agent_resolved_findings,
        tasks=tasks,
        second_pass_model=second_pass_model,
        second_pass_endpoint=second_pass_endpoint,
        second_pass_timeout_s=second_pass_timeout_s,
        max_second_pass_cases=max_second_pass_cases,
    )
    model_triage_tasks = _human_tasks_from_second_pass_cases(second_pass_prompt_cases)
    tasks.extend(model_triage_tasks)

    page_groups: dict[str, dict[str, Any]] = {}
    for task in tasks:
        page = int(task["page"])
        key = str(page)
        group = page_groups.setdefault(
            key,
            {
                "page": page,
                "task_count": 0,
                "tasks": [],
            },
        )
        group["task_count"] += 1
        group["tasks"].append(task["task_id"])

    pdf_element_notes = _build_pdf_element_notes(agent_resolved_findings, tasks)
    payload = {
        "schema_version": "pdf-lab.human-triage-queue.v1",
        "source_pdf": extraction.get("source_pdf"),
        "source_extraction": str(extraction_path),
        "source_comparison": str(comparison_path) if comparison_path else None,
        "created_at": _now_utc(),
        "engine": "pdf-lab.final-agent-pass",
        "document_family_preset": _preset_metadata(preset, preset_path),
        "page_count": extraction.get("page_count"),
        "task_count": len(tasks),
        "summary": _triage_summary(tasks),
        "agent_resolved_findings": agent_resolved_findings,
        "agent_resolved_summary": _agent_resolved_summary(agent_resolved_findings),
        "second_pass_prompt_cases": second_pass_prompt_cases,
        "pdf_element_notes": pdf_element_notes,
        "page_groups": sorted(page_groups.values(), key=lambda item: item["page"]),
        "human_triage_queue": tasks,
    }
    triage_queue_path = output_dir / "human_triage_queue.json"
    triage_queue_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "agent_resolved_findings.json").write_text(
        json.dumps(agent_resolved_findings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "pdf_element_notes.json").write_text(
        json.dumps(pdf_element_notes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "second_pass_prompt_cases.json").write_text(
        json.dumps(second_pass_prompt_cases, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return HumanTriageResult(
        extraction_path=extraction_path,
        triage_queue_path=triage_queue_path,
        task_count=len(tasks),
        page_count=int(extraction.get("page_count") or 0),
    )


def _select_agent_pages(preset_scan: dict[str, Any], *, max_pages: int) -> list[int]:
    scores: dict[int, float] = {}
    reasons: dict[int, list[str]] = {}
    for key, result in preset_scan.get("results", {}).items():
        for hit in result.get("top_pages", []):
            page = int(hit["page"])
            scores[page] = scores.get(page, 0.0) + float(hit.get("score", 0))
            reasons.setdefault(page, []).append(key)
    ranked = sorted(scores, key=lambda page: scores[page], reverse=True)
    return ranked[:max_pages]


def _build_expected_elements_with_poppler(pdf: Path, pages: list[int]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for page in pages:
        width, height, lines = _poppler_bbox_lines(pdf, page)
        for index, line in enumerate(lines):
            text = line["text"].strip()
            if not text:
                continue
            bbox = _normalize_xyxy([line["x0"], line["y0"], line["x1"], line["y1"]], width, height)
            element_type = _classify_element(text, bbox)
            confidence = _expected_confidence(element_type, text)
            elements.append(
                {
                    "id": f"expected:p{page}:line:{index}",
                    "page": page,
                    "type": element_type,
                    "bbox": bbox,
                    "text": text,
                    "confidence": confidence,
                    "source": "agent_scan.poppler_bbox_layout",
                    "agent_reasoning": _agent_reasoning(element_type, text, bbox),
                    "expected_pdf_oxide_layer": "text_lines",
                    "review_role": "oracle_element",
                }
            )
    return elements


def _poppler_bbox_lines(pdf: Path, page: int) -> tuple[float, float, list[dict[str, Any]]]:
    proc = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    root = ET.fromstring(proc.stdout)
    page_node = next((node for node in root.iter() if _strip_ns(node.tag) == "page"), None)
    if page_node is None:
        return 1.0, 1.0, []
    width = float(page_node.attrib.get("width", "1"))
    height = float(page_node.attrib.get("height", "1"))
    lines = []
    for line in page_node.iter():
        if _strip_ns(line.tag) != "line":
            continue
        words = []
        for word in line.iter():
            if _strip_ns(word.tag) == "word" and word.text:
                words.append(word.text)
        text = " ".join(words)
        if not text.strip():
            continue
        lines.append(
            {
                "x0": float(line.attrib["xMin"]),
                "y0": float(line.attrib["yMin"]),
                "x1": float(line.attrib["xMax"]),
                "y1": float(line.attrib["yMax"]),
                "text": text,
            }
        )
    return width, height, lines


def _classify_element(text: str, bbox: BBox) -> str:
    normalized = _normalize_text(text)
    y0, y1 = bbox[1], bbox[3]
    if y1 < 0.08:
        return "running_header"
    if y0 > 0.92:
        return "running_footer"
    if re.match(r"^(table|figure)\s+[a-z0-9-]+", normalized):
        return "caption"
    if re.match(r"^[a-z]{2}-\d+(?:\(\d+\))?\b", normalized):
        return "requirement"
    if re.match(r"^(?:[•●▪▫◦-]|\([a-z0-9]+\)|[a-z]\.)\s+\S+", normalized):
        return "list_item"
    if len(re.findall(r"\S\s{2,}\S", text)) >= 2:
        return "table_candidate"
    if len(text) <= 90 and (text.isupper() or re.match(r"^(appendix|chapter|\d+(?:\.\d+)*)\b", normalized)):
        return "section_header"
    return "paragraph"


def _score_element_match(expected: dict[str, Any], actual: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if expected.get("page") != actual.get("page"):
        return _score_detail(0.0, 0.0, 0.0, False, False)
    type_compatible = _types_compatible(str(expected.get("type")), str(actual.get("type")), policy)
    iou = _bbox_iou(expected.get("bbox"), actual.get("bbox"))
    text_similarity = _text_similarity(str(expected.get("text", "")), str(actual.get("text", "")))
    min_iou = float(policy["bbox_iou_thresholds"].get(str(expected.get("type")), policy["bbox_iou_thresholds"]["default"]))
    text_thresholds = policy.get("text_similarity_thresholds", {})
    min_text = float(text_thresholds.get(str(expected.get("type")), policy["text_similarity_threshold"]))
    score = (0.45 * iou) + (0.45 * text_similarity) + (0.10 if type_compatible else 0.0)
    matched = type_compatible and iou >= min_iou and text_similarity >= min_text
    return _score_detail(score, iou, text_similarity, type_compatible, matched)


def _score_detail(score: float, iou: float, text_similarity: float, type_compatible: bool, matched: bool) -> dict[str, Any]:
    return {
        "score": round(score, 4),
        "iou": round(iou, 4),
        "text_similarity": round(text_similarity, 4),
        "type_compatible": type_compatible,
        "matched": matched,
    }


def _types_compatible(expected: str, actual: str, policy: dict[str, Any] | None = None) -> bool:
    if expected == actual:
        return True
    if policy:
        aliases = policy.get("type_aliases", {})
        if actual in set(aliases.get(expected, [])):
            return True
    aliases = {
        "paragraph": {"paragraph", "table_candidate", "requirement"},
        "table_candidate": {"table_candidate", "table", "paragraph"},
        "running_header": {"running_header", "section_header"},
        "running_footer": {"running_footer"},
        "requirement": {"requirement", "paragraph", "table_candidate"},
    }
    return actual in aliases.get(expected, set())


def _bbox_iou(left: Any, right: Any) -> float:
    if not _valid_bbox(left) or not _valid_bbox(right):
        return 0.0
    ax0, ay0, ax1, ay1 = [float(value) for value in left]
    bx0, by0, bx1, by1 = [float(value) for value in right]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _text_similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm and not right_norm:
        return 1.0
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _normalize_pdf_oxide_bbox(raw_bbox: Any, width: float, height: float) -> BBox:
    if not raw_bbox or len(raw_bbox) != 4:
        return [0.0, 0.0, 0.0, 0.0]
    x, y, w, h = [float(value) for value in raw_bbox]
    x0 = x / width
    y0 = (height - (y + h)) / height
    x1 = (x + w) / width
    y1 = (height - y) / height
    return _clamp_bbox([x0, y0, x1, y1])


def _normalize_xyxy(raw_bbox: BBox, width: float, height: float) -> BBox:
    x0, y0, x1, y1 = [float(value) for value in raw_bbox]
    return _clamp_bbox([x0 / width, y0 / height, x1 / width, y1 / height])


def _coerce_table_bbox(table: Any, width: float, height: float) -> BBox:
    if isinstance(table, dict):
        bbox = table.get("bbox") or table.get("bounding_box")
        if _valid_bbox(bbox):
            return _normalize_pdf_oxide_bbox(bbox, width, height)
    return [0.0, 0.0, 1.0, 1.0]


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, list | tuple) and len(value) == 4 and all(isinstance(item, int | float) and math.isfinite(float(item)) for item in value)


def _clamp_bbox(bbox: BBox) -> BBox:
    x0, y0, x1, y1 = bbox
    return [
        round(max(0.0, min(1.0, min(x0, x1))), 6),
        round(max(0.0, min(1.0, min(y0, y1))), 6),
        round(max(0.0, min(1.0, max(x0, x1))), 6),
        round(max(0.0, min(1.0, max(y0, y1))), 6),
    ]


def _page_size(pdf: Path, page: int) -> tuple[float, float]:
    proc = subprocess.run(
        ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    for line in proc.stdout.splitlines():
        if re.match(rf"Page\s+{page}\s+size:", line):
            match = re.search(r"([0-9.]+)\s+x\s+([0-9.]+)\s+pts", line)
            if match:
                return float(match.group(1)), float(match.group(2))
    return 612.0, 792.0


def _write_preset_update_plan(comparison_path: Path, preset_update_plan_path: Path, *, pdf: Path | None = None) -> None:
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    misses = comparison.get("misses", [])
    groups: dict[str, list[dict[str, Any]]] = {}
    for miss in misses:
        groups.setdefault(str(miss.get("reason", "unknown")), []).append(miss)
    preset_updates = []
    core_patch_required = []
    for reason, items in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
        proposal = _preset_update_proposal(reason, items)
        if proposal["scope"] == "core_candidate":
            core_patch_required.append(proposal)
            continue
        preset_updates.append(proposal)

    preset_name = _infer_preset_name(pdf or comparison_path)
    payload = {
        "schema_version": "pdf-lab.preset-update-plan.v1",
        "created_at": _now_utc(),
        "comparison": str(comparison_path),
        "status": "review_required",
        "safety_rule": "Tune a document-family preset first. Do not change global pdf_oxide extraction unless core_patch_required is justified across unrelated PDFs.",
        "target_preset": {
            "name": preset_name,
            "kind": "document_family",
            "storage_hint": f"python/pdf_oxide/presets/document_families/{preset_name}.json",
        },
        "accuracy": comparison.get("accuracy"),
        "target": comparison.get("target"),
        "preset_updates": preset_updates,
        "core_patch_required": core_patch_required,
    }
    preset_update_plan_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _preset_update_proposal(reason: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    element_types = sorted({str(item.get("type", "unknown")) for item in items})
    sample_ids = [item.get("expected_id") for item in items[:10]]
    base = {
        "reason": reason,
        "count": len(items),
        "affected_expected_types": element_types,
        "sample_expected_ids": sample_ids,
        "scope": "preset",
    }
    if "bbox" in reason:
        base.update(
            {
                "preset_knobs": [
                    "bbox_iou_thresholds",
                    "line_grouping_tolerance",
                    "header_footer_band",
                    "block_merge_gap",
                ],
                "proposed_change": "Tune geometry/grouping thresholds for this document family before changing global coordinate logic.",
            }
        )
        return base
    if "type" in reason:
        base.update(
            {
                "preset_knobs": [
                    "type_aliases",
                    "block_classification_rules",
                    "section_header_patterns",
                    "table_candidate_patterns",
                ],
                "proposed_change": "Tune preset-level classification aliases/rules for this document family.",
            }
        )
        return base
    if "text" in reason:
        base.update(
            {
                "scope": "core_candidate",
                "preset_knobs": ["text_normalization_overrides"],
                "proposed_change": "Try preset-level text normalization first. If failures are due to ToUnicode/ligature/spacing defects, promote to core patch.",
                "core_review_gate": "Only patch core if the same text defect reproduces outside this document family.",
            }
        )
        return base
    base.update(
        {
            "preset_knobs": [
                "element_enabled_layers",
                "reading_order_strategy",
                "confidence_thresholds",
            ],
            "proposed_change": "Tune preset layer selection and confidence thresholds.",
        }
    )
    return base


def _infer_preset_name(path: Path) -> str:
    for part in path.parts:
        if part and part not in {"/", "tmp"} and "NIST" in part.upper():
            return _slug(part)
    return "document_family_preset"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return normalized or "document_family_preset"


def _miss_reason(best_detail: dict[str, Any] | None, policy: dict[str, Any]) -> str:
    if not best_detail:
        return "no_actual_candidate"
    if not best_detail["type_compatible"]:
        return "type_mismatch"
    if best_detail["iou"] < policy["bbox_iou_thresholds"]["default"]:
        return "bbox_iou_below_threshold"
    if best_detail["text_similarity"] < policy["text_similarity_threshold"]:
        return "text_similarity_below_threshold"
    return "combined_score_below_threshold"


def _subscores(matches: list[dict[str, Any]], expected_elements: list[dict[str, Any]]) -> dict[str, Any]:
    if not matches:
        return {
            "mean_iou": 0.0,
            "mean_text_similarity": 0.0,
            "type_accuracy_on_matches": 0.0,
        }
    return {
        "mean_iou": round(sum(item["iou"] for item in matches) / len(matches), 4),
        "mean_text_similarity": round(sum(item["text_similarity"] for item in matches) / len(matches), 4),
        "type_accuracy_on_matches": round(sum(1 for item in matches if item["type_compatible"]) / len(matches), 4),
    }


def _extract_full_document_text_lines(pdf: Path, output_path: Path, *, preset_path: Path | None = None) -> None:
    with _suppress_native_stderr():
        document = pdf_oxide.PdfDocument(str(pdf))
        page_count = int(document.page_count())
    result = run_pdf_oxide_pages(
        pdf,
        pages=list(range(1, page_count + 1)),
        output_dir=output_path.parent / "full_document",
        preset_path=preset_path,
    )
    page_payload = json.loads(result.actual_elements_path.read_text(encoding="utf-8"))
    preset = _load_document_family_preset(preset_path)
    elements = page_payload.get("elements", [])
    elements.extend(_toc_section_anchor_elements(pdf, page_count))
    payload = {
        "schema_version": "pdf-lab.full-extraction.v1",
        "source_pdf": str(pdf),
        "created_at": _now_utc(),
        "engine": "pdf_oxide",
        "document_family_preset": _preset_metadata(preset, preset_path),
        "page_count": page_count,
        "elements": elements,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _toc_section_anchor_elements(pdf: Path, page_count: int) -> list[dict[str, Any]]:
    """Return semantic section anchors backed by the PDF outline/TOC.

    These records are intentionally separate from visual ``section_header``
    lines. The NIST document has hundreds of outline-backed section targets,
    while visual heading classification can produce thousands of heading-like
    fragments. Coverage uses these anchors as the semantic section model.
    """
    outline_rows: list[Any] = []
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception:
        outline_rows = []
    else:
        try:
            document = fitz.open(str(pdf))
            outline_rows = document.get_toc(simple=False)
        except Exception:
            outline_rows = []

    if not outline_rows:
        outline_rows = _outline_rows_from_mutool(pdf)
    return _outline_rows_to_section_anchor_elements(outline_rows, page_count)


def _outline_rows_from_mutool(pdf: Path) -> list[list[Any]]:
    try:
        proc = subprocess.run(
            ["mutool", "show", str(pdf), "outline"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    rows: list[list[Any]] = []
    for line in proc.stdout.splitlines():
        match = re.search(r'^[|+\-](\t*)"(.+)"\s+#page=(\d+)', line)
        if not match:
            continue
        level = max(1, len(match.group(1)))
        title = bytes(match.group(2), "utf-8").decode("unicode_escape")
        rows.append([level, title, int(match.group(3)), {}])
    return rows


def _outline_rows_to_section_anchor_elements(outline_rows: list[Any], page_count: int) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for index, row in enumerate(outline_rows, start=1):
        try:
            level, title, page, *_ = row
            page_number = int(page)
        except Exception:
            continue
        title_text = str(title).strip()
        if not title_text:
            continue
        page_number = max(1, min(page_count, page_number))
        anchors.append(
            {
                "id": f"toc:section_anchor:{index:04d}",
                "page": page_number,
                "type": "section_anchor",
                "bbox": [0.0, 0.0, 1.0, 0.0],
                "text": title_text,
                "confidence": 1.0,
                "source": "pdf_outline.toc",
                "toc_id": f"toc:{index:04d}",
                "toc_level": int(level),
                "toc_backed": True,
                "semantic_role": "section_anchor",
                "review_role": "semantic_document_structure",
            }
        )
    return anchors


def _build_human_triage_tasks(extraction: dict[str, Any], *, comparison: dict[str, Any] | None) -> list[dict[str, Any]]:
    elements = extraction.get("elements", [])
    by_page: dict[int, list[dict[str, Any]]] = {}
    for element in elements:
        try:
            page = int(element.get("page"))
        except (TypeError, ValueError):
            continue
        by_page.setdefault(page, []).append(element)

    tasks: list[dict[str, Any]] = []
    if comparison:
        for miss in comparison.get("misses", []):
            page = _safe_int(miss.get("page"), default=0)
            if _is_agent_resolvable_comparison_miss(miss, by_page.get(page, [])):
                continue
            tasks.append(_comparison_miss_task(miss))

    for element in elements:
        if element.get("type") != "table" or element.get("source") != "pdf_oxide.extract_tables":
            continue
        page = _safe_int(element.get("page"), default=0)
        if _is_agent_resolvable_table_candidate(element, by_page.get(page, [])):
            continue
        if _is_agent_resolvable_table_row_fragment(element, by_page.get(page, [])):
            continue
        if _is_agent_resolvable_table_false_positive(element):
            continue
        tasks.append(_table_review_task(element))

    for page, page_elements in by_page.items():
        if page <= 2:
            continue
        if not any(_bbox_top(element) < 0.08 or element.get("type") == "running_header" for element in page_elements):
            tasks.append(_missing_structure_task(page, "header", "top_margin", [0.08, 0.02, 0.92, 0.07]))
        if not any(_bbox_bottom(element) > 0.92 or element.get("type") == "running_footer" for element in page_elements):
            tasks.append(_missing_structure_task(page, "footer", "bottom_margin", [0.08, 0.93, 0.92, 0.98]))

    return sorted(tasks, key=lambda item: (_severity_rank(item["severity"]), int(item["page"]), item["task_id"]))


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bbox_height(element: dict[str, Any]) -> float:
    bbox = element.get("bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        return 0.0
    try:
        return max(0.0, float(bbox[3]) - float(bbox[1]))
    except (TypeError, ValueError):
        return 0.0


def _bbox_width(element: dict[str, Any]) -> float:
    bbox = element.get("bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        return 0.0
    try:
        return max(0.0, float(bbox[2]) - float(bbox[0]))
    except (TypeError, ValueError):
        return 0.0


def _raw_table_rows(element: dict[str, Any]) -> list[Any]:
    raw = element.get("raw") if isinstance(element.get("raw"), dict) else {}
    rows = raw.get("rows")
    return rows if isinstance(rows, list) else []


def _raw_row_cell_texts(row: Any) -> list[str]:
    if isinstance(row, dict):
        cells = row.get("cells")
    else:
        cells = row
    if not isinstance(cells, list):
        return [str(row).strip()] if str(row).strip() else []
    texts: list[str] = []
    for cell in cells:
        if isinstance(cell, dict):
            texts.append(str(cell.get("text") or "").strip())
        else:
            texts.append(str(cell or "").strip())
    return texts


def _non_empty_row_cell_counts(element: dict[str, Any]) -> list[int]:
    return [sum(1 for text in _raw_row_cell_texts(row) if text) for row in _raw_table_rows(element)]


def _table_non_empty_cell_ratio(element: dict[str, Any]) -> float:
    all_cells = [text for row in _raw_table_rows(element) for text in _raw_row_cell_texts(row)]
    if not all_cells:
        return 0.0
    return sum(1 for text in all_cells if text) / len(all_cells)


def _table_plain_text(element: dict[str, Any]) -> str:
    texts = [text for row in _raw_table_rows(element) for text in _raw_row_cell_texts(row) if text]
    return " ".join(texts)


def _row_contains_table_header(row: Any) -> bool:
    texts = [_normalize_second_pass_text(text) for text in _raw_row_cell_texts(row) if text]
    joined = " ".join(texts)
    header_terms = {
        "control number": ["control", "number"],
        "control name": ["control name", "control enhancement name"],
        "implemented by": ["implemented", "by"],
        "assurance": ["assurance"],
    }
    hits = 0
    for alternatives in header_terms.values():
        if any(term in joined for term in alternatives):
            hits += 1
    return hits >= 3


TABLE_CLASS_REAL = "real_table_candidate"
TABLE_CLASS_ROW_FRAGMENT = "row_fragment_inside_table"
TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE = "page_frame_or_callout_false_positive"
TABLE_CLASS_PROSE_FALSE_POSITIVE = "prose_wrapped_pseudo_table"
TABLE_CLASS_UNRESOLVED_BOUNDS = "unresolved_table_bounds_candidate"
TABLE_SEMANTIC_CALLOUT_PROSE = "section_title_with_paragraph_or_callout_prose"
TABLE_SEMANTIC_PROSE = "paragraph_prose_boxed_as_table"
TABLE_SEMANTIC_ROW_FRAGMENT = "table_row_fragment"
TABLE_SEMANTIC_TABLE = "semantic_table"


def _table_candidate_classification(element: dict[str, Any], page_elements: list[dict[str, Any]]) -> dict[str, Any]:
    raw = element.get("raw") if isinstance(element.get("raw"), dict) else {}
    row_count = _safe_int(raw.get("row_count"), default=0)
    col_count = _safe_int(raw.get("col_count"), default=0)
    bbox_width = _bbox_width(element)
    bbox_height = _bbox_height(element)
    non_empty_counts = _non_empty_row_cell_counts(element)
    populated_rows = [count for count in non_empty_counts if count > 0]
    non_empty_ratio = _table_non_empty_cell_ratio(element)
    same_page_requirement_rows = sum(1 for item in page_elements if item.get("type") == "requirement")
    same_page_section_rows = sum(1 for item in page_elements if item.get("type") == "section_header")
    text = _normalize_second_pass_text(_table_plain_text(element))
    average_text_length = 0.0
    non_empty_texts = [
        text
        for row in _raw_table_rows(element)
        for text in _raw_row_cell_texts(row)
        if text
    ]
    if non_empty_texts:
        average_text_length = sum(len(text) for text in non_empty_texts) / len(non_empty_texts)

    evidence = {
        "row_count": row_count,
        "col_count": col_count,
        "has_header": bool(raw.get("has_header")),
        "bbox_width": bbox_width,
        "bbox_height": bbox_height,
        "non_empty_cell_ratio": non_empty_ratio,
        "non_empty_row_cell_counts": non_empty_counts[:24],
        "same_page_requirement_rows": same_page_requirement_rows,
        "same_page_section_rows": same_page_section_rows,
        "average_non_empty_cell_text_length": round(average_text_length, 2),
        "source": element.get("source"),
    }

    rows = _raw_table_rows(element)
    has_header_evidence = bool(raw.get("has_header")) or (bool(rows) and _row_contains_table_header(rows[0]))
    if has_header_evidence and row_count >= 2 and col_count >= 2 and non_empty_ratio >= 0.65:
        return {
            "classification": TABLE_CLASS_REAL,
            "semantic_candidate_type": TABLE_SEMANTIC_TABLE,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "table has explicit header-row evidence and at least one populated data row",
        }

    if row_count == 1 and col_count >= 3 and bbox_height <= 0.035 and (
        same_page_requirement_rows >= 5 or same_page_section_rows >= 10
    ):
        return {
            "classification": TABLE_CLASS_ROW_FRAGMENT,
            "semantic_candidate_type": TABLE_SEMANTIC_ROW_FRAGMENT,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "single-row table object lies on a page with repeated row-like structure",
        }

    if not populated_rows:
        return {
            "classification": TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE,
            "semantic_candidate_type": TABLE_SEMANTIC_PROSE,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "table candidate has no populated rows",
        }

    single_populated_cell_ratio = sum(1 for count in populated_rows if count == 1) / len(populated_rows)
    if bbox_width >= 0.75 and bbox_height >= 0.72 and row_count >= 5 and col_count >= 8 and non_empty_ratio <= 0.46:
        return {
            "classification": TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE,
            "semantic_candidate_type": TABLE_SEMANTIC_CALLOUT_PROSE,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "near-page frame with sparse pseudo-columns; extractor boxed page furniture/prose",
        }

    if col_count <= 2 and row_count >= 3 and single_populated_cell_ratio >= 0.8 and average_text_length >= 36:
        return {
            "classification": TABLE_CLASS_PROSE_FALSE_POSITIVE,
            "semantic_candidate_type": TABLE_SEMANTIC_PROSE,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "prose lines wrapped into one populated column plus empty filler cells",
        }

    if "control baselines" in text and bbox_width >= 0.65 and bbox_height >= 0.30 and col_count >= 6:
        return {
            "classification": TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE,
            "semantic_candidate_type": TABLE_SEMANTIC_CALLOUT_PROSE,
            "agent_resolvable": True,
            "evidence": evidence,
            "reason": "control-baselines callout was boxed as a sparse table candidate",
        }

    return {
        "classification": TABLE_CLASS_UNRESOLVED_BOUNDS,
        "semantic_candidate_type": None,
        "agent_resolvable": False,
        "evidence": evidence,
        "reason": "second-pass table filters could not prove false positive or row fragment",
    }


def _is_agent_resolvable_table_row_fragment(element: dict[str, Any], page_elements: list[dict[str, Any]]) -> bool:
    """Return true when a detected table is clearly a row fragment, not a human ambiguity.

    This is the final agentic audit boundary: humans should not decide whether an
    obvious row inside a larger grid is a table. The agent can identify this as an
    extractor bounds bug using extraction metadata plus same-page structural
    evidence, then keep it out of the human triage deck.
    """
    return _table_candidate_classification(element, page_elements)["classification"] == TABLE_CLASS_ROW_FRAGMENT


def _is_agent_resolvable_table_candidate(element: dict[str, Any], page_elements: list[dict[str, Any]]) -> bool:
    result = _table_candidate_classification(element, page_elements)
    return result["classification"] == TABLE_CLASS_REAL and bool(result.get("agent_resolvable"))


def _is_agent_resolvable_table_false_positive(element: dict[str, Any]) -> bool:
    """Return true when a table object is an obvious extractor false positive.

    These cases should not be sent to a human. The second pass can prove from the
    extraction metadata that pdf_oxide boxed prose/page furniture as a table:
    either a near-page frame with sparse pseudo-columns, or normal prose wrapped
    into one populated column plus empty filler cells.
    """
    classification = _table_candidate_classification(element, [])["classification"]
    return classification in {TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE, TABLE_CLASS_PROSE_FALSE_POSITIVE}


def _agent_resolved_table_finding(element: dict[str, Any], page_elements: list[dict[str, Any]]) -> dict[str, Any]:
    classification = _table_candidate_classification(element, page_elements)
    return {
        "finding_id": f"agent_resolved:table_row_fragment:{_slug(str(element.get('id') or 'unknown'))}",
        "kind": "table_row_fragment",
        "classification": TABLE_CLASS_ROW_FRAGMENT,
        "severity": "high",
        "page": _safe_int(element.get("page"), default=0),
        "target_id": element.get("id"),
        "target_bbox": element.get("bbox"),
        "agent_resolution": "suppressed_from_human_triage",
        "reason": (
            "pdf_oxide emitted a table object whose raw extraction contains exactly one row "
            "inside a page with repeated table-row structure. This is an extractor bounds "
            "bug, not a human table/not-table ambiguity."
        ),
        "recommended_engine_fix": "merge adjacent compatible row-band table fragments or expand row-only table bbox to the containing grid",
        "evidence": {
            **classification["evidence"],
        },
    }


def _agent_resolved_real_table_finding(element: dict[str, Any], page_elements: list[dict[str, Any]]) -> dict[str, Any]:
    classification = _table_candidate_classification(element, page_elements)
    return {
        "finding_id": f"agent_resolved:real_table_candidate:{_slug(str(element.get('id') or 'unknown'))}",
        "kind": "real_table_candidate",
        "classification": TABLE_CLASS_REAL,
        "severity": "low",
        "page": _safe_int(element.get("page"), default=0),
        "target_id": element.get("id"),
        "target_bbox": element.get("bbox"),
        "agent_resolution": "suppressed_from_human_triage",
        "reason": (
            "pdf_oxide emitted a table object and the second-pass audit found explicit table header cells "
            "plus a populated data row. This is a real table candidate and does not require a human table/not-table decision."
        ),
        "recommended_engine_fix": "record header-row evidence on table candidates so these do not become human triage cards",
        "evidence": {
            **classification["evidence"],
        },
    }


def _agent_resolved_table_false_positive_finding(element: dict[str, Any]) -> dict[str, Any]:
    classification = _table_candidate_classification(element, [])
    return {
        "finding_id": f"agent_resolved:table_false_positive:{_slug(str(element.get('id') or 'unknown'))}",
        "kind": "table_false_positive",
        "classification": classification["classification"],
        "severity": "high",
        "page": _safe_int(element.get("page"), default=0),
        "target_id": element.get("id"),
        "target_bbox": element.get("bbox"),
        "agent_resolution": "suppressed_from_human_triage",
        "reason": (
            "pdf_oxide emitted a table object, but the second-pass audit proved the region is sparse "
            "page/prose layout rather than a complete table. This is an extractor false positive, "
            "not a human ambiguity."
        ),
        "recommended_engine_fix": "reject table candidates with sparse pseudo-columns or prose-only rows before creating human triage cards",
        "evidence": {
            **classification["evidence"],
        },
    }


def _normalize_second_pass_text(text: str) -> str:
    normalized = " ".join(str(text).lower().split())
    normalized = re.sub(r"([a-z]+)\s*-\s*(\d+)", r"\1-\2", normalized)
    normalized = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1-\2", normalized)
    normalized = re.sub(r"([a-z])\s*-\s*([a-z])", r"\1 \2", normalized)
    for phrase in (
        "this publication is available free of",
        "charge] access from:",
        "charge access from:",
        "access from:",
    ):
        normalized = normalized.replace(phrase, " ")
    return " ".join(normalized.replace("[", " ").replace("]", " ").replace(":", " ").split())


def _is_layout_marker_text(text: str) -> bool:
    return str(text).strip() in {"•", "●", "▪", "▫", "◦", "-"}


def _bbox_overlap_ratio(a: Any, b: Any) -> float:
    if not _valid_bbox(a) or not _valid_bbox(b):
        return 0.0
    ax0, ay0, ax1, ay1 = [float(value) for value in a]
    bx0, by0, bx1, by1 = [float(value) for value in b]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area = max((ax1 - ax0) * (ay1 - ay0), 1e-9)
    return intersection / area


def _find_overlapping_actual_text(miss: dict[str, Any], page_elements: list[dict[str, Any]]) -> str:
    bbox = miss.get("bbox")
    candidates: list[tuple[float, str]] = []
    for element in page_elements:
        overlap = _bbox_overlap_ratio(bbox, element.get("bbox"))
        if overlap <= 0.0:
            continue
        text = str(element.get("text") or "")
        if text.strip():
            candidates.append((overlap, text))
    candidates.sort(reverse=True, key=lambda item: item[0])
    return " ".join(text for _, text in candidates[:3])


def _is_agent_resolvable_noisy_text_miss(miss: dict[str, Any], page_elements: list[dict[str, Any]]) -> bool:
    if str(miss.get("reason") or "") not in {"text_similarity_below_threshold", "bbox_iou_below_threshold"}:
        return False
    detail = miss.get("best_candidate") if isinstance(miss.get("best_candidate"), dict) else {}
    if not bool(detail.get("type_compatible")):
        return False
    raw_expected = str(miss.get("text") or "")
    overlapping_text = _find_overlapping_actual_text(miss, page_elements)
    if _is_layout_marker_text(raw_expected) and overlapping_text.strip().startswith(raw_expected.strip()):
        return True
    expected = _normalize_second_pass_text(str(miss.get("text") or ""))
    actual = _normalize_second_pass_text(overlapping_text)
    if not expected or not actual:
        return False
    if expected in actual:
        return True
    expected_tokens = [token for token in expected.split() if len(token) > 1]
    if not expected_tokens:
        return False
    covered = sum(1 for token in expected_tokens if token in actual)
    return covered / len(expected_tokens) >= 0.8


def _is_agent_resolvable_comparison_miss(miss: dict[str, Any], page_elements: list[dict[str, Any]]) -> bool:
    detail = miss.get("best_candidate") if isinstance(miss.get("best_candidate"), dict) else {}
    reason = str(miss.get("reason") or "")
    if (
        reason == "bbox_iou_below_threshold"
        and bool(detail.get("type_compatible"))
        and float(detail.get("text_similarity") or 0.0) >= 0.98
    ):
        return True
    return _is_agent_resolvable_noisy_text_miss(miss, page_elements)


def _agent_resolved_comparison_finding(miss: dict[str, Any], page_elements: list[dict[str, Any]]) -> dict[str, Any]:
    detail = miss.get("best_candidate") if isinstance(miss.get("best_candidate"), dict) else {}
    expected_id = str(miss.get("expected_id") or f"expected:p{miss.get('page')}:unknown")
    return {
        "finding_id": f"agent_resolved:bbox_only_exact_text_match:{_slug(expected_id)}",
        "kind": "noisy_text_or_bbox_match" if _is_agent_resolvable_noisy_text_miss(miss, page_elements) else "bbox_only_exact_text_match",
        "severity": "medium",
        "page": _safe_int(miss.get("page"), default=0),
        "target_id": expected_id,
        "target_bbox": miss.get("bbox"),
        "agent_resolution": "suppressed_from_human_triage",
        "reason": (
            "Representative comparison was resolvable from page evidence: the target text is present after "
            "removing known sidebar/watermark bleed, or the text/type are exact and only bbox IoU failed. "
            "This is a deterministic extraction/canonicalization issue for the agent pass, not a human ambiguity."
        ),
        "recommended_engine_fix": "suppress sidebar/watermark bleed and canonicalize bbox matching before emitting human triage",
        "evidence": {
            "comparison_reason": miss.get("reason"),
            "text_similarity": detail.get("text_similarity"),
            "type_compatible": detail.get("type_compatible"),
            "iou": detail.get("iou"),
            "text": str(miss.get("text") or "")[:160],
            "type": miss.get("type"),
            "overlapping_actual_text": _find_overlapping_actual_text(miss, page_elements)[:240],
        },
    }


def _build_agent_resolved_findings(extraction: dict[str, Any], *, comparison: dict[str, Any] | None) -> list[dict[str, Any]]:
    elements = extraction.get("elements", [])
    by_page: dict[int, list[dict[str, Any]]] = {}
    for element in elements:
        page = _safe_int(element.get("page"), default=0)
        if page:
            by_page.setdefault(page, []).append(element)

    findings: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") != "table" or element.get("source") != "pdf_oxide.extract_tables":
            continue
        page = _safe_int(element.get("page"), default=0)
        if _is_agent_resolvable_table_candidate(element, by_page.get(page, [])):
            findings.append(_agent_resolved_real_table_finding(element, by_page.get(page, [])))
        elif _is_agent_resolvable_table_row_fragment(element, by_page.get(page, [])):
            findings.append(_agent_resolved_table_finding(element, by_page.get(page, [])))
        elif _is_agent_resolvable_table_false_positive(element):
            findings.append(_agent_resolved_table_false_positive_finding(element))

    if comparison:
        for miss in comparison.get("misses", []):
            page = _safe_int(miss.get("page"), default=0)
            page_elements = by_page.get(page, [])
            if _is_agent_resolvable_comparison_miss(miss, page_elements):
                findings.append(_agent_resolved_comparison_finding(miss, page_elements))

    return sorted(findings, key=lambda item: (int(item["page"]), str(item["target_id"])))


def _finding_note_action(finding: dict[str, Any]) -> str:
    resolution = str(finding.get("agent_resolution") or "")
    if resolution == "suppressed_from_human_triage":
        return "auto_resolved"
    return resolution or "needs_review"


def _finding_to_element_note(finding: dict[str, Any]) -> dict[str, Any]:
    finding_id = str(finding.get("finding_id") or "finding:unknown")
    target_id = str(finding.get("target_id") or "unknown")
    issue_type = str(finding.get("kind") or "unknown")
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
    action = _finding_note_action(finding)
    return {
        "note_id": f"note:{_slug(finding_id)}:{_slug(target_id)}",
        "record_type": "pdf_element_note",
        "finding_id": finding_id,
        "element_id": target_id,
        "issue_type": issue_type,
        "action": action,
        "rationale": str(finding.get("reason") or ""),
        "evidence_metrics": evidence,
        "confidence": 0.95 if action == "auto_resolved" else 0.5,
        "similar_element_propagation": "needs_verification"
        if issue_type in {"table_row_fragment", "table_false_positive", "noisy_text_or_bbox_match", "bbox_only_exact_text_match"}
        else "not_applicable",
        "recommended_engine_fix": finding.get("recommended_engine_fix"),
        "page": finding.get("page"),
        "bbox": finding.get("target_bbox"),
        "created_by": "pdf-lab.final-agent-pass",
    }


def _task_to_element_note(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "task:unknown")
    target_id = str(task.get("target_id") or "unknown")
    suggested_fix = task.get("suggested_fix") if isinstance(task.get("suggested_fix"), dict) else {}
    return {
        "note_id": f"note:{_slug(task_id)}:{_slug(target_id)}",
        "record_type": "pdf_element_note",
        "finding_id": task_id,
        "element_id": target_id,
        "issue_type": str(task.get("kind") or "human_triage"),
        "action": "escalated_to_human",
        "rationale": str(task.get("agent_reasoning") or ""),
        "evidence_metrics": {
            "severity": task.get("severity"),
            "suggested_action": suggested_fix.get("action"),
        },
        "confidence": 0.0,
        "similar_element_propagation": "blocked",
        "page": task.get("page"),
        "bbox": task.get("target_bbox"),
        "created_by": "pdf-lab.final-agent-pass",
    }


def _build_pdf_element_notes(findings: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notes = [_finding_to_element_note(finding) for finding in findings]
    notes.extend(_task_to_element_note(task) for task in tasks)
    return sorted(notes, key=lambda item: (int(item.get("page") or 0), str(item.get("finding_id") or "")))


def _prompt_root() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"


def _read_prompt_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"PDF Lab prompt contract file missing: {path}")
    return path.read_text(encoding="utf-8")


def _load_element_preset(preset_id: str) -> dict[str, Any]:
    path = _prompt_root() / "presets" / f"{preset_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"PDF Lab element preset missing: {path}")
    preset = json.loads(path.read_text(encoding="utf-8"))
    if preset.get("preset_id") != preset_id:
        raise ValueError(f"Preset ID mismatch in {path}: {preset.get('preset_id')!r}")
    return preset


def _case_preset_id(record: dict[str, Any], actual_json: dict[str, Any] | None) -> str:
    kind = str(record.get("kind") or record.get("issue_type") or "")
    element_type = str((actual_json or {}).get("type") or record.get("type") or "")
    if "table" in kind or element_type == "table":
        return "pdf.table.v1"
    if "caption" in kind or element_type == "caption":
        return "pdf.caption_footnote.v1"
    if "header" in kind or "footer" in kind or element_type in {"running_header", "running_footer"}:
        return "pdf.header_footer_noise.v1"
    if "section" in kind or element_type == "section_header":
        return "pdf.section.v1"
    if "reference" in kind or element_type == "requirement":
        return "pdf.reference.v1"
    return "pdf.unknown_region.v1"


def _unknown_region_guard_for_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("preset_id") != "pdf.unknown_region.v1":
        return None
    guard = evaluate_unknown_region_candidate(payload) if evaluate_unknown_region_candidate else _local_unknown_region_guard(payload)
    if not isinstance(guard, dict) or not guard.get("applies"):
        return None
    return guard


def _table_fragment_guard_for_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("preset_id") != "pdf.table.v1":
        return None
    guard = evaluate_table_fragment_candidate(payload) if evaluate_table_fragment_candidate else _local_table_fragment_guard(payload)
    if not isinstance(guard, dict) or not guard.get("applies"):
        return None
    return guard


def _elements_by_id(extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    elements = extraction.get("elements") or []
    return {
        str(element.get("id")): element
        for element in elements
        if isinstance(element, dict) and element.get("id") is not None
    }


def _second_pass_payload_for_record(
    record: dict[str, Any],
    *,
    source_kind: str,
    extraction: dict[str, Any],
    actual_json: dict[str, Any] | None,
    preset_id: str,
) -> dict[str, Any]:
    case_id = str(record.get("finding_id") or record.get("task_id") or record.get("target_id") or "case:unknown")
    page = _safe_int(record.get("page") or (actual_json or {}).get("page"), default=0)
    payload = {
        "schema_version": "pdf_lab.second_pass_case_payload.v1",
        "case_id": case_id,
        "source_kind": source_kind,
        "preset_id": preset_id,
        "page": page,
        "element_id": record.get("target_id") or (actual_json or {}).get("id"),
        "original_page_image_path": None,
        "annotated_page_image_path": None,
        "expected_json": _expected_json_for_record(record, page=page),
        "actual_json": actual_json,
        "actual_candidates": _actual_candidates_for_record(record, extraction=extraction, page=page),
        "candidate_corrected_json": (
            record.get("proposed_json_delta", {}).get("after")
            if isinstance(record.get("proposed_json_delta"), dict)
            else None
        ),
        "known_visual_facts": _known_visual_facts(record, source_kind=source_kind),
        "provenance": {
            "source_pdf": extraction.get("source_pdf"),
            "source_extraction": extraction.get("source_extraction"),
            "created_by": "pdf-lab.final-agent-pass",
            "deterministic_record": case_id,
        },
    }
    if preset_id == "pdf.table.v1":
        payload["table_merge_review"] = _table_merge_review_for_record(
            record,
            extraction=extraction,
            actual_json=actual_json,
            page=page,
        )
    return payload


def _expected_json_for_record(record: dict[str, Any], *, page: int) -> dict[str, Any] | None:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    target_id = record.get("target_id")
    bbox = record.get("target_bbox") or record.get("bbox")
    text = evidence.get("text") or record.get("text")
    element_type = evidence.get("type") or record.get("type")
    if not any([target_id, bbox, text, element_type]):
        return None
    return {
        "id": target_id,
        "page": page,
        "type": element_type,
        "bbox": bbox,
        "text": text,
        "source": "agentic_expected_oracle",
    }


def _actual_candidates_for_record(record: dict[str, Any], *, extraction: dict[str, Any], page: int) -> list[dict[str, Any]]:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    needle = str(evidence.get("overlapping_actual_text") or evidence.get("text") or record.get("text") or "").strip()
    if not needle:
        return []
    candidates: list[dict[str, Any]] = []
    for element in extraction.get("elements") or []:
        if not isinstance(element, dict) or _safe_int(element.get("page"), default=0) != page:
            continue
        text = str(element.get("text") or "")
        if not text:
            continue
        similarity = _text_similarity(needle, text)
        if similarity < 0.35 and needle not in text and text not in needle:
            continue
        candidates.append({
            "id": element.get("id"),
            "page": element.get("page"),
            "type": element.get("type"),
            "bbox": element.get("bbox"),
            "text": text,
            "source": element.get("source"),
            "similarity_to_comparison_text": round(similarity, 4),
            "raw": element.get("raw"),
        })
    candidates.sort(key=lambda item: float(item.get("similarity_to_comparison_text") or 0), reverse=True)
    return candidates[:3]


def _table_merge_review_for_record(
    record: dict[str, Any],
    *,
    extraction: dict[str, Any],
    actual_json: dict[str, Any] | None,
    page: int,
) -> dict[str, Any]:
    primary_table = actual_json if isinstance(actual_json, dict) and actual_json.get("type") == "table" else None
    classification = str(record.get("classification") or record.get("kind") or "")
    if classification in {TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE, TABLE_CLASS_PROSE_FALSE_POSITIVE, "table_false_positive"}:
        return {
            "schema_version": "pdf_lab.table_merge_review.v1",
            "question": "Is this extractor-emitted table candidate a semantic table?",
            "instruction": "Use the annotated page image and extraction metrics to verify this is a false-positive table candidate, not a merge case.",
            "primary_table": _table_reference(primary_table),
            "primary_table_metrics": _table_extraction_metrics(primary_table),
            "adjacent_table_candidates": [],
            "merge_decision": "not_applicable",
            "semantic_table_decision": "false_positive",
            "human_triage_gate": "Do not escalate extractor-emitted sparse page/prose layout as a human table decision.",
        }
    adjacent_candidates = _adjacent_table_candidates(record, extraction=extraction, primary_table=primary_table, page=page)
    return {
        "schema_version": "pdf_lab.table_merge_review.v1",
        "question": "Should adjacent/continuation table candidates be merged into one logical table?",
        "instruction": "Use both annotated page images and extracted table shape/data-quality metrics before deciding merge, separate, or engine backlog.",
        "primary_table": _table_reference(primary_table),
        "primary_table_metrics": _table_extraction_metrics(primary_table),
        "adjacent_table_candidates": [
            {
                "table": _table_reference(candidate),
                "metrics": _table_extraction_metrics(candidate),
                "relationship": _table_candidate_relationship(primary_table, candidate),
                "visual_evidence": {
                    "original_page_image_path": None,
                    "annotated_page_image_path": None,
                },
            }
            for candidate in adjacent_candidates
        ],
        "merge_decision": None,
        "semantic_table_decision": None,
        "human_triage_gate": "Only escalate if the supplied images and metrics conflict on merge/separate status.",
    }


def _adjacent_table_candidates(
    record: dict[str, Any],
    *,
    extraction: dict[str, Any],
    primary_table: dict[str, Any] | None,
    page: int,
) -> list[dict[str, Any]]:
    target_id = str(record.get("target_id") or (primary_table or {}).get("id") or "")
    candidates: list[dict[str, Any]] = []
    for element in extraction.get("elements") or []:
        if not isinstance(element, dict) or element.get("type") != "table":
            continue
        if str(element.get("id") or "") == target_id:
            continue
        element_page = _safe_int(element.get("page"), default=0)
        if abs(element_page - page) > 1:
            continue
        candidates.append(element)
    candidates.sort(key=lambda item: (abs(_safe_int(item.get("page"), default=0) - page), str(item.get("id") or "")))
    return candidates[:4]


def _table_reference(table: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(table, dict):
        return None
    return {
        "id": table.get("id") or table.get("element_id"),
        "page": table.get("page"),
        "type": table.get("type"),
        "bbox": table.get("bbox"),
        "source": table.get("source"),
        "confidence": table.get("confidence"),
    }


def _table_extraction_metrics(table: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(table, dict):
        return None
    raw = table.get("raw") if isinstance(table.get("raw"), dict) else {}
    rows = raw.get("rows") if isinstance(raw.get("rows"), list) else []
    row_count = _safe_int(raw.get("row_count"), default=len(rows))
    col_count = _safe_int(raw.get("col_count"), default=0)
    total_cells = 0
    populated_cells = 0
    empty_cells = 0
    populated_column_indices: set[int] = set()
    cells_with_colspan = 0
    cells_with_rowspan = 0
    max_colspan = 1
    max_rowspan = 1
    covered_cell_count = 0
    for row in rows:
        cells = row.get("cells") if isinstance(row, dict) and isinstance(row.get("cells"), list) else []
        total_cells += len(cells)
        for cell_idx, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            if text:
                populated_cells += 1
                populated_column_indices.add(cell_idx)
            else:
                empty_cells += 1
            colspan = _safe_int(cell.get("colspan"), default=1)
            rowspan = _safe_int(cell.get("rowspan"), default=1)
            max_colspan = max(max_colspan, colspan)
            max_rowspan = max(max_rowspan, rowspan)
            if colspan > 1:
                cells_with_colspan += 1
            if rowspan > 1:
                cells_with_rowspan += 1
            if bool(cell.get("covered")):
                covered_cell_count += 1
    if not col_count and rows:
        col_count = max(
            (
                sum(_safe_int(cell.get("colspan"), default=1) for cell in row.get("cells", []) if isinstance(cell, dict))
                for row in rows
                if isinstance(row, dict)
            ),
            default=0,
        )
    non_empty_ratio = round(populated_cells / total_cells, 4) if total_cells else 0.0
    return {
        "table_id": table.get("id") or table.get("element_id"),
        "page": table.get("page"),
        "row_count": row_count,
        "col_count": col_count,
        "populated_column_count": len(populated_column_indices),
        "has_header": bool(raw.get("has_header")),
        "total_cell_count": total_cells,
        "populated_cell_count": populated_cells,
        "empty_cell_count": empty_cells,
        "non_empty_ratio": non_empty_ratio,
        "cells_with_colspan": cells_with_colspan,
        "cells_with_rowspan": cells_with_rowspan,
        "max_colspan": max_colspan,
        "max_rowspan": max_rowspan,
        "covered_cell_count": covered_cell_count,
        "data_quality": _table_data_quality(row_count=row_count, col_count=col_count, non_empty_ratio=non_empty_ratio),
    }


def _table_data_quality(*, row_count: int, col_count: int, non_empty_ratio: float) -> str:
    if row_count <= 0 or col_count <= 0:
        return "missing_shape"
    if row_count == 1:
        return "single_row_candidate"
    if non_empty_ratio < 0.2:
        return "sparse_grid"
    if non_empty_ratio < 0.5:
        return "partial_grid"
    return "populated_grid"


def _table_candidate_relationship(primary: dict[str, Any] | None, candidate: dict[str, Any]) -> str:
    primary_page = _safe_int((primary or {}).get("page"), default=0)
    candidate_page = _safe_int(candidate.get("page"), default=0)
    if primary_page and candidate_page == primary_page:
        return "same_page_table_candidate"
    if primary_page and candidate_page == primary_page - 1:
        return "previous_page_table_candidate"
    if primary_page and candidate_page == primary_page + 1:
        return "next_page_table_candidate"
    return "nearby_table_candidate"


def _known_visual_facts(record: dict[str, Any], *, source_kind: str) -> list[str]:
    facts: list[str] = []
    reason = str(record.get("reason") or record.get("agent_reasoning") or "")
    if reason:
        facts.append(reason)
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    if evidence:
        row_count = evidence.get("row_count")
        col_count = evidence.get("col_count")
        if row_count is not None and col_count is not None:
            facts.append(f"Deterministic table evidence reports row_count={row_count}, col_count={col_count}.")
        if evidence.get("same_page_requirement_rows") is not None:
            facts.append(f"Same-page requirement rows: {evidence.get('same_page_requirement_rows')}.")
        if evidence.get("same_page_section_rows") is not None:
            facts.append(f"Same-page section rows: {evidence.get('same_page_section_rows')}.")
    if source_kind == "human_triage":
        facts.append("This record is escalated to human triage after deterministic filters did not resolve it.")
    return facts


def _validated_second_pass_decision(
    record: dict[str, Any],
    *,
    source_kind: str,
    preset_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if source_kind == "agent_resolved":
        decision = "agent_resolved"
        human_required = False
        classification = str(record.get("classification") or record.get("kind") or "agent_resolved")
        confidence = "high" if record.get("agent_resolution") == "suppressed_from_human_triage" else "medium"
        human_question = None
        recommended_engine_fix = record.get("recommended_engine_fix")
        proposed_json_delta = None
    else:
        decision = "human_triage"
        human_required = True
        classification = str(record.get("kind") or "human_triage")
        confidence = "low"
        human_question = record.get("human_question")
        recommended_engine_fix = None
        proposed_json_delta = record.get("proposed_json_delta")

    missing_evidence = []
    if not payload.get("actual_json") and source_kind == "agent_resolved":
        missing_evidence.append("actual_json")
    validators = _validate_second_pass_payload(payload, source_kind=source_kind)
    if any(item["status"] == "blocked" for item in validators):
        confidence = "low"

    return {
        "schema_version": "pdf_lab.second_pass_decision.v1",
        "case_id": payload["case_id"],
        "preset_id": preset_id,
        "decision": decision,
        "human_triage_required": human_required,
        "classification": classification,
        "confidence": confidence,
        "reason": str(record.get("reason") or record.get("agent_reasoning") or ""),
        "target_evidence_used": _target_evidence_used(payload),
        "missing_evidence": missing_evidence,
        "validators": validators,
        "table_merge_review": payload.get("table_merge_review") if preset_id == "pdf.table.v1" else None,
        "human_question": human_question,
        "recommended_engine_fix": recommended_engine_fix,
        "proposed_json_delta": proposed_json_delta,
        "fixture_candidate": _fixture_candidate(record, decision=decision, preset_id=preset_id),
    }


def _target_evidence_used(payload: dict[str, Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else {}
    if actual.get("id") or actual.get("element_id"):
        evidence.append({"field_path": "actual_json.id", "fact": f"Actual element ID is {actual.get('id') or actual.get('element_id')}."})
    if actual.get("type"):
        evidence.append({"field_path": "actual_json.type", "fact": f"Actual element type is {actual.get('type')}."})
    if actual.get("bbox"):
        evidence.append({"field_path": "actual_json.bbox", "fact": "Actual element includes a bbox."})
    if payload.get("known_visual_facts"):
        evidence.append({"field_path": "known_visual_facts", "fact": str(payload["known_visual_facts"][0])[:240]})
    merge_review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
    metrics = merge_review.get("primary_table_metrics") if isinstance(merge_review.get("primary_table_metrics"), dict) else None
    if metrics:
        evidence.append({
            "field_path": "table_merge_review.primary_table_metrics",
            "fact": f"Primary table shape row_count={metrics.get('row_count')}, col_count={metrics.get('col_count')}, data_quality={metrics.get('data_quality')}.",
        })
    adjacent = merge_review.get("adjacent_table_candidates") if isinstance(merge_review.get("adjacent_table_candidates"), list) else []
    if adjacent:
        evidence.append({
            "field_path": "table_merge_review.adjacent_table_candidates",
            "fact": f"{len(adjacent)} adjacent table candidate(s) supplied for merge/separate review.",
        })
    return evidence


def _validate_second_pass_payload(payload: dict[str, Any], *, source_kind: str) -> list[dict[str, str]]:
    validators: list[dict[str, str]] = []
    has_extraction_evidence = bool(payload.get("actual_json") or payload.get("actual_candidates"))
    is_table_preset = payload.get("preset_id") == "pdf.table.v1"
    validators.append({
        "validator_id": "preset_id_present",
        "status": "pass" if payload.get("preset_id") else "blocked",
        "fact": str(payload.get("preset_id") or "missing preset_id"),
    })
    validators.append({
        "validator_id": "page_present",
        "status": "pass" if payload.get("page") else "blocked",
        "fact": f"page={payload.get('page')}",
    })
    validators.append({
        "validator_id": "extraction_evidence_present",
        "status": "pass" if has_extraction_evidence else ("blocked" if source_kind == "agent_resolved" else "pass"),
        "fact": "actual_json or actual_candidates is present" if has_extraction_evidence else "actual extraction evidence is missing",
    })
    validators.append({
        "validator_id": "human_triage_boundary",
        "status": "pass",
        "fact": "agent_resolved records do not create human work; human_triage records preserve the explicit question.",
    })
    if is_table_preset:
        merge_review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
        primary_metrics = merge_review.get("primary_table_metrics") if isinstance(merge_review.get("primary_table_metrics"), dict) else None
        adjacent_candidates = merge_review.get("adjacent_table_candidates") if isinstance(merge_review.get("adjacent_table_candidates"), list) else []
        adjacent_with_metrics = [
            candidate
            for candidate in adjacent_candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("metrics"), dict)
        ]
        adjacent_with_images = [
            candidate
            for candidate in adjacent_candidates
            if isinstance(candidate, dict)
            and isinstance(candidate.get("visual_evidence"), dict)
            and bool(candidate["visual_evidence"].get("annotated_page_image_path"))
        ]
        validators.append({
            "validator_id": "table_metrics_present",
            "status": "pass" if primary_metrics else "blocked",
            "fact": "primary table shape/data-quality metrics are present" if primary_metrics else "primary table metrics are missing",
        })
        validators.append({
            "validator_id": "table_merge_evidence_present",
            "status": "pass",
            "fact": f"adjacent_table_candidates={len(adjacent_candidates)}, with_metrics={len(adjacent_with_metrics)}, with_annotated_images={len(adjacent_with_images)}",
        })
    return validators


def _fixture_candidate(record: dict[str, Any], *, decision: str, preset_id: str) -> dict[str, Any]:
    kind = str(record.get("kind") or "")
    enabled = decision == "agent_resolved" and preset_id == "pdf.table.v1" and kind in {"table_row_fragment", "real_table_candidate", "table_false_positive"}
    return {
        "enabled": enabled,
        "fixture_family": "pdf_table_second_pass" if enabled else None,
        "reason": "Table second-pass case should remain out of human triage." if enabled else None,
    }


def _write_second_pass_prompt_artifacts(
    output_dir: Path,
    *,
    extraction: dict[str, Any],
    comparison: dict[str, Any] | None,
    findings: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    second_pass_model: str | None,
    second_pass_endpoint: str,
    second_pass_timeout_s: float,
    max_second_pass_cases: int | None,
) -> list[dict[str, Any]]:
    prompt_dir = output_dir / "second_pass_cases"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    root = _prompt_root()
    system_prompt = _read_prompt_file(root / "second_pass" / "global_system.txt")
    user_template = _read_prompt_file(root / "second_pass" / "global_user.txt")
    by_id = _elements_by_id(extraction)
    cases: list[dict[str, Any]] = []
    prepared_cases: list[dict[str, Any]] = []
    deterministic_resolutions: list[dict[str, Any]] = []

    records: list[tuple[str, dict[str, Any]]] = [("agent_resolved", finding) for finding in findings]
    records.extend(("human_triage", task) for task in tasks)
    if max_second_pass_cases is not None:
        records = records[: max(0, int(max_second_pass_cases))]

    for source_kind, record in records:
        target_id = str(record.get("target_id") or "")
        actual_json = by_id.get(target_id)
        preset_id = _case_preset_id(record, actual_json)
        preset = _load_element_preset(preset_id)
        payload = _second_pass_payload_for_record(
            record,
            source_kind=source_kind,
            extraction=extraction,
            actual_json=actual_json,
            preset_id=preset_id,
        )
        unknown_region_guard = _unknown_region_guard_for_payload(payload)
        if (
            unknown_region_guard
            and unknown_region_guard.get("model_review_required") is False
            and source_kind == "agent_resolved"
        ):
            deterministic_resolutions.append(
                {
                    "case_id": payload["case_id"],
                    "source_kind": source_kind,
                    "original_preset_id": preset_id,
                    "decision": "agent_resolved",
                    "human_triage_required": False,
                    "resolution_layer": unknown_region_guard.get("recommended_fix_layer"),
                    "fixture_family": unknown_region_guard.get("fixture_family"),
                    "subtype": unknown_region_guard.get("subtype"),
                    "resolved_type": unknown_region_guard.get("resolved_type"),
                    "expected_type": unknown_region_guard.get("expected_type"),
                    "best_candidate_id": unknown_region_guard.get("best_candidate_id"),
                    "best_candidate_similarity": unknown_region_guard.get("best_candidate_similarity"),
                    "reason": unknown_region_guard.get("reason"),
                }
            )
            continue
        table_fragment_guard = _table_fragment_guard_for_payload(payload)
        if (
            table_fragment_guard
            and table_fragment_guard.get("model_review_required") is False
            and source_kind == "agent_resolved"
        ):
            deterministic_resolutions.append(
                {
                    "case_id": payload["case_id"],
                    "source_kind": source_kind,
                    "original_preset_id": preset_id,
                    "decision": "agent_resolved",
                    "human_triage_required": False,
                    "resolution_layer": table_fragment_guard.get("recommended_fix_layer"),
                    "fixture_family": table_fragment_guard.get("fixture_family"),
                    "subtype": table_fragment_guard.get("subtype"),
                    "resolved_type": table_fragment_guard.get("resolved_type"),
                    "classification": table_fragment_guard.get("classification"),
                    "bbox_error_class": table_fragment_guard.get("bbox_error_class"),
                    "row_count_claimed": table_fragment_guard.get("row_count_claimed"),
                    "col_count_claimed": table_fragment_guard.get("col_count_claimed"),
                    "reason": table_fragment_guard.get("reason"),
                }
            )
            continue
        case_dir = prompt_dir / _slug(payload["case_id"])
        case_dir.mkdir(parents=True, exist_ok=True)
        _materialize_case_page_artifacts(case_dir, extraction=extraction, payload=payload)
        user_prompt = user_template.replace("{{CASE_PAYLOAD_JSON}}", json.dumps(payload, indent=2, ensure_ascii=False))
        full_prompt_payload = {
            "schema_version": "pdf_lab.second_pass_full_prompt_payload.v1",
            "case_id": payload["case_id"],
            "preset_id": preset_id,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "element_preset": preset,
            "case_payload": payload,
        }
        full_prompt_text = "\n\n".join(
            [
                "SYSTEM:\n" + system_prompt,
                "USER:\n" + user_prompt,
                "ELEMENT_PRESET_JSON:\n" + json.dumps(preset, indent=2, ensure_ascii=False),
                "CASE_PAYLOAD_JSON:\n" + json.dumps(payload, indent=2, ensure_ascii=False),
            ]
        )
        deterministic_decision = _validated_second_pass_decision(record, source_kind=source_kind, preset_id=preset_id, payload=payload)
        model_call: dict[str, Any]
        if second_pass_model:
            model_call = {
                "mode": "live_scillm_bounded_multimodal_batch",
                "model": second_pass_model,
                "endpoint": second_pass_endpoint,
                "timeout_s": second_pass_timeout_s,
                "image_input": "annotated_page_image_path",
            }
        else:
            model_call = {
                "mode": "offline_deterministic_guardrail",
                "reason": "second_pass_model was not configured",
            }
        prepared_cases.append(
            {
                "source_kind": source_kind,
                "record": record,
                "case_dir": case_dir,
                "preset_id": preset_id,
                "preset": preset,
                "payload": payload,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "full_prompt_text": full_prompt_text,
                "full_prompt_payload": full_prompt_payload,
                "deterministic_decision": deterministic_decision,
                "model_call": model_call,
            }
        )

    model_responses: dict[str, dict[str, Any]] = {}
    capability_report: dict[str, Any] | None = None
    if second_pass_model:
        capability_report = _second_pass_model_capability_report(second_pass_model)
        if capability_report.get("image_input") is False:
            model_responses = {
                str(prepared["payload"]["case_id"]): _second_pass_capability_blocker_response(
                    model=second_pass_model,
                    endpoint=second_pass_endpoint,
                    capability_report=capability_report,
                )
                for prepared in prepared_cases
            }
        else:
            model_responses = _call_second_pass_model_batch(
                prepared_cases,
                model=second_pass_model,
                endpoint=second_pass_endpoint,
                timeout_s=second_pass_timeout_s,
            )

    for prepared in prepared_cases:
        source_kind = prepared["source_kind"]
        case_dir = prepared["case_dir"]
        preset_id = prepared["preset_id"]
        preset = prepared["preset"]
        payload = prepared["payload"]
        system_prompt = prepared["system_prompt"]
        user_prompt = prepared["user_prompt"]
        full_prompt_text = prepared["full_prompt_text"]
        full_prompt_payload = prepared["full_prompt_payload"]
        deterministic_decision = prepared["deterministic_decision"]
        model_call = prepared["model_call"]
        if second_pass_model:
            model_response = model_responses.get(payload["case_id"]) or {
                "schema_version": "pdf_lab.second_pass_model_response.v1",
                "transport": "scillm_chat_completions",
                "model": second_pass_model,
                "endpoint": second_pass_endpoint,
                "error": "model batch did not return a response for this case",
                "parsed_json": None,
            }
            if isinstance(capability_report, dict):
                model_call["capability_report"] = capability_report
            decision = _validate_model_second_pass_decision(
                model_response,
                deterministic_decision=deterministic_decision,
                source_kind=source_kind,
                preset_id=preset_id,
                payload=payload,
            )
        else:
            model_response = deterministic_decision
            decision = deterministic_decision
        validation = {
            "schema_version": "pdf_lab.second_pass_validation.v1",
            "case_id": payload["case_id"],
            "status": "pass" if decision["decision"] in {"agent_resolved", "human_triage", "fixture_candidate", "blocker"} else "fail",
            "checks": decision["validators"],
            "runtime": "live_llm_multimodal_batch_with_deterministic_validation" if second_pass_model else "offline_deterministic_guardrail_with_prompt_contract",
            "model_call": model_call,
        }
        (case_dir / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")
        (case_dir / "user_prompt.txt").write_text(user_prompt, encoding="utf-8")
        (case_dir / "full_prompt.txt").write_text(full_prompt_text, encoding="utf-8")
        (case_dir / "full_prompt_payload.json").write_text(json.dumps(full_prompt_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "input_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "preset.json").write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "model_response.json").write_text(json.dumps(model_response, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "validated_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "validation_result.json").write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
        prompt_bundle_zip = _write_case_prompt_bundle_zip(case_dir)
        cases.append(
            {
                "case_id": payload["case_id"],
                "source_kind": source_kind,
                "preset_id": preset_id,
                "decision": decision["decision"],
                "human_triage_required": decision["human_triage_required"],
                "artifact_dir": str(case_dir),
                "input_payload": str(case_dir / "input_payload.json"),
                "system_prompt": str(case_dir / "system_prompt.txt"),
                "user_prompt": str(case_dir / "user_prompt.txt"),
                "full_prompt": str(case_dir / "full_prompt.txt"),
                "full_prompt_payload": str(case_dir / "full_prompt_payload.json"),
                "model_response": str(case_dir / "model_response.json"),
                "validated_decision": str(case_dir / "validated_decision.json"),
                "validation_result": str(case_dir / "validation_result.json"),
                "prompt_bundle_zip": str(prompt_bundle_zip),
            }
        )

    index = {
        "schema_version": "pdf_lab.second_pass_prompt_cases.v1",
        "created_at": _now_utc(),
        "source_comparison": comparison.get("schema_version") if isinstance(comparison, dict) else None,
        "case_count": len(cases),
        "deterministic_resolution_count": len(deterministic_resolutions),
        "deterministic_resolution_summary": {
            subtype: sum(1 for item in deterministic_resolutions if item.get("subtype") == subtype)
            for subtype in sorted({str(item.get("subtype")) for item in deterministic_resolutions})
        },
        "cases": cases,
        "deterministic_resolutions": deterministic_resolutions,
    }
    (prompt_dir / "deterministic_resolutions.json").write_text(
        json.dumps(
            {
                "schema_version": "pdf_lab.second_pass_deterministic_resolutions.v1",
                "created_at": _now_utc(),
                "resolution_count": len(deterministic_resolutions),
                "summary": index["deterministic_resolution_summary"],
                "resolutions": deterministic_resolutions,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (prompt_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    evidence_audit = _write_second_pass_candidate_report(prompt_dir, extraction=extraction, cases=cases)
    index["candidate_report"] = str(prompt_dir / "candidate_report.html")
    index["candidate_evidence_audit"] = str(prompt_dir / "candidate_evidence_audit.json")
    index["evidence_summary"] = evidence_audit["summary"]
    (prompt_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return cases


def _materialize_case_page_artifacts(case_dir: Path, *, extraction: dict[str, Any], payload: dict[str, Any]) -> None:
    source_pdf = extraction.get("source_pdf")
    page = _safe_int(payload.get("page"), default=0)
    if not source_pdf or not page or not Path(str(source_pdf)).exists():
        return

    document = pdf_oxide.PdfDocument(str(source_pdf))
    original_path = case_dir / f"page_{page}.png"
    annotated_path = case_dir / f"page_{page}_annotated.png"
    if not original_path.exists():
        original_path.write_bytes(document.render_page(page - 1))

    bbox = None
    actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else None
    expected = payload.get("expected_json") if isinstance(payload.get("expected_json"), dict) else None
    if actual and _is_normalized_bbox(actual.get("bbox")):
        bbox = actual.get("bbox")
    elif expected and _is_normalized_bbox(expected.get("bbox")):
        bbox = expected.get("bbox")

    if bbox and not annotated_path.exists():
        image = Image.open(original_path).convert("RGBA")
        width, height = image.size
        x0, y0, x1, y1 = [float(item) for item in bbox]
        draw = ImageDraw.Draw(image, "RGBA")
        rect = [x0 * width, y0 * height, x1 * width, y1 * height]
        draw.rectangle(rect, outline=(245, 158, 11, 255), width=6)
        draw.rectangle([rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3], outline=(167, 139, 250, 255), width=2)
        image.save(annotated_path)
    elif not annotated_path.exists():
        annotated_path.write_bytes(original_path.read_bytes())

    payload["original_page_image_path"] = str(original_path)
    payload["annotated_page_image_path"] = str(annotated_path)

    merge_review = payload.get("table_merge_review")
    candidates = merge_review.get("adjacent_table_candidates") if isinstance(merge_review, dict) else None
    if not isinstance(candidates, list):
        return
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        table = candidate.get("table") if isinstance(candidate.get("table"), dict) else {}
        candidate_page = _safe_int(table.get("page"), default=0)
        if not candidate_page:
            continue
        candidate_original = case_dir / f"merge_candidate_{idx}_page_{candidate_page}.png"
        candidate_annotated = case_dir / f"merge_candidate_{idx}_page_{candidate_page}_annotated.png"
        if not candidate_original.exists():
            candidate_original.write_bytes(document.render_page(candidate_page - 1))
        candidate_bbox = table.get("bbox")
        if _is_normalized_bbox(candidate_bbox):
            _write_annotated_page_image(candidate_original, candidate_annotated, candidate_bbox)
        elif not candidate_annotated.exists():
            candidate_annotated.write_bytes(candidate_original.read_bytes())
        visual = candidate.get("visual_evidence") if isinstance(candidate.get("visual_evidence"), dict) else {}
        visual["original_page_image_path"] = str(candidate_original)
        visual["annotated_page_image_path"] = str(candidate_annotated)
        candidate["visual_evidence"] = visual


def _write_case_prompt_bundle_zip(case_dir: Path) -> Path:
    """Create a portable review bundle for one second-pass case.

    The bundle is intentionally self-contained: prompt text, full payload, selected
    preset, model response, deterministic validation, and all rendered/annotated
    images in the case directory.
    """
    bundle_path = case_dir / "prompt_payload_bundle.zip"
    include_suffixes = {".txt", ".json", ".png", ".jpg", ".jpeg", ".webp"}
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(case_dir.iterdir()):
            if path == bundle_path or not path.is_file():
                continue
            if path.suffix.lower() not in include_suffixes:
                continue
            archive.write(path, arcname=path.name)
    return bundle_path


def _write_annotated_page_image(source_path: Path, target_path: Path, bbox: Any) -> None:
    if target_path.exists():
        return
    image = Image.open(source_path).convert("RGBA")
    width, height = image.size
    x0, y0, x1, y1 = [float(item) for item in bbox]
    draw = ImageDraw.Draw(image, "RGBA")
    rect = [x0 * width, y0 * height, x1 * width, y1 * height]
    draw.rectangle(rect, outline=(245, 158, 11, 255), width=6)
    draw.rectangle([rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3], outline=(167, 139, 250, 255), width=2)
    image.save(target_path)


def _call_second_pass_model_batch(
    prepared_cases: list[dict[str, Any]],
    *,
    model: str,
    endpoint: str,
    timeout_s: float,
) -> dict[str, dict[str, Any]]:
    if not prepared_cases:
        return {}
    concurrency = _second_pass_concurrency(model)
    try:
        return asyncio.run(
            _call_second_pass_model_batch_async(
                prepared_cases,
                model=model,
                endpoint=endpoint,
                timeout_s=timeout_s,
                concurrency=concurrency,
            )
        )
    except RuntimeError:
        results: dict[str, dict[str, Any]] = {}
        for prepared in prepared_cases:
            payload = prepared["payload"]
            results[str(payload["case_id"])] = _call_second_pass_model(
                model=model,
                endpoint=endpoint,
                timeout_s=timeout_s,
                system_prompt=prepared["system_prompt"],
                user_prompt=prepared["user_prompt"],
                preset=prepared["preset"],
                payload=payload,
            )
        return results


def _second_pass_model_capability_report(model: str) -> dict[str, Any]:
    base_url = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001").rstrip("/")
    report: dict[str, Any] = {
        "schema_version": "pdf_lab.second_pass_model_capability_report.v1",
        "model": model,
        "source": f"{base_url}/v1/scillm/models",
        "found": False,
        "image_input": None,
        "capabilities": None,
        "raw_model": None,
    }
    try:
        response = httpx.get(
            f"{base_url}/v1/scillm/models",
            headers=_scillm_headers(),
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        if response.status_code >= 400:
            report["error"] = f"HTTP {response.status_code}"
            report["error_body"] = response.text[:1000]
            return report
        data = response.json()
        flattened = data.get("models") if isinstance(data.get("models"), dict) else {}
        model_info = flattened.get(model)
        if isinstance(model_info, dict):
            capabilities = model_info.get("capabilities") if isinstance(model_info.get("capabilities"), dict) else {}
            report.update(
                {
                    "found": True,
                    "target": model_info.get("target"),
                    "endpoint": model_info.get("endpoint"),
                    "capabilities": capabilities,
                    "image_input": bool(capabilities.get("image_input")),
                    "raw_model": model_info,
                }
            )
            return report

        aliases = data.get("aliases") if isinstance(data.get("aliases"), dict) else {}
        target = aliases.get(model, model)
        report["target"] = target
        report["fallback_note"] = "flattened models map was unavailable; using aliases/groups fallback"
        groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
        for group_name, group_info in groups.items():
            models = group_info.get("models") if isinstance(group_info, dict) else None
            if isinstance(models, list) and target in models:
                report.update(
                    {
                        "found": True,
                        "group": group_name,
                        "image_input": group_name.startswith("vlm") or "vision" in group_name,
                        "raw_model": group_info,
                    }
                )
                return report
    except Exception as exc:
        report["error"] = str(exc)

    if model in {"oc-kimi", "opencode-go/kimi-k2.6"}:
        opencode_report = _opencode_go_model_capability_report(model)
        if opencode_report.get("found"):
            return opencode_report
    return report


def _opencode_go_model_capability_report(model: str) -> dict[str, Any]:
    base_url = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001").rstrip("/")
    target = "opencode-go/kimi-k2.6" if model == "oc-kimi" else model
    report: dict[str, Any] = {
        "schema_version": "pdf_lab.second_pass_model_capability_report.v1",
        "model": model,
        "target": target,
        "source": f"{base_url}/v1/scillm/opencode-go/models",
        "found": False,
        "image_input": None,
        "capabilities": None,
        "raw_model": None,
    }
    try:
        response = httpx.get(
            f"{base_url}/v1/scillm/opencode-go/models",
            headers=_scillm_headers(),
            timeout=httpx.Timeout(20.0, connect=3.0),
        )
        if response.status_code >= 400:
            report["error"] = f"HTTP {response.status_code}"
            report["error_body"] = response.text[:1000]
            return report
        data = response.json()
        model_list = data.get("models") if isinstance(data.get("models"), list) else []
        for item in model_list:
            if not isinstance(item, dict):
                continue
            if item.get("id") != target:
                continue
            input_caps = item.get("input") if isinstance(item.get("input"), dict) else {}
            capabilities = {
                "text_input": bool(input_caps.get("text")),
                "image_input": bool(input_caps.get("image")),
                "pdf_input": bool(input_caps.get("pdf")),
                "streaming": item.get("endpoint_type") == "chat_completions",
                "batch": False,
            }
            report.update(
                {
                    "found": True,
                    "endpoint": item.get("route"),
                    "capabilities": capabilities,
                    "image_input": capabilities["image_input"],
                    "raw_model": item,
                }
            )
            return report
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _second_pass_capability_blocker_response(
    *,
    model: str,
    endpoint: str,
    capability_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "pdf_lab.second_pass_model_response.v1",
        "transport": "scillm_chat_completions",
        "model": model,
        "endpoint": endpoint,
        "error": "selected second-pass model does not advertise image_input capability",
        "capability_report": capability_report,
        "parsed_json": None,
    }


async def _call_second_pass_model_batch_async(
    prepared_cases: list[dict[str, Any]],
    *,
    model: str,
    endpoint: str,
    timeout_s: float,
    concurrency: int,
) -> dict[str, dict[str, Any]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    timeout = httpx.Timeout(timeout_s, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(
                _call_second_pass_model_async(
                    client,
                    semaphore,
                    model=model,
                    endpoint=endpoint,
                    timeout_s=timeout_s,
                    system_prompt=prepared["system_prompt"],
                    user_prompt=prepared["user_prompt"],
                    preset=prepared["preset"],
                    payload=prepared["payload"],
                )
            )
            for prepared in prepared_cases
        ]
        results: dict[str, dict[str, Any]] = {}
        for task in asyncio.as_completed(tasks):
            case_id, response = await task
            results[case_id] = response
        return results


async def _call_second_pass_model_async(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    model: str,
    endpoint: str,
    timeout_s: float,
    system_prompt: str,
    user_prompt: str,
    preset: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    case_id = str(payload.get("case_id") or "")
    async with semaphore:
        request_payload = _second_pass_model_request_payload(
            model=model,
            timeout_s=timeout_s,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            preset=preset,
            payload=payload,
        )
        try:
            response = await client.post(
                endpoint,
                json=request_payload,
                headers=_scillm_headers(),
            )
            return case_id, _parse_second_pass_model_http_response(
                response,
                model=model,
                endpoint=endpoint,
            )
        except Exception as exc:
            return case_id, {
                "schema_version": "pdf_lab.second_pass_model_response.v1",
                "transport": "scillm_chat_completions",
                "model": model,
                "endpoint": endpoint,
                "error": str(exc),
                "parsed_json": None,
            }


def _second_pass_concurrency(model: str) -> int:
    configured = os.environ.get("PDF_LAB_SECOND_PASS_CONCURRENCY")
    if configured:
        return max(1, _safe_int(configured, default=2))
    if model in {"oc-kimi", "opencode-go/kimi-k2.6"}:
        return 2
    if model.startswith("claude-") or model.startswith("gpt-") or model.startswith("codex-"):
        return 1
    return 4


def _scillm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('SCILLM_PROXY_KEY', 'sk-dev-proxy-123')}",
        "X-Caller-Skill": "pdf-lab",
        "Content-Type": "application/json",
    }


def _second_pass_model_request_payload(
    *,
    model: str,
    timeout_s: float,
    system_prompt: str,
    user_prompt: str,
    preset: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    text_content = "\n\n".join(
        [
            user_prompt,
            "ELEMENT_PRESET_JSON:\n" + json.dumps(preset, indent=2, ensure_ascii=False),
            "CASE_PAYLOAD_JSON:\n" + json.dumps(payload, indent=2, ensure_ascii=False),
        ]
    )
    image_paths = _second_pass_image_paths(payload)
    image_path = image_paths[0] if image_paths else None
    user_content: str | list[dict[str, Any]] = text_content
    if image_paths:
        user_content = [
            {
                "type": "text",
                "text": (
                    text_content
                    + "\n\nVISUAL_EVIDENCE_INSTRUCTION:\n"
                    + "Inspect all attached annotated page images before deciding whether deterministic extraction evidence resolves this case. "
                    + "For table merge/split questions, compare the primary table image against adjacent table candidate images and the supplied table metrics."
                ),
            }
        ]
        for path in image_paths:
            image_b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}})

    request_payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "timeout": timeout_s,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "scillm_metadata": {
            "caller": "pdf-lab.final-pass",
            "case_id": payload.get("case_id"),
            "preset_id": payload.get("preset_id"),
            "batch_id": payload.get("batch_id") or "pdf-lab-second-pass",
            "item_id": payload.get("case_id"),
            "image_input": str(image_path) if image_path else None,
            "image_inputs": image_paths,
        },
    }
    if model.startswith("gpt-") or model.startswith("codex-") or model.startswith("claude-"):
        request_payload["reasoning_effort"] = os.environ.get("PDF_LAB_SECOND_PASS_REASONING", "high")
    return request_payload


def _second_pass_image_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for value in [payload.get("annotated_page_image_path"), payload.get("original_page_image_path")]:
        if isinstance(value, str) and Path(value).exists() and value not in paths:
            paths.append(value)
    merge_review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
    candidates = merge_review.get("adjacent_table_candidates") if isinstance(merge_review.get("adjacent_table_candidates"), list) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        visual = candidate.get("visual_evidence") if isinstance(candidate.get("visual_evidence"), dict) else {}
        for value in [visual.get("annotated_page_image_path"), visual.get("original_page_image_path")]:
            if isinstance(value, str) and Path(value).exists() and value not in paths:
                paths.append(value)
                break
    return paths[:4]


def _parse_second_pass_model_http_response(
    response: httpx.Response,
    *,
    model: str,
    endpoint: str,
) -> dict[str, Any]:
    if response.status_code >= 400:
        return {
            "schema_version": "pdf_lab.second_pass_model_response.v1",
            "transport": "scillm_chat_completions",
            "model": model,
            "endpoint": endpoint,
            "error": f"HTTP {response.status_code}",
            "error_body": response.text[:4000],
            "parsed_json": None,
        }
    response_json = response.json()
    content = response_json["choices"][0]["message"]["content"]
    parsed = _parse_json_object_from_text(str(content))
    return {
        "schema_version": "pdf_lab.second_pass_model_response.v1",
        "transport": "scillm_chat_completions",
        "model": model,
        "endpoint": endpoint,
        "raw_response": response_json,
        "content": content,
        "parsed_json": parsed,
    }


def _call_second_pass_model(
    *,
    model: str,
    endpoint: str,
    timeout_s: float,
    system_prompt: str,
    user_prompt: str,
    preset: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    request_payload = _second_pass_model_request_payload(
        model=model,
        timeout_s=timeout_s,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        preset=preset,
        payload=payload,
    )
    try:
        response = httpx.post(
            endpoint,
            json=request_payload,
            headers=_scillm_headers(),
            timeout=httpx.Timeout(timeout_s, connect=10.0),
        )
        return _parse_second_pass_model_http_response(response, model=model, endpoint=endpoint)
    except Exception as exc:
        return {
            "schema_version": "pdf_lab.second_pass_model_response.v1",
            "transport": "scillm_chat_completions",
            "model": model,
            "endpoint": endpoint,
            "error": str(exc),
            "parsed_json": None,
        }


def _parse_json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(stripped[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _validate_model_second_pass_decision(
    model_response: dict[str, Any],
    *,
    deterministic_decision: dict[str, Any],
    source_kind: str,
    preset_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    parsed = model_response.get("parsed_json") if isinstance(model_response.get("parsed_json"), dict) else None
    validators = _validate_second_pass_payload(payload, source_kind=source_kind)
    if not parsed:
        validators.append({
            "validator_id": "model_json_parse",
            "status": "blocked",
            "fact": model_response.get("error") or "model did not return parseable JSON object",
        })
        blocked = dict(deterministic_decision)
        blocked.update({
            "decision": "blocker",
            "human_triage_required": True,
            "classification": "second_pass_model_failure",
            "confidence": "low",
            "human_question": "Second-pass model response was unavailable or invalid; inspect prompt payload and deterministic extraction evidence.",
            "validators": validators,
        })
        return blocked

    decision = str(parsed.get("decision") or "")
    if decision not in {"agent_resolved", "human_triage", "fixture_candidate", "blocker"}:
        validators.append({
            "validator_id": "model_decision_vocabulary",
            "status": "blocked",
            "fact": f"unsupported decision={decision!r}",
        })
        decision = "blocker"
    else:
        validators.append({
            "validator_id": "model_decision_vocabulary",
            "status": "pass",
            "fact": decision,
        })

    human_required = bool(parsed.get("human_triage_required")) or decision in {"human_triage", "blocker"}
    if decision == "agent_resolved" and human_required:
        validators.append({
            "validator_id": "decision_boundary_consistency",
            "status": "blocked",
            "fact": "agent_resolved cannot require human triage",
        })
        decision = "blocker"
        human_required = True
    else:
        validators.append({
            "validator_id": "decision_boundary_consistency",
            "status": "pass",
            "fact": f"human_triage_required={human_required}",
        })

    return {
        "schema_version": "pdf_lab.second_pass_decision.v1",
        "case_id": payload["case_id"],
        "preset_id": preset_id,
        "decision": decision,
        "human_triage_required": human_required,
        "classification": str(parsed.get("classification") or parsed.get("issue_type") or deterministic_decision.get("classification") or decision),
        "confidence": str(parsed.get("confidence") or deterministic_decision.get("confidence") or "low"),
        "reason": str(parsed.get("reason") or parsed.get("decision_reason") or deterministic_decision.get("reason") or ""),
        "target_evidence_used": parsed.get("target_evidence_used") if isinstance(parsed.get("target_evidence_used"), list) else deterministic_decision.get("target_evidence_used", []),
        "missing_evidence": parsed.get("missing_evidence") if isinstance(parsed.get("missing_evidence"), list) else deterministic_decision.get("missing_evidence", []),
        "validators": validators,
        "table_merge_review": parsed.get("table_merge_review") if isinstance(parsed.get("table_merge_review"), dict) else deterministic_decision.get("table_merge_review"),
        "human_question": parsed.get("human_question") or (None if not human_required else deterministic_decision.get("human_question")),
        "recommended_engine_fix": parsed.get("recommended_engine_fix") or deterministic_decision.get("recommended_engine_fix"),
        "proposed_json_delta": parsed.get("proposed_json_delta") if isinstance(parsed.get("proposed_json_delta"), dict) else deterministic_decision.get("proposed_json_delta"),
        "fixture_candidate": parsed.get("fixture_candidate") if isinstance(parsed.get("fixture_candidate"), dict) else deterministic_decision.get("fixture_candidate"),
    }


def _write_second_pass_candidate_report(
    prompt_dir: Path,
    *,
    extraction: dict[str, Any],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    page_dir = prompt_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = extraction.get("source_pdf")
    rendered_pages: dict[int, str] = {}
    if source_pdf and Path(str(source_pdf)).exists():
        document = pdf_oxide.PdfDocument(str(source_pdf))
        for page in sorted({int(_safe_int(_read_case_payload(case).get("page"), default=0)) for case in cases} - {0}):
            page_path = page_dir / f"page_{page}.png"
            if not page_path.exists():
                page_path.write_bytes(document.render_page(page - 1))
            rendered_pages[page] = f"pages/page_{page}.png"

    audit_cases: list[dict[str, Any]] = []
    rows: list[str] = []
    for case in cases:
        payload = _read_case_payload(case)
        decision = _read_json_path(case["validated_decision"])
        validation = _read_json_path(case["validation_result"])
        actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else {}
        expected = payload.get("expected_json") if isinstance(payload.get("expected_json"), dict) else {}
        actual_candidates = payload.get("actual_candidates") if isinstance(payload.get("actual_candidates"), list) else []
        merge_review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
        merge_candidates = merge_review.get("adjacent_table_candidates") if isinstance(merge_review.get("adjacent_table_candidates"), list) else []
        page = _safe_int(payload.get("page"), default=0)
        bbox = actual.get("bbox") if isinstance(actual, dict) else None
        annotation_bbox = bbox or expected.get("bbox")
        page_image = rendered_pages.get(page)
        artifact_dir = Path(case["artifact_dir"])
        prompt_files = [
            "system_prompt.txt",
            "user_prompt.txt",
            "full_prompt.txt",
            "full_prompt_payload.json",
            "input_payload.json",
            "preset.json",
            "model_response.json",
            "validated_decision.json",
            "validation_result.json",
        ]
        prompt_files_present = all((artifact_dir / name).exists() for name in prompt_files)
        audit = {
            "case_id": case["case_id"],
            "page": page,
            "preset_id": case["preset_id"],
            "decision": case["decision"],
            "human_triage_required": bool(case["human_triage_required"]),
            "expected_json_present": bool(expected),
            "actual_json_present": bool(actual),
            "actual_candidate_count": len(actual_candidates),
            "actual_element_id": actual.get("id") or actual.get("element_id") if actual else None,
            "bbox_present": bool(annotation_bbox),
            "bbox_normalized": _is_normalized_bbox(annotation_bbox),
            "page_image_rendered": bool(page_image),
            "annotated_in_report": bool(page_image and _is_normalized_bbox(annotation_bbox)),
            "prompt_files_present": prompt_files_present,
            "validation_status": validation.get("status"),
            "table_metrics_present": isinstance(merge_review.get("primary_table_metrics"), dict),
            "table_merge_candidate_count": len(merge_candidates),
        }
        audit_cases.append(audit)
        rows.append(_render_candidate_report_case(case, payload, decision, validation, page_image))

    summary = {
        "case_count": len(audit_cases),
        "expected_json_present": sum(1 for item in audit_cases if item["expected_json_present"]),
        "actual_json_present": sum(1 for item in audit_cases if item["actual_json_present"]),
        "actual_candidate_present": sum(1 for item in audit_cases if item["actual_candidate_count"] > 0),
        "extraction_evidence_present": sum(1 for item in audit_cases if item["actual_json_present"] or item["actual_candidate_count"] > 0),
        "bbox_present": sum(1 for item in audit_cases if item["bbox_present"]),
        "page_image_rendered": sum(1 for item in audit_cases if item["page_image_rendered"]),
        "annotated_in_report": sum(1 for item in audit_cases if item["annotated_in_report"]),
        "prompt_files_present": sum(1 for item in audit_cases if item["prompt_files_present"]),
        "human_triage_required": sum(1 for item in audit_cases if item["human_triage_required"]),
        "table_metrics_present": sum(1 for item in audit_cases if item["table_metrics_present"]),
        "table_merge_candidates": sum(int(item["table_merge_candidate_count"]) for item in audit_cases),
    }
    audit_doc = {
        "schema_version": "pdf_lab.second_pass_candidate_evidence_audit.v1",
        "created_at": _now_utc(),
        "source_pdf": source_pdf,
        "summary": summary,
        "cases": audit_cases,
    }
    (prompt_dir / "candidate_evidence_audit.json").write_text(json.dumps(audit_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (prompt_dir / "candidate_report.html").write_text(_render_candidate_report_html(summary, rows), encoding="utf-8")
    return audit_doc


def _human_tasks_from_second_pass_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for case in cases:
        if not case.get("human_triage_required"):
            continue
        payload = _read_json_path(case["input_payload"])
        decision = _read_json_path(case["validated_decision"])
        page = _safe_int(payload.get("page"), default=0)
        case_id = str(case.get("case_id") or payload.get("case_id") or "second_pass_case")
        tasks.append({
            "task_id": f"second_pass_model:{_slug(case_id)}",
            "kind": str(decision.get("classification") or "second_pass_model_human_triage"),
            "severity": "high" if decision.get("decision") == "blocker" else "medium",
            "page": page,
            "target_id": payload.get("element_id") or case_id,
            "target_bbox": (
                (payload.get("actual_json") or {}).get("bbox")
                if isinstance(payload.get("actual_json"), dict)
                else (payload.get("expected_json") or {}).get("bbox") if isinstance(payload.get("expected_json"), dict) else None
            ),
            "human_question": decision.get("human_question") or "Second-pass model could not resolve this candidate from supplied artifacts.",
            "agent_reasoning": decision.get("reason") or "",
            "suggested_fix": decision.get("recommended_engine_fix"),
            "proposed_json_delta": decision.get("proposed_json_delta"),
            "source": "second_pass_model",
            "second_pass_case_id": case_id,
            "second_pass_artifact_dir": case.get("artifact_dir"),
        })
    return tasks


def _read_case_payload(case: dict[str, Any]) -> dict[str, Any]:
    return _read_json_path(case["input_payload"])


def _read_json_path(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _is_normalized_bbox(bbox: Any) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        x0, y0, x1, y1 = [float(item) for item in bbox]
    except (TypeError, ValueError):
        return False
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def _bbox_style(bbox: Any) -> str:
    if not _is_normalized_bbox(bbox):
        return ""
    x0, y0, x1, y1 = [float(item) for item in bbox]
    return f"left:{x0 * 100:.3f}%;top:{y0 * 100:.3f}%;width:{(x1 - x0) * 100:.3f}%;height:{(y1 - y0) * 100:.3f}%;"


def _render_candidate_report_case(
    case: dict[str, Any],
    payload: dict[str, Any],
    decision: dict[str, Any],
    validation: dict[str, Any],
    page_image: str | None,
) -> str:
    actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else {}
    expected = payload.get("expected_json") if isinstance(payload.get("expected_json"), dict) else {}
    actual_candidates = payload.get("actual_candidates") if isinstance(payload.get("actual_candidates"), list) else []
    merge_review = payload.get("table_merge_review") if isinstance(payload.get("table_merge_review"), dict) else {}
    classification = str(decision.get("classification") or "")
    semantic_table_decision = str(merge_review.get("semantic_table_decision") or "")
    if semantic_table_decision == "false_positive" or classification in {TABLE_CLASS_PAGE_FRAME_FALSE_POSITIVE, TABLE_CLASS_PROSE_FALSE_POSITIVE, "table_false_positive"}:
        title_prefix = "Extractor table false positive"
        conclusion = "Not a semantic table; pdf_oxide emitted a table candidate for sparse page/prose layout."
    elif classification == TABLE_CLASS_REAL:
        title_prefix = "Semantic table candidate"
        conclusion = "Semantic table candidate accepted by the second-pass table preset."
    else:
        title_prefix = "Extractor table candidate"
        conclusion = "Table preset evaluation result; inspect metrics and visual evidence."
    bbox = actual.get("bbox") if actual else None
    annotation_bbox = bbox or expected.get("bbox")
    overlay = f'<span class="bbox" style="{_bbox_style(annotation_bbox)}"></span>' if page_image and _is_normalized_bbox(annotation_bbox) else ""
    image = (
        f'<div class="page-proof"><img src="{html.escape(page_image)}" alt="Rendered page {payload.get("page")}">{overlay}</div>'
        if page_image
        else '<div class="missing">No rendered page image available.</div>'
    )
    artifact_dir = Path(case["artifact_dir"]).name
    bundle_name = Path(str(case.get("prompt_bundle_zip") or "prompt_payload_bundle.zip")).name
    bundle_href = f"{artifact_dir}/{bundle_name}"
    copy_value = html.escape(bundle_href, quote=True)
    full_payload_path = Path(case["artifact_dir"]) / "full_prompt_payload.json"
    full_payload_json = full_payload_path.read_text(encoding="utf-8") if full_payload_path.exists() else "{}"
    payload_textarea_id = f"payload-{_slug(str(case['case_id']))}"
    bundle_controls = (
        f'<div class="bundle-actions">'
        f'<a class="bundle-link" href="{html.escape(bundle_href)}" download>Download full prompt payload ZIP</a>'
        f'<button type="button" data-copy="{copy_value}" onclick="copyBundlePath(this)">Copy ZIP path</button>'
        f'<button type="button" data-copy-target="{html.escape(payload_textarea_id, quote=True)}" onclick="copyPayloadText(this)">Copy full prompt payload JSON</button>'
        f'</div>'
    )
    merge_images: list[str] = []
    for candidate in merge_review.get("adjacent_table_candidates", []) if isinstance(merge_review.get("adjacent_table_candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        visual = candidate.get("visual_evidence") if isinstance(candidate.get("visual_evidence"), dict) else {}
        image_path = visual.get("annotated_page_image_path") or visual.get("original_page_image_path")
        if isinstance(image_path, str):
            relative = f"{artifact_dir}/{Path(image_path).name}"
            table = candidate.get("table") if isinstance(candidate.get("table"), dict) else {}
            merge_images.append(
                f'<figure class="merge-proof"><img src="{html.escape(relative)}" alt="Adjacent table candidate {html.escape(str(table.get("id") or ""))}"><figcaption>{html.escape(str(candidate.get("relationship") or "adjacent table"))}</figcaption></figure>'
            )
    merge_gallery = "".join(merge_images) or '<div class="missing">No adjacent table page images supplied.</div>'
    return f"""
      <article class="case">
        <header>
          <div>
            <div class="eyebrow">{html.escape(str(case["preset_id"]))} · page {html.escape(str(payload.get("page")))}</div>
            <h2>{html.escape(str(case["case_id"]))}</h2>
          </div>
          <span class="badge {'human' if case['human_triage_required'] else 'resolved'}">{html.escape(str(case["decision"]))}</span>
        </header>
        <div class="grid">
          {image}
          <div class="facts">
            <dl>
              <dt>Element</dt><dd>{html.escape(str(payload.get("element_id") or "none"))}</dd>
              <dt>Conclusion</dt><dd>{html.escape(conclusion)}</dd>
              <dt>Classification</dt><dd>{html.escape(classification or "missing")}</dd>
              <dt>Expected type</dt><dd>{html.escape(str(expected.get("type") if expected else "missing"))}</dd>
              <dt>Extractor emitted</dt><dd>{html.escape(str(actual.get("type") if actual else "missing"))}</dd>
              <dt>Annotation bbox</dt><dd>{html.escape(json.dumps(annotation_bbox, ensure_ascii=False))}</dd>
              <dt>Actual candidates</dt><dd>{html.escape(str(len(actual_candidates)))}</dd>
              <dt>Validation</dt><dd>{html.escape(str(validation.get("status")))}</dd>
              <dt>Human question</dt><dd>{html.escape(str(decision.get("human_question") or "not required"))}</dd>
            </dl>
            {bundle_controls}
            <details open><summary>Known visual facts</summary><pre>{html.escape(json.dumps(payload.get("known_visual_facts"), indent=2, ensure_ascii=False))}</pre></details>
            <details open><summary>{html.escape(title_prefix)} metrics</summary><pre>{html.escape(json.dumps(merge_review, indent=2, ensure_ascii=False))}</pre></details>
            <details><summary>Adjacent table images</summary><div class="merge-gallery">{merge_gallery}</div></details>
            <details><summary>Expected JSON</summary><pre>{html.escape(json.dumps(expected, indent=2, ensure_ascii=False))}</pre></details>
            <details><summary>Actual pdf_oxide JSON</summary><pre>{html.escape(json.dumps(actual, indent=2, ensure_ascii=False))}</pre></details>
            <details><summary>Actual candidate extractions</summary><pre>{html.escape(json.dumps(actual_candidates, indent=2, ensure_ascii=False))}</pre></details>
            <details><summary>Validated decision</summary><pre>{html.escape(json.dumps(decision, indent=2, ensure_ascii=False))}</pre></details>
            <details open><summary>Full prompt payload JSON</summary><textarea id="{html.escape(payload_textarea_id, quote=True)}" class="payload-copy" spellcheck="false">{html.escape(full_payload_json)}</textarea></details>
          </div>
        </div>
      </article>
    """


def _render_candidate_report_html(summary: dict[str, Any], rows: list[str]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PDF Lab Second-Pass Candidate Report</title>
  <style>
    :root {{ color-scheme: dark; --bg:#07101d; --panel:#101a2a; --line:#26364e; --text:#f4f7fb; --muted:#9eb0c7; --green:#22c55e; --amber:#f59e0b; --purple:#a78bfa; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, sans-serif; }}
    main {{ max-width: 1800px; margin: 0 auto; padding: 24px; }}
    .hero, .case {{ border:1px solid var(--line); border-radius:18px; background:linear-gradient(180deg,#121d2e,#0c1422); box-shadow:0 18px 60px rgba(0,0,0,.3); }}
    .hero {{ padding:20px; margin-bottom:16px; }}
    h1, h2 {{ margin:0; letter-spacing:-.03em; }}
    h1 {{ font-size:28px; }}
    h2 {{ font-size:18px; word-break: break-word; }}
    .summary {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .metric {{ border:1px solid var(--line); border-radius:12px; padding:10px 12px; background:#0a1322; color:var(--muted); }}
    .metric strong {{ display:block; color:var(--text); font-size:22px; }}
    .case {{ padding:16px; margin:16px 0; }}
    .case header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:14px; }}
    .eyebrow {{ color:var(--purple); font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; margin-bottom:6px; }}
    .badge {{ border:1px solid var(--line); border-radius:999px; padding:6px 10px; font-weight:800; }}
    .badge.resolved {{ color:#bbf7d0; border-color:rgba(34,197,94,.45); background:rgba(34,197,94,.12); }}
    .badge.human {{ color:#fde68a; border-color:rgba(245,158,11,.45); background:rgba(245,158,11,.12); }}
    .grid {{ display:grid; grid-template-columns:minmax(280px, .72fr) minmax(420px, 1fr); gap:16px; align-items:start; }}
    .page-proof {{ position:relative; background:#fff; border-radius:12px; overflow:hidden; border:1px solid rgba(255,255,255,.2); }}
    .page-proof img {{ display:block; width:100%; height:auto; }}
    .merge-gallery {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:10px 12px 12px; }}
    .merge-proof {{ margin:0; border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#07101d; }}
    .merge-proof img {{ display:block; width:100%; height:auto; }}
    .merge-proof figcaption {{ padding:8px 10px; color:var(--muted); font-size:12px; }}
    .bundle-actions {{ display:flex; flex-wrap:wrap; gap:10px; margin:12px 0; }}
    .bundle-link, .bundle-actions button {{ display:inline-flex; align-items:center; min-height:36px; border:1px solid var(--line); border-radius:10px; background:#13233a; color:var(--text); padding:0 12px; font-weight:800; text-decoration:none; cursor:pointer; }}
    .bundle-actions button {{ font:inherit; }}
    .payload-copy {{ display:block; width:100%; min-height:360px; resize:vertical; border:0; border-top:1px solid var(--line); padding:12px; color:#d8b4fe; background:#050914; font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre; }}
    .bbox {{ position:absolute; border:3px solid var(--amber); box-shadow:0 0 0 2px rgba(167,139,250,.95), 0 0 0 9999px rgba(15,23,42,.10); pointer-events:none; }}
    .facts {{ min-width:0; }}
    dl {{ display:grid; grid-template-columns:140px minmax(0,1fr); gap:8px 12px; margin:0 0 12px; }}
    dt {{ color:var(--muted); font-weight:800; text-transform:uppercase; font-size:11px; letter-spacing:.05em; }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    details {{ border:1px solid var(--line); border-radius:12px; background:#0a1322; margin:8px 0; overflow:hidden; }}
    summary {{ cursor:pointer; padding:10px 12px; font-weight:800; }}
    pre {{ margin:0; padding:12px; overflow:auto; max-height:420px; color:#d8b4fe; background:#050914; font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    .missing {{ border:1px dashed var(--line); border-radius:12px; padding:20px; color:var(--muted); }}
    @media (max-width: 1100px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">PDF Lab · second-pass candidate report</div>
      <h1>Every candidate with prompt payload, preset, extraction JSON, decision, and annotation status</h1>
      <div class="summary">
        <div class="metric"><strong>{summary['case_count']}</strong> candidates</div>
        <div class="metric"><strong>{summary['expected_json_present']}</strong> with expected JSON</div>
        <div class="metric"><strong>{summary['actual_json_present']}</strong> with actual JSON</div>
        <div class="metric"><strong>{summary['actual_candidate_present']}</strong> with actual candidates</div>
        <div class="metric"><strong>{summary['extraction_evidence_present']}</strong> with extraction evidence</div>
        <div class="metric"><strong>{summary['bbox_present']}</strong> with bbox</div>
        <div class="metric"><strong>{summary['page_image_rendered']}</strong> rendered page images</div>
        <div class="metric"><strong>{summary['annotated_in_report']}</strong> annotated overlays</div>
        <div class="metric"><strong>{summary.get('table_metrics_present', 0)}</strong> with table metrics</div>
        <div class="metric"><strong>{summary.get('table_merge_candidates', 0)}</strong> merge candidates</div>
        <div class="metric"><strong>{summary['human_triage_required']}</strong> human required</div>
      </div>
    </section>
    {''.join(rows)}
  </main>
  <script>
    function copyBundlePath(button) {{
      const value = button.getAttribute('data-copy') || '';
      navigator.clipboard.writeText(value).then(() => {{
        button.textContent = 'Copied ZIP path';
      }}).catch(() => {{
        button.textContent = value;
      }});
    }}
    function copyPayloadText(button) {{
      const id = button.getAttribute('data-copy-target') || '';
      const field = document.getElementById(id);
      const value = field ? field.value : '';
      navigator.clipboard.writeText(value).then(() => {{
        button.textContent = 'Copied full prompt payload JSON';
      }}).catch(() => {{
        if (field) {{
          field.focus();
          field.select();
        }}
        button.textContent = 'Select payload text below';
      }});
    }}
  </script>
</body>
</html>
"""


def _comparison_miss_task(miss: dict[str, Any]) -> dict[str, Any]:
    reason = str(miss.get("reason", "unknown"))
    page = int(miss.get("page") or 0)
    expected_id = str(miss.get("expected_id") or f"expected:p{page}:unknown")
    detail = miss.get("best_candidate") or {}
    if "bbox" in reason:
        action = "FIX_BBOX"
        question = "Is this extracted region bounded correctly?"
        severity = "medium"
    elif "text" in reason:
        action = "VERIFY_TEXT"
        question = "Does this extracted text match the PDF?"
        severity = "medium"
    elif "type" in reason:
        action = "RECLASSIFY"
        question = "Is this element classified correctly?"
        severity = "high"
    else:
        action = "VERIFY_OR_ADD"
        question = "Should this expected element exist in the extraction?"
        severity = "high"
    text = str(miss.get("text", ""))
    snippet = text[:180] + ("…" if len(text) > 180 else "")
    return {
        "task_id": f"review:comparison_miss:{_slug(expected_id)}",
        "page": page,
        "kind": "comparison_miss",
        "severity": severity,
        "target_id": expected_id,
        "target_bbox": miss.get("bbox"),
        "human_question": question,
        "agent_reasoning": (
            f"Representative-page JSON comparison missed `{expected_id}` because `{reason}`. "
            f"IoU={detail.get('iou')}, text_similarity={detail.get('text_similarity')}, "
            f"type_compatible={detail.get('type_compatible')}."
        ),
        "preview": {
            "type": miss.get("type"),
            "text": snippet,
        },
        "suggested_fix": {
            "action": action,
            "reviewStatus": "pending_human_review",
        },
        "proposed_json_delta": {
            "before": {
                "id": expected_id,
                "reviewStatus": "unresolved",
                "reason": reason,
            },
            "after": {
                "id": expected_id,
                "reviewStatus": "verified",
                "resolution": action,
            },
        },
    }


def _table_review_task(element: dict[str, Any]) -> dict[str, Any]:
    target_id = str(element.get("id"))
    page = int(element.get("page") or 0)
    return {
        "task_id": f"review:table_candidate:{_slug(target_id)}",
        "page": page,
        "kind": "table_uncertain",
        "severity": "high",
        "target_id": target_id,
        "target_bbox": element.get("bbox"),
        "human_question": "Is this unresolved table candidate bounded correctly?",
        "agent_reasoning": (
            "The second-pass audit could not prove this table object was a row fragment, sparse page-frame, "
            "or prose-only false positive. Review only whether the highlighted region covers a complete table; "
            "cell editing belongs in Audit Mode."
        ),
        "preview": {
            "type": "table",
            "text": str(element.get("text", ""))[:240],
        },
        "suggested_fix": {
            "action": "VERIFY_TABLE",
            "fallback_actions": ["RECLASSIFY", "FIX_BBOX", "REJECT_FALSE_POSITIVE"],
        },
        "proposed_json_delta": {
            "before": {"id": target_id, "reviewStatus": "pending_review"},
            "after": {"id": target_id, "reviewStatus": "verified", "type": "table"},
        },
    }


def _missing_structure_task(page: int, kind: str, focus_area: str, bbox: BBox) -> dict[str, Any]:
    return {
        "task_id": f"review:missed_{kind}:p{page}",
        "page": page,
        "kind": "missing_object",
        "severity": "medium",
        "target_id": None,
        "target_bbox": bbox,
        "human_question": f"Should a missing {kind} block be added here?",
        "agent_reasoning": f"No deterministic {kind} element was found in the expected {focus_area} band.",
        "preview": {"type": kind, "text": ""},
        "suggested_fix": {
            "action": "ADD_BLOCK",
            "type": kind,
            "bbox": bbox,
        },
        "proposed_json_delta": {
            "before": {"reviewStatus": "missing"},
            "after": {"type": kind, "bbox": bbox, "reviewStatus": "verified"},
        },
    }


def _agent_resolved_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("kind") or "unknown")
        severity = str(finding.get("severity") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
    return {
        "finding_count": len(findings),
        "findings_by_kind": dict(sorted(by_kind.items())),
        "findings_by_severity": dict(sorted(by_severity.items())),
    }


def _triage_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    pages = set()
    for task in tasks:
        by_kind[str(task.get("kind"))] = by_kind.get(str(task.get("kind")), 0) + 1
        by_severity[str(task.get("severity"))] = by_severity.get(str(task.get("severity")), 0) + 1
        pages.add(int(task.get("page") or 0))
    return {
        "tasks_by_kind": dict(sorted(by_kind.items())),
        "tasks_by_severity": dict(sorted(by_severity.items())),
        "pages_with_tasks": len(pages),
    }


def _bbox_top(element: dict[str, Any]) -> float:
    bbox = element.get("bbox")
    return float(bbox[1]) if _valid_bbox(bbox) else 1.0


def _bbox_bottom(element: dict[str, Any]) -> float:
    bbox = element.get("bbox")
    return float(bbox[3]) if _valid_bbox(bbox) else 0.0


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)


def _load_document_family_preset(preset_path: Path | None) -> dict[str, Any] | None:
    if preset_path is None:
        return None
    path = preset_path.expanduser().resolve()
    if not path.exists() and not preset_path.is_absolute():
        repo_root = Path(os.environ.get("PDF_OXIDE_ROOT", "")).expanduser()
        candidate = (repo_root / preset_path).resolve() if repo_root.exists() else path
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise FileNotFoundError(f"Document-family preset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_preset_to_expected_payload(payload: dict[str, Any], preset: dict[str, Any] | None, preset_path: Path | None) -> None:
    if not preset:
        return
    payload["document_family_preset"] = _preset_metadata(preset, preset_path)
    overrides = preset.get("match_policy_overrides", {})
    if overrides:
        payload["match_policy"] = _deep_merge(payload.get("match_policy", {}), overrides)
    expected_transforms = preset.get("expected_element_transforms", {})
    if expected_transforms:
        elements = payload.get("elements", [])
        elements = _apply_text_replacements(elements, expected_transforms.get("text_replacements", []))
        elements = _filter_elements(elements, expected_transforms.get("drop_rules", []))
        elements = _apply_type_rules(elements, expected_transforms.get("type_rules", []))
        elements = _merge_same_line_elements(elements, expected_transforms.get("merge_same_line", {}))
        payload["elements"] = elements


def _apply_preset_to_actual_elements(elements: list[dict[str, Any]], preset: dict[str, Any]) -> list[dict[str, Any]]:
    extraction = preset.get("actual_element_transforms", {})
    text_replacements = extraction.get("text_replacements", [])
    type_rules = extraction.get("type_rules", [])
    bbox_expansion = extraction.get("bbox_expansion", {})
    drop_rules = extraction.get("drop_rules", [])
    embedded_rules = extraction.get("embedded_elements", [])
    revision_log_cells = extraction.get("revision_log_cells", {})
    transformed = []
    for element in elements:
        item = dict(element)
        text = str(item.get("text", ""))
        for replacement in text_replacements:
            pattern = replacement.get("pattern")
            value = replacement.get("replacement", "")
            if pattern:
                text = re.sub(pattern, value, text)
        item["text"] = text
        normalized = _normalize_text(text)
        for rule in type_rules:
            pattern = rule.get("pattern")
            target_type = rule.get("type")
            if pattern and target_type and re.search(pattern, normalized, re.I):
                item["type"] = target_type
                break
        expand_by = bbox_expansion.get(str(item.get("type")), bbox_expansion.get("default", 0.0))
        if expand_by and _valid_bbox(item.get("bbox")):
            item["bbox"] = _expand_bbox(item["bbox"], float(expand_by))
        item["preset_applied"] = preset.get("name", "document_family_preset")
        transformed.append(item)
        transformed.extend(_extract_embedded_elements(item, embedded_rules, preset))
    transformed = _filter_elements(transformed, drop_rules)
    transformed = _merge_same_line_elements(transformed, extraction.get("merge_same_line", {}))
    if revision_log_cells:
        generated_cells = []
        for item in transformed:
            generated_cells.extend(_extract_revision_log_cells(item, revision_log_cells, preset))
        transformed.extend(generated_cells)
    return transformed


def _extract_embedded_elements(element: dict[str, Any], rules: list[dict[str, Any]], preset: dict[str, Any]) -> list[dict[str, Any]]:
    if not rules or not _valid_bbox(element.get("bbox")):
        return []
    text = str(element.get("text", ""))
    created: list[dict[str, Any]] = []
    for rule in rules:
        source_text_regex = rule.get("source_text_regex")
        if source_text_regex and re.search(str(source_text_regex), text, re.I) is None:
            continue
        pattern = rule.get("extract_regex")
        target_type = rule.get("type")
        if not pattern or not target_type:
            continue
        for index, match in enumerate(re.finditer(str(pattern), text, re.I)):
            value = match.group(rule.get("group", 1))
            bbox = _embedded_bbox(element["bbox"], rule)
            created.append(
                {
                    "id": f"{element.get('id')}:embedded:{target_type}:{index}",
                    "page": element.get("page"),
                    "type": target_type,
                    "bbox": bbox,
                    "text": value,
                    "confidence": float(rule.get("confidence", 0.85)),
                    "source": f"{element.get('source', 'unknown')}+preset_embedded",
                    "preset_applied": preset.get("name", "document_family_preset"),
                    "embedded_from": element.get("id"),
                }
            )
    return created


def _embedded_bbox(source_bbox: BBox, rule: dict[str, Any]) -> BBox:
    x0, y0, x1, y1 = [float(value) for value in source_bbox]
    template = rule.get("bbox_template", {})
    return _clamp_bbox(
        [
            float(template.get("x0", x0)),
            y0 + float(template.get("y0_offset", 0.0)),
            float(template.get("x1", x1)),
            y1 + float(template.get("y1_offset", 0.0)),
        ]
    )


def _extract_revision_log_cells(element: dict[str, Any], config: dict[str, Any], preset: dict[str, Any]) -> list[dict[str, Any]]:
    if not config or not config.get("enabled", False) or not _valid_bbox(element.get("bbox")):
        return []
    text = re.sub(r"\s+", " ", str(element.get("text", "")).strip())
    date_pattern = str(config.get("date_regex", r"\d{2}-\d{2}-\d{4}"))
    row_pattern = re.compile(rf"^({date_pattern})\s+([A-Za-z]+)\s+(.+)$")
    match = row_pattern.match(text)
    if not match:
        return []
    row_type = match.group(2)
    allowed_types = {str(value).lower() for value in config.get("allowed_types", [])}
    if allowed_types and row_type.lower() not in allowed_types:
        return []

    remainder = match.group(3).strip()
    page_text = None
    page_match = re.search(r"\s+([0-9]+|[ivxlcdm]+)$", remainder, re.I)
    if page_match:
        page_text = page_match.group(1)
        revision_text = remainder[: page_match.start()].strip()
    else:
        revision_text = remainder
    if not revision_text:
        return []

    x0, y0, x1, y1 = [float(value) for value in element["bbox"]]
    columns = config.get("columns", {})
    cells = [
        ("date", "section_header", match.group(1), columns.get("date", [x0, x1])),
        ("type", "paragraph", row_type, columns.get("type", [x0, x1])),
        ("revision", "paragraph", revision_text, columns.get("revision", [x0, x1])),
    ]
    if page_text:
        cells.append(("page", "section_header", page_text, columns.get("page", [x0, x1])))

    created = []
    for cell_name, cell_type, cell_text, x_bounds in cells:
        cell_x0, cell_x1 = [float(value) for value in x_bounds]
        created.append(
            {
                "id": f"{element.get('id')}:revision_cell:{cell_name}",
                "page": element.get("page"),
                "type": cell_type,
                "bbox": _clamp_bbox([cell_x0, y0, cell_x1, y1]),
                "text": cell_text,
                "confidence": float(config.get("confidence", 0.9)),
                "source": f"{element.get('source', 'unknown')}+preset_revision_log_cell",
                "preset_applied": preset.get("name", "document_family_preset"),
                "embedded_from": element.get("id"),
            }
        )
    return created


def _filter_elements(elements: list[dict[str, Any]], drop_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not drop_rules:
        return elements
    return [element for element in elements if not any(_matches_drop_rule(element, rule) for rule in drop_rules)]


def _apply_text_replacements(elements: list[dict[str, Any]], text_replacements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not text_replacements:
        return elements
    updated = []
    for element in elements:
        item = dict(element)
        text = str(item.get("text", ""))
        for replacement in text_replacements:
            pattern = replacement.get("pattern")
            value = replacement.get("replacement", "")
            if pattern:
                text = re.sub(pattern, value, text)
        item["text"] = text
        updated.append(item)
    return updated


def _matches_drop_rule(element: dict[str, Any], rule: dict[str, Any]) -> bool:
    text = str(element.get("text", ""))
    element_type = str(element.get("type", ""))
    bbox = element.get("bbox")
    if "type" in rule and element_type != rule["type"]:
        return False
    if "types" in rule and element_type not in set(rule["types"]):
        return False
    if "text_regex" in rule and re.search(str(rule["text_regex"]), text, re.I) is None:
        return False
    if "text_equals" in rule and text.strip() != str(rule["text_equals"]):
        return False
    if _valid_bbox(bbox):
        x0, y0, x1, y1 = [float(value) for value in bbox]
        if "max_x1" in rule and x1 > float(rule["max_x1"]):
            return False
        if "min_x0" in rule and x0 < float(rule["min_x0"]):
            return False
        if "max_y1" in rule and y1 > float(rule["max_y1"]):
            return False
        if "min_y0" in rule and y0 < float(rule["min_y0"]):
            return False
    return True


def _apply_type_rules(elements: list[dict[str, Any]], type_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not type_rules:
        return elements
    updated = []
    for element in elements:
        item = dict(element)
        normalized = _normalize_text(str(item.get("text", "")))
        for rule in type_rules:
            pattern = rule.get("pattern")
            target_type = rule.get("type")
            if pattern and target_type and re.search(pattern, normalized, re.I):
                item["type"] = target_type
                break
        updated.append(item)
    return updated


def _merge_same_line_elements(elements: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config or not config.get("enabled", False):
        return elements
    merge_types = set(config.get("types", []))
    max_gap = float(config.get("max_gap", 0.03))
    max_y_delta = float(config.get("max_y_delta", 0.004))
    max_y_overlap_required = float(config.get("min_y_overlap", 0.55))
    pages: dict[int, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for element in elements:
        if merge_types and str(element.get("type")) not in merge_types:
            passthrough.append(element)
            continue
        if not _valid_bbox(element.get("bbox")):
            passthrough.append(element)
            continue
        pages.setdefault(int(element.get("page", 0)), []).append(element)

    merged: list[dict[str, Any]] = list(passthrough)
    for page, page_elements in pages.items():
        for ordered in _same_line_bands(page_elements, max_y_delta, max_y_overlap_required):
            current: dict[str, Any] | None = None
            for element in ordered:
                if current is None:
                    current = dict(element)
                    continue
                if _can_merge_same_line(current, element, max_gap, max_y_delta, max_y_overlap_required):
                    current = _merge_two_elements(current, element)
                else:
                    merged.append(current)
                    current = dict(element)
            if current is None:
                continue
            merged.append(current)
    return sorted(merged, key=lambda item: (int(item.get("page", 0)), item.get("bbox", [0, 0, 0, 0])[1], item.get("bbox", [0, 0, 0, 0])[0], str(item.get("id", ""))))


def _same_line_bands(elements: list[dict[str, Any]], max_y_delta: float, min_y_overlap: float) -> list[list[dict[str, Any]]]:
    bands: list[list[dict[str, Any]]] = []
    for element in sorted(elements, key=lambda item: (_bbox_center_y(item["bbox"]), item["bbox"][0])):
        placed = False
        for band in bands:
            representative = band[0]
            if abs(_bbox_center_y(representative["bbox"]) - _bbox_center_y(element["bbox"])) <= max_y_delta and _y_overlap_ratio(representative["bbox"], element["bbox"]) >= min_y_overlap:
                band.append(element)
                placed = True
                break
        if not placed:
            bands.append([element])
    return [sorted(band, key=lambda item: item["bbox"][0]) for band in bands]


def _can_merge_same_line(left: dict[str, Any], right: dict[str, Any], max_gap: float, max_y_delta: float, min_y_overlap: float) -> bool:
    if left.get("page") != right.get("page"):
        return False
    if left.get("type") != right.get("type"):
        return False
    left_bbox = left["bbox"]
    right_bbox = right["bbox"]
    if abs(_bbox_center_y(left_bbox) - _bbox_center_y(right_bbox)) > max_y_delta:
        return False
    if _y_overlap_ratio(left_bbox, right_bbox) < min_y_overlap:
        return False
    gap = float(right_bbox[0]) - float(left_bbox[2])
    return -0.005 <= gap <= max_gap


def _merge_two_elements(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    merged["id"] = f"{left.get('id')}+{right.get('id')}"
    merged["text"] = _join_fragments(str(left.get("text", "")), str(right.get("text", "")))
    merged["bbox"] = [
        min(float(left["bbox"][0]), float(right["bbox"][0])),
        min(float(left["bbox"][1]), float(right["bbox"][1])),
        max(float(left["bbox"][2]), float(right["bbox"][2])),
        max(float(left["bbox"][3]), float(right["bbox"][3])),
    ]
    merged["source"] = f"{left.get('source', 'unknown')}+preset_merge"
    merged["merged_from"] = [left.get("id"), right.get("id")]
    return merged


def _join_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if right.startswith("-") or left.endswith("-"):
        return f"{left}{right}"
    return f"{left} {right}"


def _bbox_center_y(bbox: BBox) -> float:
    return (float(bbox[1]) + float(bbox[3])) / 2.0


def _y_overlap_ratio(left: BBox, right: BBox) -> float:
    top = max(float(left[1]), float(right[1]))
    bottom = min(float(left[3]), float(right[3]))
    overlap = max(0.0, bottom - top)
    min_height = min(float(left[3]) - float(left[1]), float(right[3]) - float(right[1]))
    return overlap / min_height if min_height > 0 else 0.0


def _preset_metadata(preset: dict[str, Any] | None, preset_path: Path | None) -> dict[str, Any] | None:
    if not preset:
        return None
    return {
        "name": preset.get("name"),
        "schema_version": preset.get("schema_version"),
        "path": str(preset_path.expanduser().resolve()) if preset_path else None,
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_bbox(bbox: BBox, amount: float) -> BBox:
    x0, y0, x1, y1 = [float(value) for value in bbox]
    return _clamp_bbox([x0 - amount, y0 - amount, x1 + amount, y1 + amount])


def _default_match_policy() -> dict[str, Any]:
    return {
        "accuracy_formula": "matched_expected_elements / total_expected_elements",
        "text_similarity_threshold": 0.80,
        "bbox_iou_thresholds": {
            "default": 0.50,
            "running_header": 0.35,
            "running_footer": 0.35,
            "caption": 0.45,
            "table_candidate": 0.40,
        },
        "type_aliases": {
            "paragraph": ["paragraph", "table_candidate", "requirement"],
            "table_candidate": ["table_candidate", "table", "paragraph"],
            "requirement": ["requirement", "paragraph", "table_candidate"],
        },
    }


def _expected_confidence(element_type: str, text: str) -> float:
    if element_type in {"running_header", "running_footer", "requirement", "caption"}:
        return 0.9
    if element_type in {"table_candidate", "section_header", "list_item"}:
        return 0.8
    return 0.7


def _agent_reasoning(element_type: str, text: str, bbox: BBox) -> str:
    if element_type == "running_header":
        return "Element is in the top page band and should be recoverable as a running header."
    if element_type == "running_footer":
        return "Element is in the bottom page band and should be recoverable as footer/boilerplate."
    if element_type == "table_candidate":
        return "Line has multiple aligned whitespace gaps; verify deterministic grouping/classification."
    if element_type == "requirement":
        return "Line begins with a compliance-style control identifier."
    if element_type == "section_header":
        return "Short heading-like line detected by structural position/text cues."
    return "Expected text-bearing page element from independent bbox-layout scan."


def _table_text(table: Any) -> str:
    if isinstance(table, dict):
        if "text" in table:
            return str(table["text"])
        if "rows" in table:
            return " ".join(str(cell) for row in table["rows"] for cell in (row if isinstance(row, list) else [row]))
    return ""


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {key: _json_safe(item) for key, item in vars(value).items()}
    return str(value)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextmanager
def _suppress_native_stderr():
    """Suppress native extension writes to fd 2 while preserving Python errors."""
    saved_stderr = os.dup(2)
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)
