#!/usr/bin/env python3
"""Bounded README adjudication: T0 checks + $ask webkimi oracle gate."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
from loguru import logger

app = typer.Typer(add_completion=False, no_args_is_help=True)

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
ASK_RUN = SKILLS_DIR / "ask" / "run.sh"
RUBRIC_PATH = SKILL_DIR / "references" / "readme_review_rubric.md"

VERDICT_RE = re.compile(
    r"^\s*VERDICT:\s*(PASS|NEEDS_CHANGES|BLOCKED)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SKILL_ALIAS_RE = re.compile(r"\$[a-z][a-z0-9_-]*", re.IGNORECASE)


@dataclass
class T0Finding:
    severity: str
    location: str
    problem: str
    suggestion: str = ""


@dataclass
class T0Result:
    findings: list[T0Finding] = field(default_factory=list)

    @property
    def has_blocker(self) -> bool:
        return any(f.severity.upper() == "BLOCKER" for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity.upper() in {"BLOCKER", "HIGH"} for f in self.findings)


def run_t0(readme_path: Path, *, strict: bool) -> T0Result:
    result = T0Result()
    if not readme_path.exists():
        result.findings.append(
            T0Finding("BLOCKER", str(readme_path), "README file does not exist")
        )
        return result
    text = readme_path.read_text(encoding="utf-8", errors="replace")

    if not text.strip().startswith("#"):
        result.findings.append(
            T0Finding(
                "MEDIUM",
                "top",
                "Missing top-level Markdown title (# …)",
                "Add a single H1 with the project or skill name",
            )
        )

    if len(text.strip()) < 200:
        result.findings.append(
            T0Finding(
                "HIGH",
                "document",
                "README is very short (<200 characters of content)",
                "Expand purpose, quick start, and verification",
            )
        )

    aliases = sorted(set(SKILL_ALIAS_RE.findall(text)))
    if aliases and "glossary" not in text.lower() and "alias" not in text.lower():
        result.findings.append(
            T0Finding(
                "HIGH",
                "terminology",
                f"Uses skill shorthand {aliases} without a glossary or alias table",
                "Define each $alias on first use or add a Terminology section",
            )
        )

    lower = text.lower()
    for pattern, label in (
        (r"purpose|about|overview", "Purpose"),
        (r"quick start|getting started|usage", "Quick start"),
    ):
        if not re.search(pattern, lower):
            sev = "HIGH" if strict else "MEDIUM"
            result.findings.append(
                T0Finding(
                    sev,
                    "structure",
                    f"No section matching /{pattern}/ for {label}",
                    f"Add a {label} section with concrete steps",
                )
            )

    return result


def build_bundle(
    readme_path: Path,
    *,
    audience: str,
    goal: str,
    domain: str,
    check_implementation: bool,
    prereq_doc: str,
    t0: T0Result,
    round_no: int,
    prior_verdict: str | None,
    prior_summary: str | None,
) -> str:
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
    parts = [
        "# README review bundle (adjudication only)",
        "",
        "You are an external README reviewer. **Do not** edit the repository.",
        "Use review-only language: adjudicate, flag, suggest revision — not fix or implement.",
        "",
        f"- Round: {round_no}",
        f"- Audience: {audience}",
        f"- Reader goal: {goal}",
        f"- Domain: {domain or '(unspecified)'}",
        f"- Implementation cross-check requested: {'YES' if check_implementation else 'NO'}",
    ]
    if prereq_doc:
        parts.append(f"- Prerequisite doc: {prereq_doc}")
    if prior_verdict:
        parts.append(f"- Prior round verdict: {prior_verdict}")
    if prior_summary:
        parts.extend(["", "## Prior round executive summary", "", prior_summary.strip(), ""])
    if t0.findings:
        parts.extend(["", "## Deterministic T0 findings (pre-oracle)", ""])
        for f in t0.findings:
            line = f"- **{f.severity}** @ {f.location}: {f.problem}"
            if f.suggestion:
                line += f" — Suggestion: {f.suggestion}"
            parts.append(line)
    parts.extend(
        [
            "",
            "## Rubric and required output format",
            "",
            rubric,
            "",
            "## README under review",
            "",
            f"Host path (context only): `{readme_path}`",
            "",
            readme_text,
            "",
        ]
    )
    if check_implementation:
        parts.extend(
            [
                "## Implementation check instruction",
                "",
                "Source files were not inlined. Flag unverifiable claims and set "
                "IMPLEMENTATION SYNC to NO unless correctness is clear from the README alone.",
                "",
            ]
        )
    return "\n".join(parts)


def parse_verdict(text: str) -> str | None:
    match = VERDICT_RE.search(text)
    return match.group(1).upper() if match else None


def extract_executive_summary(text: str) -> str:
    m = re.search(
        r"EXECUTIVE SUMMARY\s*\n(.*?)(?=\nREADER CONTRACT|\nISSUES|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def resolve_ask_run() -> Path:
    if ASK_RUN.exists():
        return ASK_RUN
    alt = Path.home() / ".claude" / "skills" / "ask" / "run.sh"
    return alt if alt.exists() else ASK_RUN


def run_ask_webkimi(
    *,
    bundle_path: Path,
    ask_id: str,
    kimi_tab_id: str,
    timeout: int,
) -> dict[str, Any]:
    ask_run = resolve_ask_run()
    if not ask_run.exists():
        return {
            "status": "blocked",
            "reason": "ask runtime not found",
            "ask_run": str(ask_run),
        }

    question = (
        f"Adjudicate the attached README review bundle at {bundle_path}. "
        "Return the required VERDICT structure from the rubric exactly. "
        "Do not implement fixes or edit files."
    )
    command = [
        str(ask_run),
        "ask",
        "webkimi",
        question,
        "--oracle",
        "--oracle-backend",
        "webkimi",
        "--once",
        "--kimi-tab-id",
        kimi_tab_id,
        "--ask-id",
        ask_id,
        "--overwrite",
        "--json",
    ]
    logger.info("Running: {}", " ".join(command))
    proc = subprocess.run(
        command,
        cwd=ask_run.parent,
        capture_output=True,
        text=True,
        timeout=timeout + 120,
    )
    run_dir = ask_run.parent / ".ask_artifacts" / "runs" / ask_id
    status_path = run_dir / f"{ask_id}.status.json"
    response_md: Path | None = None
    status_data: dict[str, Any] = {}
    if status_path.exists():
        try:
            status_data = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            status_data = {}
        artifacts = status_data.get("artifacts") or {}
        if isinstance(artifacts, dict):
            for key in ("response_md", "markdown", "answer_md", "review_md"):
                val = artifacts.get(key)
                if isinstance(val, str):
                    response_md = Path(val)
                    if not response_md.is_absolute():
                        response_md = ask_run.parent / response_md
                    break
    if response_md is None:
        candidates = sorted(run_dir.glob("*.md"))
        response_md = candidates[-1] if candidates else None

    body = ""
    if response_md and response_md.exists():
        body = response_md.read_text(encoding="utf-8", errors="replace")

    verdict = parse_verdict(body)
    meta = status_data.get("meta") or {}
    capacity_busy = meta.get("status") == "capacity_busy"
    return {
        "status": "answered" if verdict else "needs_attention",
        "capacity_busy": capacity_busy,
        "returncode": proc.returncode,
        "ask_id": ask_id,
        "command": command,
        "bundle_path": str(bundle_path),
        "status_json": str(status_path),
        "response_md": str(response_md) if response_md else None,
        "verdict": verdict,
        "body": body,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def combine_verdict(
    t0: T0Result, oracle_verdict: str | None, *, skip_oracle: bool = False
) -> tuple[str, str]:
    if t0.has_blocker:
        return "BLOCKED", "t0_blocker_findings"
    if skip_oracle:
        if t0.has_high:
            return "NEEDS_CHANGES", "t0_high_findings"
        if t0.findings:
            return "NEEDS_CHANGES", "t0_non_high_findings"
        return "PASS", "t0_only_clear"
    if oracle_verdict is None:
        return "INSUFFICIENT_EVIDENCE", "oracle_verdict_not_parsed"
    if oracle_verdict == "BLOCKED":
        return "BLOCKED", "oracle_blocked"
    if oracle_verdict == "NEEDS_CHANGES" or t0.has_high:
        if oracle_verdict == "PASS" and t0.has_high:
            return "NEEDS_CHANGES", "t0_high_overrides_oracle_pass"
        return "NEEDS_CHANGES", "oracle_or_t0_needs_changes"
    if oracle_verdict == "PASS":
        return "PASS", "oracle_pass_and_t0_clear"
    return "INSUFFICIENT_EVIDENCE", "unmapped_oracle_verdict"


def write_gate(
    output_dir: Path,
    *,
    readme_path: Path,
    round_no: int,
    max_rounds: int,
    t0: T0Result,
    ask_artifacts: dict[str, Any],
    verdict: str,
    reason: str,
    audience: str,
    goal: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    next_plan: list[str] = []
    if verdict != "PASS":
        next_plan = [
            "Apply suggested revisions to the README (human or project agent).",
            "Re-run /review-readme with the same flags.",
            f"Rounds used: {round_no}/{max_rounds}.",
        ]
        if round_no >= max_rounds:
            next_plan.append(
                "Max rounds reached; accept residual risk or extend --max-rounds."
            )

    payload = {
        "schema": "review_readme.gate.v1",
        "target": str(readme_path.resolve()),
        "verdict": verdict,
        "reason": reason,
        "round": round_no,
        "max_rounds": max_rounds,
        "audience": audience,
        "goal": goal,
        "t0_findings": [
            {
                "severity": f.severity,
                "location": f.location,
                "problem": f.problem,
                "suggestion": f.suggestion,
            }
            for f in t0.findings
        ],
        "ask_artifacts": ask_artifacts,
        "next_iteration_plan": next_plan,
    }
    path = output_dir / "review_result.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (output_dir / "review.md").write_text(
        ask_artifacts.get("body") or "(no oracle body captured)\n",
        encoding="utf-8",
    )
    return path


@app.command()
def review(
    readme_path: str = typer.Argument(..., help="Path to README.md"),
    audience: str = typer.Option(
        "competent developer or technical agent new to the project",
        "--audience",
    ),
    goal: str = typer.Option(
        "understand the project, install or run it, and know what to do next",
        "--goal",
    ),
    domain: str = typer.Option("", "--domain"),
    check_implementation: bool = typer.Option(
        False, "--check-implementation", help="Request implementation accuracy review"
    ),
    prereq_doc: str = typer.Option("", "--prereq-doc"),
    strict: bool = typer.Option(False, "--strict", help="Treat missing sections as HIGH"),
    max_rounds: int = typer.Option(
        1,
        "--max-rounds",
        help="Bounded cycles; re-read README each round; stop if unchanged",
    ),
    output_dir: str = typer.Option("", "--output-dir"),
    kimi_tab_id: str = typer.Option("", "--kimi-tab-id", help="Chrome tab id for Kimi"),
    ask_timeout: int = typer.Option(900, "--ask-timeout"),
    skip_oracle: bool = typer.Option(False, "--skip-oracle", help="T0 only"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Adjudicate README quality (read-only). Composes $ask webkimi unless --skip-oracle."""
    path = Path(readme_path).expanduser().resolve()
    if max_rounds < 1:
        logger.error("--max-rounds must be >= 1")
        raise typer.Exit(2)
    if not skip_oracle and not kimi_tab_id:
        logger.error("--kimi-tab-id is required for webkimi (or use --skip-oracle)")
        raise typer.Exit(2)

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name).strip("-") or "readme"
    gate_dir = (
        Path(output_dir)
        if output_dir
        else SKILL_DIR / "artifacts" / "review-readme" / f"{safe}-{ts}"
    )

    prior_verdict: str | None = None
    prior_summary: str | None = None
    prev_mtime: float | None = None
    final_verdict = "INSUFFICIENT_EVIDENCE"
    final_reason = "no_rounds_completed"
    last_ask: dict[str, Any] = {}

    for round_no in range(1, max_rounds + 1):
        if not path.exists():
            final_verdict, final_reason = "BLOCKED", "readme_missing"
            break

        mtime = path.stat().st_mtime
        if round_no > 1 and prev_mtime is not None and mtime == prev_mtime:
            logger.warning(
                "README unchanged since round {}; stopping".format(round_no - 1)
            )
            final_verdict, final_reason = "NEEDS_CHANGES", "readme_unchanged_between_rounds"
            break
        prev_mtime = mtime

        t0 = run_t0(path, strict=strict)
        round_dir = gate_dir / f"round-{round_no}"
        round_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = round_dir / "readme_review_bundle.md"
        bundle_path.write_text(
            build_bundle(
                path,
                audience=audience,
                goal=goal,
                domain=domain,
                check_implementation=check_implementation,
                prereq_doc=prereq_doc,
                t0=t0,
                round_no=round_no,
                prior_verdict=prior_verdict,
                prior_summary=prior_summary,
            ),
            encoding="utf-8",
        )

        ask_artifacts: dict[str, Any] = {"status": "skipped", "reason": "--skip-oracle"}
        oracle_verdict: str | None = None
        if not skip_oracle:
            ask_id = f"review-readme-{safe}-r{round_no}-{ts}"
            last_ask = run_ask_webkimi(
                bundle_path=bundle_path,
                ask_id=ask_id,
                kimi_tab_id=kimi_tab_id,
                timeout=ask_timeout,
            )
            ask_artifacts = last_ask
            oracle_verdict = last_ask.get("verdict")
            if last_ask.get("capacity_busy"):
                final_verdict, final_reason = "BLOCKED", "kimi_capacity_busy"
                write_gate(
                    round_dir,
                    readme_path=path,
                    round_no=round_no,
                    max_rounds=max_rounds,
                    t0=t0,
                    ask_artifacts=ask_artifacts,
                    verdict=final_verdict,
                    reason=final_reason,
                    audience=audience,
                    goal=goal,
                )
                break

        final_verdict, final_reason = combine_verdict(
            t0, oracle_verdict, skip_oracle=skip_oracle
        )
        prior_verdict = oracle_verdict or final_verdict
        prior_summary = extract_executive_summary(ask_artifacts.get("body") or "")

        gate_path = write_gate(
            round_dir,
            readme_path=path,
            round_no=round_no,
            max_rounds=max_rounds,
            t0=t0,
            ask_artifacts=ask_artifacts,
            verdict=final_verdict,
            reason=final_reason,
            audience=audience,
            goal=goal,
        )
        (gate_dir / "review_result.json").write_text(
            gate_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

        if final_verdict == "PASS":
            break

    if json_out:
        print((gate_dir / "review_result.json").read_text(encoding="utf-8"))
    else:
        print(f"Verdict: {final_verdict} ({final_reason})")
        print(f"Artifact: {gate_dir / 'review_result.json'}")
        if last_ask.get("response_md"):
            print(f"Oracle response: {last_ask['response_md']}")

    raise typer.Exit(0 if final_verdict == "PASS" else 1)


if __name__ == "__main__":
    app()
