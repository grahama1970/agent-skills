"""Three-call /scillm adversarial argue protocol for /ask."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .ask_config import SCILLM_API_KEY, SCILLM_BASE_URL
from .run_state import AskRunState, NoopRunState, atomic_write_json
from .scillm_runtime import (
    CITATION_SCHEMA_VERSION,
    KNOWLEDGE_CITATION_KINDS,
    build_scillm_metadata,
    build_source_bundle,
    extract_scillm_observability,
    fetch_recent_scillm_debug,
    normalize_citations,
    render_citations_markdown,
    scillm_error_advice,
    summarize_scillm_observability,
    serialize_source_bundle,
    validate_citations,
)


ARGUE_SCHEMA_VERSION = "ask.argue.v1"
ARGUE_VERDICTS = frozenset({"FOR", "AGAINST", "NO_CLEAR_WINNER", "INSUFFICIENT_EVIDENCE"})
ARGUE_CONFIDENCE = frozenset({"low", "medium", "high"})
ARGUE_TIE_BREAKERS = frozenset({
    "lower-risk",
    "more-reversible",
    "simpler",
    "cheaper-to-test",
    "fail-closed",
    "higher-upside",
})
SCILLM_TRANSIENT_ERRORS = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("scillm response was not a JSON object")
    return parsed


def _context_payload(context_items: list[dict[str, Any]], current_answer: str = "") -> str:
    payload = {
        "current_answer": current_answer,
        "memory_items": [
            {
                "problem": item.get("problem", ""),
                "solution": item.get("solution", item.get("answer", "")),
                "source": item.get("_source", item.get("source", "")),
                "confidence": item.get("confidence", item.get("score", "")),
            }
            for item in context_items[:8]
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def build_advocate_prompt(side: str, question: str, context_items: list[dict[str, Any]], current_answer: str = "") -> str:
    opposing_side = "AGAINST" if side == "FOR" else "FOR"
    return f"""You are one side of a calibrated /ask argue protocol.

Take the {side} position on the user question. Do not decide the final answer.
Your job is to build the strongest admissible {side} case and disclose uncertainty.

Question:
{question}

Available context:
{_context_payload(context_items, current_answer=current_answer)}

Rules:
- Use only the question and available context. Do not invent private evidence.
- Cite every evidence item with a structured citation from QUESTION or MEMORY.N.
- Memory citations are admissible for knowledge/context claims, not code-review safety claims.
- Explicitly identify assumptions and missing evidence.
- Include weaknesses in your own case and what would change your mind.
- Format the response as a single JSON object.

Required JSON fields:
{{
  "side": "{side}",
  "position": "short statement of the {side} position",
  "strongest_argument": "best argument for {side}",
  "evidence": ["evidence strings copied or paraphrased from the available context or question"],
  "evidence_citations": [
    {{"source_id": "QUESTION or MEMORY.N", "source_kind": "question | memory", "quote_or_summary": "quoted or summarized support", "supports": "advocate_evidence"}}
  ],
  "assumptions": ["assumptions"],
  "weaknesses": ["weaknesses in the {side} case"],
  "missing_evidence": ["missing evidence"],
  "response_to_{opposing_side.lower()}": "how the likely opposing case should be answered",
  "what_would_change_my_mind": ["evidence that would weaken or reverse this side"],
  "confidence": "low | medium | high"
}}
"""


def build_judge_prompt(
    question: str,
    for_case: dict[str, Any],
    against_case: dict[str, Any],
    *,
    decision_required: bool = False,
    tie_breaker: str | None = None,
) -> str:
    decision_instruction = (
        f"A decision is explicitly required. Return FOR or AGAINST using the tie-breaker '{tie_breaker}'. "
        "Disclose that this is a forced choice if evidence is weak."
        if decision_required
        else "A decision is not required. Use NO_CLEAR_WINNER or INSUFFICIENT_EVIDENCE when warranted."
    )
    return f"""You are the sequential judge in a three-call /ask argue protocol.

Two independent advocates have already argued FOR and AGAINST in parallel.
Do not manufacture certainty. A FOR or AGAINST verdict is only valid if the
winning side defeats the strongest opposing argument under an explicit criterion.
Every evidence item must carry structured citations from the advocate outputs.
Memory citations can support knowledge/context claims, not code-review safety claims.

{decision_instruction}

Question:
{question}

FOR advocate JSON:
{json.dumps(for_case, indent=2, default=str)}

AGAINST advocate JSON:
{json.dumps(against_case, indent=2, default=str)}

Admissibility rule for FOR or AGAINST:
1. state the deciding criterion;
2. identify evidence supporting the winning side;
3. identify the strongest counterargument;
4. explain why the counterargument does or does not overturn the verdict;
5. state what would change the verdict.

Required JSON fields:
{{
  "verdict": "FOR | AGAINST | NO_CLEAR_WINNER | INSUFFICIENT_EVIDENCE",
  "confidence": "low | medium | high",
  "decision_required": {str(decision_required).lower()},
  "tie_breaker": "{tie_breaker or ""}",
  "decision_criterion": "criterion used",
  "winning_side": "FOR | AGAINST | none",
  "deciding_factors": ["factors"],
  "strongest_for_argument": "strongest FOR argument",
  "strongest_against_argument": "strongest AGAINST argument",
  "strongest_counterargument": "strongest losing-side counterargument, or strongest unresolved objection",
  "why_counterargument_does_or_does_not_win": "calibrated explanation",
  "evidence_used": ["evidence strings from the advocate evidence or arguments"],
  "evidence_citations": [
    {{"source_id": "QUESTION or MEMORY.N", "source_kind": "question | memory", "quote_or_summary": "quoted or summarized support", "supports": "verdict"}}
  ],
  "assumptions": ["assumptions"],
  "missing_evidence": ["missing evidence"],
  "what_would_change_the_verdict": ["evidence that would change the verdict"],
  "recommended_next_action": "next action",
  "uncertainty_disclosure": "required when decision_required is true or evidence is weak"
}}
"""


def normalize_advocate_output(raw_output: dict[str, Any], side: str) -> dict[str, Any]:
    confidence = _string_value(raw_output.get("confidence")).lower()
    if confidence not in ARGUE_CONFIDENCE:
        confidence = "low"
    return {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "side": side,
        "position": _string_value(raw_output.get("position")),
        "strongest_argument": _string_value(raw_output.get("strongest_argument")),
        "evidence": _string_list(raw_output.get("evidence")),
        "evidence_citations": normalize_citations(raw_output.get("evidence_citations"), supports="advocate_evidence"),
        "assumptions": _string_list(raw_output.get("assumptions")),
        "weaknesses": _string_list(raw_output.get("weaknesses")),
        "missing_evidence": _string_list(raw_output.get("missing_evidence")),
        "response_to_opposition": _string_value(
            raw_output.get("response_to_against" if side == "FOR" else "response_to_for")
            or raw_output.get("response_to_opposition")
        ),
        "what_would_change_my_mind": _string_list(raw_output.get("what_would_change_my_mind")),
        "confidence": confidence,
    }


def normalize_judge_output(
    raw_output: dict[str, Any],
    *,
    decision_required: bool = False,
    tie_breaker: str | None = None,
) -> dict[str, Any]:
    verdict = _string_value(raw_output.get("verdict")).upper()
    if verdict not in ARGUE_VERDICTS:
        verdict = "INSUFFICIENT_EVIDENCE"
    confidence = _string_value(raw_output.get("confidence")).lower()
    if confidence not in ARGUE_CONFIDENCE:
        confidence = "low"
    winning_side = _string_value(raw_output.get("winning_side")).upper() or "none"
    if winning_side not in {"FOR", "AGAINST", "NONE"}:
        winning_side = "none"
    if winning_side == "NONE":
        winning_side = "none"
    return {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "verdict": verdict,
        "confidence": confidence,
        "decision_required": bool(decision_required),
        "tie_breaker": tie_breaker or _string_value(raw_output.get("tie_breaker")),
        "decision_criterion": _string_value(raw_output.get("decision_criterion")),
        "winning_side": winning_side,
        "deciding_factors": _string_list(raw_output.get("deciding_factors")),
        "strongest_for_argument": _string_value(raw_output.get("strongest_for_argument")),
        "strongest_against_argument": _string_value(raw_output.get("strongest_against_argument")),
        "strongest_counterargument": _string_value(raw_output.get("strongest_counterargument")),
        "why_counterargument_does_or_does_not_win": _string_value(raw_output.get("why_counterargument_does_or_does_not_win")),
        "evidence_used": _string_list(raw_output.get("evidence_used")),
        "evidence_citations": normalize_citations(raw_output.get("evidence_citations"), supports="verdict"),
        "assumptions": _string_list(raw_output.get("assumptions")),
        "missing_evidence": _string_list(raw_output.get("missing_evidence")),
        "what_would_change_the_verdict": _string_list(raw_output.get("what_would_change_the_verdict")),
        "recommended_next_action": _string_value(raw_output.get("recommended_next_action")),
        "uncertainty_disclosure": _string_value(raw_output.get("uncertainty_disclosure")),
    }


def _failed_advocate_output(side: str, exc: BaseException, elapsed_seconds: float) -> dict[str, Any]:
    return {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "side": side,
        "status": "failed",
        "position": "",
        "strongest_argument": "",
        "evidence": [],
        "evidence_citations": [],
        "assumptions": [],
        "weaknesses": [],
        "missing_evidence": ["Advocate call failed before returning evidence."],
        "response_to_opposition": "",
        "what_would_change_my_mind": [],
        "confidence": "low",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "scillm_advice": scillm_error_advice(exc),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def _failed_judge_output(exc: BaseException, elapsed_seconds: float) -> dict[str, Any]:
    return {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "status": "failed",
        "verdict": "INSUFFICIENT_EVIDENCE",
        "confidence": "low",
        "decision_required": False,
        "tie_breaker": "",
        "decision_criterion": "",
        "winning_side": "none",
        "deciding_factors": [],
        "strongest_for_argument": "",
        "strongest_against_argument": "",
        "strongest_counterargument": "",
        "why_counterargument_does_or_does_not_win": "",
        "evidence_used": [],
        "evidence_citations": [],
        "assumptions": [],
        "missing_evidence": ["Judge call failed before returning a verdict."],
        "what_would_change_the_verdict": [],
        "recommended_next_action": "Inspect argue artifacts and rerun after fixing the /scillm failure.",
        "uncertainty_disclosure": "No trustworthy verdict was produced because the judge call failed.",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "scillm_advice": scillm_error_advice(exc),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def _skipped_judge_output(reason: str) -> dict[str, Any]:
    return {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "status": "skipped",
        "verdict": "INSUFFICIENT_EVIDENCE",
        "confidence": "low",
        "decision_required": False,
        "tie_breaker": "",
        "decision_criterion": "",
        "winning_side": "none",
        "deciding_factors": [],
        "strongest_for_argument": "",
        "strongest_against_argument": "",
        "strongest_counterargument": "",
        "why_counterargument_does_or_does_not_win": "",
        "evidence_used": [],
        "evidence_citations": [],
        "assumptions": [],
        "missing_evidence": [reason],
        "what_would_change_the_verdict": [],
        "recommended_next_action": "Inspect advocate artifacts and rerun after fixing the /scillm failure.",
        "uncertainty_disclosure": "No judge call was made because the advocate stage did not complete.",
    }


def verify_argue_result(result: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    judge = result.get("judge", {})
    for_case = result.get("for_case", {})
    against_case = result.get("against_case", {})
    source_bundle = result.get("source_bundle", {})
    scillm_summary = summarize_scillm_observability([for_case, against_case, judge])

    verdict = judge.get("verdict")
    confidence = judge.get("confidence")
    evidence_used = _string_list(judge.get("evidence_used"))
    evidence_citations = normalize_citations(judge.get("evidence_citations"), supports="verdict")
    missing_evidence = _string_list(judge.get("missing_evidence"))
    decision_required = bool(judge.get("decision_required"))
    tie_breaker = _string_value(judge.get("tie_breaker"))

    if verdict not in ARGUE_VERDICTS:
        failures.append("judge verdict is not in the allowed enum")
    if confidence not in ARGUE_CONFIDENCE:
        failures.append("judge confidence is not in the allowed enum")
    if not evidence_used and verdict != "INSUFFICIENT_EVIDENCE":
        failures.append("empty evidence_used requires INSUFFICIENT_EVIDENCE")
    failures.extend(validate_citations(
        "judge evidence_citations",
        evidence_citations,
        source_bundle=source_bundle,
        allowed_source_kinds=KNOWLEDGE_CITATION_KINDS,
        require_any=verdict != "INSUFFICIENT_EVIDENCE",
    ))
    if confidence == "high" and missing_evidence:
        failures.append("high confidence is not allowed when missing_evidence is non-empty")
    if confidence == "high" and scillm_summary["grounding_degraded"]:
        failures.append("high confidence is not allowed when source grounding is degraded")
    failures.extend(scillm_summary["metadata_failures"])

    if verdict in {"FOR", "AGAINST"}:
        if scillm_summary["grounding_degraded"]:
            failures.append("FOR/AGAINST verdict requires successful source grounding")
        required_fields = [
            "decision_criterion",
            "strongest_counterargument",
            "why_counterargument_does_or_does_not_win",
            "what_would_change_the_verdict",
        ]
        for field_name in required_fields:
            value = judge.get(field_name)
            if isinstance(value, list):
                if not _string_list(value):
                    failures.append(f"{verdict} verdict requires {field_name}")
            elif not _string_value(value):
                failures.append(f"{verdict} verdict requires {field_name}")
        if judge.get("winning_side") != verdict:
            failures.append("FOR/AGAINST verdict requires matching winning_side")

    if verdict == "NO_CLEAR_WINNER" and not _string_list(judge.get("what_would_change_the_verdict")):
        failures.append("NO_CLEAR_WINNER requires what_would_change_the_verdict")
    if verdict == "INSUFFICIENT_EVIDENCE" and not missing_evidence:
        failures.append("INSUFFICIENT_EVIDENCE requires missing_evidence")

    if decision_required:
        if verdict not in {"FOR", "AGAINST"}:
            failures.append("--decision-required requires a FOR or AGAINST verdict")
        if tie_breaker not in ARGUE_TIE_BREAKERS:
            failures.append("--decision-required requires an allowed tie_breaker")
        if not _string_value(judge.get("uncertainty_disclosure")):
            failures.append("--decision-required requires uncertainty_disclosure")

    advocate_material = set()
    for source_case in (for_case, against_case):
        failures.extend(validate_citations(
            f"{source_case.get('side', 'advocate')} evidence_citations",
            normalize_citations(source_case.get("evidence_citations"), supports="advocate_evidence"),
            source_bundle=source_bundle,
            allowed_source_kinds=KNOWLEDGE_CITATION_KINDS,
            require_any=bool(_string_list(source_case.get("evidence"))),
        ))
        for field_name in [
            "evidence",
            "missing_evidence",
            "assumptions",
            "weaknesses",
            "what_would_change_my_mind",
        ]:
            advocate_material.update(_string_list(source_case.get(field_name)))
    for field_name in ["strongest_argument", "position", "response_to_opposition"]:
        for value in (for_case.get(field_name), against_case.get(field_name)):
            if _string_value(value):
                advocate_material.add(_string_value(value))
    if evidence_used and advocate_material:
        unsupported = [
            evidence
            for evidence in evidence_used
            if evidence not in advocate_material
            and not any(evidence in material or material in evidence for material in advocate_material)
        ]
        if unsupported:
            failures.append("judge evidence_used contains material not present in advocate outputs")

    return {
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "grounding_degraded": scillm_summary["grounding_degraded"],
        "observability_degraded": scillm_summary["observability_degraded"],
    }


async def _scillm_json_call_async(
    client: httpx.AsyncClient,
    *,
    model: str,
    reasoning_effort: str,
    timeout: float,
    role: str,
    prompt: str,
    metadata: dict[str, Any] | None = None,
    source: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    requested_metadata = metadata or {}
    request_json: dict[str, Any] = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": f"You are the {role} node in /ask argue. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "scillm_metadata": requested_metadata,
    }
    if source:
        request_json["source"] = source
        request_json["grounding_threshold"] = 0.6
        request_json["grounding_retries"] = 1
    source_grounding_status = "not_requested"
    if source:
        source_grounding_status = "requested"
    headers = {
        "Authorization": f"Bearer {SCILLM_API_KEY}",
        "X-Caller-Skill": "ask",
        "Content-Type": "application/json",
    }
    endpoint = f"{SCILLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    try:
        response = await client.post(
            endpoint,
            headers=headers,
            json=request_json,
            timeout=min(timeout, 15.0) if source else timeout,
        )
        response.raise_for_status()
    except Exception as source_exc:
        if not source:
            raise
        fallback_json = dict(request_json)
        fallback_json.pop("source", None)
        fallback_json.pop("grounding_threshold", None)
        fallback_json.pop("grounding_retries", None)
        fallback_json["scillm_metadata"] = {
            **requested_metadata,
            "source_grounding_retry_without_source": True,
        }
        try:
            response = await client.post(
                endpoint,
                headers=headers,
                json=fallback_json,
                timeout=timeout,
            )
            response.raise_for_status()
        except SCILLM_TRANSIENT_ERRORS:
            await asyncio.sleep(0.2)
            response = await client.post(
                endpoint,
                headers=headers,
                json=fallback_json,
                timeout=timeout,
            )
            try:
                response.raise_for_status()
            except Exception as fallback_exc:
                raise fallback_exc from source_exc
        except Exception as fallback_exc:
            raise fallback_exc from source_exc
        source_grounding_status = "retry_without_source_after_error"
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    model_served = _string_value(payload.get("model")) or model
    observability = extract_scillm_observability(payload, requested_metadata)
    observability["source_grounding_status"] = source_grounding_status
    return _parse_json_object(content), model_served, observability


def _failed_scillm_observability(metadata: dict[str, Any], source: str | None) -> dict[str, Any]:
    return {
        "metadata_requested": metadata,
        "source_requested": bool(source),
        "source_grounding_status": "failed_before_response_with_source" if source else "not_requested",
    }


def _unpack_scillm_call_result(result: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if isinstance(result, tuple) and len(result) == 3:
        return result
    if isinstance(result, tuple) and len(result) == 2:
        raw_output, model_served = result
        return raw_output, model_served, {}
    raise ValueError("Unexpected /scillm call result shape")


async def _run_advocate_side(
    client: httpx.AsyncClient,
    *,
    side: str,
    question: str,
    context_items: list[dict[str, Any]],
    current_answer: str,
    model: str,
    reasoning_effort: str,
    timeout: float,
    run_state: AskRunState | NoopRunState | None,
    source: str | None,
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    started_at = time.time()
    if run_state:
        run_state.event("argue_advocate_started", side=side, model=model)
    prompt = build_advocate_prompt(side, question, context_items, current_answer=current_answer)
    try:
        raw_output, model_served, scillm_observability = _unpack_scillm_call_result(await _scillm_json_call_async(
            client,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            role=f"{side} advocate",
            prompt=prompt,
            metadata=metadata,
            source=source,
        ))
    except Exception as exc:
        advocate = _failed_advocate_output(side, exc, time.time() - started_at)
        advocate["scillm"] = _failed_scillm_observability(metadata, source)
        if run_state:
            run_state.event(
                "argue_advocate_failed",
                side=side,
                error_type=advocate["error_type"],
                error=advocate["error"],
                elapsed_seconds=advocate["elapsed_seconds"],
            )
        return side, advocate

    advocate = normalize_advocate_output(raw_output, side)
    advocate["status"] = "ok"
    advocate["model"] = model_served
    advocate["scillm"] = scillm_observability
    advocate["elapsed_seconds"] = round(time.time() - started_at, 3)
    if run_state:
        run_state.event(
            "argue_advocate_finished",
            side=side,
            model=model_served,
            elapsed_seconds=advocate["elapsed_seconds"],
        )
    return side, advocate


async def _run_argue_async(
    *,
    question: str,
    context_items: list[dict[str, Any]],
    current_answer: str,
    model: str,
    reasoning_effort: str,
    timeout: float,
    decision_required: bool,
    tie_breaker: str | None,
    run_state: AskRunState | NoopRunState | None,
    source_bundle: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    source = serialize_source_bundle(source_bundle)
    ask_id = str(getattr(run_state, "ask_id", "ask-run")) if run_state else "ask-run"
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(
                _run_advocate_side(
                    client,
                    side=side,
                    question=question,
                    context_items=context_items,
                    current_answer=current_answer,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    timeout=timeout,
                    run_state=run_state,
                    source=source,
                    metadata=build_scillm_metadata(
                        ask_id=ask_id,
                        protocol="argue",
                        node_id=side,
                        node_role="advocate",
                        question=question,
                        artifact_dir=artifact_dir,
                        source_bundle_id=str(source_bundle.get("source_bundle_id", "")),
                    ),
                )
            )
            for side in ("FOR", "AGAINST")
        ]
        advocate_outputs: dict[str, dict[str, Any]] = {}
        try:
            for completed in asyncio.as_completed(tasks):
                side, advocate = await completed
                advocate_outputs[side] = advocate
        except Exception:
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

        failed_advocates = [
            advocate for advocate in advocate_outputs.values()
            if advocate.get("status") == "failed"
        ]
        if failed_advocates:
            if run_state:
                run_state.event("argue_judge_skipped", reason="advocate_failure", failed_advocates=len(failed_advocates))
            return {
                "for_case": advocate_outputs.get("FOR") or _skipped_judge_output("FOR advocate did not return."),
                "against_case": advocate_outputs.get("AGAINST") or _skipped_judge_output("AGAINST advocate did not return."),
                "judge": _skipped_judge_output("One or more advocate calls failed before judge execution."),
                "judge_prompt": "",
                "error": {
                    "stage": "advocate",
                    "reason": "argue_scillm_call_failed",
                    "failures": [
                        {
                            "side": advocate.get("side"),
                            "error_type": advocate.get("error_type"),
                            "error": advocate.get("error"),
                        }
                        for advocate in failed_advocates
                    ],
                },
            }

        if run_state:
            run_state.event("argue_judge_started", model=model)
        judge_prompt = build_judge_prompt(
            question,
            advocate_outputs["FOR"],
            advocate_outputs["AGAINST"],
            decision_required=decision_required,
            tie_breaker=tie_breaker,
        )
        judge_started = time.time()
        try:
            raw_judge, judge_model, scillm_observability = _unpack_scillm_call_result(await _scillm_json_call_async(
                client,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                role="sequential judge",
                prompt=judge_prompt,
                metadata=build_scillm_metadata(
                    ask_id=ask_id,
                    protocol="argue",
                    node_id="judge",
                    node_role="judge",
                    question=question,
                    artifact_dir=artifact_dir,
                    source_bundle_id=str(source_bundle.get("source_bundle_id", "")),
                ),
                source=source,
            ))
        except Exception as exc:
            judge = _failed_judge_output(exc, time.time() - judge_started)
            judge_metadata = build_scillm_metadata(
                ask_id=ask_id,
                protocol="argue",
                node_id="judge",
                node_role="judge",
                question=question,
                artifact_dir=artifact_dir,
                source_bundle_id=str(source_bundle.get("source_bundle_id", "")),
            )
            judge["scillm"] = _failed_scillm_observability(judge_metadata, source)
            if run_state:
                run_state.event(
                    "argue_judge_failed",
                    error_type=judge["error_type"],
                    error=judge["error"],
                    elapsed_seconds=judge["elapsed_seconds"],
                )
            return {
                "for_case": advocate_outputs["FOR"],
                "against_case": advocate_outputs["AGAINST"],
                "judge": judge,
                "judge_prompt": judge_prompt,
                "error": {
                    "stage": "judge",
                    "reason": "argue_scillm_call_failed",
                    "failures": [
                        {
                            "role": "sequential judge",
                            "error_type": judge["error_type"],
                            "error": judge["error"],
                        }
                    ],
                },
            }
        judge = normalize_judge_output(raw_judge, decision_required=decision_required, tie_breaker=tie_breaker)
        judge["model"] = judge_model
        judge["scillm"] = scillm_observability
        judge["elapsed_seconds"] = round(time.time() - judge_started, 3)
        if run_state:
            run_state.event("argue_judge_finished", model=judge_model, elapsed_seconds=judge["elapsed_seconds"])
        return {
            "for_case": advocate_outputs["FOR"],
            "against_case": advocate_outputs["AGAINST"],
            "judge": judge,
            "judge_prompt": judge_prompt,
        }


def render_argue_markdown(result: dict[str, Any]) -> str:
    judge = result["judge"]
    for_case = result["for_case"]
    against_case = result["against_case"]
    lines = [
        "# /ask argue verdict",
        "",
        f"- Verdict: `{judge.get('verdict')}`",
        f"- Confidence: `{judge.get('confidence')}`",
        f"- Decision criterion: {judge.get('decision_criterion') or 'not stated'}",
        f"- Winning side: `{judge.get('winning_side')}`",
        f"- Verifier: `{result.get('verifier', {}).get('status')}`",
        "",
        "## Judge",
        "",
        judge.get("why_counterargument_does_or_does_not_win") or "",
        "",
        "## Deciding Factors",
        "",
    ]
    lines.extend(f"- {item}" for item in _string_list(judge.get("deciding_factors")))
    lines.extend([
        "",
        "## Evidence Used",
        "",
    ])
    lines.extend(f"- {item}" for item in _string_list(judge.get("evidence_used")))
    lines.extend([
        "",
        "## Citations",
        "",
        render_citations_markdown(judge.get("evidence_citations", [])),
    ])
    lines.extend([
        "",
        "## Missing Evidence",
        "",
    ])
    lines.extend(f"- {item}" for item in _string_list(judge.get("missing_evidence")))
    lines.extend([
        "",
        "## What Would Change The Verdict",
        "",
    ])
    lines.extend(f"- {item}" for item in _string_list(judge.get("what_would_change_the_verdict")))
    lines.extend([
        "",
        "## FOR Advocate",
        "",
        for_case.get("strongest_argument") or "",
        "",
        "## AGAINST Advocate",
        "",
        against_case.get("strongest_argument") or "",
        "",
        "## Recommended Next Action",
        "",
        judge.get("recommended_next_action") or "",
        "",
    ])
    return "\n".join(lines)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_argue(
    *,
    question: str,
    context_items: list[dict[str, Any]],
    current_answer: str,
    model: str,
    reasoning_effort: str,
    timeout: float,
    run_state: AskRunState | NoopRunState,
    decision_required: bool = False,
    tie_breaker: str | None = None,
) -> dict[str, Any]:
    """Run two parallel advocates and a sequential judge through /scillm."""
    started_at = time.time()
    argue_dir = run_state.run_dir / "argue" if hasattr(run_state, "run_dir") else Path.cwd() / ".ask_argue"
    argue_dir.mkdir(parents=True, exist_ok=True)
    source_bundle = build_source_bundle(question=question, context_items=context_items)
    run_state.event("argue_started", model=model, reasoning_effort=reasoning_effort, decision_required=decision_required)
    protocol_result = asyncio.run(
        _run_argue_async(
            question=question,
            context_items=context_items,
            current_answer=current_answer,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            decision_required=decision_required,
            tie_breaker=tie_breaker,
            run_state=run_state,
            source_bundle=source_bundle,
            artifact_dir=argue_dir,
        )
    )
    argue_result = {
        "schema_version": ARGUE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "decision_required": decision_required,
        "tie_breaker": tie_breaker or "",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "citation_schema_version": CITATION_SCHEMA_VERSION,
        "source_bundle": {
            "source_bundle_id": source_bundle["source_bundle_id"],
            "citation_schema_version": source_bundle.get("citation_schema_version", CITATION_SCHEMA_VERSION),
            "source_ids": [source["source_id"] for source in source_bundle["sources"]],
            "sources": source_bundle["sources"],
        },
        "for_case": protocol_result["for_case"],
        "against_case": protocol_result["against_case"],
        "judge": protocol_result["judge"],
        "execution": {
            "dag": "for_advocate || against_advocate -> judge -> verifier",
            "scillm_calls": 3,
            "elapsed_seconds": round(time.time() - started_at, 3),
            "read_only": True,
        },
    }
    scillm_summary = summarize_scillm_observability([
        argue_result["for_case"],
        argue_result["against_case"],
        argue_result["judge"],
    ])
    argue_result["execution"]["grounding_degraded"] = scillm_summary["grounding_degraded"]
    argue_result["execution"]["observability_degraded"] = scillm_summary["observability_degraded"]
    argue_result["grounding_degraded"] = scillm_summary["grounding_degraded"]
    argue_result["observability_degraded"] = scillm_summary["observability_degraded"]
    protocol_error = protocol_result.get("error")
    if protocol_error:
        verifier = {
            "status": "FAIL",
            "failures": [
                f"{protocol_error.get('stage', 'scillm')} call failed: {failure.get('error_type')}: {failure.get('error')}"
                for failure in protocol_error.get("failures", [])
            ],
        }
    else:
        verifier = verify_argue_result(argue_result)
    argue_result["verifier"] = verifier
    markdown = render_argue_markdown(argue_result)

    artifacts = {
        "argue_for": str(argue_dir / "for.json"),
        "argue_against": str(argue_dir / "against.json"),
        "argue_judge": str(argue_dir / "judge.json"),
        "argue_result": str(argue_dir / "argue.json"),
        "argue_markdown": str(argue_dir / "argue.md"),
        "argue_verifier": str(argue_dir / "verifier.log"),
        "argue_judge_prompt": str(argue_dir / "judge_prompt.md"),
        "argue_source_bundle": str(argue_dir / "source_bundle.json"),
    }
    atomic_write_json(argue_dir / "source_bundle.json", source_bundle)
    atomic_write_json(argue_dir / "for.json", argue_result["for_case"])
    atomic_write_json(argue_dir / "against.json", argue_result["against_case"])
    atomic_write_json(argue_dir / "judge.json", argue_result["judge"])
    atomic_write_json(argue_dir / "argue.json", argue_result)
    _write_text(argue_dir / "argue.md", markdown)
    _write_text(argue_dir / "verifier.log", "\n".join(verifier["failures"]) if verifier["failures"] else "PASS\n")
    _write_text(argue_dir / "judge_prompt.md", protocol_result["judge_prompt"])
    run_state.add_artifacts(artifacts)
    run_state.event("argue_verifier_finished", status=verifier["status"], failures=len(verifier["failures"]))

    response = {
        "answer": markdown,
        "argue": {
            "schema_version": ARGUE_SCHEMA_VERSION,
            "verdict": argue_result["judge"]["verdict"],
            "confidence": argue_result["judge"]["confidence"],
            "decision_required": decision_required,
            "tie_breaker": tie_breaker or "",
            "verifier_status": verifier["status"],
            "grounding_degraded": argue_result["grounding_degraded"],
            "observability_degraded": argue_result["observability_degraded"],
            "artifact_paths": artifacts,
        },
    }
    if protocol_error:
        scillm_debug = fetch_recent_scillm_debug(caller="ask", limit=1)
        response["needs_attention"] = run_state.needs_attention(
            reason=str(protocol_error.get("reason") or "argue_scillm_call_failed"),
            question="Argue /scillm call failed before a trustworthy verdict was produced.",
            safe_default="do_not_trust_verdict",
            resume_hint=f"Inspect {argue_dir} and rerun with a narrower prompt or different backend.",
            stage=protocol_error.get("stage", "scillm"),
            failures=protocol_error.get("failures", []),
            scillm_debug=scillm_debug,
        )
    elif verifier["status"] != "PASS":
        response["needs_attention"] = run_state.needs_attention(
            reason="argue_verifier_failed",
            question="Argue judge output failed deterministic verifier checks.",
            safe_default="do_not_trust_verdict",
            resume_hint=f"Inspect {artifacts['argue_verifier']} and rerun with stronger evidence or --decision-required if appropriate.",
            verifier_failures=verifier["failures"],
        )
    return response
