"""Code-runner task-shape validation for /plan.

This module keeps conservative runner contract checks out of the CLI file.
It validates that `/plan` emits code-runner tasks only when the task is bounded,
machine-checkable, worktree-local, and suitable for `/orchestrate`.
"""

from __future__ import annotations

import re
from typing import Any

_LIVE_DOD_MARKERS = (
    "curl ",
    "wget ",
    "http://",
    "https://",
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "playwright",
    "puppeteer",
    "cypress",
    "webdriver",
    "chromium",
    "selenium",
    "storybook",
    "test-runner",
    "browser",
    "cdp",
    "e2e",
)
_LIVE_SURFACE_RE = re.compile(
    r"https?://|curl\s|wget\s|requests\.get|httpx\.\w+|urllib|"
    r"playwright|puppeteer|cypress|webdriver|chromium|selenium|storybook|test-runner|browser|cdp|\be2e\b",
    re.IGNORECASE,
)
_OPAQUE_CODE_RUNNER_COMMAND_RE = re.compile(
    r"(^|\s)(npm|pnpm|yarn|bun)\s+(run|test|exec)\b|"
    r"(^|\s)make(\s|$)|"
    r"(^|\s)(bash|sh|python|python3|uv\s+run\s+python)\s+(scripts|tools)/|"
    r"(^|\s)(\./)?(scripts|tools)/[^\s;|&]+",
    re.IGNORECASE,
)
_CODE_RUNNER_SAFE_POLICIES = {"isolated_worktree"}
_MACHINE_CHECKABLE_ASSERTION = re.compile(
    r"^\s*(exit_code\s*(==|!=)\s*\d+|stdout_regex:.+|stderr_regex:.+|contains:.+|json_path:.+|json_equals:.+)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_CODE_RUNNER_LOW_VALUE_TERMS = (
    "docs",
    "documentation",
    "readme",
    "config",
    "yaml",
    "compose",
    "docker compose",
    "setup",
    "bootstrap",
    "validation",
    "verify",
    "test gate",
    "lint",
    "format",
    "report",
)


def dod_uses_live_endpoint(command: str) -> bool:
    command_lower = command.lower()
    return any(marker in command_lower for marker in _LIVE_DOD_MARKERS) or bool(_LIVE_SURFACE_RE.search(command))


def dod_uses_opaque_command(command: str) -> bool:
    return bool(_OPAQUE_CODE_RUNNER_COMMAND_RE.search(command or ""))


def opaque_command_is_audited(task: dict[str, Any]) -> bool:
    return (
        bool(task.get("opaque_command_reviewed"))
        and str(task.get("dod_scope") or "").strip() == "worktree_local"
        and task.get("requires_network") is False
        and task.get("requires_live_server") is False
        and task.get("browser_required") is False
        and bool(task.get("blind_tests") or [])
    )


def code_runner_live_surface(task: dict[str, Any], dod_command: str) -> str:
    parts = [dod_command]
    for item in task.get("tests") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("command") or item))
        else:
            parts.append(str(item))
    return "\n".join(parts)


def is_machine_checkable_assertion(assertion: str) -> bool:
    return bool(_MACHINE_CHECKABLE_ASSERTION.match(assertion or ""))


def task_text(task: dict[str, Any]) -> str:
    parts: list[str] = [
        str(task.get("title") or ""),
        str(task.get("prompt") or ""),
        str(task.get("context_boundary") or ""),
    ]
    for key in ("implementation", "tests", "blind_tests"):
        value = task.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts).lower()


def audit_code_runner_routing(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return blocking issues/warnings for tasks routed to code-runner."""
    issues: list[str] = []
    warnings: list[str] = []
    tasks = data.get("tasks") or []
    if not isinstance(tasks, list):
        return issues, warnings

    for task in tasks:
        if not isinstance(task, dict):
            continue
        runner = str(task.get("runner") or "").strip()
        if runner != "code-runner":
            continue

        task_id = str(task.get("id") or "?")
        title = str(task.get("title") or "")
        dod = task.get("definition_of_done") or {}
        dod_command = str(dod.get("command") or "") if isinstance(dod, dict) else ""
        dod_assertion = str(dod.get("assertion") or "") if isinstance(dod, dict) else ""
        prompt = str(task.get("prompt") or "")
        allowlist = task.get("allowlist") or []
        read_context = task.get("read_context") or []
        blind_tests = task.get("blind_tests") or []
        max_rounds = int(task.get("max_rounds") or 5)
        dirty_policy = str(task.get("dirty_worktree_policy") or "isolated_worktree").strip()
        unsafe_justification = str(task.get("unsafe_direct_justification") or "").strip()
        apply_to_source = bool(task.get("apply_to_source", False))
        commit_on_success = bool(task.get("commit_on_success", False))
        rollback_on_failure = bool(task.get("rollback_on_failure", True))

        prefix = f"Task {task_id} ({title}):"
        if task.get("command") and not prompt:
            issues.append(f"{prefix} command-only work must be runner=local, not code-runner.")
        if not prompt or len(prompt.strip()) < 20:
            issues.append(f"{prefix} code-runner requires a concrete prompt describing the bounded code change.")
        if not allowlist:
            issues.append(f"{prefix} code-runner requires allowlist for write-scope/context isolation.")
        if not dod_command:
            issues.append(f"{prefix} code-runner requires definition_of_done.command.")
        if not dod_assertion:
            issues.append(f"{prefix} code-runner requires definition_of_done.assertion; use 'exit_code == 0' for silent commands.")
        elif not is_machine_checkable_assertion(dod_assertion):
            issues.append(
                f"{prefix} code-runner definition_of_done.assertion must be machine-checkable "
                "(exit_code == N, stdout_regex:..., stderr_regex:..., contains:..., json_path:..., json_equals:...)."
            )
        if not blind_tests:
            issues.append(f"{prefix} code-runner requires blind_tests so /orchestrate has an information barrier.")
        if dirty_policy not in _CODE_RUNNER_SAFE_POLICIES and not unsafe_justification:
            issues.append(
                f"{prefix} code-runner dirty_worktree_policy must be isolated_worktree unless unsafe_direct_justification is explicit."
            )
        if commit_on_success and not apply_to_source:
            issues.append(f"{prefix} commit_on_success requires apply_to_source=true.")
        if apply_to_source and not commit_on_success:
            issues.append(f"{prefix} complete-task mode requires commit_on_success=true for reliable revert.")
        if apply_to_source and not rollback_on_failure:
            issues.append(f"{prefix} complete-task mode requires rollback_on_failure=true.")
        if dod_uses_live_endpoint(code_runner_live_surface(task, dod_command)):
            issues.append(
                f"{prefix} code-runner cannot use live endpoint/browser DoD or tests. "
                "Code-runner edits an isolated worktree, while live servers serve the source tree. "
                "Use scillm for the edit plus a separate local verification task, or use a file/process-local DoD."
            )
        if dod_uses_opaque_command(code_runner_live_surface(task, dod_command)) and not opaque_command_is_audited(task):
            issues.append(
                f"{prefix} code-runner DoD/tests use an opaque shell indirection command. "
                "Use an explicit file/process-local command such as `python -m pytest tests/test_file.py -q`, "
                "or route the opaque script/make/npm check to a separate runner=local verification task."
            )
        if max_rounds <= 1:
            warnings.append(f"{prefix} max_rounds <= 1; use scillm/local unless iteration is actually needed.")
        if not read_context:
            issues.append(f"{prefix} code-runner requires read_context so interface context is separated from writable allowlist.")
        text = task_text(task)
        if any(term in text for term in _CODE_RUNNER_LOW_VALUE_TERMS):
            warnings.append(
                f"{prefix} appears to be setup/config/docs/validation work; prefer local for deterministic gates "
                "or scillm for one-shot edits unless this is a bounded failing code loop."
            )

    return issues, warnings
