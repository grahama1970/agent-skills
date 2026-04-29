"""Deep-review prompt, artifact, and verifier support for ask."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scillm_runtime import CITATION_SCHEMA_VERSION, CODE_REVIEW_CITATION_KINDS, normalize_citations, render_citations_markdown, validate_citations


ALLOWED_VERDICTS = {"SAFE", "SAFE_WITH_CONDITIONS", "NOT_SAFE", "INSUFFICIENT_EVIDENCE"}
ALLOWED_SECTION_STATUSES = {"verified", "issues_found", "none_found", "not_assessed"}
ALLOWED_ARTIFACT_PREFIXES = (".ask_artifacts/", "reviews/")
DEEP_REVIEW_SCHEMA_VERSION = "1.0"
DEEP_REVIEW_SECTION_NAMES = (
    "target_reconstruction",
    "architecture_boundaries",
    "fail_closed_behavior",
    "production_failure_modes",
    "evidence_auditability",
    "deterministic_checks",
    "test_proof",
    "complexity_removal",
    "security_data_risk",
)


def infer_deep_review(question: str) -> bool:
    """Return True when natural language clearly asks for a deep review."""
    normalized = question.lower()
    triggers = (
        "deep review",
        "web gpt",
        "heavy reasoning review",
        "comprehensive review",
        "safe to proceed",
        "safe-to-proceed",
        "production readiness",
    )
    return any(trigger in normalized for trigger in triggers)


def build_deep_review_request(
    *,
    question: str,
    explicit_target: str | None,
    profile: str,
    reviewers: int,
    focus: str | None,
    fallback_policy: str,
    dogpile_mode: str,
    output_root: str,
    model: str | None,
    reasoning: str,
    backend: str,
) -> dict[str, Any]:
    """Build a deterministic request object for the review wrapper."""
    target = resolve_deep_review_target(question, explicit_target)
    return {
        "mode": "deep_review",
        "schema_version": DEEP_REVIEW_SCHEMA_VERSION,
        "original_question": question,
        "target": target,
        "profile": profile,
        "reviewers": reviewers,
        "focus": focus or "",
        "fallback_policy": fallback_policy,
        "dogpile_mode": dogpile_mode,
        "output_root": output_root,
        "requested_model": model or "",
        "requested_reasoning": reasoning,
        "requested_backend": backend,
        "git_before": capture_git_status(),
    }


def resolve_deep_review_target(question: str, explicit_target: str | None = None) -> dict[str, Any]:
    """Resolve the review target without inventing repo scope."""
    if explicit_target and explicit_target.strip():
        return {"status": "explicit", "target": explicit_target.strip(), "requires_target": False}
    normalized = question.lower().strip()
    vague = (
        normalized in {"safe to proceed?", "safe to proceed", "is this safe?", "is this safe"}
        or "safe to proceed" in normalized
    )
    if vague:
        return {
            "status": "missing",
            "target": "",
            "requires_target": True,
            "message": "Deep review needs an explicit target: paths, branch diff, plan, manifest, or artifact.",
        }
    return {"status": "question", "target": question.strip(), "requires_target": False}


def build_deep_review_prompt(result: dict[str, Any], request: dict[str, Any]) -> str:
    """Build the pass-based prompt sent to the oracle runner."""
    target = request["target"]
    resolved_target = target.get("target") or "[missing explicit target]"
    inspected_context = _summarize_context_items(result.get("items", []))
    return f"""You are performing a Web-GPT-heavy-reasoning-equivalent deep review.

This is not a terse PR review and not an implementation task. Do not edit files.
Treat memory recall as context, not evidence. Prefer inspected files, diffs, tests,
artifacts, command output, or explicit user-provided target material as evidence.

Target:
{resolved_target}

User question:
{request["original_question"]}

Requested profile:
- profile: {request["profile"]}
- reviewers: {request["reviewers"]}
- focus: {request["focus"] or "architecture,boundaries,fail-closed,tests,auditability,complexity"}
- dogpile: {request["dogpile_mode"]}

Retrieved context:
{inspected_context}

Required passes:
1. Reconstruct the target and intended architecture.
2. Identify responsibility boundaries and invariants.
3. Check fail-closed behavior for malformed, empty, partial, stale, and failed outputs.
4. Search production failure modes: timeout, retry, concurrency, idempotency, stale cache, partial run.
5. Assess evidence and auditability.
6. Identify deterministic checks that should replace LLM judgment.
7. Assess whether tests prove the intended guarantees.
8. Identify complexity to remove.
9. Review command execution, write permissions, artifact persistence, prompt injection, and memory pollution.
10. Synthesize a verdict without introducing unsupported new claims.

Every major issue must include severity, evidence, evidence_citations, impact, fix, and verification.
Structured citations are required for review safety claims. Memory may guide context but
must not be used as code/review safety evidence.
Final verdict must be SAFE, SAFE_WITH_CONDITIONS, NOT_SAFE, or INSUFFICIENT_EVIDENCE.

Return a comprehensive markdown review. End with one fenced JSON block matching this shape:
```json
{{
  "verdict": "SAFE_WITH_CONDITIONS",
  "target_reviewed": "{_json_escape(resolved_target)}",
  "files_inspected": [],
  "files_not_inspected_but_relevant": [],
  "evidence_citations": [
    {{"source_id": "file path, diff id, command id, artifact id, or explicit target id", "source_kind": "file | diff | command_output | runtime_artifact | target_bundle", "quote_or_summary": "quoted or summarized support", "supports": "verdict"}}
  ],
  "sections": {{
    "target_reconstruction": {{"status": "verified", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "architecture_boundaries": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "fail_closed_behavior": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "production_failure_modes": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "evidence_auditability": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "deterministic_checks": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "test_proof": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "complexity_removal": {{"status": "none_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}},
    "security_data_risk": {{"status": "issues_found", "summary": "", "evidence_examined": [], "evidence_citations": [], "findings": []}}
  }},
  "blocking_issues": [],
  "significant_risks": [],
  "missing_deterministic_checks": [],
  "test_gaps": [],
  "read_only_claim": true,
  "confidence": "low"
}}
```
"""


def finalize_deep_review_result(result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Attach verifier metadata and write review.md/review.json artifacts."""
    output_dir = _next_output_dir(Path(request["output_root"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed = extract_review_json(str(result.get("answer", ""))) or {}
    review_json = normalise_review_json(parsed, result, request)
    review_json["execution"]["git_after"] = capture_git_status()
    review_json["execution"]["unexpected_file_changes"] = unexpected_git_changes(
        request.get("git_before", []),
        review_json["execution"]["git_after"],
    )
    verification = verify_review_json(review_json)
    review_json["verifier"] = verification
    review_json["artifact_paths"] = {
        "review_md": str(output_dir / "review.md"),
        "review_json": str(output_dir / "review.json"),
    }
    review_md = render_review_markdown(result, review_json, request)
    (output_dir / "review.md").write_text(review_md, encoding="utf-8")
    (output_dir / "review.json").write_text(json.dumps(review_json, indent=2, sort_keys=True), encoding="utf-8")
    result["deep_review"] = {
        "verdict": review_json["verdict"],
        "verifier_status": verification["status"],
        "verifier_failures": verification["failures"],
        "artifact_paths": review_json["artifact_paths"],
        "target": review_json["target_reviewed"],
        "profile": request["profile"],
    }
    return review_json


def extract_review_json(answer: str) -> dict[str, Any] | None:
    """Extract the last fenced JSON block from a markdown review."""
    matches = re.findall(r"```json\s*(\{.*?\})\s*```", answer, flags=re.DOTALL)
    for candidate in reversed(matches):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def normalise_review_json(parsed: dict[str, Any], result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Normalize model output into the machine-checkable deep-review schema."""
    target = request["target"]
    sections = parsed.get("sections") if isinstance(parsed.get("sections"), dict) else {}
    normalized_sections = {
        name: _normalize_section(sections.get(name) if isinstance(sections.get(name), dict) else None)
        for name in DEEP_REVIEW_SECTION_NAMES
    }
    verdict = str(parsed.get("verdict") or "INSUFFICIENT_EVIDENCE").upper()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "INSUFFICIENT_EVIDENCE"
    return {
        "mode": "deep_review",
        "schema_version": DEEP_REVIEW_SCHEMA_VERSION,
        "citation_schema_version": CITATION_SCHEMA_VERSION,
        "verdict": verdict,
        "target_reviewed": parsed.get("target_reviewed") or target.get("target") or request["original_question"],
        "target_resolution": target,
        "files_inspected": _list_value(parsed.get("files_inspected")),
        "files_not_inspected_but_relevant": _list_value(parsed.get("files_not_inspected_but_relevant")),
        "evidence_citations": normalize_citations(parsed.get("evidence_citations"), supports="verdict"),
        "sections": normalized_sections,
        "blocking_issues": _list_value(parsed.get("blocking_issues")),
        "significant_risks": _list_value(parsed.get("significant_risks")),
        "missing_deterministic_checks": _list_value(parsed.get("missing_deterministic_checks")),
        "test_gaps": _list_value(parsed.get("test_gaps")),
        "read_only_claim": bool(parsed.get("read_only_claim", True)),
        "confidence": parsed.get("confidence", "low"),
        "execution": {
            "requested_model": request["requested_model"],
            "requested_reasoning": request["requested_reasoning"],
            "requested_backend": request["requested_backend"],
            "actual_model": result.get("oracle", {}).get("model_served") or result.get("oracle", {}).get("model", ""),
            "actual_reasoning": result.get("oracle", {}).get("reasoning_effort", ""),
            "actual_backend": result.get("oracle", {}).get("backend", ""),
            "capability_degraded": _capability_degraded(result, request),
            "git_before": request.get("git_before", []),
        },
    }


def verify_review_json(review_json: dict[str, Any]) -> dict[str, Any]:
    """Deterministically reject shallow or incomplete deep-review artifacts."""
    failures: list[str] = []
    if review_json.get("verdict") not in ALLOWED_VERDICTS:
        failures.append("invalid verdict")
    if not review_json.get("target_reviewed"):
        failures.append("missing target_reviewed")
    if not review_json.get("read_only_claim"):
        failures.append("read_only_claim must be true")
    if review_json.get("execution", {}).get("unexpected_file_changes"):
        failures.append("unexpected file changes detected")
    if review_json.get("verdict") in {"SAFE", "SAFE_WITH_CONDITIONS"} and not review_json.get("files_inspected"):
        failures.append("safe verdict requires files_inspected evidence")
    if review_json.get("verdict") in {"SAFE", "SAFE_WITH_CONDITIONS"}:
        failures.extend(validate_citations(
            "deep_review evidence_citations",
            normalize_citations(review_json.get("evidence_citations"), supports="verdict"),
            allowed_source_kinds=CODE_REVIEW_CITATION_KINDS,
            require_any=True,
        ))
    sections = review_json.get("sections", {})
    for name in DEEP_REVIEW_SECTION_NAMES:
        section = sections.get(name)
        if not isinstance(section, dict):
            failures.append(f"missing section: {name}")
            continue
        status = section.get("status")
        if status not in ALLOWED_SECTION_STATUSES:
            failures.append(f"{name}: invalid status")
        if status == "not_assessed":
            failures.append(f"{name}: not assessed")
        if status == "none_found" and not section.get("evidence_examined"):
            failures.append(f"{name}: none_found requires evidence")
        if status in {"verified", "issues_found", "none_found"}:
            failures.extend(validate_citations(
                f"{name}: evidence_citations",
                normalize_citations(section.get("evidence_citations"), supports=name),
                allowed_source_kinds=CODE_REVIEW_CITATION_KINDS,
                require_any=status != "issues_found" or not section.get("findings"),
            ))
        if len(str(section.get("summary", "")).strip()) < 20:
            failures.append(f"{name}: summary too shallow")
        for finding in section.get("findings", []):
            if isinstance(finding, dict):
                _verify_finding(name, finding, failures)
    for collection in ("blocking_issues", "significant_risks"):
        for finding in review_json.get(collection, []):
            if isinstance(finding, dict):
                _verify_finding(collection, finding, failures)
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def render_review_markdown(result: dict[str, Any], review_json: dict[str, Any], request: dict[str, Any]) -> str:
    """Render a human-readable review artifact with deterministic metadata."""
    header = [
        "# ask Deep Review",
        "",
        f"- Verdict: `{review_json['verdict']}`",
        f"- Verifier: `{review_json['verifier']['status']}`",
        f"- Target: `{review_json['target_reviewed']}`",
        f"- Profile: `{request['profile']}`",
        f"- Requested model: `{request['requested_model']}`",
        f"- Requested reasoning: `{request['requested_reasoning']}`",
        f"- Citation schema: `{review_json.get('citation_schema_version', CITATION_SCHEMA_VERSION)}`",
        "",
        "## Citations",
        "",
        render_citations_markdown(review_json.get("evidence_citations", [])),
        "",
        "## Review",
        "",
    ]
    return "\n".join(header) + str(result.get("answer", "")).strip() + "\n"


def capture_git_status(cwd: str | Path | None = None) -> list[str]:
    """Capture git status without raising when not in a repository."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def unexpected_git_changes(before: list[str], after: list[str]) -> list[str]:
    """Return new dirty paths outside allowed artifact prefixes."""
    before_set = set(before)
    unexpected: list[str] = []
    for line in after:
        if line in before_set:
            continue
        path = _porcelain_path(line)
        if path and not path.startswith(ALLOWED_ARTIFACT_PREFIXES):
            unexpected.append(line)
    return unexpected


def _normalize_section(section: dict[str, Any] | None) -> dict[str, Any]:
    if not section:
        return {"status": "not_assessed", "summary": "", "evidence_examined": [], "findings": []}
    status = section.get("status", "not_assessed")
    if status not in ALLOWED_SECTION_STATUSES:
        status = "not_assessed"
    return {
        "status": status,
        "summary": str(section.get("summary", "")),
        "evidence_examined": _list_value(section.get("evidence_examined")),
        "evidence_citations": normalize_citations(section.get("evidence_citations"), supports="section"),
        "findings": [
            _normalize_finding(finding)
            for finding in _list_value(section.get("findings"))
            if isinstance(finding, dict)
        ],
    }


def _verify_finding(prefix: str, finding: dict[str, Any], failures: list[str]) -> None:
    required = ("severity", "evidence", "impact", "fix", "verification")
    for field in required:
        if not str(finding.get(field, "")).strip():
            failures.append(f"{prefix}: finding missing {field}")
    failures.extend(validate_citations(
        f"{prefix}: finding evidence_citations",
        normalize_citations(finding.get("evidence_citations"), supports="finding"),
        allowed_source_kinds=CODE_REVIEW_CITATION_KINDS,
        require_any=True,
    ))


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(finding)
    normalized["evidence_citations"] = normalize_citations(finding.get("evidence_citations"), supports="finding")
    return normalized


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _summarize_context_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- No memory items were retrieved."
    lines = []
    for index, item in enumerate(items[:5], 1):
        problem = str(item.get("problem") or item.get("text") or "")[:200]
        solution = str(item.get("solution") or "")[:400]
        lines.append(f"{index}. {problem}\n   {solution}")
    return "\n".join(lines)


def _next_output_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = root / stamp
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = root / f"{stamp}-{suffix}"
    return candidate


def _porcelain_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.strip()


def _capability_degraded(result: dict[str, Any], request: dict[str, Any]) -> bool:
    oracle = result.get("oracle", {})
    actual_model = oracle.get("model_served") or oracle.get("model") or ""
    requested_model = request.get("requested_model") or ""
    actual_reasoning = oracle.get("reasoning_effort") or ""
    requested_reasoning = request.get("requested_reasoning") or ""
    if requested_model and actual_model and requested_model != actual_model:
        return True
    if requested_reasoning and actual_reasoning and requested_reasoning != actual_reasoning:
        return True
    return False


def _json_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
