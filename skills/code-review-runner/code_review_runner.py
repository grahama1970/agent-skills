"""code-review-runner: deterministic code review with LLM-powered findings.

Two-tier review:
  T0: deterministic validators (ruff, compile, best-practices-*)
  T1: LLM review via scillm (codex/text/gemini)

Suggested fixes remain advisory because the runner does not apply them.

Output: structured ReviewResult JSON with scored findings.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import httpx
import typer
from loguru import logger

from models import Finding, ReviewResult, ReviewSpec, T0Violation
from validators import run_all_validators

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
SCILLM_URL = os.environ.get("SCILLM_URL", "http://localhost:4001").rstrip("/")

app = typer.Typer(no_args_is_help=True)

# ── Severity weights ────────────────────────────────────────────────

SEVERITY_WEIGHTS = {"critical": 1.0, "major": 0.7, "minor": 0.3, "info": 0.1}


# ── LLM review via scillm ──────────────────────────────────────────

def _build_review_prompt(spec: ReviewSpec, files_content: dict[str, str],
                         t0_violations: list[T0Violation],
                         prior_findings: list[Finding] | None = None) -> str:
    """Build structured review prompt for the LLM."""
    parts = [
        "You are a code reviewer. Review the following files and produce structured findings.",
        "",
        "## Output Format (MANDATORY)",
        "",
        "Respond with ONLY a JSON array of findings. No prose before or after.",
        "Each finding must have these fields:",
        '  {"severity": "critical|major|minor|info", "file": "path", "line": N, '
        '"description": "what is wrong", "suggested_fix": "code or description"}',
        "",
        "## Review Focus",
        "",
        f"Focus: {spec.focus or 'security, correctness, maintainability, performance'}",
        "",
    ]

    if spec.context:
        parts.extend(["## Context", "", spec.context, ""])

    if t0_violations:
        parts.append("## T0 Violations Already Found (do NOT repeat these)")
        parts.append("")
        for v in t0_violations:
            parts.append(f"- [{v.severity}] {v.file}:{v.line} — {v.message} ({v.rule})")
        parts.append("")
        parts.append("Focus on issues that T0 validators CANNOT detect: logic errors, "
                      "race conditions, security vulnerabilities, design problems.")
        parts.append("")

    if prior_findings:
        parts.append("## Prior Round Findings (reassess independently)")
        parts.append("")
        for f in prior_findings:
            status = "VALIDATED" if f.validated else f"UNVALIDATED: {f.validation_error}"
            parts.append(f"- [{f.severity}] {f.file}:{f.line} — {f.description} → {status}")
        parts.append("")
        parts.append("Reassess prior findings against the authoritative change set.")
        parts.append("")

    if spec.base_ref:
        parts.extend(
            [
                "## Authoritative Change Set",
                "",
                f"Git diff against `{spec.base_ref}`:",
                "```diff",
                _build_review_diff(spec),
                "```",
                "",
                "Review the change set above. Use the file excerpts below only as supporting context.",
                "",
            ]
        )

    parts.append("## Files to Review")
    parts.append("")
    for fpath, content in files_content.items():
        parts.append(f"### {fpath}")
        parts.append("```")
        # Cap file content at 500 lines to avoid token bloat
        lines = content.splitlines()
        if len(lines) > 500:
            parts.append("\n".join(lines[:500]))
            parts.append(f"\n... ({len(lines) - 500} more lines truncated)")
        else:
            parts.append(content)
        parts.append("```")
        parts.append("")

    return "\n".join(parts)


def _build_review_diff(spec: ReviewSpec) -> str:
    try:
        merge_base_result = subprocess.run(
            ["git", "merge-base", spec.base_ref, "HEAD"],
            cwd=spec.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if merge_base_result.returncode != 0 or not merge_base_result.stdout.strip():
            raise ScillmReviewError(
                f"could not resolve merge base for {spec.base_ref}: "
                f"{merge_base_result.stderr.strip()[:500]}"
            )
        merge_base = merge_base_result.stdout.strip()
        result = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--unified=80", merge_base, "--", *spec.files],
            cwd=spec.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", *spec.files],
            cwd=spec.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScillmReviewError(f"could not build review diff: {exc}") from exc
    if result.returncode != 0:
        raise ScillmReviewError(
            f"could not build review diff against {spec.base_ref}: {result.stderr.strip()[:1000]}"
        )
    if untracked.returncode != 0:
        raise ScillmReviewError(
            f"could not enumerate untracked review files: {untracked.stderr.strip()[:1000]}"
        )

    diff_parts = [result.stdout]
    for path in untracked.stdout.splitlines():
        try:
            addition = subprocess.run(
                ["git", "diff", "--no-index", "--unified=80", "--", "/dev/null", path],
                cwd=spec.cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ScillmReviewError(
                f"could not build untracked-file diff for {path}: {exc}"
            ) from exc
        if addition.returncode not in {0, 1}:
            raise ScillmReviewError(
                f"could not build untracked-file diff for {path}: {addition.stderr.strip()[:1000]}"
            )
        diff_parts.append(addition.stdout)

    diff = "\n".join(part for part in diff_parts if part.strip())
    if not diff.strip():
        raise ScillmReviewError(f"review diff against {spec.base_ref} is empty")
    return diff


class ScillmReviewError(RuntimeError):
    """SciLLM transport or response failure that invalidates a review round."""


def _resolve_scillm_api_key_from_docker() -> tuple[str, str] | None:
    """Resolve the key actually configured on the running SciLLM proxy."""

    for container in ("docker-scillm-proxy-1", "scillm-proxy"):
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    container,
                    "--format",
                    "{{range .Config.Env}}{{println .}}{{end}}",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        env = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        for name in ("SCILLM_MASTER_KEY", "SCILLM_PROXY_KEY", "LITELLM_MASTER_KEY"):
            value = env.get(name, "").strip()
            if value:
                return value, f"docker:{container}:{name}"
    return None


def _resolve_scillm_api_key() -> tuple[str, str]:
    for name in (
        "SCILLM_PROXY_KEY",
        "SCILLM_MASTER_KEY",
        "LITELLM_MASTER_KEY",
        "SCILLM_API_KEY",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value, f"env:{name}"

    docker_key = _resolve_scillm_api_key_from_docker()
    if docker_key is not None:
        return docker_key

    raise ScillmReviewError(
        "SciLLM API key not found in the environment or running proxy container"
    )


def _call_scillm(prompt: str, backend: str) -> str:
    """Call scillm for LLM review. Returns raw response text."""
    # Map short names to scillm model IDs
    model_map = {
        "codex": "gpt-5.5",
        "text": "text",
        "gemini": "text-gemini",
        "claude": "text-claude",
        "text-gemini": "text-gemini",
        "text-claude": "text-claude",
        "gpt-5.3-codex": "gpt-5.5",
        "gpt-5.5": "gpt-5.5",
    }
    model = model_map.get(backend, "gpt-5.5")

    api_key, api_key_source = _resolve_scillm_api_key()
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.startswith("gpt-"):
        request["temperature"] = 0.2

    def post(key: str) -> httpx.Response:
        return httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "X-Caller-Skill": "code-review-runner",
            },
            json=request,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    try:
        resp = post(api_key)
        if resp.status_code == 401:
            refreshed = _resolve_scillm_api_key_from_docker()
            if refreshed is not None and refreshed[0] != api_key:
                api_key, api_key_source = refreshed
                resp = post(api_key)
        if resp.status_code >= 400:
            raise ScillmReviewError(
                f"SciLLM HTTP {resp.status_code} using {api_key_source}"
            )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except ScillmReviewError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ScillmReviewError(
            f"SciLLM review call failed using {api_key_source}: {exc}"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ScillmReviewError("SciLLM review call returned empty assistant content")
    return content


def _parse_findings(raw: str) -> list[Finding]:
    """Parse LLM response into Finding objects."""
    # Try to extract JSON array from response
    raw = raw.strip()

    # Strip markdown code fence if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        import re
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
            except json.JSONDecodeError:
                raise ScillmReviewError("SciLLM review findings were not valid JSON")
        else:
            raise ScillmReviewError("SciLLM review response contained no JSON findings array")

    if not isinstance(items, list):
        raise ScillmReviewError("SciLLM review response must be a JSON array")

    findings = []
    required_fields = {"severity", "file", "line", "description", "suggested_fix"}
    allowed_severities = set(SEVERITY_WEIGHTS)
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ScillmReviewError(f"SciLLM finding {i + 1} must be an object")
        missing = sorted(required_fields - set(item))
        if missing:
            raise ScillmReviewError(
                f"SciLLM finding {i + 1} missing required fields: {', '.join(missing)}"
            )
        if item["severity"] not in allowed_severities:
            raise ScillmReviewError(
                f"SciLLM finding {i + 1} has invalid severity: {item['severity']!r}"
            )
        if not isinstance(item["file"], str) or not item["file"].strip():
            raise ScillmReviewError(f"SciLLM finding {i + 1} has invalid file")
        if type(item["line"]) is not int or item["line"] < 0:
            raise ScillmReviewError(f"SciLLM finding {i + 1} has invalid line")
        if not isinstance(item["description"], str) or not item["description"].strip():
            raise ScillmReviewError(f"SciLLM finding {i + 1} has invalid description")
        if not isinstance(item["suggested_fix"], str):
            raise ScillmReviewError(f"SciLLM finding {i + 1} has invalid suggested_fix")
        try:
            f = Finding(
                id=f"F{i+1}",
                severity=item["severity"],
                file=item["file"],
                line=item["line"],
                description=item["description"],
                suggested_fix=item["suggested_fix"],
            )
            findings.append(f)
        except Exception as exc:
            raise ScillmReviewError(
                f"SciLLM finding {i + 1} failed schema validation: {exc}"
            ) from exc

    if items and not findings:
        raise ScillmReviewError("SciLLM review response contained no valid finding objects")

    return findings


# ── Fix validation ──────────────────────────────────────────────────

def _mark_finding_advisory(finding: Finding) -> Finding:
    """Record impact without claiming that an unapplied suggested fix is valid."""
    finding.validated = False
    finding.score = finding.severity_weight * 0.3
    if not finding.suggested_fix:
        finding.validation_error = "no suggested fix"
    else:
        finding.validation_error = "suggested fix was not applied; finding remains advisory"

    return finding


# ── Memory integration ──────────────────────────────────────────────

def _recall_prior_reviews(task_id: str, files: list[str]) -> str:
    """Recall prior review findings for these files from /memory."""
    if not Path(MEMORY_SOCKET).exists():
        return ""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        client = httpx.Client(transport=transport, base_url="http://memory")
        query = f"code review findings for {' '.join(files[:3])}"
        resp = client.post("/recall", json={
            "query": query, "scope": "code-review-runner", "k": 3,
        }, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                return "\n".join(r.get("problem", "") for r in results[:3])
        client.close()
    except Exception as exc:
        logger.debug(f"Memory recall failed (non-fatal): {exc}")
    return ""


def _learn_review(task_id: str, result: ReviewResult) -> None:
    """Store review result in /memory for future recall."""
    if not Path(MEMORY_SOCKET).exists():
        return
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        client = httpx.Client(transport=transport, base_url="http://memory")

        critical = [f for f in result.all_findings if f.severity == "critical" and f.validated]
        finding_summary = "; ".join(
            f"[{f.severity}] {f.file}:{f.line} {f.description}"
            for f in result.all_findings[:10]
        )

        client.post("/learn", json={
            "problem": f"CODE REVIEW: {task_id}\nScore: {result.score:.3f} | "
                       f"Findings: {result.findings_total} (validated: {result.findings_validated}) | "
                       f"T0 violations: {result.t0_violation_count}\n{finding_summary}",
            "solution": json.dumps({
                "task_id": task_id,
                "score": result.score,
                "findings_total": result.findings_total,
                "findings_validated": result.findings_validated,
                "findings_critical": result.findings_critical,
                "t0_violation_count": result.t0_violation_count,
                "backend": result.backend,
            }),
            "tags": ["code-review-runner", f"task:{task_id}",
                     f"score:{result.score:.1f}",
                     *(f"critical:{f.file}" for f in critical)],
            "scope": "code-review-runner",
        }, timeout=5.0)
        client.close()
        logger.info(f"Learned review result for {task_id}")
    except Exception as exc:
        logger.debug(f"Memory learn failed (non-fatal): {exc}")


# ── Main review loop ────────────────────────────────────────────────

def run_review(spec: ReviewSpec) -> ReviewResult:
    """Execute the full review: T0 validators → LLM review → scoring."""
    output_dir = Path(spec.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read all target files via shared bundler
    import sys
    skills_dir = str(Path(__file__).resolve().parent.parent)
    if skills_dir not in sys.path:
        sys.path.insert(0, skills_dir)
    from common.file_bundler import bundle_for_review

    files_content = bundle_for_review(spec.files, spec.cwd)
    missing_files = [f for f in spec.files if f not in files_content]

    if not files_content and not spec.base_ref:
        return ReviewResult(
            task_id=spec.task_id,
            status="error",
            summary=f"No readable files found. Missing: {missing_files}",
        )

    # Recall prior reviews
    prior_context = _recall_prior_reviews(spec.task_id, spec.files)
    if prior_context:
        logger.info(f"Recalled prior review context ({len(prior_context)} chars)")

    # T0: Run all deterministic validators
    logger.info("Running T0 validators...")
    t0_violations = run_all_validators(spec.files, spec.cwd)
    logger.info(f"T0 complete: {len(t0_violations)} violation(s)")

    # LLM review rounds
    all_findings: list[Finding] = []
    round_details: list[dict] = []
    prior_findings: list[Finding] | None = None
    successful_rounds = 0
    had_provider_error = False

    for round_num in range(1, spec.max_rounds + 1):
        logger.info(f"Round {round_num}/{spec.max_rounds}: LLM review via {spec.backend}")

        try:
            prompt = _build_review_prompt(spec, files_content, t0_violations, prior_findings)
            raw_response = _call_scillm(prompt, spec.backend)
            findings = _parse_findings(raw_response)
        except ScillmReviewError as exc:
            had_provider_error = True
            logger.error(f"Round {round_num}: {exc}")
            round_details.append({
                "round": round_num,
                "findings": 0,
                "error": str(exc),
            })
            continue
        successful_rounds += 1
        logger.info(f"Round {round_num}: {len(findings)} findings parsed")

        # Validate each finding
        for f in findings:
            _mark_finding_advisory(f)

        validated_count = sum(1 for f in findings if f.validated)
        advisory_count = sum(1 for f in findings if not f.validated)
        logger.info(f"Round {round_num}: {validated_count} validated, {advisory_count} advisory")

        round_details.append({
            "round": round_num,
            "findings": len(findings),
            "validated": validated_count,
            "advisory": advisory_count,
            "backend": spec.backend,
            "timestamp": time.time(),
        })

        # Self-improvement: keep best findings across rounds
        if round_num == 1:
            all_findings = findings
        else:
            # Keep advisory findings across rounds; validation status describes
            # suggested-fix proof, not whether the reported defect exists.
            existing_keys = {(f.file, f.line, f.severity) for f in all_findings}
            for f in findings:
                key = (f.file, f.line, f.severity)
                if key not in existing_keys:
                    all_findings.append(f)
                    existing_keys.add(key)
                else:
                    for i, existing in enumerate(all_findings):
                        if (existing.file, existing.line, existing.severity) == key:
                            if len(f.description) > len(existing.description):
                                all_findings[i] = f
                            break

        prior_findings = findings

    # Score calculation
    findings_total = len(all_findings)
    findings_validated = sum(1 for f in all_findings if f.validated)
    findings_critical = sum(1 for f in all_findings if f.severity == "critical")
    findings_major = sum(1 for f in all_findings if f.severity == "major")
    t0_blocking = any(v.severity in {"critical", "major"} for v in t0_violations)

    # Quality score: 1.0 = clean, lower = more issues
    # Weighted by severity: critical findings reduce score more
    issue_weight = sum(f.score for f in all_findings)

    if findings_total == 0 and len(t0_violations) == 0:
        quality_score = 1.0  # Clean
    else:
        # Advisory findings and deterministic violations both reduce confidence.
        t0_weight = sum(SEVERITY_WEIGHTS.get(v.severity, 0.1) for v in t0_violations)
        total_issue_weight = issue_weight + t0_weight
        quality_score = max(0.0, 1.0 - (total_issue_weight / 10.0))  # Normalize to 0-1

    # Status: fail if critical findings or quality < 0.5
    status = "pass"
    if successful_rounds == 0 or had_provider_error:
        status = "error"
        quality_score = 0.0
    elif findings_critical > 0 or findings_major > 0 or t0_blocking:
        status = "fail"
    elif quality_score < 0.5:
        status = "fail"

    # Summary
    parts = []
    if findings_critical:
        parts.append(f"{findings_critical} critical")
    if findings_major:
        parts.append(f"{findings_major} major")
    if successful_rounds == 0:
        parts.append("no successful LLM review rounds")
    elif had_provider_error:
        parts.append("one or more LLM review rounds failed")
    parts.append(f"{findings_validated}/{findings_total} findings validated")
    parts.append(f"{len(t0_violations)} T0 violations")
    parts.append(f"score={quality_score:.3f}")
    summary = " | ".join(parts)

    result = ReviewResult(
        task_id=spec.task_id,
        status=status,
        score=quality_score,
        findings_total=findings_total,
        findings_validated=findings_validated,
        findings_critical=findings_critical,
        t0_violation_count=len(t0_violations),
        rounds=len(round_details),
        summary=summary,
        all_findings=all_findings,
        all_t0_violations=t0_violations,
        round_details=round_details,
        backend=spec.backend,
    )

    # Write result
    result_path = output_dir / f"{spec.task_id}.review-result.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Result written to {result_path}")

    # Write human-readable report
    report_path = output_dir / f"{spec.task_id}.review-report.md"
    report_path.write_text(_format_report(result, t0_violations, all_findings), encoding="utf-8")
    logger.info(f"Report written to {report_path}")

    # Learn to memory
    _learn_review(spec.task_id, result)

    return result


def _format_report(result: ReviewResult, t0_violations: list[T0Violation],
                   findings: list[Finding]) -> str:
    """Format review result as human-readable markdown."""
    lines = [
        f"# Code Review: {result.task_id}",
        "",
        f"**Status**: {result.status.upper()} | **Score**: {result.score:.3f} | "
        f"**Rounds**: {result.rounds}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ]

    if t0_violations:
        lines.extend([
            "## T0 Violations (Deterministic)",
            "",
            "| Severity | File | Line | Rule | Message |",
            "|----------|------|------|------|---------|",
        ])
        for v in t0_violations:
            lines.append(f"| {v.severity} | {v.file} | {v.line} | {v.rule} | {v.message} |")
        lines.append("")

    if findings:
        lines.extend([
            "## LLM Findings",
            "",
            "| ID | Severity | File | Line | Description | Validated | Score |",
            "|----|----------|------|------|-------------|-----------|-------|",
        ])
        for f in findings:
            valid = "yes" if f.validated else f"NO: {f.validation_error}"
            lines.append(
                f"| {f.id} | {f.severity} | {f.file} | {f.line} | "
                f"{f.description[:60]} | {valid} | {f.score:.2f} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────

@app.command()
def review(
    spec_file: str = typer.Argument(..., help="Path to review spec JSON"),
    max_rounds: int = typer.Option(0, help="Override max rounds (0 = use spec)"),
    backend: str = typer.Option("", help="Override backend"),
):
    """Run T0 validators + LLM review on files specified in the spec."""
    spec_path = Path(spec_file)
    if not spec_path.exists():
        logger.error(f"Spec file not found: {spec_file}")
        raise typer.Exit(1)

    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = ReviewSpec(**raw)
    except Exception as exc:
        logger.error(f"Invalid spec: {exc}")
        raise typer.Exit(1)

    if max_rounds > 0:
        spec.max_rounds = max_rounds
    if backend:
        spec.backend = backend

    result = run_review(spec)

    # Print summary
    logger.info(f"Review complete: {result.status.upper()} — {result.summary}")
    print(json.dumps(result.model_dump(), indent=2))

    if result.status != "pass":
        raise typer.Exit(1)


@app.command(name="dry-run")
def dry_run(
    spec_file: str = typer.Argument(..., help="Path to review spec JSON"),
):
    """Run T0 validators only (no LLM call)."""
    spec_path = Path(spec_file)
    if not spec_path.exists():
        logger.error(f"Spec file not found: {spec_file}")
        raise typer.Exit(1)

    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = ReviewSpec(**raw)
    except Exception as exc:
        logger.error(f"Invalid spec: {exc}")
        raise typer.Exit(1)

    t0_violations = run_all_validators(spec.files, spec.cwd)
    logger.info(f"T0 dry-run: {len(t0_violations)} violation(s)")

    for v in t0_violations:
        severity_icon = {"critical": "!!!", "major": "!!", "minor": "!", "info": "."}.get(v.severity, "?")
        print(f"  {severity_icon} [{v.severity}] {v.file}:{v.line} — {v.message} ({v.rule})")

    if not t0_violations:
        print("  No T0 violations found.")


if __name__ == "__main__":
    app()
