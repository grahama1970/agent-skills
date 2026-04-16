"""Helper functions, data classes, and pure logic for structured plan execution.

Extracted from structured_execute.py to keep each module under 800 lines.
Contains TaskRuntime dataclass, dependency graph builder, state renderer,
and prompt/task construction helpers.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

SCILLM_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1/chat/completions")
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parents[1])))
STATE_ROOT = Path(os.environ.get("ORCHESTRATE_HOME", str(Path(__file__).resolve().parent)))
WATCHDOG_POLL_S = 2


@dataclass
class TaskRuntime:
    task_id: str
    title: str
    lane: str
    runner: str
    backend: str
    mode: str
    prompt: str
    command: str
    cwd: Path
    agent: str = ""
    definition_of_done: dict = field(default_factory=dict)
    allowlist: list[str] | None = None
    read_context: list[str] = field(default_factory=list)
    blind_tests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # skill names for context compilation
    skill: str = ""  # skill name for runner=skill (e.g., "assess")
    skill_command: str = ""  # skill subcommand (e.g., "run", "search")
    skill_args: list[str] = field(default_factory=list)  # additional CLI args
    lang: str = ""  # Language profile: python, rust, typescript. Empty = auto-detect.
    max_rounds: int = 5
    timeout_seconds: int = 1800  # per-task timeout (default 30min)
    worktree: bool = False  # opt-in git worktree isolation (for parallel file-only tasks)
    status: str = "queued"
    started_at: float | None = None
    finished_at: float | None = None
    output_path: Path | None = None
    error: str = ""
    review_status: str = ""  # pass/warn/fail
    review_output: str = ""
    _subagent_port: int = 0
    _subagent_task_id: str = ""
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _proc: asyncio.subprocess.Process | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Helpers (pure functions, no async needed)
# ---------------------------------------------------------------------------

def _build_system_prompt(task: TaskRuntime) -> str:
    """Inject extension rules + persona context into subagent system prompt."""
    parts = [
        "You are executing a task within an Embry OS orchestration pipeline.",
        "",
        "## NON-NEGOTIABLE RULES",
        "- Query /memory recall BEFORE scanning any codebase",
        "- Use `from loguru import logger` (NEVER `import logging`)",
        "- Use `httpx` (NEVER `import requests`)",
        "- Use `typer` for CLI (NEVER `argparse`)",
        "- Max 800 lines per Python file",
        "- If an existing skill handles this, USE IT — never reimplement",
        "- All AQL must reside in the memory project only",
        "- Run tests before claiming done",
    ]
    if task.agent:
        agents_md = SKILLS_DIR.parent / "agents" / task.agent / "AGENTS.md"
        if agents_md.exists():
            lines = agents_md.read_text().splitlines()[:50]
            parts.extend(["", f"## Persona: {task.agent}", ""])
            parts.extend(lines)
    return "\n".join(parts)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _task_prompt(task: dict[str, Any]) -> str:
    explicit = str(task.get("prompt") or "").strip()
    if explicit:
        return explicit
    impl = [str(item).strip() for item in _as_list(task.get("implementation")) if str(item).strip()]
    if not impl:
        return ""
    parts = [f"Task: {task.get('title', '')}", "", "Implementation:"]
    parts.extend(f"- {item}" for item in impl)
    dod = task.get("definition_of_done") or {}
    if isinstance(dod, dict) and (dod.get("command") or dod.get("assertion")):
        parts.extend(["", "Definition of Done:",
                       f"- Command: {dod.get('command', '')}",
                       f"- Assertion: {dod.get('assertion', '')}"])
    tests = [str(item).strip() for item in _as_list(task.get("tests")) if str(item).strip()]
    if tests:
        parts.extend(["", "Tests:"])
        parts.extend(f"- {item}" for item in tests)
    return "\n".join(parts).strip()


def _compile_skill_context(skill_names: list[str]) -> str:
    """Compile SKILL.md files into a single context block for code-runner.

    Like an import statement — code-runner sees the API surface of each skill
    without discovering or selecting skills at runtime.
    """
    if not skill_names:
        return ""

    sections = ["## Available Skills (compiled by /orchestrate)\n"]
    for name in skill_names:
        skill_md = SKILLS_DIR / name / "SKILL.md"
        if not skill_md.exists():
            sections.append(f"### SKILL: /{name}\n(SKILL.md not found)\n")
            continue

        text = skill_md.read_text()
        # Extract up to Quick Start or first 80 lines of content (skip frontmatter)
        lines = text.splitlines()
        # Skip YAML frontmatter
        content_start = 0
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    content_start = i + 1
                    break
        # Take first 80 lines of content (API surface, not full docs)
        content_lines = lines[content_start:content_start + 80]
        sections.append(f"### SKILL: /{name}\n" + "\n".join(content_lines) + "\n")

    return "\n".join(sections)


def _compile_skill_task(skill_name: str, skill_command: str, skill_args: list[str]) -> str:
    """Compile a skill invocation into a typed run.sh command.

    Reads SKILL.md to validate the skill exists and has a run.sh entrypoint,
    then generates the exact shell command that _run_skill() will execute.
    Returns the compiled command string for logging/display.
    """
    skill_dir = SKILLS_DIR / skill_name
    run_sh = skill_dir / "run.sh"
    skill_md = skill_dir / "SKILL.md"

    if not skill_dir.exists():
        raise ValueError(
            f"Skill '{skill_name}' not found at {skill_dir}. "
            f"Check .pi/skills/ for available skills."
        )
    if not run_sh.exists():
        raise ValueError(
            f"Skill '{skill_name}' has no run.sh entrypoint at {run_sh}."
        )
    if not skill_md.exists():
        logger.warning("Skill '{}' has no SKILL.md — invocation may be incorrect", skill_name)

    parts = [str(run_sh)]
    if skill_command:
        parts.append(skill_command)
    parts.extend(skill_args)
    compiled = " ".join(parts)
    logger.info("Compiled skill task: {}", compiled)
    return compiled


def _build_runtimes(plan: dict[str, Any], repo_root: Path) -> dict[str, TaskRuntime]:
    runtimes: dict[str, TaskRuntime] = {}
    for raw_task in _as_list(plan.get("tasks")):
        if not isinstance(raw_task, dict):
            continue
        task_id = str(raw_task.get("id") or "").strip()
        # Sanitize task_id to prevent path traversal in generated filenames
        if not re.match(r'^[A-Za-z0-9._-]+$', task_id):
            logger.error("Invalid task_id '{}' — must be alphanumeric/dash/dot/underscore", task_id)
            continue
        cwd = Path(str(raw_task.get("cwd") or repo_root))
        if not cwd.is_absolute():
            cwd = (repo_root / cwd).resolve()
        # Compile skill context: /plan declares skills, /orchestrate compiles them
        # into read_context so code-runner sees SKILL.md as API documentation
        task_skills = _as_list(raw_task.get("skills"))
        read_ctx = list(raw_task.get("read_context") or [])

        # Skill compiler: extract skill invocation fields
        task_skill = str(raw_task.get("skill") or "").strip()
        task_skill_command = str(raw_task.get("skill_command") or "").strip()
        task_skill_args = _as_list(raw_task.get("skill_args"))

        runner = str(raw_task.get("runner") or "").strip()

        # Auto-route: if skill is set and runner is empty, set runner=skill
        if task_skill and not runner:
            runner = "skill"

        # Compile skill invocation at build time — validates skill exists
        if runner == "skill":
            if not task_skill:
                raise ValueError(
                    f"Task {task_id} uses runner=skill but has no 'skill' field. "
                    f"Set skill: <skill-name> (e.g., skill: assess)."
                )
            _compile_skill_task(task_skill, task_skill_command, task_skill_args)

        # Auto-migrate: subagent-service → code-runner (writes files) or scillm (one-shot)
        if runner == "subagent-service":
            mode = str(raw_task.get("mode") or "").strip()
            has_implementation = bool(raw_task.get("implementation") or raw_task.get("allowlist"))
            if has_implementation or mode == "iterative":
                runner = "code-runner"
                logger.info("Task {} auto-migrated: subagent-service → code-runner", task_id)
            else:
                runner = "scillm"
                logger.info("Task {} auto-migrated: subagent-service → scillm", task_id)

        # Compile skill SKILL.md files into the prompt for code-runner tasks
        if task_skills and runner == "code-runner":
            skill_context = _compile_skill_context(task_skills)
            if skill_context:
                # Write compiled context to a temp file so code-runner reads it
                skill_ctx_path = cwd / f".code-runner-skills-{task_id}.md"
                skill_ctx_path.write_text(skill_context)
                read_ctx.append(str(skill_ctx_path))

        runtimes[task_id] = TaskRuntime(
            task_id=task_id,
            title=str(raw_task.get("title") or "").strip(),
            lane=str(raw_task.get("lane") or "default").strip() or "default",
            runner=runner,
            backend=str(raw_task.get("backend") or raw_task.get("model") or "").strip(),
            mode=str(raw_task.get("mode") or "").strip(),
            prompt=_task_prompt(raw_task),
            command=str(raw_task.get("command") or "").strip(),
            cwd=cwd,
            agent=str(raw_task.get("agent") or "").strip(),
            definition_of_done=raw_task.get("definition_of_done") or {},
            allowlist=raw_task.get("allowlist"),
            read_context=read_ctx,
            blind_tests=raw_task.get("blind_tests") or [],
            skills=task_skills,
            skill=task_skill,
            skill_command=task_skill_command,
            skill_args=[str(a) for a in task_skill_args],
            lang=str(raw_task.get("lang") or "").strip(),
            max_rounds=int(raw_task.get("max_rounds") or 5),
            timeout_seconds=int(raw_task.get("timeout_seconds") or 1800),
            worktree=bool(raw_task.get("worktree", False)),
        )

    # Gate: code-runner tasks MUST have blind_tests. DoD alone is gameable.
    # ImpossibleBench (arXiv:2510.20270): GPT-5 cheats 76% when it sees tests.
    for tid, rt in runtimes.items():
        if rt.runner == "code-runner" and not rt.blind_tests:
            raise ValueError(
                f"Task {tid} ({rt.title!r}) uses runner=code-runner but has no blind_tests. "
                f"DoD is gameable — add blind_tests[] that the coding agent cannot see. "
                f"See /test-lab SKILL.md and /code-runner WALKTHROUGH.md."
            )

    return runtimes


def _dependency_graph(plan: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, int]]:
    deps: dict[str, list[str]] = {}
    indegree: dict[str, int] = {}
    task_ids = {str(t.get("id")) for t in _as_list(plan.get("tasks")) if isinstance(t, dict)}
    for task in _as_list(plan.get("tasks")):
        if not isinstance(task, dict):
            continue
        tid = str(task.get("id"))
        raw = [str(i) for i in _as_list(task.get("depends_on")) if str(i)]
        filtered = [i for i in raw if i in task_ids]
        deps[tid] = filtered
        indegree[tid] = len(filtered)
    return deps, indegree


def _render_state(session_dir: Path, runtimes: dict[str, TaskRuntime],
                  deps: dict[str, list[str]], failed: bool) -> None:
    payload = {
        "generated_at": time.time(), "failed": failed, "session_dir": str(session_dir),
        "tasks": [
            {"id": t.task_id, "title": t.title, "lane": t.lane, "runner": t.runner,
             "backend": t.backend, "mode": t.mode, "agent": t.agent, "status": t.status,
             "depends_on": deps.get(t.task_id, []),
             "output_path": str(t.output_path) if t.output_path else "",
             "error": t.error, "started_at": t.started_at, "finished_at": t.finished_at,
             "subagent_task_id": t._subagent_task_id or "",
             "subagent_port": t._subagent_port or 0}
            for t in runtimes.values()
        ],
    }
    (session_dir / "status.json").write_text(json.dumps(payload, indent=2))


def render_report(
    session_dir: Path,
    runtimes: dict[str, TaskRuntime],
    plan: dict[str, Any],
    verbose: bool = False,
) -> str:
    """Render human-readable execution report (pytest/GitHub Actions style).

    Args:
        session_dir: Path to session directory
        runtimes: Task ID -> TaskRuntime mapping
        plan: Original plan dict (for metadata, lanes)
        verbose: Include stdout/stderr excerpts for failed tasks
    """
    lines: list[str] = []
    metadata = plan.get("metadata", {})
    title = metadata.get("title", "Orchestrate Execution")
    lanes = {str(l.get("id")): l.get("label", f"Lane {l.get('id')}") for l in plan.get("lanes", [])}

    # Header
    lines.append("╭" + "─" * 67 + "╮")
    lines.append(f"│ ORCHESTRATE: {title[:52]:<52} │")
    lines.append(f"│ Session: {session_dir.name:<56} │")
    lines.append("╰" + "─" * 67 + "╯")
    lines.append("")

    # Group tasks by lane
    tasks_by_lane: dict[str, list[TaskRuntime]] = {}
    for t in runtimes.values():
        lane_id = t.lane or "default"
        if lane_id not in tasks_by_lane:
            tasks_by_lane[lane_id] = []
        tasks_by_lane[lane_id].append(t)

    # Sort lanes by ID (numeric if possible)
    def lane_sort_key(lid: str) -> tuple[int, str]:
        try:
            return (0, str(int(lid)).zfill(10))
        except ValueError:
            return (1, lid)

    # Render each lane
    for lane_id in sorted(tasks_by_lane.keys(), key=lane_sort_key):
        lane_tasks = sorted(tasks_by_lane[lane_id], key=lambda t: t.task_id)
        lane_label = lanes.get(lane_id, f"Lane {lane_id}")

        # Calculate lane timing and status
        lane_times = [
            (t.finished_at or 0) - (t.started_at or 0)
            for t in lane_tasks if t.started_at and t.finished_at
        ]
        lane_total = sum(lane_times)
        lane_statuses = [t.status for t in lane_tasks]

        if "failed" in lane_statuses:
            lane_status = "FAILED"
        elif all(s == "completed" for s in lane_statuses):
            lane_status = f"{_fmt_duration(lane_total)}"
        elif all(s in ("queued", "blocked") for s in lane_statuses):
            lane_status = "skipped"
        else:
            lane_status = "partial"

        lines.append(f"{lane_label} {'─' * (60 - len(lane_label))} {lane_status}")

        # Render tasks in lane
        for t in lane_tasks:
            duration = ""
            if t.started_at and t.finished_at:
                duration = f"{t.finished_at - t.started_at:.1f}s"

            # Status symbol
            if t.status == "completed":
                symbol = "✓"
            elif t.status == "failed":
                symbol = "✗"
            elif t.status == "running":
                symbol = "▶"
            elif t.status == "blocked":
                symbol = "○"
            else:
                symbol = "·"

            # Backend tag
            backend_tag = f"[{t.backend}]" if t.backend else f"[{t.runner}]"

            # Main task line
            title_trunc = t.title[:38] if len(t.title) > 38 else t.title
            lines.append(f"  {symbol} {t.task_id:<3} {title_trunc:<40} {backend_tag:<10} {duration:>6}")

            # Error details for failed tasks
            if t.status == "failed" and t.error:
                # Extract key error info
                error_line = t.error.split("\n")[0][:60] if t.error else "unknown"
                lines.append(f"       └─ {error_line}")

                # Load result.json for more detail if available
                if verbose:
                    result_file = session_dir / f"{t.task_id}.result.json"
                    if result_file.exists():
                        try:
                            result = json.loads(result_file.read_text())
                            rounds = result.get("rounds", 0)
                            best_score = result.get("best_score", 0)
                            lines.append(f"       └─ Rounds: {rounds} | Score: {best_score:.3f}")
                        except (json.JSONDecodeError, IOError):
                            pass

            # Blocked indicator
            elif t.status == "blocked":
                # Find which parent failed
                blocked_by = t.error.split("blocked by")[-1].strip()[:20] if "blocked by" in t.error else ""
                if blocked_by:
                    lines.append(f"       └─ blocked by {blocked_by}")

        lines.append("")

    # Summary footer
    completed = sum(1 for t in runtimes.values() if t.status == "completed")
    failed = sum(1 for t in runtimes.values() if t.status == "failed")
    blocked = sum(1 for t in runtimes.values() if t.status in ("blocked", "queued"))

    total_time = sum(
        (t.finished_at or 0) - (t.started_at or 0)
        for t in runtimes.values() if t.started_at and t.finished_at
    )

    lines.append("─" * 68)
    lines.append(f"SUMMARY: {completed} ✓ | {failed} ✗ | {blocked} ○ | Total: {_fmt_duration(total_time)}")
    lines.append(f"Session: {session_dir}/")
    if failed or blocked:
        lines.append(f"Resume:  orchestrate run <plan.yaml> --resume")

    return "\n".join(lines)


def _fmt_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    else:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}m"


def _subagent_backend_name(model: str) -> str:
    low = model.lower()
    if low.startswith(("gpt", "codex", "o3", "o4")):
        return "codex"
    if low.startswith(("gemini",)):
        return "gemini"
    return "claude"
