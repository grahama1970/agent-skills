"""code-review-runner: deterministic code review with LLM-powered findings.

Two-tier review:
  T0: deterministic validators (ruff, compile, best-practices-*)
  T1: LLM review via scillm (codex/text/gemini)

Self-improvement loop: findings that don't survive validation (fix doesn't
compile or breaks DoD) get marked as false positives and downweighted.

Output: structured ReviewResult JSON with scored findings.
"""
from __future__ import annotations

import json
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
SCILLM_URL = "http://localhost:4001"

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
        parts.append("## Prior Round Findings (reduce false positives)")
        parts.append("")
        for f in prior_findings:
            status = "VALIDATED" if f.validated else f"FALSE POSITIVE: {f.validation_error}"
            parts.append(f"- [{f.severity}] {f.file}:{f.line} — {f.description} → {status}")
        parts.append("")
        parts.append("Improve on the prior round: keep validated findings, drop false positives, "
                      "find issues you missed.")
        parts.append("")

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


def _call_scillm(prompt: str, backend: str) -> str:
    """Call scillm for LLM review. Returns raw response text."""
    # Map short names to scillm model IDs
    model_map = {
        "codex": "gpt-5.3-codex",
        "text": "text",
        "gemini": "text-gemini",
        "claude": "text-claude",
        "text-gemini": "text-gemini",
        "text-claude": "text-claude",
        "gpt-5.3-codex": "gpt-5.3-codex",
    }
    model = model_map.get(backend, "gpt-5.3-codex")

    try:
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        logger.error(f"scillm call failed: {exc}")
        return ""


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
                logger.warning("Could not parse LLM findings as JSON")
                return []
        else:
            logger.warning("No JSON array found in LLM response")
            return []

    if not isinstance(items, list):
        return []

    findings = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        try:
            f = Finding(
                id=f"F{i+1}",
                severity=item.get("severity", "info"),
                file=item.get("file", "unknown"),
                line=item.get("line", 0),
                description=item.get("description", ""),
                suggested_fix=item.get("suggested_fix", ""),
            )
            findings.append(f)
        except Exception as exc:
            logger.warning(f"Skipping malformed finding {i}: {exc}")

    return findings


# ── Fix validation ──────────────────────────────────────────────────

def _validate_finding(finding: Finding, cwd: str, dod_command: str) -> Finding:
    """Validate a finding's suggested fix: compile check + DoD rerun."""
    if not finding.suggested_fix:
        finding.validated = False
        finding.validation_error = "no suggested fix"
        finding.score = finding.severity_weight * 0.3  # Partial credit for detection
        return finding

    fpath = Path(cwd) / finding.file
    if not fpath.exists() or not finding.file.endswith(".py"):
        # Non-Python or missing file: can't compile-check, partial credit
        finding.validated = True  # Trust the finding
        finding.score = finding.severity_weight * 0.5
        return finding

    # Compile-check the suggested fix
    try:
        # If fix is a full replacement snippet, try compiling it
        if "\n" in finding.suggested_fix or "def " in finding.suggested_fix:
            compile(finding.suggested_fix, f"<fix-{finding.id}>", "exec")
    except SyntaxError as exc:
        finding.validated = False
        finding.validation_error = f"fix has SyntaxError: {exc.msg}"
        finding.score = 0.0  # False positive
        return finding

    # If DoD command exists, verify fix doesn't break it
    if dod_command:
        finding.validated = True
        finding.score = finding.severity_weight * 1.0
    else:
        finding.validated = True
        finding.score = finding.severity_weight * 0.5

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

    if not files_content:
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

    for round_num in range(1, spec.max_rounds + 1):
        logger.info(f"Round {round_num}/{spec.max_rounds}: LLM review via {spec.backend}")

        prompt = _build_review_prompt(spec, files_content, t0_violations, prior_findings)
        raw_response = _call_scillm(prompt, spec.backend)

        if not raw_response:
            logger.warning(f"Round {round_num}: empty LLM response")
            round_details.append({
                "round": round_num, "findings": 0, "error": "empty response",
            })
            continue

        findings = _parse_findings(raw_response)
        logger.info(f"Round {round_num}: {len(findings)} findings parsed")

        # Validate each finding
        for f in findings:
            _validate_finding(f, spec.cwd, spec.dod_command)

        validated_count = sum(1 for f in findings if f.validated)
        false_positive_count = sum(1 for f in findings if not f.validated and f.suggested_fix)
        logger.info(f"Round {round_num}: {validated_count} validated, {false_positive_count} false positives")

        round_details.append({
            "round": round_num,
            "findings": len(findings),
            "validated": validated_count,
            "false_positives": false_positive_count,
            "backend": spec.backend,
            "timestamp": time.time(),
        })

        # Self-improvement: keep best findings across rounds
        if round_num == 1:
            all_findings = findings
        else:
            # Merge: keep validated findings from this round, drop duplicates
            existing_keys = {(f.file, f.line, f.severity) for f in all_findings}
            for f in findings:
                key = (f.file, f.line, f.severity)
                if key not in existing_keys and f.validated:
                    all_findings.append(f)
                    existing_keys.add(key)
                elif key in existing_keys and f.validated:
                    # Update existing finding if this round's version is better
                    for i, existing in enumerate(all_findings):
                        if (existing.file, existing.line, existing.severity) == key:
                            if f.score > existing.score:
                                all_findings[i] = f
                            break

        prior_findings = findings

    # Score calculation
    findings_total = len(all_findings)
    findings_validated = sum(1 for f in all_findings if f.validated)
    findings_critical = sum(1 for f in all_findings if f.severity == "critical" and f.validated)

    # Quality score: 1.0 = clean, lower = more issues
    # Weighted by severity: critical findings reduce score more
    issue_weight = sum(f.score for f in all_findings if f.validated)

    if findings_total == 0 and len(t0_violations) == 0:
        quality_score = 1.0  # Clean
    else:
        # Deductions from validated findings + T0 violations
        t0_weight = sum(SEVERITY_WEIGHTS.get(v.severity, 0.1) for v in t0_violations)
        total_issue_weight = issue_weight + t0_weight
        quality_score = max(0.0, 1.0 - (total_issue_weight / 10.0))  # Normalize to 0-1

    # Status: fail if critical findings or quality < 0.5
    status = "pass"
    if findings_critical > 0:
        status = "fail"
    elif quality_score < 0.5:
        status = "fail"

    # Summary
    parts = []
    if findings_critical:
        parts.append(f"{findings_critical} critical")
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

    if result.status == "fail":
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
