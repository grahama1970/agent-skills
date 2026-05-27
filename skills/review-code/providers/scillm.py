"""scillm provider for review-code — routes through local proxy to any backend.

Supports all scillm models including gpt-5.3-codex (Codex Cloud via OAuth).
No CLI subprocess, no temp workspace — direct httpx SSE stream.

Usage:
    review-full --provider scillm --model gpt-5.3-codex
    review-full --provider scillm --model gpt-5.5
    review-full --provider scillm --model gemini-flash
    review-full --provider scillm --model chutes-deepseek
"""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import hashlib
import json
import os
from typing import Any, Optional

import httpx
from loguru import logger

SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"
DEFAULT_MODEL = os.environ.get("REVIEW_CODE_SCILLM_MODEL", "gpt-5.5")

CONTRACT_SCHEMA = """Return a strict JSON object only. No prose, no markdown.
{
  "scope": "string",
  "verdict": "PASS|NEEDS_CHANGES|BLOCKED|INSUFFICIENT_EVIDENCE",
  "summary": "one sentence",
  "blocking_findings": [
    {
      "id": "string",
      "severity": "blocker|major|minor",
      "file": "path",
      "lines": "line or range if available",
      "evidence": "specific file/diff/test/log/artifact evidence",
      "claim": "what is wrong",
      "impact": "why it matters",
      "suggested_fix": "smallest safe fix",
      "confidence": "high|medium|low"
    }
  ],
  "non_blocking_findings": [],
  "unsupported_or_rejected_concerns": [
    {
      "claim": "string",
      "reason_rejected": "string"
    }
  ],
  "evidence_checked": [
    {
      "type": "file|diff|test|log|artifact|command",
      "reference": "string",
      "result": "string"
    }
  ],
  "missing_evidence": []
}"""

SCOPED_REVIEW_CONTRACTS: dict[str, str] = {
    "correctness_regression": """You are the correctness/regression reviewer.
Your task is narrow: determine whether the diff correctly satisfies the requested change without breaking existing behavior.
You are read-only. Do not edit files. Do not propose broad rewrites. Do not comment on style unless it creates a correctness problem.
Review focus:
- Does the implementation satisfy the stated task, plan, or issue?
- Are there edge cases where the new behavior fails?
- Does the change preserve existing public behavior unless the change explicitly requires otherwise?
- Are error paths, null/empty states, missing inputs, retries, and failure handling correct?
- Are function signatures, call sites, return values, and control flow consistent?
- Are there hidden regressions caused by partial updates across files?
- Does the implementation accidentally change scope beyond the request?
Evidence rules:
- Every finding must cite a concrete file path and line/range when available.
- A finding without file/diff/test/log evidence must be rejected.
- If the diff is too incomplete to judge, return INSUFFICIENT_EVIDENCE and list the missing evidence.
- Do not infer bugs from vibes; verify from code, tests, command output, or stated requirements.
Set "scope" to "correctness_regression".""",
    "tests_validation": """You are the tests/validation reviewer.
Your task is narrow: determine whether the change has sufficient verification for the risk it introduces.
You are read-only. Do not edit files. Do not ask for maximal test coverage. Require only tests or validation that are justified by the change.
Review focus:
- Are there tests for the changed behavior?
- Do tests assert the important invariant, or do they merely exercise code superficially?
- Are negative/error cases covered when the diff changes validation, parsing, IO, state transitions, permissions, or failure handling?
- Are existing tests updated correctly when behavior intentionally changed?
- Are the chosen validation commands sufficient for the changed scope?
- Are there missing deterministic checks that should block merge?
- Are snapshots, mocks, fixtures, or golden files updated safely and intentionally?
- Did the author claim validation passed without evidence?
Evidence rules:
- Cite exact test files, commands, logs, or artifact paths.
- A missing test is a blocker only when the change creates meaningful regression risk that cannot be covered by existing tests or deterministic validation.
- Do not require broad integration tests when a focused unit or fixture test would prove the invariant.
- If validation output is missing or stale, return NEEDS_CHANGES or INSUFFICIENT_EVIDENCE depending on severity.
Set "scope" to "tests_validation".""",
    "simplicity_maintainability": """You are the simplicity/maintainability reviewer.
Your task is narrow: identify unnecessary complexity that makes the change harder to review, maintain, or safely extend.
You are read-only. Do not edit files. Do not nitpick personal style. Only report issues that are concretely worth fixing now.
Review focus:
- Is the change larger than necessary for the requested behavior?
- Are there duplicate helpers, duplicate types, duplicate state, or repeated logic?
- Are there single-use abstractions that obscure simple behavior?
- Are names misleading or inconsistent with nearby code?
- Are comments explaining obvious code, stale rationale, or implementation noise?
- Does the code introduce future-proofing, generic frameworks, or configuration that the task does not need?
- Does the change violate local patterns in nearby files?
- Is there a smaller fix that preserves behavior and improves clarity?
Evidence rules:
- Cite nearby existing patterns when claiming inconsistency.
- Do not report "could be cleaner" unless there is a specific simpler alternative.
- Do not recommend large refactors unless the current diff introduced the complexity.
- Mark findings as non-blocking unless the complexity creates real correctness, testability, or maintenance risk.
Set "scope" to "simplicity_maintainability".""",
    "evidence_closure_safety": """You are the scillm evidence/closure-safety reviewer.
Your task is narrow: determine whether the diff preserves scillm's evidence, provenance, review, and phase-closure invariants.
You are read-only. Do not edit files. Do not review general style unless it weakens evidence integrity.
Review focus:
- Does the diff preserve the rule that implementation output is evidence, not closure?
- Does only the final review/merge-gate path have authority to mark a phase complete?
- Are review artifacts, execution results, hashes, commands, changed files, and provenance preserved?
- Are reviewer findings traceable to files, diffs, logs, artifacts, or deterministic outputs?
- Does the change prevent fabricated review success, missing artifacts, stale hashes, or ungrounded closure?
- Are code-runner handoffs clearly separated from reviewer adjudication?
- Does the reducer distinguish accepted findings, rejected findings, conflicts, optional improvements, and blockers?
- Does the diff weaken fail-closed behavior when evidence is missing?
- Are async, batch, or parallel review results persisted in a way that can be audited later?
Evidence rules:
- Treat missing provenance as a real finding.
- Treat "review passed" without persisted evidence as a blocker.
- Treat any path that lets a worker, child reviewer, or implementation step directly close a phase as a blocker.
- Treat stale or unverified hashes as NEEDS_CHANGES or BLOCKED depending on whether they can launder completion.
- Cite artifact paths, JSON fields, command output, or code paths for every finding.
Set "scope" to "evidence_closure_safety".""",
    "security": """You are the security reviewer.
Your task is narrow: determine whether the diff introduces a security boundary failure or weakens an existing security control.
You are read-only. Do not edit files. Do not report generic hardening advice without concrete evidence in the diff.
Review focus:
- Auth, permissions, secrets, shell commands, file IO, network IO, deserialization, user input, path handling, tokens, and logs containing sensitive data.
- Does the implementation validate untrusted input before using it in filesystem, network, command, database, or model-provider calls?
- Are secrets, tokens, credentials, or private paths exposed in logs, artifacts, errors, or UI output?
- Are privilege boundaries and fail-closed behavior preserved?
- Are security-sensitive defaults explicit and conservative?
Evidence rules:
- Every finding must cite a concrete file path and line/range when available.
- A finding without file/diff/test/log evidence must be rejected.
- Do not turn missing defense-in-depth into a blocker unless the change creates reachable risk.
Set "scope" to "security".""",
}

EVIDENCE_TRIGGER_TERMS = {
    "artifact",
    "artifacts",
    "closure",
    "evidence",
    "orchestration",
    "phase",
    "plan-iterate",
    "provenance",
    "review-code",
    "reviewer",
    "code-runner",
    "handoff",
    "ledger",
}

SECURITY_TRIGGER_TERMS = {
    "auth",
    "permission",
    "permissions",
    "secret",
    "secrets",
    "shell",
    "command",
    "subprocess",
    "file io",
    "filesystem",
    "network",
    "deserialize",
    "deserialization",
    "user input",
    "path",
    "token",
    "tokens",
    "credential",
    "credentials",
    "sandbox",
}


def _env_true(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _json_error(message: str, *, model: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": "",
        "model": (data or {}).get("model", model),
        "usage": (data or {}).get("usage", {}),
        "ok": False,
        "error": message,
        "raw_response": data or {},
    }


def _extract_review_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped == "[]":
        raise ValueError(
            "inadmissible_empty_findings: bare [] is not a valid review-code closure receipt"
        )
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    parsed = json.loads(stripped)
    if isinstance(parsed, list):
        raise ValueError(
            "inadmissible_array_receipt: review-code requires a JSON object with "
            "verdict, findings, reviewed_scope, rationale, and model_proof"
        )
    if not isinstance(parsed, dict):
        raise ValueError("inadmissible_receipt_type: review-code response must be a JSON object")
    return parsed


def _normalize_contract_verdict(verdict: Any) -> str:
    normalized = str(verdict or "").strip().upper()
    aliases = {
        "SATISFIED": "PASS",
        "PASSED": "PASS",
        "FAIL": "NEEDS_CHANGES",
        "FAILED": "NEEDS_CHANGES",
        "UNSATISFIED": "NEEDS_CHANGES",
        "NEEDS CHANGE": "NEEDS_CHANGES",
        "NEEDS-CHANGES": "NEEDS_CHANGES",
        "INSUFFICIENT": "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT-EVIDENCE": "INSUFFICIENT_EVIDENCE",
    }
    return aliases.get(normalized, normalized)


def finding_has_concrete_evidence(finding: dict[str, Any]) -> bool:
    """Return whether a reviewer finding is grounded enough for handoff."""
    evidence = str(finding.get("evidence") or "").strip()
    file_path = str(finding.get("file") or "").strip()
    claim = str(finding.get("claim") or "").strip()
    unsupported_markers = {
        "n/a",
        "none",
        "not available",
        "not applicable",
        "no evidence",
        "unknown",
    }
    if not evidence or evidence.lower() in unsupported_markers:
        return False
    if not file_path or file_path.lower() in unsupported_markers:
        return False
    return bool(claim)


def validate_contract_receipt(receipt: dict[str, Any], expected_scope: str) -> dict[str, Any]:
    """Normalize and validate a scoped evidence-contract review receipt."""
    if not isinstance(receipt, dict):
        raise ValueError("contract response must be a JSON object")
    scope = str(receipt.get("scope") or "").strip()
    if scope != expected_scope:
        raise ValueError(f"contract scope mismatch: expected={expected_scope}, got={scope or '<missing>'}")
    verdict = _normalize_contract_verdict(receipt.get("verdict"))
    if verdict not in {"PASS", "NEEDS_CHANGES", "BLOCKED", "INSUFFICIENT_EVIDENCE"}:
        raise ValueError("contract verdict must be PASS, NEEDS_CHANGES, BLOCKED, or INSUFFICIENT_EVIDENCE")
    receipt["verdict"] = verdict
    for key in (
        "blocking_findings",
        "non_blocking_findings",
        "unsupported_or_rejected_concerns",
        "evidence_checked",
        "missing_evidence",
    ):
        if not isinstance(receipt.get(key), list):
            raise ValueError(f"contract field {key} must be a list")
    if not str(receipt.get("summary") or "").strip():
        raise ValueError("contract summary is required")
    return receipt


def select_default_review_scopes(
    *,
    files_reviewed: list[str],
    context: str = "",
    focus: str = "",
) -> list[str]:
    """Select default scoped contracts from changed paths and review context."""
    haystack = " ".join([*files_reviewed, context, focus]).lower()
    security_triggered = any(term in haystack for term in SECURITY_TRIGGER_TERMS)
    evidence_triggered = any(term in haystack for term in EVIDENCE_TRIGGER_TERMS)
    scopes = ["correctness_regression", "tests_validation"]
    scopes.append("security" if security_triggered else "simplicity_maintainability")
    if evidence_triggered:
        scopes.append("evidence_closure_safety")
    return scopes


def reduce_contract_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate scoped reviewer receipts with evidence-gated finding acceptance."""
    accepted_blocking: list[dict[str, Any]] = []
    accepted_non_blocking: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    per_scope: list[dict[str, Any]] = []

    for receipt in receipts:
        scope = str(receipt.get("scope") or "")
        per_scope.append({
            "scope": scope,
            "verdict": receipt.get("verdict"),
            "blocking_findings": len(receipt.get("blocking_findings") or []),
            "non_blocking_findings": len(receipt.get("non_blocking_findings") or []),
            "missing_evidence": len(receipt.get("missing_evidence") or []),
        })
        for finding in receipt.get("blocking_findings") or []:
            if finding_has_concrete_evidence(finding):
                accepted_blocking.append({"scope": scope, **finding})
            else:
                unsupported.append({
                    "scope": scope,
                    "claim": finding.get("claim") or finding.get("id") or "blocking finding",
                    "reason_rejected": "missing concrete file/diff/test/log/artifact evidence",
                    "original": finding,
                })
        for finding in receipt.get("non_blocking_findings") or []:
            if finding_has_concrete_evidence(finding):
                accepted_non_blocking.append({"scope": scope, **finding})
            else:
                unsupported.append({
                    "scope": scope,
                    "claim": finding.get("claim") or finding.get("id") or "non-blocking finding",
                    "reason_rejected": "missing concrete file/diff/test/log/artifact evidence",
                    "original": finding,
                })
        for concern in receipt.get("unsupported_or_rejected_concerns") or []:
            unsupported.append({"scope": scope, **concern})
        for item in receipt.get("missing_evidence") or []:
            missing_evidence.append({"scope": scope, "missing": item})

    verdicts = {str(receipt.get("verdict") or "") for receipt in receipts}
    if "BLOCKED" in verdicts:
        verdict = "BLOCKED"
    elif accepted_blocking:
        verdict = "NEEDS_CHANGES"
    elif "INSUFFICIENT_EVIDENCE" in verdicts or missing_evidence:
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "PASS"

    return {
        "schema": "review_code.aggregate.v1",
        "verdict": verdict,
        "summary": (
            f"{len(accepted_blocking)} evidence-backed blocking findings, "
            f"{len(accepted_non_blocking)} evidence-backed non-blocking findings, "
            f"{len(unsupported)} unsupported/rejected concerns."
        ),
        "accepted_blocking_findings": accepted_blocking,
        "accepted_non_blocking_findings": accepted_non_blocking,
        "unsupported_or_rejected_concerns": unsupported,
        "missing_evidence": missing_evidence,
        "per_scope": per_scope,
    }


def _validate_and_attach_receipt(
    *,
    content: str,
    model_requested: str,
    data: dict[str, Any],
    files_reviewed: list[str],
    prompt_sha256: str,
) -> str:
    receipt = _extract_review_object(content)
    verdict = str(receipt.get("verdict", "")).strip().lower()
    if verdict in {"pass", "passed"}:
        verdict = "satisfied"
        receipt["verdict"] = verdict
    elif verdict in {"fail", "failed", "unsatisfied", "reject", "rejected"}:
        verdict = "needs_changes"
        receipt["verdict"] = verdict
    if verdict not in {"satisfied", "needs_changes", "blocked"}:
        raise ValueError(
            "inadmissible_verdict: verdict must be satisfied, needs_changes, or blocked"
        )
    if "blocking_findings" not in receipt or not isinstance(receipt["blocking_findings"], list):
        raise ValueError("inadmissible_receipt: blocking_findings list is required")
    if "non_blocking_findings" not in receipt or not isinstance(receipt["non_blocking_findings"], list):
        raise ValueError("inadmissible_receipt: non_blocking_findings list is required")
    rationale = str(receipt.get("rationale", "")).strip()
    if len(rationale) < 40:
        raise ValueError("inadmissible_receipt: reviewer rationale is required")

    served_model = data.get("model", model_requested)
    receipt["reviewed_scope"] = {
        **(receipt.get("reviewed_scope") if isinstance(receipt.get("reviewed_scope"), dict) else {}),
        "files_reviewed": files_reviewed,
        "prompt_sha256": prompt_sha256,
    }
    receipt["model_proof"] = {
        **(receipt.get("model_proof") if isinstance(receipt.get("model_proof"), dict) else {}),
        "requested_model": model_requested,
        "served_model": served_model,
        "exact_model_required": _env_true("REVIEW_CODE_SCILLM_REQUIRE_EXACT_MODEL", True),
        "reasoning_effort": os.environ.get("REVIEW_CODE_SCILLM_REASONING_EFFORT", "high"),
        "scillm_reasoning": data.get("scillm_reasoning"),
        "scillm_multimodal": data.get("scillm_multimodal"),
    }
    receipt["response_shape"] = "review_code_receipt_v1"
    return json.dumps(receipt, indent=2, sort_keys=True)


def _build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    prompt_sha256: str,
    request_timeout: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "reasoning_effort": os.environ.get("REVIEW_CODE_SCILLM_REASONING_EFFORT", "high"),
        "require_exact_model": _env_true("REVIEW_CODE_SCILLM_REQUIRE_EXACT_MODEL", True),
        "allow_model_remap": False,
        "timeout": request_timeout,
        "stream": True,
        "stream_progress_events": True,
        "stream_heartbeat_s": float(os.environ.get("REVIEW_CODE_SCILLM_HEARTBEAT_S", "5")),
        "stream_options": {"include_usage": True},
        "scillm_metadata": {
            "skill": "review-code",
            "prompt_sha256": prompt_sha256,
        },
    }
    # Codex Cloud rejects temperature param.
    if not model.startswith("gpt-"):
        payload["temperature"] = 0.2
    return payload


async def _send_review_streaming(
    *,
    payload: dict[str, Any],
    model: str,
    timeout: float,
) -> dict[str, Any]:
    chunks: list[str] = []
    served_model = model
    usage: dict[str, Any] = {}
    progress_events = 0
    heartbeat_events = 0
    last_event_type = ""
    raw_error: dict[str, Any] | None = None

    http_timeout = httpx.Timeout(
        connect=5.0,
        read=timeout + 30.0,
        write=30.0,
        pool=5.0,
    )
    async with httpx.AsyncClient(timeout=http_timeout) as client:
        async with client.stream(
            "POST",
            SCILLM_URL,
            headers={
                "Authorization": f"Bearer {SCILLM_KEY}",
                "Content-Type": "application/json",
                "X-Caller-Skill": "review-code",
            },
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                text = body.decode("utf-8", errors="replace")
                return _json_error(f"HTTP {resp.status_code}: {text[:1000]}", model=model)

            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith(":"):
                    heartbeat_events += 1
                    continue
                if line.startswith("event:"):
                    last_event_type = line[len("event:"):].strip()
                    if last_event_type in {"started", "heartbeat", "done"}:
                        progress_events += 1
                    continue
                if not line.startswith("data:"):
                    continue

                data_text = line[len("data:"):].strip()
                if data_text == "[DONE]":
                    break
                try:
                    event = json.loads(data_text)
                except json.JSONDecodeError:
                    continue

                if "error" in event:
                    raw_error = event["error"] if isinstance(event["error"], dict) else {"message": str(event["error"])}
                    break
                if event.get("model"):
                    served_model = str(event["model"])
                if event.get("usage"):
                    usage = event["usage"]
                if event.get("cost"):
                    continue

                choices = event.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] or {}
                delta = choice.get("delta") or {}
                message = choice.get("message") or {}
                content_delta = delta.get("content")
                if content_delta is None:
                    content_delta = message.get("content")
                if content_delta:
                    chunks.append(str(content_delta))

    if raw_error is not None:
        return _json_error(
            raw_error.get("message") or json.dumps(raw_error, sort_keys=True),
            model=served_model,
            data={"model": served_model, "usage": usage, "stream_error": raw_error},
        )

    content = "".join(chunks)
    if not content:
        return _json_error(
            "empty_stream_response: scillm stream completed without review content",
            model=served_model,
            data={"model": served_model, "usage": usage},
        )

    return {
        "content": content,
        "model": served_model,
        "usage": usage,
        "ok": True,
        "error": None,
        "raw_response": {
            "model": served_model,
            "usage": usage,
            "stream": True,
            "progress_events": progress_events,
            "heartbeat_events": heartbeat_events,
        },
    }


async def send_review(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    timeout: Optional[float] = None,
    files_reviewed: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Send a review request through scillm and return structured response.

    Returns:
        {"content": str, "model": str, "usage": dict, "ok": bool, "error": str | None}

    Note: Does NOT set max_tokens per best-practices-scillm Rule 4.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    request_timeout = timeout or float(os.environ.get("REVIEW_CODE_SCILLM_TIMEOUT_SEC", "300"))

    try:
        payload = _build_payload(
            model=model,
            messages=messages,
            prompt_sha256=prompt_sha256,
            request_timeout=request_timeout,
        )
        result = await _send_review_streaming(payload=payload, model=model, timeout=request_timeout)
        if not result["ok"]:
            result["prompt_sha256"] = prompt_sha256
            return result

        data = result.get("raw_response") or {}
        content = result["content"]
        served_model = result.get("model", model)
        if payload["require_exact_model"] and served_model != model:
            return _json_error(
                f"served_model_mismatch: requested={model}, served={served_model}",
                model=model,
                data=data,
            )
        try:
            content = _validate_and_attach_receipt(
                content=content,
                model_requested=model,
                data=data,
                files_reviewed=files_reviewed or [],
                prompt_sha256=prompt_sha256,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            error_result = _json_error(str(exc), model=model, data=data)
            error_result["raw_review_content"] = result["content"]
            error_result["prompt_sha256"] = prompt_sha256
            return error_result
        return {
            "content": content,
            "model": served_model,
            "usage": result.get("usage", {}),
            "ok": True,
            "error": None,
            "prompt_sha256": prompt_sha256,
            "raw_response": data,
        }
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(f"scillm review failed: {error}")
        return {"content": "", "model": model, "usage": {}, "ok": False, "error": error}
    except httpx.TimeoutException as e:
        error = (
            f"scillm timeout after {request_timeout:.0f}s while waiting for {model}; "
            f"{type(e).__name__}"
        )
        logger.error(f"scillm review failed: {error}")
        return {"content": "", "model": model, "usage": {}, "ok": False, "error": error}
    except Exception as e:
        error = str(e) or type(e).__name__
        logger.error(f"scillm review failed: {error}")
        return {"content": "", "model": model, "usage": {}, "ok": False, "error": error}


def build_scoped_review_prompt(
    *,
    files: dict[str, str],
    context: str,
    focus: str,
    scope: str,
) -> str:
    """Build one scoped evidence-contract review prompt."""
    if scope not in SCOPED_REVIEW_CONTRACTS:
        valid = ", ".join(sorted(SCOPED_REVIEW_CONTRACTS))
        raise ValueError(f"unknown review scope {scope!r}; valid scopes: {valid}")
    parts = [
        "## Scoped Review Contract",
        SCOPED_REVIEW_CONTRACTS[scope],
        "",
        "## Required Output Schema",
        CONTRACT_SCHEMA,
        "",
        "## Reducer Enforcement",
        "- Findings without concrete evidence will be rejected by the reducer.",
        "- Repeated unsupported claims do not become consensus.",
        "- Only accepted, evidence-backed findings become code-runner handoff items.",
        "- If evidence is missing, use missing_evidence or unsupported_or_rejected_concerns instead of fabricating a finding.",
        "",
        "## Project Context",
        context,
    ]
    if focus:
        parts.extend(["", "## Additional Focus", focus])
    parts.append("")
    parts.append("## Files to Review")
    for filepath, content in files.items():
        parts.append(f"### `{filepath}`\n\n```\n{content}\n```")
    return "\n".join(parts)


async def send_scoped_review(
    *,
    files: dict[str, str],
    context: str,
    focus: str,
    scope: str,
    model: str = DEFAULT_MODEL,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Send one scoped evidence-contract review through scillm SSE."""
    prompt = build_scoped_review_prompt(files=files, context=context, focus=focus, scope=scope)
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    request_timeout = timeout or float(os.environ.get("REVIEW_CODE_SCILLM_TIMEOUT_SEC", "300"))
    system_prompt = (
        "You are a read-only scoped code reviewer. Follow the scoped contract exactly. "
        "Return strict JSON only with the required schema."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    payload = _build_payload(
        model=model,
        messages=messages,
        prompt_sha256=prompt_sha256,
        request_timeout=request_timeout,
    )
    payload["scillm_metadata"] = {
        **payload.get("scillm_metadata", {}),
        "review_scope": scope,
    }
    try:
        result = await _send_review_streaming(payload=payload, model=model, timeout=request_timeout)
        if not result["ok"]:
            result.update({"scope": scope, "prompt_sha256": prompt_sha256})
            return result
        data = result.get("raw_response") or {}
        served_model = result.get("model", model)
        if payload["require_exact_model"] and served_model != model:
            error = _json_error(
                f"served_model_mismatch: requested={model}, served={served_model}",
                model=model,
                data=data,
            )
            error.update({"scope": scope, "prompt_sha256": prompt_sha256})
            return error
        try:
            receipt = validate_contract_receipt(_extract_review_object(result["content"]), scope)
        except (json.JSONDecodeError, ValueError) as exc:
            error = _json_error(str(exc), model=model, data=data)
            error.update({
                "scope": scope,
                "prompt_sha256": prompt_sha256,
                "raw_review_content": result["content"],
            })
            return error
        receipt["_review_proof"] = {
            "prompt_sha256": prompt_sha256,
            "model_requested": model,
            "model_served": served_model,
            "exact_model_required": payload["require_exact_model"],
            "reasoning_effort": payload.get("reasoning_effort"),
            "raw_response": data,
            "files_reviewed": list(files.keys()),
        }
        return {
            "scope": scope,
            "content": json.dumps(receipt, indent=2, sort_keys=True),
            "receipt": receipt,
            "model": served_model,
            "usage": result.get("usage", {}),
            "ok": True,
            "error": None,
            "prompt_sha256": prompt_sha256,
            "raw_response": data,
        }
    except httpx.TimeoutException as exc:
        error = f"scillm timeout after {request_timeout:.0f}s while waiting for {model}; {type(exc).__name__}"
        logger.error("scoped scillm review failed: {}", error)
        return {"scope": scope, "content": "", "model": model, "usage": {}, "ok": False, "error": error}
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        logger.error("scoped scillm review failed: {}", error)
        return {"scope": scope, "content": "", "model": model, "usage": {}, "ok": False, "error": error}


def build_review_prompt(
    files: dict[str, str],
    context: str = "",
    focus: str = "",
) -> str:
    """Build a complete review prompt with all files bundled.

    # RATIONALE (not sent to LLM — for maintainers)
    # Purpose: Generate structured code review findings from source files
    # Consumer: review-code skill → parsed into ReviewFinding objects → displayed or stored
    # Why this matters: Unstructured reviews are unparseable. Severity without vocabulary causes inconsistency.
    # Input: dict of {filepath: content}, optional context and focus strings
    # Output: JSON array of findings with severity, file, line, title, evidence, issue, fix
    # Last reviewed: 2026-04-15

    Args:
        files: {relative_path: file_content} — all files to review
        context: Architectural context, what problem this solves, what it replaces
        focus: Specific areas to focus on (security, correctness, etc.)
    """
    parts = []

    parts.append("## Task\n")
    parts.append("Review the code below and produce a structured review receipt.")
    parts.append("For each finding, identify the file, line number, and provide a concrete fix.\n")

    if context:
        parts.append(f"## Context\n\n{context}\n")

    if focus:
        parts.append(f"## Focus Areas\n\n{focus}\n")

    parts.append("## Review Criteria\n")
    parts.append("Check for these issues in priority order:")
    parts.append("1. **Security**: injection (SQL, command, XSS), path traversal, SSRF, auth bypass, secrets in code")
    parts.append("2. **Correctness**: logic errors, race conditions, null/undefined access, off-by-one, edge cases")
    parts.append("3. **Error handling**: uncaught exceptions, silent failures, missing validation")
    parts.append("4. **Resource leaks**: unclosed files, database connections, spawned processes")
    parts.append("5. **Documentation drift**: code behavior differs from comments/docs/SKILL.md claims")
    parts.append("6. **Maintainability**: dead code, unclear naming, missing type hints on public APIs\n")

    parts.append("## Rejection Criteria (do NOT report these)\n")
    parts.append("- Style preferences (quote style, trailing commas) unless they cause bugs")
    parts.append("- Missing tests (unless the code is untestable)")
    parts.append("- Hypothetical issues that require conditions not present in the code")
    parts.append("- Duplicate findings for the same root cause\n")

    parts.append("## Severity Vocabulary (use exactly these strings)\n")
    parts.append("- `critical`: exploitable without authentication, leads to RCE or data loss")
    parts.append("- `high`: exploitable with low-privilege access, significant security/data impact")
    parts.append("- `medium`: requires specific conditions to exploit, moderate impact")
    parts.append("- `low`: minor issue, defense-in-depth concern, no direct exploit path")
    parts.append("- `info`: observation or suggestion, no security impact\n")

    parts.append("## Files to Review\n")
    for filepath, content in files.items():
        parts.append(f"### `{filepath}`\n\n```\n{content}\n```\n")

    parts.append("## Output Format\n")
    parts.append("Output ONLY one JSON object. No commentary before or after the JSON.")
    parts.append("A bare `[]` is invalid even when you find no blockers.")
    parts.append("Use this exact top-level shape:\n")
    parts.append("```json")
    parts.append('{')
    parts.append('  "verdict": "satisfied",')
    parts.append('  "blocking_findings": [],')
    parts.append('  "non_blocking_findings": [],')
    parts.append('  "patch_suggestions": [],')
    parts.append('  "tests_to_run": [],')
    parts.append('  "do_not_do": [],')
    parts.append('  "reviewed_scope": {')
    parts.append('    "scope_summary": "what files and behavior you actually reviewed"')
    parts.append('  },')
    parts.append('  "rationale": "Explain why this verdict follows from the reviewed code. If there are no findings, explain the concrete invariants you checked and why they are satisfied."')
    parts.append('}')
    parts.append("```\n")

    parts.append("If the code has no findings, return the JSON object above with `verdict: \"satisfied\"`, empty findings arrays, and a concrete rationale.")

    return "\n".join(parts)
