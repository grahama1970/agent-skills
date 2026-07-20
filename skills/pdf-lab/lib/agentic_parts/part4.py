"""Agentic implementation chunk 4.

Loaded by lib/agentic.py to keep each Python source file below 800 lines.
"""

from dotenv import load_dotenv

load_dotenv()

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
        if actual_json is None and source_kind == "human_triage":
            page = _safe_int(record.get("page"), default=0)
            actual_json = _fallback_actual_json_for_record(
                record,
                extraction=extraction,
                page=page,
            )
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
        validation_status = (
            "blocked"
            if decision["decision"] == "blocker"
            or any(check.get("status") == "blocked" for check in decision["validators"])
            else "pass"
            if decision["decision"] in {"agent_resolved", "human_triage", "fixture_candidate"}
            else "fail"
        )
        validation = {
            "schema_version": "pdf_lab.second_pass_validation.v1",
            "case_id": payload["case_id"],
            "status": validation_status,
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
    image = Image.open(original_path)
    width, height = image.size

    bbox = None
    actual = payload.get("actual_json") if isinstance(payload.get("actual_json"), dict) else None
    expected = payload.get("expected_json") if isinstance(payload.get("expected_json"), dict) else None
    if actual:
        bbox = _normalize_bbox_for_page_image(actual.get("bbox"), width, height)
    if bbox is None and expected:
        bbox = _normalize_bbox_for_page_image(expected.get("bbox"), width, height)

    if bbox:
        image = image.convert("RGBA")
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
        with Image.open(candidate_original) as candidate_image:
            candidate_width, candidate_height = candidate_image.size
        normalized_candidate_bbox = _normalize_bbox_for_page_image(candidate_bbox, candidate_width, candidate_height)
        if normalized_candidate_bbox:
            _write_annotated_page_image(candidate_original, candidate_annotated, normalized_candidate_bbox)
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
