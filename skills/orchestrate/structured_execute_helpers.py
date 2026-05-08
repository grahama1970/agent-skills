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
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from monitor_renderer import render_monitor_html
from structured_execute_context import retrieval_context_block, retrieval_context_payload

def normalize_scillm_chat_url(raw_url: str | None) -> str:
    """Return the concrete OpenAI-compatible chat completions endpoint."""
    url = (raw_url or "http://localhost:4001/v1/chat/completions").strip().rstrip("/")
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        return f"{url}/v1/chat/completions"
    if path == "/v1":
        return f"{url}/chat/completions"
    return url


SCILLM_URL = normalize_scillm_chat_url(os.environ.get("SCILLM_API_BASE"))
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parents[1])))
DEFAULT_ARTIFACT_ROOT = Path(
    os.environ.get("AGENT_SKILLS_ARTIFACT_ROOT", "/mnt/storage12tb/artifacts/agent-skills")
)
STATE_ROOT = Path(os.environ.get("ORCHESTRATE_HOME", str(DEFAULT_ARTIFACT_ROOT / "orchestrate")))
WATCHDOG_POLL_S = 2

TASK_VIEWER_STATES = {
    "queued",
    "running",
    "passed",
    "failed",
    "blocked",
    "stale",
    "paused",
    "skipped",
    "retrying",
}

FAILURE_CODES = {
    "REVIEW_PLAN_FAILED",
    "PREFLIGHT_FAILED",
    "WORKTREE_DIRTY",
    "DEPENDENCY_FAILED",
    "DOD_FAILED",
    "BLIND_TEST_FAILED",
    "QUALITY_GATE_FAILED",
    "LIVE_SERVER_MISMATCH",
    "RUNNER_TIMEOUT",
    "RUNNER_CRASHED",
    "CANCELLED",
    "MANUAL_INTERVENTION_REQUIRED",
}

STATUS_NORMALIZATION = {
    "completed": "passed",
    "cancelled": "failed",
    "pending": "queued",
}

ARTIFACT_KIND_BY_SUFFIX = {
    ".blind-eval.json": "blind_eval",
    ".code-runner-spec.json": "code_runner_spec",
    ".hunk.md": "diff",
    ".result.json": "result",
    ".response.txt": "response",
    ".review-output.txt": "review",
    ".review-request.md": "review_request",
    ".review-spec.json": "review_spec",
    ".stderr.txt": "stderr",
    ".stdout.txt": "stdout",
}


@dataclass
class Precondition:
    """A precondition that must be satisfied before a task can execute."""
    type: str  # path_exists, service_reachable, env_var_set, command_succeeds
    path: str = ""
    url: str = ""
    var: str = ""
    command: str = ""


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
    dependency_patch_artifacts: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # skill names for context compilation
    skill: str = ""  # skill name for runner=skill (e.g., "assess")
    skill_command: str = ""  # skill subcommand (e.g., "run", "search")
    skill_args: list[str] = field(default_factory=list)  # additional CLI args
    lang: str = ""  # Language profile: python, rust, typescript. Empty = auto-detect.
    max_rounds: int = 5
    dirty_worktree_policy: str = "isolated_worktree"
    timeout_seconds: int = 1800  # per-task timeout (default 30min)
    apply_to_source: bool = False
    commit_on_success: bool = False
    rollback_on_failure: bool = True
    retrieval_context: dict[str, Any] = field(default_factory=dict)
    source_commit: str = ""
    worktree: bool = False  # opt-in git worktree isolation (for parallel file-only tasks)
    preconditions: list[Precondition] = field(default_factory=list)  # checked before dispatch
    status: str = "queued"
    started_at: float | None = None
    finished_at: float | None = None
    output_path: Path | None = None
    error: str = ""
    review_status: str = ""  # pass/warn/fail
    review_output: str = ""
    patch_artifact: str = ""
    phase: str = "queued"
    failure_code: str = ""
    last_event_at: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    control_notes: list[str] = field(default_factory=list)
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


def _extract_wave(lane: str) -> int:
    """Extract wave number from lane ID. Lane "0", "0.1", "0.2" → wave 0. Lane "1", "1.1" → wave 1."""
    if not lane:
        return 0
    first_part = lane.split(".")[0]
    try:
        return int(first_part)
    except ValueError:
        return 0


def check_precondition(pc: "Precondition", cwd: Path) -> tuple[bool, str]:
    """Check a single precondition. Returns (passed, error_message)."""
    import subprocess
    import httpx

    if pc.type == "path_exists":
        path = Path(pc.path)
        if not path.is_absolute():
            path = cwd / path
        if path.exists():
            return True, ""
        return False, f"path_exists: {path} does not exist"

    elif pc.type == "service_reachable":
        try:
            resp = httpx.get(pc.url, timeout=5.0)
            if resp.status_code < 500:
                return True, ""
            return False, f"service_reachable: {pc.url} returned {resp.status_code}"
        except Exception as e:
            return False, f"service_reachable: {pc.url} unreachable ({e})"

    elif pc.type == "env_var_set":
        if os.environ.get(pc.var):
            return True, ""
        return False, f"env_var_set: ${pc.var} is not set"

    elif pc.type == "command_succeeds":
        try:
            result = subprocess.run(
                pc.command, shell=True, capture_output=True, timeout=10, cwd=str(cwd)
            )
            if result.returncode == 0:
                return True, ""
            return False, f"command_succeeds: '{pc.command}' exited {result.returncode}"
        except Exception as e:
            return False, f"command_succeeds: '{pc.command}' failed ({e})"

    return False, f"unknown precondition type: {pc.type}"


def check_all_preconditions(task: "TaskRuntime") -> list[str]:
    """Check all preconditions for a task. Returns list of error messages (empty = all passed)."""
    errors = []
    for pc in task.preconditions:
        passed, msg = check_precondition(pc, task.cwd)
        if not passed:
            errors.append(f"Task {task.task_id}: {msg}")
    return errors


def _task_prompt(task: dict[str, Any]) -> str:
    explicit = str(task.get("prompt") or "").strip()
    if explicit:
        base = explicit
    else:
        impl = [str(item).strip() for item in _as_list(task.get("implementation")) if str(item).strip()]
        if not impl:
            base = ""
        else:
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
            base = "\n".join(parts).strip()

    retrieval_context = retrieval_context_block(task)
    if base and retrieval_context:
        return f"{base}\n\n{retrieval_context}"
    return base


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
        # Keep this intentionally small: code-runner already receives explicit
        # read_context/allowlist files, and oversized skill imports can overflow
        # the local scillm context before any tool call is made.
        max_lines = int(os.environ.get("ORCHESTRATE_SKILL_CONTEXT_LINES", "25"))
        content_lines = lines[content_start:content_start + max_lines]
        sections.append(f"### SKILL: /{name}\n" + "\n".join(content_lines) + "\n")

    return "\n".join(sections)


def _write_compiled_skill_context(task_id: str, skill_context: str) -> Path:
    """Write compiled skill context outside the repo so preflight stays clean."""
    context_dir = Path(tempfile.gettempdir()) / "orchestrate-code-runner-context"
    context_dir.mkdir(parents=True, exist_ok=True)
    context_path = context_dir / f"{task_id}-{os.getpid()}-{int(time.time() * 1000)}.md"
    context_path.write_text(skill_context)
    return context_path


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
    force_patch_only = os.environ.get("ORCHESTRATE_FORCE_PATCH_ONLY") == "1"
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
                # Write compiled context to an execution artifact so code-runner
                # can read it without dirtying the target repo before preflight.
                skill_ctx_path = _write_compiled_skill_context(task_id, skill_context)
                read_ctx.append(str(skill_ctx_path))

        # Parse preconditions
        raw_preconditions = raw_task.get("preconditions") or []
        preconditions = []
        for pc in raw_preconditions:
            if isinstance(pc, dict):
                preconditions.append(Precondition(
                    type=str(pc.get("type") or ""),
                    path=str(pc.get("path") or ""),
                    url=str(pc.get("url") or ""),
                    var=str(pc.get("var") or ""),
                    command=str(pc.get("command") or ""),
                ))

        # Normalize read_context: convert structured objects to string paths
        # {path: "foo.py", start_line: 10, end_line: 20} → "foo.py:10-20"
        normalized_read_ctx = []
        for rc in read_ctx:
            if isinstance(rc, dict):
                path = rc.get("path", "")
                start = rc.get("start_line")
                end = rc.get("end_line")
                if start and end:
                    normalized_read_ctx.append(f"{path}:{start}-{end}")
                else:
                    normalized_read_ctx.append(path)
            else:
                normalized_read_ctx.append(str(rc))

        raw_apply_to_source = bool(raw_task.get("apply_to_source", False))
        raw_commit_on_success = bool(raw_task.get("commit_on_success", False))
        raw_rollback_on_failure = bool(raw_task.get("rollback_on_failure", True))
        if raw_apply_to_source and force_patch_only:
            logger.warning(
                "Task {} requested complete-task source apply; ORCHESTRATE_FORCE_PATCH_ONLY=1 is forcing patch-only.",
                task_id,
            )

        prompt = _task_prompt(raw_task)
        if runner == "code-runner" and not prompt:
            raise ValueError(
                f"Task {task_id} uses runner=code-runner but has no prompt or implementation. "
                "Retrieved context can guide a task; it cannot be the task."
            )

        runtimes[task_id] = TaskRuntime(
            task_id=task_id,
            title=str(raw_task.get("title") or "").strip(),
            lane=str(raw_task.get("lane") or "default").strip() or "default",
            runner=runner,
            backend=str(raw_task.get("backend") or raw_task.get("model") or "").strip(),
            mode=str(raw_task.get("mode") or "").strip(),
            prompt=prompt,
            command=str(raw_task.get("command") or "").strip(),
            cwd=cwd,
            agent=str(raw_task.get("agent") or "").strip(),
            definition_of_done=raw_task.get("definition_of_done") or {},
            allowlist=raw_task.get("allowlist"),
            read_context=normalized_read_ctx,
            blind_tests=raw_task.get("blind_tests") or [],
            skills=task_skills,
            skill=task_skill,
            skill_command=task_skill_command,
            skill_args=[str(a) for a in task_skill_args],
            lang=str(raw_task.get("lang") or "").strip(),
            max_rounds=int(raw_task.get("max_rounds") or 5),
            dirty_worktree_policy=str(raw_task.get("dirty_worktree_policy") or "isolated_worktree").strip(),
            timeout_seconds=int(raw_task.get("timeout_seconds") or 1800),
            apply_to_source=raw_apply_to_source and not force_patch_only,
            commit_on_success=raw_commit_on_success if not force_patch_only else False,
            rollback_on_failure=raw_rollback_on_failure if not force_patch_only else True,
            retrieval_context=retrieval_context_payload(task_id, raw_task),
            worktree=bool(raw_task.get("worktree", False)),
            preconditions=preconditions,
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


def normalize_task_status(status: str) -> str:
    normalized = STATUS_NORMALIZATION.get(status, status)
    if normalized in TASK_VIEWER_STATES:
        return normalized
    return "failed" if status else "queued"


def infer_failure_code(task: TaskRuntime) -> str:
    if task.failure_code:
        return task.failure_code
    if task.status == "blocked":
        return "DEPENDENCY_FAILED"
    if task.status == "cancelled":
        return "CANCELLED"
    if task.status == "failed" and task.preconditions:
        return "PREFLIGHT_FAILED"
    if task.status == "failed" and task.runner == "code-runner":
        if task.blind_tests and "blind" in task.error.lower():
            return "BLIND_TEST_FAILED"
        return "DOD_FAILED"
    if task.status == "failed":
        return "RUNNER_CRASHED"
    return ""


def _artifact_kind(path: Path) -> str:
    name = path.name
    for suffix, kind in ARTIFACT_KIND_BY_SUFFIX.items():
        if name.endswith(suffix):
            return kind
    if name == "report.txt":
        return "report"
    if name == "plan.json":
        return "plan"
    if name == "INTERVENTION.md":
        return "controls"
    return "artifact"


def _task_artifacts(session_dir: Path, task: TaskRuntime) -> list[dict[str, Any]]:
    artifact_paths: list[Path] = []
    for path in sorted(session_dir.glob(f"{task.task_id}.*")):
        if path.is_file():
            artifact_paths.append(path)
    if task.output_path and task.output_path.exists():
        artifact_paths.append(task.output_path)

    seen: set[Path] = set()
    artifacts: list[dict[str, Any]] = []
    for path in artifact_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            rel = resolved.relative_to(session_dir.resolve())
        except ValueError:
            rel = Path(resolved.name)
        artifacts.append(
            {
                "name": path.name,
                "path": rel.as_posix(),
                "kind": _artifact_kind(path),
                "size_bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
            }
        )
    return artifacts


def _session_artifacts(session_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for name in ("plan.json", "report.txt", "INTERVENTION.md", "events.jsonl"):
        path = session_dir / name
        if path.exists():
            artifacts.append(
                {
                    "name": path.name,
                    "path": path.name,
                    "kind": _artifact_kind(path),
                    "size_bytes": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )
    return artifacts


def _render_state(session_dir: Path, runtimes: dict[str, TaskRuntime],
                  deps: dict[str, list[str]], failed: bool) -> None:
    generated_at = time.time()
    task_payloads = []
    for t in runtimes.values():
        normalized_status = normalize_task_status(t.status)
        failure_code = infer_failure_code(t)
        task_payloads.append(
            {
                "id": t.task_id,
                "title": t.title,
                "lane": t.lane,
                "runner": t.runner,
                "backend": t.backend,
                "mode": t.mode,
                "agent": t.agent,
                "status": normalized_status,
                "raw_status": t.status,
                "phase": t.phase or normalized_status,
                "failure_code": failure_code,
                "depends_on": deps.get(t.task_id, []),
                "command": t.command,
                "cwd": str(t.cwd),
                "output_path": str(t.output_path) if t.output_path else "",
                "error": t.error,
                "review_status": t.review_status,
                "review_output": t.review_output,
                "started_at": t.started_at,
                "finished_at": t.finished_at,
                "last_event_at": t.last_event_at,
                "subagent_task_id": t._subagent_task_id or "",
                "subagent_port": t._subagent_port or 0,
                "artifacts": _task_artifacts(session_dir, t.task_id),
                "events": t.events[-20:],
                "control_notes": t.control_notes[-5:],
            }
        )
    payload = {
        "schema_version": "task-viewer.v1",
        "generated_at": generated_at,
        "failed": failed,
        "session_id": session_dir.name,
        "session_dir": str(session_dir),
        "state_model": sorted(TASK_VIEWER_STATES),
        "failure_codes": sorted(FAILURE_CODES),
        "counts": {
            state: sum(1 for t in task_payloads if t["status"] == state)
            for state in sorted(TASK_VIEWER_STATES)
        },
        "tasks": task_payloads,
        "artifacts": _session_artifacts(session_dir),
    }
    (session_dir / "status.json").write_text(json.dumps(payload, indent=2))
    plan = _load_session_plan(session_dir)
    render_monitor_html(session_dir, payload, plan, deps)


def _load_session_plan(session_dir: Path) -> dict[str, Any]:
    plan_file = session_dir / "plan.json"
    if not plan_file.exists():
        return {}
    try:
        data = json.loads(plan_file.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _load_monitor_url(session_dir: Path) -> str:
    metadata_file = session_dir / "monitor-server.json"
    if not metadata_file.exists():
        return ""
    try:
        data = json.loads(metadata_file.read_text())
        return str(data.get("url") or "")
    except (json.JSONDecodeError, OSError):
        return ""


def _task_artifacts(session_dir: Path, task_id: str) -> dict[str, str]:
    candidates = {
        "code_runner_spec": session_dir / f"{task_id}.code-runner-spec.json",
        "response": session_dir / f"{task_id}.response.txt",
        "stdout": session_dir / f"{task_id}.stdout.txt",
        "stderr": session_dir / f"{task_id}.stderr.txt",
        "result": session_dir / f"{task_id}.result.json",
        "rounds": session_dir / f"{task_id}.rounds.jsonl",
        "hunk": session_dir / f"{task_id}.hunk.md",
        "blind_eval": session_dir / f"{task_id}.blind-eval.json",
        "review_request": session_dir / f"{task_id}.review-request.md",
        "review_output": session_dir / f"{task_id}.review-output.txt",
    }
    return {
        name: path.name
        for name, path in candidates.items()
        if path.exists()
    }


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
    lines.append(f"Monitor: {session_dir / 'monitor.html'}")
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
