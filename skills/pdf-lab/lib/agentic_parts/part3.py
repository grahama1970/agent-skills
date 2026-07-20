"""Agentic implementation chunk 3.

Loaded by lib/agentic.py to keep each Python source file below 800 lines.
"""

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
    return {
        str(element.get("id")): element
        for element in _iter_extraction_elements(extraction)
        if isinstance(element, dict) and element.get("id") is not None
    }


def _iter_extraction_elements(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for collection in ("elements", "blocks", "tables", "figures", "requirements"):
        for item in extraction.get(collection) or []:
            if not isinstance(item, dict):
                continue
            element = dict(item)
            element.setdefault("source_collection", collection)
            if collection == "tables" and not element.get("text"):
                element["text"] = element.get("csv_data") or element.get("html_data") or ""
            elif collection == "figures" and not element.get("text"):
                element["text"] = element.get("caption") or ""
            elements.append(element)
    return elements


def _fallback_actual_json_for_record(
    record: dict[str, Any],
    *,
    extraction: dict[str, Any],
    page: int,
) -> dict[str, Any] | None:
    candidates = _actual_candidates_for_record(record, extraction=extraction, page=page)
    if not candidates:
        return None
    candidate = dict(candidates[0])
    candidate["source"] = candidate.get("source") or "pdf_lab.candidate_text_match"
    candidate["selection_reason"] = "best_text_match_for_second_pass_case"
    return candidate


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
    preview = record.get("preview") if isinstance(record.get("preview"), dict) else {}
    needle = str(
        evidence.get("overlapping_actual_text")
        or evidence.get("text")
        or record.get("text")
        or preview.get("text")
        or ""
    ).strip()
    if not needle:
        return []
    candidates: list[dict[str, Any]] = []
    for element in _iter_extraction_elements(extraction):
        if not isinstance(element, dict) or _safe_int(element.get("page"), default=0) != page:
            continue
        text = str(element.get("text") or "")
        if not text:
            continue
        similarity = _text_similarity(needle, text)
        if (
            similarity < 0.35
            and needle not in text
            and text not in needle
            and not _truncated_preview_matches(needle, text)
        ):
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


def _truncated_preview_matches(needle: str, text: str) -> bool:
    normalized_needle = _normalize_text(
        needle.replace("[…", " ").replace("…", " ").replace("...", " ")
    )
    normalized_text = _normalize_text(text)
    return len(normalized_needle) >= 40 and normalized_needle in normalized_text


def _normalize_bbox_for_page_image(bbox: Any, width: int, height: int) -> list[float] | None:
    if _is_normalized_bbox(bbox):
        return [float(item) for item in bbox]
    if not isinstance(bbox, list) or len(bbox) != 4 or width <= 0 or height <= 0:
        return None
    try:
        x0, y0, x1, y1 = [float(item) for item in bbox]
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        return None

    # pdf_oxide emits PDF user-space coordinates; page images use a top-left origin.
    normalized = [x0 / width, (height - y1) / height, x1 / width, (height - y0) / height]
    return normalized if _is_normalized_bbox(normalized) else None


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
