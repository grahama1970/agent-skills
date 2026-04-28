"""Bounded, read-only parallel review support for /ask."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .deep_review import ALLOWED_VERDICTS, capture_git_status, unexpected_git_changes
from .reviewer_specs import select_reviewer_angles


PARALLEL_REVIEW_SCHEMA_VERSION = "ask.parallel_review.v1"
CODE_RUNNER_TASK_SCHEMA_VERSION = "ask.code_runner_task.v1"
MAX_REVIEWERS = 7
DEFAULT_REVIEWERS = 3
MAX_TARGET_CHARS = 200_000
SAFE_VERDICTS = {"SAFE", "SAFE_WITH_CONDITIONS"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|private[_-]?key)(\s*[=:]\s*)([^\s\"']+)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


class ParallelReviewError(RuntimeError):
    """Raised when a parallel review cannot be completed safely."""


class ScillmReviewerAdapter:
    """OpenAI-compatible /scillm reviewer adapter."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "text",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("SCILLM_BASE_URL") or "http://localhost:4001").rstrip("/")
        self.api_key = api_key or os.environ.get("SCILLM_API_KEY") or "sk-dev-proxy-123"
        self.model = os.environ.get("ASK_PARALLEL_REVIEW_MODEL") or model or "text"
        self.timeout = timeout

    async def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = build_reviewer_prompt(payload)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Caller-Skill": "ask",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a read-only code reviewer. Return one JSON object only. "
                                "Do not claim files were inspected unless the target bundle contains them."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return parse_reviewer_output(content, payload)


def build_parallel_review_plan(
    *,
    question: str,
    target: str,
    reviewers: int = DEFAULT_REVIEWERS,
    personas: str | None = None,
    focus: str | None = None,
    runner: str = "scillm",
    read_only: bool = True,
    model: str | None = None,
    dag_mode: str = "hybrid",
) -> dict[str, Any]:
    persona_specs = _parse_reviewer_personas(personas)
    reviewer_count = max(1, min(max(reviewers, len(persona_specs)), MAX_REVIEWERS))
    specs = persona_specs or select_reviewer_angles(question, focus=focus, count=reviewer_count)
    reviewer_payloads = []
    for index, spec in enumerate(specs[:reviewer_count], 1):
        reviewer_payloads.append(
            {
                "id": f"reviewer-{index}",
                "name": str(spec.get("name") or f"reviewer-{index}"),
                "role": str(spec.get("protocol_role") or spec.get("name") or "reviewer"),
                "focus": spec.get("focus", []),
                "prompt": str(spec.get("prompt") or spec.get("scope") or "Review the target."),
                "model": str(spec.get("model") or model or "text"),
                "read_only": read_only,
            }
        )
    return {
        "schema_version": PARALLEL_REVIEW_SCHEMA_VERSION,
        "mode": "parallel_review",
        "question": question,
        "target": target,
        "runner": runner,
        "read_only": read_only,
        "dag_mode": dag_mode,
        "reviewers_requested": reviewers,
        "reviewers": reviewer_payloads,
        "dag": [
            {"id": "target_bundle", "type": "target_bundle", "depends_on": []},
            {"id": "parallel_reviewers", "type": "parallel_group", "depends_on": ["target_bundle"]},
            {"id": "judge", "type": "scillm_call", "depends_on": ["parallel_reviewers"]},
            {"id": "synthesis", "type": "synthesis", "depends_on": ["judge"]},
            {"id": "verifier", "type": "verifier", "depends_on": ["synthesis"]},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run_parallel_review(
    *,
    question: str,
    target: str,
    reviewers: int,
    personas: str | None,
    focus: str | None,
    runner: str,
    read_only: bool,
    model: str | None,
    timeout: float,
    run_state: Any,
    dag_mode: str = "hybrid",
    code_runner_handoff: bool = False,
    implement_with: str | None = None,
    apply_fixes: bool = False,
    code_runner_allowed_files: list[str] | None = None,
    code_runner_dod_commands: list[str] | None = None,
    implementation_non_goals: list[str] | None = None,
    risk_notes: list[str] | None = None,
) -> dict[str, Any]:
    if runner != "scillm":
        raise ParallelReviewError("Only the scillm parallel-review adapter is implemented")
    if not read_only:
        raise ParallelReviewError("Parallel review is read-only; use /code-runner handoff for edits")
    if reviewers > MAX_REVIEWERS:
        raise ParallelReviewError(f"Parallel review supports at most {MAX_REVIEWERS} reviewers")
    if dag_mode not in {"hybrid", "judge-best"}:
        raise ParallelReviewError("Parallel review DAG must be hybrid or judge-best")
    implementation_requested = bool(apply_fixes or implement_with)
    if implement_with and implement_with != "code-runner":
        raise ParallelReviewError("Only --implement-with code-runner is supported")
    if implementation_requested:
        code_runner_handoff = True
    run_dir = Path(getattr(run_state, "run_dir", ""))
    if not run_dir:
        raise ParallelReviewError("Parallel review requires runtime artifacts")
    if implementation_requested and not any(command.strip() for command in (code_runner_dod_commands or [])):
        attention = run_state.needs_attention(
            reason="missing_code_runner_dod",
            question="Explicit implementation intent requires at least one --code-runner-dod-command.",
            safe_default="do_not_invoke_code_runner",
            resume_hint="Run again with --code-runner-dod-command <safe validation command>.",
        )
        return {
            "question": question,
            "scope": "parallel_review",
            "items": [],
            "answer": "Parallel review paused before reviewer fanout because implementation intent lacks an explicit DoD command.",
            "needs_attention": attention,
            "parallel_review": {
                "target": target,
                "verdict": "NEEDS_ATTENTION",
                "verifier_status": "NOT_RUN",
                "verifier_failures": ["missing_code_runner_dod"],
                "findings_count": 0,
                "artifact_paths": {},
                "runner": runner,
                "read_only": read_only,
                "dag_mode": dag_mode,
                "implementation_requested": implementation_requested,
            },
        }
    if code_runner_allowed_files:
        validate_code_runner_allowed_files(code_runner_allowed_files)
    run_state.step_started("parallel_review", target=target, reviewers=reviewers, runner=runner)
    review_dir = run_dir / "parallel_review"
    outputs_dir = review_dir / "reviewer_outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    git_before = capture_git_status()
    target_bundle = build_target_bundle(target)
    target_bundle_path = review_dir / "target_bundle.md"
    target_bundle_path.write_text(target_bundle["markdown"], encoding="utf-8")
    plan = build_parallel_review_plan(
        question=question,
        target=target,
        reviewers=reviewers,
        personas=personas,
        focus=focus,
        runner=runner,
        read_only=read_only,
        model=model,
        dag_mode=dag_mode,
    )
    plan["target_bundle"] = {
        "path": str(target_bundle_path),
        "kind": target_bundle["kind"],
        "entries": target_bundle["entries"],
        "truncated": target_bundle["truncated"],
    }
    plan_path = review_dir / "reviewer_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    adapter = ScillmReviewerAdapter(model=model or "text", timeout=timeout)
    reviewer_outputs = _run_reviewers(adapter, plan, target_bundle["markdown"], timeout, run_state)
    judge_output = _run_judge(adapter, plan, reviewer_outputs, timeout, run_state)
    for output in reviewer_outputs:
        output_path = outputs_dir / f"{safe_artifact_name(output.get('reviewer') or output.get('id') or 'reviewer')}.json"
        output_path.write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        output["artifact_path"] = str(output_path)
    judge_path = review_dir / "judge.json"
    judge_path.write_text(json.dumps(judge_output, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    git_after = capture_git_status()
    verdict = synthesize_parallel_review(
        question=question,
        target=target,
        plan=plan,
        target_bundle=target_bundle,
        reviewer_outputs=reviewer_outputs,
        judge_output=judge_output,
        git_before=git_before,
        git_after=git_after,
    )
    run_state.event("verifier_started", step="parallel_review")
    verifier = verify_parallel_review_bundle(verdict)
    run_state.event("verifier_finished", step="parallel_review", status=verifier["status"], failures=len(verifier["failures"]))
    verdict["verifier"] = verifier
    if verifier["status"] == "FAIL" and verdict["verdict"] in SAFE_VERDICTS:
        verdict["verdict"] = "INSUFFICIENT_EVIDENCE"
    verdict_path = review_dir / "verdict.json"
    synthesis_path = review_dir / "synthesis.md"
    verifier_path = review_dir / "verifier.log"
    handoff_path = review_dir / "code_runner_handoff.md"
    task_path = review_dir / "code_runner_task.json"
    synthesis = render_parallel_review_markdown(verdict)
    synthesis_path.write_text(synthesis, encoding="utf-8")
    verdict["artifact_paths"] = {
        "target_bundle": str(target_bundle_path),
        "reviewer_plan": str(plan_path),
        "reviewer_outputs": str(outputs_dir),
        "judge_json": str(judge_path),
        "synthesis_md": str(synthesis_path),
        "verdict_json": str(verdict_path),
        "verifier_log": str(verifier_path),
    }
    if code_runner_handoff and _has_actionable_findings(verdict) and verifier["status"] == "PASS":
        task = None
        if implementation_requested:
            try:
                task = build_code_runner_task(
                    verdict=verdict,
                    ask_id=str(getattr(run_state, "ask_id", "")),
                    allowed_files=code_runner_allowed_files or [],
                    dod_commands=code_runner_dod_commands or [],
                    non_goals=implementation_non_goals or [],
                    risk_notes=risk_notes or [],
                    implementation_requested=implementation_requested,
                )
            except ParallelReviewError as exc:
                verifier["status"] = "FAIL"
                verifier["failures"].append(f"code_runner_task_invalid: {exc}")
            else:
                task_path.write_text(json.dumps(task, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
                verdict["artifact_paths"]["code_runner_task_json"] = str(task_path)
        handoff_path.write_text(render_code_runner_handoff(verdict, task), encoding="utf-8")
        verdict["artifact_paths"]["code_runner_handoff"] = str(handoff_path)
        run_state.event(
            "code_runner_handoff_prepared",
            step="parallel_review",
            task_id=task["task_id"] if task else None,
            implementation_requested=implementation_requested,
            execution_status=task["execution"]["status"] if task else "handoff_markdown_only",
        )
    verifier_path.write_text("\n".join(verifier["failures"] or ["PASS"]) + "\n", encoding="utf-8")
    verdict_path.write_text(json.dumps(verdict, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    run_state.add_artifacts(verdict["artifact_paths"])
    if verifier["status"] == "FAIL":
        attention = run_state.needs_attention(
            reason="parallel_review_verifier_failed",
            question="Parallel review verifier rejected the generated review artifacts.",
            safe_default="do_not_trust_review",
            resume_hint=f"Inspect {verifier_path} and rerun with a narrower target or stronger reviewer prompt.",
            verifier_failures=verifier["failures"],
            artifact_paths=verdict["artifact_paths"],
        )
        return {
            "question": question,
            "scope": "parallel_review",
            "items": [],
            "answer": synthesis,
            "needs_attention": attention,
            "parallel_review": {
                "target": target,
                "verdict": verdict["verdict"],
                "verifier_status": verifier["status"],
                "verifier_failures": verifier["failures"],
                "findings_count": len(verdict["findings"]),
                "artifact_paths": verdict["artifact_paths"],
                "runner": runner,
                "read_only": read_only,
                "dag_mode": dag_mode,
                "implementation_requested": implementation_requested,
            },
        }
    run_state.step_finished(
        "parallel_review",
        verdict=verdict["verdict"],
        verifier_status=verifier["status"],
        findings_count=len(verdict["findings"]),
    )
    return {
        "question": question,
        "scope": "parallel_review",
        "items": [{"problem": question, "solution": synthesis, "via": "parallel_review"}],
        "answer": synthesis,
        "parallel_review": {
            "target": target,
            "verdict": verdict["verdict"],
            "verifier_status": verifier["status"],
            "verifier_failures": verifier["failures"],
            "findings_count": len(verdict["findings"]),
            "artifact_paths": verdict["artifact_paths"],
            "runner": runner,
            "read_only": read_only,
            "dag_mode": dag_mode,
            "implementation_requested": implementation_requested,
        },
    }


def _run_reviewers(
    adapter: ScillmReviewerAdapter,
    plan: dict[str, Any],
    target_bundle: str,
    timeout: float,
    run_state: Any,
) -> list[dict[str, Any]]:
    reviewer_payloads = []
    for reviewer in plan["reviewers"]:
        reviewer_payloads.append(
            {
                "schema_version": PARALLEL_REVIEW_SCHEMA_VERSION,
                "question": plan["question"],
                "target": plan["target"],
                "target_bundle": target_bundle,
                "reviewer": reviewer,
                "required_output_schema": reviewer_output_schema(),
            }
        )
    return asyncio.run(_run_reviewers_async(adapter, reviewer_payloads, timeout, run_state))


def _run_judge(
    adapter: ScillmReviewerAdapter,
    plan: dict[str, Any],
    reviewer_outputs: list[dict[str, Any]],
    timeout: float,
    run_state: Any,
) -> dict[str, Any]:
    return asyncio.run(_run_judge_async(adapter, plan, reviewer_outputs, timeout, run_state))


async def _run_judge_async(
    adapter: ScillmReviewerAdapter,
    plan: dict[str, Any],
    reviewer_outputs: list[dict[str, Any]],
    timeout: float,
    run_state: Any,
) -> dict[str, Any]:
    prompt = build_judge_prompt(plan, reviewer_outputs)
    payload = {
        "schema_version": PARALLEL_REVIEW_SCHEMA_VERSION,
        "question": plan["question"],
        "target": plan["target"],
        "reviewer": {
            "id": "judge",
            "name": "review-judge",
            "role": "judge",
            "focus": ["evidence-quality", "best-review", "hybrid-synthesis"],
            "prompt": "Judge reviewer output quality and synthesize the best defensible review.",
        },
        "target_bundle": prompt,
        "required_output_schema": {
            "judge": "review-judge",
            "best_reviewer": "name",
            "best_review_reason": "why this review is strongest",
            "hybrid_summary": "combined synthesis using strongest evidence",
            "verdict": "SAFE | SAFE_WITH_CONDITIONS | NOT_SAFE | INSUFFICIENT_EVIDENCE",
            "evidence": [],
            "findings": [],
            "test_gaps": [],
            "read_only_claim": True,
        },
    }
    started = time.monotonic()
    run_state.event("judge_started", step="parallel_review", dag_mode=plan["dag_mode"])
    try:
        output = await asyncio.wait_for(adapter.review(payload), timeout=max(timeout, 1.0))
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        run_state.event("judge_failed", step="parallel_review", elapsed_ms=elapsed_ms, error=str(exc))
        return {
            "reviewer": "review-judge",
            "judge": "review-judge",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "summary": "Judge call failed.",
            "hybrid_summary": "",
            "best_reviewer": "",
            "best_review_reason": "",
            "evidence": [],
            "findings": [],
            "test_gaps": [],
            "read_only_claim": True,
            "status": "failed",
            "error": str(exc),
        }
    elapsed_ms = int((time.monotonic() - started) * 1000)
    output.setdefault("judge", "review-judge")
    output.setdefault("best_reviewer", "")
    output.setdefault("best_review_reason", "")
    output.setdefault("hybrid_summary", output.get("summary", ""))
    output.setdefault("status", "ok")
    run_state.event("judge_finished", step="parallel_review", elapsed_ms=elapsed_ms, verdict=output.get("verdict"))
    return output


async def _run_reviewers_async(
    adapter: ScillmReviewerAdapter,
    reviewer_payloads: list[dict[str, Any]],
    timeout: float,
    run_state: Any,
) -> list[dict[str, Any]]:
    concurrency = min(3, len(reviewer_payloads))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(payload: dict[str, Any]) -> dict[str, Any]:
        reviewer = payload["reviewer"]
        reviewer_name = str(reviewer.get("name") or reviewer.get("id") or "reviewer")
        started = time.monotonic()
        async with semaphore:
            run_state.event("reviewer_started", step="parallel_review", reviewer=reviewer_name)
            try:
                output = await asyncio.wait_for(adapter.review(payload), timeout=max(timeout, 1.0))
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                run_state.event(
                    "reviewer_failed",
                    step="parallel_review",
                    reviewer=reviewer_name,
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                )
                return {
                    "reviewer": reviewer_name,
                    "role": reviewer.get("role", "reviewer"),
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "summary": f"Reviewer call failed: {exc}",
                    "files_inspected": [],
                    "evidence": [],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                    "confidence": "low",
                    "status": "failed",
                    "error": str(exc),
                    "schema_version": PARALLEL_REVIEW_SCHEMA_VERSION,
                }
            elapsed_ms = int((time.monotonic() - started) * 1000)
            output.setdefault("status", "ok")
            run_state.event(
                "reviewer_finished",
                step="parallel_review",
                reviewer=reviewer_name,
                elapsed_ms=elapsed_ms,
                verdict=output.get("verdict"),
            )
            return output

    tasks = [asyncio.create_task(run_one(payload)) for payload in reviewer_payloads]
    outputs = await asyncio.gather(*tasks)
    outputs.sort(key=lambda item: str(item.get("reviewer") or item.get("id") or ""))
    return outputs


def build_judge_prompt(plan: dict[str, Any], reviewer_outputs: list[dict[str, Any]]) -> str:
    if plan["dag_mode"] == "judge-best":
        instruction = (
            "Pick the single strongest reviewer by evidence quality. Preserve that review's "
            "evidence-supported verdict and findings; do not create a merged hybrid finding set."
        )
    else:
        instruction = (
            "Pick the best single reviewer by evidence quality, then create a hybrid summary "
            "that merges only evidence-supported findings across reviewers."
        )
    return f"""Judge the parallel reviewer outputs.

Question:
{plan["question"]}

Target:
{plan["target"]}

DAG mode:
{plan["dag_mode"]}

Reviewer outputs:
{json.dumps(reviewer_outputs, indent=2, sort_keys=True, default=str)}

Return JSON only. {instruction} Do not add claims not present in the reviewer outputs.
"""


def build_target_bundle(target: str, *, review_root: Path | None = None) -> dict[str, Any]:
    target = target.strip()
    root = (review_root or Path.cwd()).resolve()
    if target == "git:diff":
        diff = _git_diff()
        markdown = f"# /ask Parallel Review Target\n\n## Target\n\n`git:diff`\n\n## Diff\n\n```diff\n{diff or '(empty git diff)'}\n```\n"
        return {
            "kind": "git:diff",
            "entries": [
                {
                    "target": target,
                    "kind": "git:diff",
                    "chars": len(diff),
                    "paths": _paths_from_git_diff(diff),
                }
            ],
            "markdown": _truncate(markdown),
            "truncated": len(markdown) > MAX_TARGET_CHARS,
        }
    entries = []
    sections = ["# /ask Parallel Review Target", "", f"## Target Declaration\n\n`{target}`", ""]
    for raw_part in [part.strip() for part in target.split(",") if part.strip()]:
        path = Path(raw_part).expanduser()
        if path.is_file():
            resolved = path.resolve()
            if not _is_relative_to(resolved, root):
                raise ParallelReviewError(f"review target outside allowed root: {raw_part}")
            text = _redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
            try:
                rel_path = str(resolved.relative_to(root))
            except ValueError:
                rel_path = str(resolved)
            entries.append({"target": raw_part, "kind": "file", "path": rel_path, "resolved_path": str(resolved), "chars": len(text)})
            sections.extend([f"## File: `{raw_part}`", "", "```text", text, "```", ""])
        elif path.is_dir():
            resolved = path.resolve()
            if not _is_relative_to(resolved, root):
                raise ParallelReviewError(f"review target outside allowed root: {raw_part}")
            entries.append({"target": raw_part, "kind": "directory", "path": str(resolved.relative_to(root)), "chars": 0})
            sections.extend([f"## Directory: `{raw_part}`", "", "Directory target declared; reviewer must treat listing as not inspected.", ""])
        else:
            entries.append({"target": raw_part, "kind": "declared", "chars": 0})
            sections.extend([f"## Declared Target: `{raw_part}`", "", "Target does not resolve to a local file in this runtime.", ""])
    markdown = "\n".join(sections)
    return {
        "kind": "paths",
        "entries": entries,
        "markdown": _truncate(markdown),
        "truncated": len(markdown) > MAX_TARGET_CHARS,
    }


def build_reviewer_prompt(payload: dict[str, Any]) -> str:
    reviewer = payload["reviewer"]
    return f"""Review target in read-only mode.

Question:
{payload["question"]}

Target:
{payload["target"]}

Reviewer role:
- name: {reviewer["name"]}
- role: {reviewer["role"]}
- focus: {reviewer["focus"]}
- prompt: {reviewer["prompt"]}

Target bundle:
{payload["target_bundle"]}

Return exactly one JSON object matching:
{json.dumps(payload["required_output_schema"], indent=2, sort_keys=True)}

Rules:
- Do not edit files.
- Memory can guide context but is not evidence.
- Findings require evidence from the target bundle.
- If evidence is insufficient, use verdict INSUFFICIENT_EVIDENCE.
"""


def reviewer_output_schema() -> dict[str, Any]:
    return {
        "reviewer": "role/name",
        "verdict": "SAFE | SAFE_WITH_CONDITIONS | NOT_SAFE | INSUFFICIENT_EVIDENCE",
        "summary": "specific review summary",
        "files_inspected": [],
        "evidence": [],
        "findings": [
            {
                "severity": "high | medium | low",
                "title": "finding title",
                "evidence": "specific evidence",
                "impact": "why it matters",
                "fix": "exact fix",
                "verification": "test/check",
            }
        ],
        "test_gaps": [],
        "read_only_claim": True,
        "confidence": "low | medium | high",
    }


def parse_reviewer_output(content: str, payload: dict[str, Any]) -> dict[str, Any]:
    reviewer = payload["reviewer"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"summary": content, "verdict": "INSUFFICIENT_EVIDENCE", "raw_response": content}
    if not isinstance(parsed, dict):
        parsed = {"summary": str(parsed), "verdict": "INSUFFICIENT_EVIDENCE"}
    parsed.setdefault("reviewer", reviewer["name"])
    parsed.setdefault("role", reviewer["role"])
    parsed.setdefault("files_inspected", [])
    parsed.setdefault("evidence", [])
    parsed.setdefault("findings", [])
    parsed.setdefault("test_gaps", [])
    parsed.setdefault("read_only_claim", True)
    parsed.setdefault("confidence", "low")
    parsed["files_inspected"] = [str(item) for item in _list_value(parsed.get("files_inspected")) if item]
    parsed["evidence"] = [str(item) for item in _list_value(parsed.get("evidence")) if item]
    parsed["test_gaps"] = [str(item) for item in _list_value(parsed.get("test_gaps")) if item]
    parsed["findings"] = [item for item in _list_value(parsed.get("findings")) if isinstance(item, dict)]
    verdict = str(parsed.get("verdict") or "INSUFFICIENT_EVIDENCE").upper()
    parsed["verdict"] = verdict if verdict in ALLOWED_VERDICTS else "INSUFFICIENT_EVIDENCE"
    parsed["schema_version"] = PARALLEL_REVIEW_SCHEMA_VERSION
    return parsed


def synthesize_parallel_review(
    *,
    question: str,
    target: str,
    plan: dict[str, Any],
    target_bundle: dict[str, Any],
    reviewer_outputs: list[dict[str, Any]],
    judge_output: dict[str, Any],
    git_before: list[str],
    git_after: list[str],
) -> dict[str, Any]:
    findings = []
    test_gaps = []
    evidence = []
    files_inspected = []
    for output in reviewer_outputs:
        for finding in _list_value(output.get("findings")):
            if isinstance(finding, dict):
                findings.append({"reviewer": output.get("reviewer", ""), **finding})
        test_gaps.extend(str(item) for item in _list_value(output.get("test_gaps")) if item)
        evidence.extend(str(item) for item in _list_value(output.get("evidence")) if item)
        files_inspected.extend(str(item) for item in _list_value(output.get("files_inspected")) if item)
    for finding in _list_value(judge_output.get("findings")):
        if isinstance(finding, dict):
            findings.append({"reviewer": "review-judge", **finding})
    test_gaps.extend(str(item) for item in _list_value(judge_output.get("test_gaps")) if item)
    evidence.extend(str(item) for item in _list_value(judge_output.get("evidence")) if item)
    unexpected_changes = unexpected_git_changes(git_before, git_after)
    verdict = _aggregate_verdict([*reviewer_outputs, judge_output], findings)
    return {
        "schema_version": PARALLEL_REVIEW_SCHEMA_VERSION,
        "mode": "parallel_review",
        "question": question,
        "target_reviewed": target,
        "verdict": verdict,
        "runner": plan["runner"],
        "read_only": plan["read_only"],
        "dag_mode": plan["dag_mode"],
        "target_bundle": {
            "kind": target_bundle["kind"],
            "entries": target_bundle["entries"],
            "truncated": target_bundle["truncated"],
        },
        "reviewers": reviewer_outputs,
        "judge": judge_output,
        "best_reviewer": judge_output.get("best_reviewer", ""),
        "best_review_reason": judge_output.get("best_review_reason", ""),
        "hybrid_summary": judge_output.get("hybrid_summary", ""),
        "files_inspected": sorted(set(files_inspected)),
        "evidence": evidence,
        "findings": findings,
        "test_gaps": sorted(set(test_gaps)),
        "execution": {
            "git_before": git_before,
            "git_after": git_after,
            "unexpected_file_changes": unexpected_changes,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_parallel_review_bundle(verdict: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if verdict.get("schema_version") != PARALLEL_REVIEW_SCHEMA_VERSION:
        failures.append("invalid schema_version")
    if verdict.get("verdict") not in ALLOWED_VERDICTS:
        failures.append("invalid verdict")
    if not verdict.get("target_reviewed"):
        failures.append("missing target_reviewed")
    if not verdict.get("read_only"):
        failures.append("parallel review must be read-only")
    if verdict.get("execution", {}).get("unexpected_file_changes"):
        failures.append("unexpected file changes detected")
    target_bundle = verdict.get("target_bundle")
    concrete_targets = _concrete_target_names(target_bundle if isinstance(target_bundle, dict) else {})
    if verdict.get("verdict") in SAFE_VERDICTS:
        _verify_safe_target_bundle(target_bundle if isinstance(target_bundle, dict) else {}, failures)
    reviewers = verdict.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        failures.append("missing reviewer outputs")
    for output in reviewers or []:
        if not isinstance(output, dict):
            failures.append("reviewer output is not an object")
            continue
        if output.get("verdict") not in ALLOWED_VERDICTS:
            failures.append(f"{output.get('reviewer', 'reviewer')}: invalid verdict")
        if output.get("status") == "failed":
            failures.append(f"{output.get('reviewer', 'reviewer')}: reviewer failed: {output.get('error', '')}")
        if not str(output.get("summary", "")).strip():
            failures.append(f"{output.get('reviewer', 'reviewer')}: missing summary")
        if not output.get("read_only_claim"):
            failures.append(f"{output.get('reviewer', 'reviewer')}: missing read_only_claim")
        if output.get("verdict") in {"SAFE", "SAFE_WITH_CONDITIONS"} and not output.get("evidence"):
            failures.append(f"{output.get('reviewer', 'reviewer')}: safe verdict requires evidence")
        if output.get("verdict") in SAFE_VERDICTS:
            _verify_files_inspected_in_target(
                output.get("reviewer", "reviewer"),
                output.get("files_inspected"),
                concrete_targets,
                failures,
            )
        for finding in _list_value(output.get("findings")):
            if isinstance(finding, dict):
                _verify_parallel_finding(output.get("reviewer", "reviewer"), finding, failures)
    judge = verdict.get("judge")
    if not isinstance(judge, dict):
        failures.append("missing judge output")
    else:
        if judge.get("status") == "failed":
            failures.append(f"judge failed: {judge.get('error', '')}")
        if not str(judge.get("hybrid_summary", "")).strip():
            failures.append("judge missing hybrid_summary")
        if not str(judge.get("best_reviewer", "")).strip():
            failures.append("judge missing best_reviewer")
    if verdict.get("verdict") in {"SAFE", "SAFE_WITH_CONDITIONS"} and not verdict.get("files_inspected"):
        failures.append("safe verdict requires files_inspected")
    if verdict.get("verdict") in SAFE_VERDICTS:
        _verify_files_inspected_in_target("verdict", verdict.get("files_inspected"), concrete_targets, failures)
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def render_parallel_review_markdown(verdict: dict[str, Any]) -> str:
    lines = [
        "# ask Parallel Review",
        "",
        f"- Verdict: `{verdict['verdict']}`",
        f"- Target: `{verdict['target_reviewed']}`",
        f"- Runner: `{verdict['runner']}`",
        f"- Verifier: `{verdict.get('verifier', {}).get('status', 'PENDING')}`",
        f"- Best reviewer: `{verdict.get('best_reviewer', '')}`",
        "",
        "## Judge Synthesis",
        "",
        str(verdict.get("hybrid_summary", "")).strip() or "No judge synthesis.",
        "",
        "## Reviewer Summaries",
        "",
    ]
    for output in verdict.get("reviewers", []):
        lines.extend([
            f"### {output.get('reviewer', 'reviewer')}",
            "",
            f"- Verdict: `{output.get('verdict', 'INSUFFICIENT_EVIDENCE')}`",
            f"- Confidence: `{output.get('confidence', 'low')}`",
            "",
            str(output.get("summary", "")).strip() or "No summary.",
            "",
        ])
    lines.extend(["## Findings", ""])
    if not verdict.get("findings"):
        lines.append("No findings reported.")
    for finding in verdict.get("findings", []):
        lines.extend([
            f"- `{finding.get('severity', 'unknown')}` {finding.get('title', 'Untitled')}",
            f"  - Evidence: {finding.get('evidence', '')}",
            f"  - Impact: {finding.get('impact', '')}",
            f"  - Fix: {finding.get('fix', '')}",
            f"  - Verification: {finding.get('verification', '')}",
        ])
    lines.append("")
    return "\n".join(lines)


def render_code_runner_handoff(verdict: dict[str, Any], task: dict[str, Any] | None = None) -> str:
    lines = [
        "# /code-runner Handoff",
        "",
        f"Target: `{verdict['target_reviewed']}`",
        f"Review verdict: `{verdict['verdict']}`",
        "",
        "Apply fixes in an isolated worktree. Do not rely on memory as evidence.",
        "`/ask` prepared this handoff but did not edit files or invoke `/code-runner`.",
        "",
    ]
    if task:
        lines.extend(
            [
                "## Task",
                "",
                f"- Task ID: `{task['task_id']}`",
                f"- Task JSON: `code_runner_task.json`",
                f"- Execution status: `{task['execution']['status']}`",
                "",
                "## Allowed Files",
                "",
            ]
        )
        for path in task["allowed_files"]:
            lines.append(f"- `{path}`")
        lines.extend(["", "## Definition Of Done", ""])
        for command in task["definition_of_done"]["commands"]:
            lines.append(f"- `{command}`")
        lines.extend(["", "## Non-Goals", ""])
        for item in task["non_goals"]:
            lines.append(f"- {item}")
        lines.extend(["", "## Risk Notes", ""])
        for item in task["risk_notes"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend([
        "## Findings",
        "",
    ])
    for finding in verdict.get("findings", []):
        lines.extend([
            f"- {finding.get('title', 'Untitled')}",
            f"  - Severity: {finding.get('severity', 'unknown')}",
            f"  - Evidence: {finding.get('evidence', '')}",
            f"  - Fix: {finding.get('fix', '')}",
            f"  - Verification: {finding.get('verification', '')}",
        ])
    return "\n".join(lines) + "\n"


def build_code_runner_task(
    *,
    verdict: dict[str, Any],
    ask_id: str,
    allowed_files: list[str],
    dod_commands: list[str],
    non_goals: list[str],
    risk_notes: list[str],
    implementation_requested: bool,
) -> dict[str, Any]:
    findings = [finding for finding in verdict.get("findings", []) if isinstance(finding, dict)]
    target_files = _task_target_files(verdict)
    allowed = validate_code_runner_allowed_files(allowed_files or target_files)
    commands = _task_dod_commands(findings, dod_commands)
    non_goal_items = non_goals or [
        "Do not edit files outside allowed_files.",
        "Do not broaden scope beyond verified review findings.",
        "Do not treat memory or reviewer speculation as implementation evidence.",
    ]
    risk_note_items = risk_notes or _task_risk_notes(findings)
    task = {
        "schema_version": CODE_RUNNER_TASK_SCHEMA_VERSION,
        "task_id": f"ask-fix-{safe_artifact_name(ask_id or verdict.get('generated_at', 'run'))}",
        "source_review_run": ask_id,
        "source_review_protocol": PARALLEL_REVIEW_SCHEMA_VERSION,
        "target_files": target_files,
        "allowed_files": allowed,
        "findings_to_fix": findings,
        "definition_of_done": {
            "commands": commands,
        },
        "non_goals": non_goal_items,
        "risk_notes": risk_note_items,
        "post_fix_review": True,
        "execution": {
            "requested": implementation_requested,
            "backend": "code-runner" if implementation_requested else None,
            "status": "prepared_not_executable",
            "reason": "/ask is read-only; this is an /ask handoff schema, not a native executable /code-runner task.",
        },
        "code_runner_invocation": {
            "status": "not_generated",
            "reason": "Native /code-runner execution schema is not integrated; invoke /code-runner explicitly after human review.",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    errors = validate_code_runner_task(task)
    if errors:
        raise ParallelReviewError("Cannot prepare /code-runner task: " + "; ".join(errors))
    return task


def validate_code_runner_task(task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if task.get("schema_version") != CODE_RUNNER_TASK_SCHEMA_VERSION:
        errors.append("invalid code-runner task schema_version")
    for field in ("target_files", "allowed_files", "findings_to_fix", "non_goals", "risk_notes"):
        if not task.get(field):
            errors.append(f"missing {field}")
    if not task.get("definition_of_done", {}).get("commands"):
        errors.append("missing definition_of_done.commands")
    if task.get("execution", {}).get("requested") is not True:
        errors.append("code-runner task requires explicit implementation intent")
    target_files = set(task.get("target_files") or [])
    allowed_files = set(task.get("allowed_files") or [])
    if target_files and not target_files.issubset(allowed_files):
        errors.append("allowed_files must include all target_files")
    return errors


def safe_artifact_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in str(value)).strip("-._") or "reviewer"


def _git_diff() -> str:
    completed = subprocess.run(
        ["git", "diff", "--"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else ""


def _truncate(markdown: str) -> str:
    if len(markdown) <= MAX_TARGET_CHARS:
        return markdown
    return markdown[:MAX_TARGET_CHARS] + "\n\n[Target bundle truncated]\n"


def _aggregate_verdict(reviewer_outputs: list[dict[str, Any]], findings: list[dict[str, Any]]) -> str:
    reviewer_verdicts = {str(output.get("verdict", "")).upper() for output in reviewer_outputs}
    if "NOT_SAFE" in reviewer_verdicts or any(str(finding.get("severity", "")).lower() == "high" for finding in findings):
        return "NOT_SAFE"
    if not reviewer_outputs or "INSUFFICIENT_EVIDENCE" in reviewer_verdicts:
        return "INSUFFICIENT_EVIDENCE"
    if findings or "SAFE_WITH_CONDITIONS" in reviewer_verdicts:
        return "SAFE_WITH_CONDITIONS"
    return "SAFE"


def _parse_reviewer_personas(personas: str | None) -> list[dict[str, Any]]:
    specs = []
    for item in [part.strip() for part in (personas or "").split(",") if part.strip()]:
        if ":" in item:
            name, role = [part.strip() for part in item.split(":", 1)]
        else:
            name, role = item, "reviewer"
        specs.append(
            {
                "name": name,
                "protocol_role": role.replace("-", "_"),
                "focus": [role] if role else ["review"],
                "prompt": f"Review as {name}. Apply the {role} role if specified. Stay evidence-bound.",
                "model": "text",
            }
        )
    return specs


def _verify_parallel_finding(reviewer: str, finding: dict[str, Any], failures: list[str]) -> None:
    for field in ("severity", "title", "evidence", "impact", "fix", "verification"):
        if not str(finding.get(field, "")).strip():
            failures.append(f"{reviewer}: finding missing {field}")


def _has_actionable_findings(verdict: dict[str, Any]) -> bool:
    return any(isinstance(finding, dict) for finding in verdict.get("findings", []))


def _task_target_files(verdict: dict[str, Any]) -> list[str]:
    target_bundle = verdict.get("target_bundle") if isinstance(verdict.get("target_bundle"), dict) else {}
    files: set[str] = set()
    for entry in _list_value(target_bundle.get("entries")):
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") == "file":
            path = str(entry.get("path") or entry.get("target") or "").strip()
            if path:
                files.add(path)
        elif entry.get("kind") == "git:diff":
            for path in _list_value(entry.get("paths")):
                value = str(path).strip()
                if value:
                    files.add(value)
    return sorted(files)


def _task_dod_commands(findings: list[dict[str, Any]], explicit_commands: list[str]) -> list[str]:
    commands = [command.strip() for command in explicit_commands if command.strip()]
    return sorted(set(commands))


def validate_code_runner_allowed_files(allowed_files: list[str], repo_root: Path | None = None) -> list[str]:
    root = (repo_root or Path.cwd()).resolve()
    normalized: list[str] = []
    for raw in allowed_files:
        value = str(raw).strip()
        if not value:
            continue
        path = Path(value).expanduser()
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        if not _is_relative_to(resolved, root):
            raise ParallelReviewError(f"allowed file outside repository: {raw}")
        if resolved.exists() and resolved.is_dir():
            raise ParallelReviewError(f"allowed file is a directory: {raw}")
        normalized.append(str(resolved.relative_to(root)))
    return sorted(set(normalized))


def _task_risk_notes(findings: list[dict[str, Any]]) -> list[str]:
    notes = [
        "Implementation must stay within allowed_files.",
        "Run /ask post-fix review before merge.",
    ]
    for finding in findings:
        impact = str(finding.get("impact", "")).strip()
        if impact:
            notes.append(impact)
    return sorted(set(notes))


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.flags & re.DOTALL:
            redacted = pattern.sub("[REDACTED PRIVATE KEY]", redacted)
        else:
            redacted = pattern.sub(r"\1\2[REDACTED]", redacted)
    return redacted


def _paths_from_git_diff(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) >= 4:
            paths.append(parts[3][2:] if parts[3].startswith("b/") else parts[3])
    return sorted(set(paths))


def _concrete_target_names(target_bundle: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in _list_value(target_bundle.get("entries")):
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") == "file":
            for key in ("target", "path", "resolved_path"):
                value = str(entry.get(key) or "").strip()
                if value:
                    names.add(value)
                    names.add(Path(value).name)
        elif entry.get("kind") == "git:diff":
            names.add("git:diff")
            for path in _list_value(entry.get("paths")):
                value = str(path).strip()
                if value:
                    names.add(value)
                    names.add(Path(value).name)
    return names


def _verify_safe_target_bundle(target_bundle: dict[str, Any], failures: list[str]) -> None:
    entries = [entry for entry in _list_value(target_bundle.get("entries")) if isinstance(entry, dict)]
    if not target_bundle:
        failures.append("missing target_bundle metadata")
        return
    if target_bundle.get("truncated"):
        failures.append("safe verdict requires untruncated target_bundle")
    if not entries:
        failures.append("safe verdict requires concrete target entries")
    for entry in entries:
        if entry.get("kind") in {"declared", "directory"}:
            failures.append(f"safe verdict cannot rely on {entry.get('kind')} target: {entry.get('target')}")


def _verify_files_inspected_in_target(
    reviewer: str,
    files_inspected: Any,
    concrete_targets: set[str],
    failures: list[str],
) -> None:
    inspected = [str(item).strip() for item in _list_value(files_inspected) if str(item).strip()]
    if not inspected:
        failures.append(f"{reviewer}: safe verdict requires files_inspected")
        return
    if not concrete_targets:
        failures.append(f"{reviewer}: no concrete target files available for files_inspected")
        return
    for item in inspected:
        if item not in concrete_targets and Path(item).name not in concrete_targets:
            failures.append(f"{reviewer}: files_inspected outside target bundle: {item}")
