"""Deep-review prompt, artifact, and verifier support for ask."""

from __future__ import annotations

import json
import hashlib
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scillm_runtime import CITATION_SCHEMA_VERSION, CODE_REVIEW_CITATION_KINDS, normalize_citations, render_citations_markdown, validate_citations


ALLOWED_VERDICTS = {"SAFE", "SAFE_WITH_CONDITIONS", "NOT_SAFE", "INSUFFICIENT_EVIDENCE"}
ALLOWED_SECTION_STATUSES = {"verified", "issues_found", "none_found", "not_assessed"}
ALLOWED_ARTIFACT_PREFIXES = (".ask_artifacts/", "reviews/")
DEEP_REVIEW_SCHEMA_VERSION = "1.0"
MAX_TARGET_FILE_CHARS = 120_000
MAX_TARGET_BUNDLE_CHARS = 240_000
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
        target = explicit_target.strip()
        return {
            "status": "explicit",
            "target": target,
            "requires_target": False,
            "target_bundle": build_target_bundle(target),
        }
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
    return {"status": "question", "target": question.strip(), "requires_target": False, "target_bundle": build_target_bundle("")}


def build_target_bundle(target: str) -> dict[str, Any]:
    """Build bounded, auditable target material for the deep-review prompt."""
    entries: list[dict[str, Any]] = []
    remaining = MAX_TARGET_BUNDLE_CHARS
    tokens = _target_tokens(target)
    for index, token in enumerate(tokens, 1):
        entry, remaining = _target_entry(index, token, remaining)
        entries.append(entry)
    return {
        "schema_version": "ask.deep_review.target_bundle.v1",
        "entries": entries,
        "truncated": any(bool(entry.get("truncated")) for entry in entries),
        "total_entries": len(entries),
    }


def build_deep_review_prompt(result: dict[str, Any], request: dict[str, Any]) -> str:
    """Build the pass-based prompt sent to the oracle runner."""
    target = request["target"]
    resolved_target = target.get("target") or "[missing explicit target]"
    inspected_context = _summarize_context_items(result.get("items", []))
    target_material = _render_target_bundle(target.get("target_bundle") or {})
    return f"""You are performing a Web-GPT-heavy-reasoning-equivalent deep review.

This is not a terse PR review and not an implementation task. Do not edit files.
Treat memory recall as context, not evidence. Prefer inspected files, diffs, tests,
artifacts, command output, or explicit user-provided target material as evidence.

Target:
{resolved_target}

Target material:
{target_material}

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
Use `TARGET.N` source IDs or concrete file paths from Target material for evidence citations.
If Target material is missing, declared-only, unreadable, or truncated, do not return SAFE.
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
    evidence_citations = normalize_citations(parsed.get("evidence_citations"), supports="verdict")
    evidence_index = _build_evidence_citation_index(evidence_citations, target.get("target_bundle") or {})
    normalized_sections = {
        name: _normalize_section(
            sections.get(name) if isinstance(sections.get(name), dict) else None,
            evidence_index=evidence_index,
        )
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
        "target_bundle": target.get("target_bundle") or {},
        "files_inspected": _list_value(parsed.get("files_inspected")),
        "files_not_inspected_but_relevant": _list_value(parsed.get("files_not_inspected_but_relevant")),
        "evidence_citations": evidence_citations,
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
        _verify_deep_review_target_bundle(review_json.get("target_bundle") or {}, failures)
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


def _normalize_section(
    section: dict[str, Any] | None,
    *,
    evidence_index: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not section:
        return {"status": "not_assessed", "summary": "", "evidence_examined": [], "findings": []}
    status = section.get("status", "not_assessed")
    if status not in ALLOWED_SECTION_STATUSES:
        status = "not_assessed"
    evidence_examined = _list_value(section.get("evidence_examined"))
    evidence_citations = _normalize_section_citations(
        section.get("evidence_citations"),
        evidence_examined=evidence_examined,
        evidence_index=evidence_index or {},
    )
    return {
        "status": status,
        "summary": str(section.get("summary", "")),
        "evidence_examined": evidence_examined,
        "evidence_citations": evidence_citations,
        "findings": [
            _normalize_finding(
                finding,
                evidence_index=evidence_index or {},
                fallback_citations=evidence_citations,
            )
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


def _normalize_finding(
    finding: dict[str, Any],
    *,
    evidence_index: dict[str, dict[str, str]] | None = None,
    fallback_citations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    normalized = dict(finding)
    normalized["evidence_citations"] = _normalize_finding_citations(
        finding.get("evidence_citations"),
        finding=finding,
        evidence_index=evidence_index or {},
        fallback_citations=fallback_citations or [],
    )
    return normalized


def _normalize_finding_citations(
    raw_citations: Any,
    *,
    finding: dict[str, Any],
    evidence_index: dict[str, dict[str, str]],
    fallback_citations: list[dict[str, str]],
) -> list[dict[str, str]]:
    citations = normalize_citations(raw_citations, supports="finding")
    repaired: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        repaired_citation = _repair_finding_citation(citation, evidence_index)
        if not repaired_citation.get("source_id") or not repaired_citation.get("source_kind"):
            continue
        key = (repaired_citation.get("source_id", ""), repaired_citation.get("quote_or_summary", ""))
        if key not in seen:
            repaired.append(repaired_citation)
            seen.add(key)
    if repaired:
        return repaired
    for field in ("evidence", "verification", "impact", "fix"):
        citation = _citation_from_evidence_value(
            str(finding.get(field) or ""),
            evidence_index,
            supports="finding",
        )
        if citation:
            key = (citation.get("source_id", ""), citation.get("quote_or_summary", ""))
            if key not in seen:
                repaired.append(citation)
                seen.add(key)
    if repaired:
        return repaired
    if fallback_citations and str(finding.get("evidence", "")).strip():
        fallback_repaired: list[dict[str, str]] = []
        for fallback_citation in fallback_citations:
            if not fallback_citation.get("source_id") or not fallback_citation.get("source_kind"):
                continue
            citation = dict(fallback_citation)
            citation["supports"] = "finding"
            citation["quote_or_summary"] = str(finding.get("evidence"))
            key = (citation.get("source_id", ""), citation.get("quote_or_summary", ""))
            if key not in seen:
                fallback_repaired.append(citation)
                seen.add(key)
        if fallback_repaired:
            return fallback_repaired
    return []


def _repair_finding_citation(
    citation: dict[str, str],
    evidence_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    if citation.get("source_id") and citation.get("source_kind"):
        repaired = dict(citation)
        repaired["supports"] = "finding"
        return repaired
    match = _citation_from_evidence_value(
        citation.get("quote_or_summary", ""),
        evidence_index,
        supports="finding",
    )
    if not match:
        return citation
    repaired = dict(citation)
    repaired["source_id"] = match["source_id"]
    repaired["source_kind"] = match["source_kind"]
    repaired["supports"] = "finding"
    if not repaired.get("quote_or_summary"):
        repaired["quote_or_summary"] = match.get("quote_or_summary", match["source_id"])
    return repaired


def _normalize_section_citations(
    raw_citations: Any,
    *,
    evidence_examined: list[Any],
    evidence_index: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    citations = normalize_citations(raw_citations, supports="section")
    repaired: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        repaired_citation = _repair_section_citation(citation, evidence_index)
        key = (repaired_citation.get("source_id", ""), repaired_citation.get("quote_or_summary", ""))
        if key not in seen:
            repaired.append(repaired_citation)
            seen.add(key)
    if repaired:
        return repaired
    for value in evidence_examined:
        citation = _citation_from_evidence_value(str(value), evidence_index)
        if citation:
            key = (citation.get("source_id", ""), citation.get("quote_or_summary", ""))
            if key not in seen:
                repaired.append(citation)
                seen.add(key)
    return repaired


def _repair_section_citation(
    citation: dict[str, str],
    evidence_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    if citation.get("source_id") and citation.get("source_kind"):
        return citation
    match = _citation_from_evidence_value(citation.get("quote_or_summary", ""), evidence_index)
    if not match:
        return citation
    repaired = dict(citation)
    repaired["source_id"] = match["source_id"]
    repaired["source_kind"] = match["source_kind"]
    if not repaired.get("quote_or_summary"):
        repaired["quote_or_summary"] = match.get("quote_or_summary", match["source_id"])
    return repaired


def _citation_from_evidence_value(
    value: str,
    evidence_index: dict[str, dict[str, str]],
    *,
    supports: str = "section",
) -> dict[str, str] | None:
    literal = _citation_from_literal_source(value, supports=supports)
    if literal:
        return literal
    for alias in _evidence_aliases(value):
        citation = evidence_index.get(alias)
        if citation:
            return {
                "source_id": citation["source_id"],
                "source_kind": citation["source_kind"],
                "quote_or_summary": value or citation.get("quote_or_summary", citation["source_id"]),
                "supports": supports,
            }
    return None


def _citation_from_literal_source(value: str, *, supports: str) -> dict[str, str] | None:
    stripped = value.strip()
    if not stripped:
        return None
    source_id = _literal_source_id(stripped)
    if not source_id:
        return None
    return {
        "source_id": source_id,
        "source_kind": _source_kind_for_literal_source(source_id),
        "quote_or_summary": stripped,
        "supports": supports,
    }


def _build_evidence_citation_index(
    evidence_citations: list[dict[str, str]],
    target_bundle: dict[str, Any],
) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for citation in evidence_citations:
        source_id = citation.get("source_id", "")
        source_kind = citation.get("source_kind", "")
        if not source_id or not source_kind:
            continue
        entry = {
            "source_id": source_id,
            "source_kind": source_kind,
            "quote_or_summary": citation.get("quote_or_summary", ""),
        }
        for alias in _evidence_aliases(source_id):
            index.setdefault(alias, entry)
        for alias in _evidence_aliases(citation.get("quote_or_summary", "")):
            index.setdefault(alias, entry)
    target_entries = [entry for entry in _list_value(target_bundle.get("entries")) if isinstance(entry, dict)]
    for entry in target_entries:
        source_id = str(entry.get("source_id") or "")
        if not source_id:
            continue
        citation = {
            "source_id": source_id,
            "source_kind": "target_bundle",
            "quote_or_summary": str(entry.get("target") or entry.get("resolved_path") or source_id),
        }
        for field in ("source_id", "target", "resolved_path"):
            for alias in _evidence_aliases(str(entry.get(field) or "")):
                index.setdefault(alias, citation)
        if len(target_entries) == 1:
            for alias in ("target", "target material", "target bundle", "review target", "seed payload"):
                index.setdefault(alias, citation)
    return index


def _evidence_aliases(value: str) -> set[str]:
    stripped = value.strip()
    if not stripped:
        return set()
    aliases = {stripped}
    for token in _source_tokens(stripped):
        aliases.add(token)
        path = Path(_strip_line_suffix(token))
        aliases.add(str(path))
        if path.name:
            aliases.add(path.name)
    path = Path(_strip_line_suffix(stripped))
    if path.name:
        aliases.add(path.name)
    return aliases


def _literal_source_id(value: str) -> str:
    if _looks_like_target_source(value):
        return value
    tokens = _source_tokens(value)
    if len(tokens) == 1 and tokens[0] == value:
        return value
    return ""


def _source_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"\bTARGET\.\d+\b", value):
        tokens.append(match.group(0))
    for match in re.finditer(
        r"(?:/|\.{1,2}/|~\/)[^\s,;`'\"<>)]*(?:\.[A-Za-z0-9_+-]+)(?::\d+(?:-\d+)?)?",
        value,
    ):
        tokens.append(match.group(0))
    return tokens


def _strip_line_suffix(value: str) -> str:
    return re.sub(r":\d+(?:-\d+)?$", "", value)


def _looks_like_target_source(value: str) -> bool:
    return bool(re.fullmatch(r"TARGET\.\d+", value))


def _source_kind_for_literal_source(source_id: str) -> str:
    if _looks_like_target_source(source_id):
        return "target_bundle"
    if source_id.startswith("DIFF."):
        return "diff"
    if source_id.startswith("COMMAND."):
        return "command_output"
    if source_id.startswith("ARTIFACT."):
        return "runtime_artifact"
    stripped = _strip_line_suffix(source_id)
    if "/.ask_artifacts/" in stripped or stripped.endswith(".json"):
        return "runtime_artifact"
    return "file"


def _verify_deep_review_target_bundle(target_bundle: dict[str, Any], failures: list[str]) -> None:
    entries = [entry for entry in _list_value(target_bundle.get("entries")) if isinstance(entry, dict)]
    if not entries:
        failures.append("safe verdict requires target material")
        return
    if target_bundle.get("truncated"):
        failures.append("safe verdict requires untruncated target material")
    concrete = [entry for entry in entries if entry.get("kind") == "file" and entry.get("content")]
    if not concrete:
        failures.append("safe verdict requires inspected file or artifact content")
    for entry in entries:
        if entry.get("kind") in {"declared", "missing", "directory", "unreadable"}:
            failures.append(f"safe verdict cannot rely on {entry.get('kind')} target: {entry.get('target')}")


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


def _target_tokens(target: str) -> list[str]:
    if not target.strip():
        return []
    try:
        tokens = shlex.split(target)
    except ValueError:
        tokens = target.split()
    return tokens or [target]


def _target_entry(index: int, token: str, remaining: int) -> tuple[dict[str, Any], int]:
    path = Path(token).expanduser()
    resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    source_id = f"TARGET.{index}"
    base = {
        "source_id": source_id,
        "target": token,
        "resolved_path": str(resolved),
    }
    if not resolved.exists():
        return {**base, "kind": "missing", "content": "", "truncated": False}, remaining
    if resolved.is_dir():
        return {**base, "kind": "directory", "content": "", "truncated": False}, remaining
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        return {**base, "kind": "unreadable", "error": str(exc), "content": "", "truncated": False}, remaining
    digest = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8", errors="replace")
    allowed = max(0, min(MAX_TARGET_FILE_CHARS, remaining))
    truncated = len(text) > allowed
    content = text[:allowed]
    remaining = max(0, remaining - len(content))
    return {
        **base,
        "kind": "file",
        "bytes": len(data),
        "sha256": digest,
        "content_chars": len(content),
        "truncated": truncated,
        "content": content,
    }, remaining


def _render_target_bundle(target_bundle: dict[str, Any]) -> str:
    entries = [entry for entry in _list_value(target_bundle.get("entries")) if isinstance(entry, dict)]
    if not entries:
        return "- No concrete target material was resolved. Treat this as insufficient evidence."
    rendered: list[str] = []
    for entry in entries:
        source_id = entry.get("source_id", "TARGET.?")
        kind = entry.get("kind", "unknown")
        rendered.append(
            f"[{source_id}] kind={kind} target={entry.get('target', '')} "
            f"resolved_path={entry.get('resolved_path', '')} "
            f"sha256={entry.get('sha256', '')} bytes={entry.get('bytes', '')} "
            f"truncated={entry.get('truncated', False)}"
        )
        content = str(entry.get("content") or "")
        if content:
            rendered.append("```text")
            rendered.append(content)
            rendered.append("```")
        elif entry.get("error"):
            rendered.append(f"Error: {entry['error']}")
    return "\n".join(rendered)


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
