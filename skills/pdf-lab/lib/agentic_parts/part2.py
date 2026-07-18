"""Agentic implementation chunk 2.

Loaded by lib/agentic.py to keep each Python source file below 800 lines.
"""

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
    # Every suppressed (agent-resolved) defect becomes a fingerprinted
    # engineering-backlog entry; status-report audits runs against this file.
    from lib.discrepancy import write_second_pass_backlog

    source_pdf = extraction.get("source_pdf")
    source_pdf_sha256 = ""
    if source_pdf:
        source_pdf_path = Path(str(source_pdf)).expanduser()
        if source_pdf_path.exists():
            source_pdf_sha256 = "sha256:" + hashlib.sha256(
                source_pdf_path.read_bytes()
            ).hexdigest()
    preset_hash = ""
    if preset_path is not None and Path(preset_path).expanduser().exists():
        preset_hash = "sha256:" + hashlib.sha256(
            Path(preset_path).expanduser().read_bytes()
        ).hexdigest()
    comparison_receipt_hash = ""
    if comparison:
        comparison_receipt_hash = "sha256:" + hashlib.sha256(
            json.dumps(comparison, sort_keys=True).encode("utf-8")
        ).hexdigest()
    write_second_pass_backlog(
        output_dir,
        agent_resolved_findings,
        source_pdf_sha256=source_pdf_sha256,
        extractor_commit=str(getattr(pdf_oxide, "__version__", "") or ""),
        preset_hash=preset_hash,
        comparison_receipt_hash=comparison_receipt_hash,
        created_at=_now_utc(),
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
    # matcher_precedence step 1: text_hint. A row declaring a *_contains strategy
    # matches when the actual text CONTAINS the hint, which is what the human
    # labeller recorded. Similarity against the full block text penalises rows
    # whose expected text carries text-layer artefacts (this document's running
    # header extracts as "R EV . 5 S ECURITY" because the PDF sets it in small
    # caps and the text layer splits every word) even when the extractor read it
    # correctly. Containment on the hint is artefact-free.
    strategy = str(expected.get("match_strategy") or "")
    hint = str(expected.get("text_hint") or "").strip()
    if "contains" in strategy and hint:
        norm_actual = " ".join(str(actual.get("text") or "").lower().split())
        norm_hint = " ".join(hint.lower().split())
        if norm_hint and norm_hint in norm_actual:
            text_similarity = max(text_similarity, 1.0)
    if "_or_bbox_region" in strategy:
        matched = type_compatible and (iou >= min_iou or text_similarity >= min_text)
    else:
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
