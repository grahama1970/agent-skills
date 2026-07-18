"""Agentic implementation chunk 5.

Loaded by lib/agentic.py to keep each Python source file below 800 lines.
"""

from dotenv import load_dotenv

load_dotenv()

def _second_pass_concurrency(model: str) -> int:
    configured = os.environ.get("PDF_LAB_SECOND_PASS_CONCURRENCY")
    if configured:
        return max(1, _safe_int(configured, default=2))
    if model in {"oc-kimi", "opencode-go/kimi-k2.6"}:
        return 2
    if model.startswith("claude-") or model.startswith("gpt-") or model.startswith("codex-"):
        return 1
    return 4


class ScillmAuthNotConfiguredError(RuntimeError):
    """Raised when no scillm credential is configured. The second pass must
    fail closed instead of spending per-case reviewer attempts against a
    hard-coded development key (agent-skills issue #70)."""


_SCILLM_AUTH_ENV_VARS = ("SCILLM_API_KEY", "SCILLM_MASTER_KEY", "SCILLM_PROXY_KEY")


def _scillm_auth_credential() -> tuple[str, str]:
    for name in _SCILLM_AUTH_ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    raise ScillmAuthNotConfiguredError(
        "scillm auth is not configured: set one of "
        + ", ".join(_SCILLM_AUTH_ENV_VARS)
        + " (no hard-coded fallback key; failing closed)"
    )


def _scillm_headers() -> dict[str, str]:
    _, key = _scillm_auth_credential()
    return {
        "Authorization": f"Bearer {key}",
        "X-Caller-Skill": "pdf-lab",
        "Content-Type": "application/json",
    }


def _scillm_auth_base_url(endpoint: str | None = None) -> str:
    configured = os.environ.get("SCILLM_BASE_URL")
    if configured:
        return configured.rstrip("/")
    if endpoint:
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:4001"


def run_scillm_auth_preflight(
    output_dir: Path,
    *,
    endpoint: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Fail-closed auth probe run BEFORE any per-case second-pass model call.

    Writes scillm_preflight.json into output_dir. ok=True requires a
    configured credential AND HTTP 200 from {base}/v1/scillm/auth.
    """
    report: dict[str, Any] = {
        "schema_version": "pdf_lab.scillm_auth_preflight.v1",
        "checked_at": _now_utc(),
        "auth_env_source": None,
        "auth_url": None,
        "auth_http_status": None,
        "ok": False,
        "classification": None,
        "error": None,
    }
    try:
        source, _ = _scillm_auth_credential()
        report["auth_env_source"] = source
    except ScillmAuthNotConfiguredError as exc:
        report["classification"] = "auth_not_configured"
        report["error"] = str(exc)
        _write_scillm_preflight(output_dir, report)
        return report

    base_url = _scillm_auth_base_url(endpoint)
    auth_url = f"{base_url}/v1/scillm/auth"
    report["auth_url"] = auth_url
    try:
        response = httpx.get(
            auth_url,
            headers=_scillm_headers(),
            timeout=httpx.Timeout(timeout_s, connect=3.0),
        )
        report["auth_http_status"] = response.status_code
        if response.status_code == 200:
            report["ok"] = True
        else:
            report["classification"] = "auth_rejected"
            report["error"] = f"HTTP {response.status_code}: {response.text[:500]}"
    except Exception as exc:
        report["classification"] = "auth_endpoint_unreachable"
        report["error"] = str(exc)
    _write_scillm_preflight(output_dir, report)
    return report


def _write_scillm_preflight(output_dir: Path, report: dict[str, Any]) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "scillm_preflight.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


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
