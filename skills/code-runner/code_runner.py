#!/usr/bin/env python3
"""Code Runner v2 — Autoresearch-pattern self-improvement loop for code tasks.

Architecture (same pattern as classifier-lab backbone_train_loop.py):
  1. LLM proposes code
  2. T0 deterministic evidence collection (errors, lint, DoD)
  3. Composite score (0-1) like autoresearch's val_bpb
  4. Score improved? → git commit (KEEP) : git revert (DISCARD)
  5. /scillm structured fix prompt with full trajectory
  6. Strategy escalation (5-step)
  7. Experiment log (rounds.jsonl)

90% deterministic (subprocess, regex, git), 10% LLM (propose fix).
The subagent CAN follow this because every step is a subprocess call.
"""
from __future__ import annotations

import fcntl
import random
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import typer
from loguru import logger
from trace_compress import compress_tool_trace, trace_events_to_dict

# common/ modules may be present but are not required by the minimal runner.
_skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
_common = str(_skills_dir / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)

from evidence import (
    classify_errors,
    collect_evidence,
    get_strategy,
    build_fix_prompt,
)
from event_emitter import EventEmitter
from models import EventType, ReasonCode, RunState
from apply import (
    build_file_context,
    generate_hunk_review,
)
from tool_use import _stream_chat_completion, run_tool_use_loop
from models import TaskSpec, TaskResult, PreflightError
from worktree_runtime import (
    WorktreeInfo,
    WorktreeRuntimeError,
    changed_path_statuses,
    changed_paths,
    create_disposable_worktree,
    dirty_paths_for_allowlist,
    export_allowlist_patch,
    remove_disposable_worktree,
    remove_untracked_paths,
    paths_within_allowlist,
    restore_patch_base_tree,
)
from _misuse_guard import (
    validate_task_spec,
    format_misuse_errors,
    MisuseError,
)
from _debug_dashboard import TraceCollector, generate_dashboard

app = typer.Typer(no_args_is_help=True)


def _emit_event(event: str, **fields) -> None:
    """Emit a structured JSON event to stderr for real-time monitoring.

    Project agents can parse lines starting with '{"event":' from the
    stderr stream while loguru provides human-readable output alongside.
    """
    payload = {"event": event, "ts": time.time(), **fields}
    print(json.dumps(payload, default=str), file=sys.stderr, flush=True)

def _normalize_scillm_chat_url(raw_url: str | None) -> str:
    """Return the OpenAI-compatible chat-completions URL for scillm."""
    base_url = (raw_url or "http://localhost:4001").rstrip("/")
    if base_url.endswith("/v1/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


SCILLM_URL = _normalize_scillm_chat_url(os.environ.get("SCILLM_API_BASE"))
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
GIT_TIMEOUT = 30  # seconds — prevents hangs on large repos

# Actionable fix advice per field (for Pydantic validation errors)
_FIX_ADVICE = {
    "prompt": "Add: which file to read, what's broken, what the fix should do. Min 20 chars.",
    "definition_of_done": "Add definition_of_done: {command: '...', assertion: '...'}",
    "definition_of_done.command": "Add a shell command that RUNS the code and checks OUTPUT. "
        "Example: 'python3 -c \"from module import func; assert func(x) == y; print(OK)\"'",
    "allowlist": "Add specific files: [\"src/auth.py\"]. For dirs: [\"scripts/\"]. "
        "Or set allowlist_optional: true.",
    "cwd": "Set cwd to an existing directory, typically the repo root.",
    "backend": "Use one of: codex, claude, text, gemini, deepseek.",
    "task_id": "Add a unique task_id string.",
}


def _preflight_fix_advice(field: str, msg: str) -> str:
    """Map a Pydantic field error to actionable fix advice."""
    # Try exact match, then prefix match
    if field in _FIX_ADVICE:
        return _FIX_ADVICE[field]
    for prefix, advice in _FIX_ADVICE.items():
        if field.startswith(prefix):
            return advice
    return f"Fix the '{field}' field: {msg}"


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    tmp.replace(path)


def _task_summary_for_correction(raw_spec: dict) -> dict:
    """Return a bounded task summary safe to send to scillm for plan feedback."""
    dod = raw_spec.get("definition_of_done") or {}
    return {
        "task_id": raw_spec.get("task_id", "unknown"),
        "title": raw_spec.get("title", ""),
        "runner": raw_spec.get("runner", "code-runner"),
        "backend": raw_spec.get("backend", ""),
        "cwd": raw_spec.get("cwd", ""),
        "prompt_excerpt": str(raw_spec.get("prompt", ""))[:1000],
        "allowlist": raw_spec.get("allowlist"),
        "read_context": raw_spec.get("read_context", []),
        "definition_of_done": {
            "command": str(dod.get("command", ""))[:1000],
            "assertion": str(dod.get("assertion", ""))[:500],
        },
        "has_blind_tests": bool(raw_spec.get("blind_tests")),
        "service_under_test": raw_spec.get("service_under_test"),
        "external_service": raw_spec.get("external_service"),
    }


def _preflight_error_dicts(preflight_errors: list[PreflightError]) -> list[dict]:
    return [error.model_dump() for error in preflight_errors]


def _warning_dicts(misuse_warnings: list) -> list[dict]:
    return [
        {
            "field": getattr(warning, "field", ""),
            "message": getattr(warning, "message", ""),
            "suggestion": getattr(warning, "suggestion", ""),
        }
        for warning in misuse_warnings
    ]


def _infer_course_action(raw_spec: dict, preflight_errors: list[PreflightError]) -> tuple[str, str]:
    fields = {error.field for error in preflight_errors}
    error_text = " ".join(f"{error.field} {error.error}" for error in preflight_errors).lower()
    has_prompt = bool(str(raw_spec.get("prompt", "")).strip())
    has_command = bool(raw_spec.get("command") or (raw_spec.get("definition_of_done") or {}).get("command"))

    if "service_under_test" in fields or "live endpoint" in error_text:
        return "split_task", "scillm"
    if not has_prompt and has_command:
        return "use_local", "local"
    if "allowlist" in fields and not raw_spec.get("allowlist"):
        return "reroute_or_amend", "scillm"
    if "definition_of_done" in fields or "definition_of_done.command" in fields:
        return "amend_code_runner_contract", "code-runner"
    return "reroute_or_amend", "scillm"


def _deterministic_course_correction(
    raw_spec: dict,
    preflight_errors: list[PreflightError],
    misuse_warnings: list,
    source: str,
    scillm_error: str = "",
) -> dict:
    action, runner = _infer_course_action(raw_spec, preflight_errors)
    missing_fields = sorted({error.field for error in preflight_errors})
    corrections = {error.field: error.fix for error in preflight_errors if error.fix}
    split_tasks = []
    dod_command = str((raw_spec.get("definition_of_done") or {}).get("command", "") or raw_spec.get("command", ""))

    if action == "split_task":
        split_tasks = [
            {
                "runner": "code-runner",
                "purpose": "bounded implementation only",
                "required_additions": [
                    "prompt",
                    "allowlist",
                    "definition_of_done.command",
                    "definition_of_done.assertion",
                    "blind_tests",
                ],
            },
            {
                "runner": "local",
                "purpose": "restart/verify the live service from the main working directory",
                "command": dod_command,
            },
        ]

    return {
        "status": "blocked",
        "error_type": "incomplete_code_runner_contract",
        "source": source,
        "missing_fields": missing_fields,
        "recommended_action": action,
        "course_correction": {
            "message": "Code-runner preflight blocked this task before the LLM loop because the task contract is incomplete or misrouted.",
            "runner_recommendation": runner,
            "rationale": "Plan owns YAML amendment. Code-runner reports a course correction and does not silently mutate or execute an unsafe task.",
            "plan_patch": corrections,
            "split_tasks": split_tasks,
            "next_validation": [
                "Amend the plan YAML in /plan.",
                "Run plan.py --validate on the amended plan.",
                "Review the generated task spec before retrying.",
            ],
        },
        "preflight_errors": _preflight_error_dicts(preflight_errors),
        "preflight_warnings": _warning_dicts(misuse_warnings),
        "scillm": {
            "used": False,
            "error": scillm_error,
        },
    }


def _build_course_correction(
    raw_spec: dict,
    preflight_errors: list[PreflightError],
    misuse_warnings: list,
    source: str,
) -> dict:
    return _deterministic_course_correction(raw_spec, preflight_errors, misuse_warnings, source)


def _write_course_correction(output_dir: Path, task_id: str, course_correction: dict) -> Path:
    correction_file = output_dir / f"{task_id}.course_correction.json"
    _atomic_write_json(correction_file, course_correction)
    return correction_file


def _git_status_porcelain(cwd: str) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=GIT_TIMEOUT,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _source_status_changed(source_cwd: str, baseline: list[str]) -> list[str]:
    """Return current source status when it differs from the run baseline."""

    current = _git_status_porcelain(source_cwd)
    return current if current != baseline else []


def _dirty_overlaps_allowlist(dirty_entries: list[str], allowlist: list[str] | None) -> bool:
    if not dirty_entries:
        return False
    if not allowlist:
        return True
    allowed = [item.rstrip("/") for item in allowlist]
    for entry in dirty_entries:
        path = entry[3:] if len(entry) > 3 else entry
        path = path.strip()
        if any(path == item or path.startswith(f"{item}/") for item in allowed):
            return True
    return False


def _write_request_artifact(output_dir: Path, task_id: str, raw_spec: dict, spec_file: str) -> Path:
    request_file = output_dir / f"{task_id}.request.json"
    payload = {
        "task_id": task_id,
        "spec_file": str(Path(spec_file).resolve()),
        "captured_at": time.time(),
        "raw_spec": raw_spec,
        "status_protocol_version": "code-runner.status.v1",
    }
    _atomic_write_json(request_file, payload)
    return request_file


def _default_escalation_chain(backend: str) -> list[list[str]]:
    return [[backend, "high"]]


def _backend_model_name(backend: str) -> str:
    model_by_backend = {
        "codex": "gpt-5.5",
        "claude": "claude-sonnet-4-6",
        "gemini": "text-gemini",
        "text": "text",
        "deepseek": "deepseek-ai/DeepSeek-V3",
        "test": "test",
    }
    if backend not in model_by_backend:
        raise ValueError(f"Unsupported code-runner backend: {backend}")
    return model_by_backend[backend]


def _git_apply_patch(cwd: str, patch_file: Path) -> None:
    if not patch_file.exists() or not patch_file.read_text():
        return
    subprocess.run(
        ["git", "apply", "--whitespace=nowarn", str(patch_file)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=True,
    )


def _git_rev_parse_head(cwd: str) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=True,
    )
    return proc.stdout.strip()


def _git_staged_paths(cwd: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _restore_source_allowlist(cwd: str, allowlist: list[str]) -> None:
    if not allowlist:
        return
    subprocess.run(
        ["git", "restore", "--staged", "--worktree", "--", *allowlist],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=False,
    )
    subprocess.run(
        ["git", "clean", "-fd", "--", *allowlist],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=False,
    )


def _cleanup_new_untracked_non_allowlist(cwd: str, baseline_status: list[str], allowlist: list[str]) -> list[str]:
    baseline_entries = set(baseline_status)
    new_untracked: list[str] = []
    for entry in _git_status_porcelain(cwd):
        if not entry.startswith("?? ") or entry in baseline_entries:
            continue
        path = entry[3:].strip()
        allowed, _ = paths_within_allowlist([path.rstrip("/")], allowlist)
        if not allowed:
            new_untracked.append(path)
    if new_untracked:
        subprocess.run(
            ["git", "clean", "-fd", "--", *new_untracked],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    return new_untracked


def _commit_source_allowlist(cwd: str, allowlist: list[str], task_id: str, title: str) -> str:
    if not allowlist:
        raise RuntimeError("cannot commit source changes without an allowlist")
    subprocess.run(
        ["git", "add", "--", *allowlist],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=True,
    )
    staged = _git_staged_paths(cwd)
    staged_ok, staged_violations = paths_within_allowlist(staged, allowlist)
    if not staged_ok:
        raise RuntimeError(
            "commit_on_success would include staged paths outside allowlist: "
            + ", ".join(staged_violations[:20])
        )
    if not staged:
        raise RuntimeError("commit_on_success requested but no allowlisted changes are staged")
    message_title = " ".join((title or task_id).split())[:120]
    subprocess.run(
        ["git", "commit", "-m", f"code-runner: {task_id} - {message_title}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=True,
    )
    return _git_rev_parse_head(cwd)


def _finalize_source_apply(
    *,
    source_cwd: str,
    patch_artifact: Path,
    allowlist: list[str],
    dod_command: str,
    dod_assertion: str,
    lang: str,
    task_id: str,
    title: str,
    commit_on_success: bool,
    rollback_on_failure: bool,
) -> dict:
    state = {
        "source_patch_applied": False,
        "source_commit": "",
        "source_dod_passed": False,
        "source_rollback_applied": False,
        "source_apply_error": "",
    }
    if not patch_artifact.exists() or not patch_artifact.read_text().strip():
        state["source_apply_error"] = "apply_to_source requested but patch artifact is missing or empty"
        return state
    baseline_status = _git_status_porcelain(source_cwd)
    dirty_overlap = dirty_paths_for_allowlist(source_cwd, allowlist)
    if dirty_overlap:
        state["source_apply_error"] = (
            "source has dirty paths overlapping allowlist before apply: "
            + ", ".join(dirty_overlap[:20])
        )
        return state
    try:
        _emit_event("source_apply_started", task_id=task_id, patch_artifact=str(patch_artifact))
        _git_apply_patch(source_cwd, patch_artifact)
        state["source_patch_applied"] = True
        source_evidence = collect_evidence(source_cwd, dod_command, dod_assertion, lang)
        cleaned = _cleanup_new_untracked_non_allowlist(source_cwd, baseline_status, allowlist)
        if cleaned:
            logger.warning("Removed source DoD byproducts outside allowlist: {}", cleaned)
        state["source_dod_passed"] = bool(source_evidence.get("dod_passed"))
        if not state["source_dod_passed"]:
            state["source_apply_error"] = (
                "source DoD failed after applying patch: "
                + str(source_evidence.get("stdout") or source_evidence.get("stderr") or "")[:1000]
            )
            raise RuntimeError(state["source_apply_error"])
        if commit_on_success:
            state["source_commit"] = _commit_source_allowlist(source_cwd, allowlist, task_id, title)
        _emit_event(
            "source_apply_complete",
            task_id=task_id,
            source_commit=state["source_commit"],
            source_dod_passed=state["source_dod_passed"],
        )
    except Exception as exc:
        if not state["source_apply_error"]:
            state["source_apply_error"] = f"{type(exc).__name__}: {exc}"
        if rollback_on_failure:
            _restore_source_allowlist(source_cwd, allowlist)
            state["source_rollback_applied"] = True
        _emit_event(
            "source_apply_failed",
            task_id=task_id,
            error=state["source_apply_error"],
            rollback_applied=state["source_rollback_applied"],
        )
    return state


def _restore_round_state(
    cwd: str,
    base_commit: str,
    written_files: list[str],
    best_patch: Path | None,
    worktree_info: WorktreeInfo | None = None,
) -> None:
    if worktree_info is not None:
        restore_patch_base_tree(worktree_info)
    else:
        git_revert_to(cwd, base_commit, written_files)
    if best_patch is not None:
        _git_apply_patch(cwd, best_patch)


def _risk_report(raw_spec: dict, spec_file: str) -> dict:
    task_id = raw_spec.get("task_id", "unknown")
    output_dir = Path(raw_spec.get("output_dir", "/tmp/code-runner"))
    report: dict = {
        "task_id": task_id,
        "spec_file": str(Path(spec_file).resolve()),
        "valid": False,
        "danger_flags": [],
        "warnings": [],
    }

    misuse_errors, misuse_warnings = validate_task_spec(raw_spec, task_id)
    report["misuse_errors"] = [err.__dict__ for err in misuse_errors]
    report["misuse_warnings"] = [warn.__dict__ for warn in misuse_warnings]
    for err in misuse_errors:
        report["danger_flags"].append(f"misuse:{err.error_type}:{err.field}")

    try:
        spec = TaskSpec.model_validate(raw_spec)
    except Exception as exc:
        report["validation_error"] = str(exc)
        report["danger_flags"].append("spec_validation_failed")
        return report

    backend = raw_spec.get("backend") or spec.backend
    cwd = spec.cwd
    allowlist = spec.allowlist or []
    dod = spec.definition_of_done
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=GIT_TIMEOUT,
    )
    is_git_repo = git_dir_proc.returncode == 0
    dirty_entries = _git_status_porcelain(cwd) if is_git_repo else []

    if not is_git_repo:
        report["danger_flags"].append("cwd_is_not_git_repo")
    if dirty_entries:
        report["danger_flags"].append("dirty_worktree")
    if spec.has_weak_dod:
        report["danger_flags"].append("weak_dod")
    if "grep" in dod.command and dod.assertion:
        report["danger_flags"].append("dod_may_be_string_existence_check")
    if allowlist and not any(("test" in item.lower() or "spec" in item.lower()) for item in allowlist):
        report["warnings"].append("allowlist_missing_obvious_test_file")

    report.update({
        "valid": not misuse_errors,
        "title": spec.title,
        "cwd": cwd,
        "git_state": "dirty" if dirty_entries else ("clean" if is_git_repo else "not_git"),
        "dirty_entries": dirty_entries,
        "dirty_worktree_policy": spec.dirty_worktree_policy,
        "output_dir": str(output_dir),
        "artifacts": {
            "request": str(output_dir / f"{spec.task_id}.request.json"),
            "status": str(output_dir / f"{spec.task_id}.status.json"),
            "events": str(output_dir / f"{spec.task_id}.events.jsonl"),
            "rounds": str(output_dir / f"{spec.task_id}.rounds.jsonl"),
            "result": str(output_dir / f"{spec.task_id}.result.json"),
            "response": str(output_dir / f"{spec.task_id}.response.txt"),
            "hunk": str(output_dir / f"{spec.task_id}.hunk.md"),
            "verifier_log": str(output_dir / f"{spec.task_id}.verifier.log"),
        },
        "allowlist": allowlist,
        "read_context": spec.read_context,
        "definition_of_done": {
            "command": dod.command,
            "assertion": dod.assertion,
        },
        "backend": backend,
        "composition_mode": "minimal",
        "context_mode": "project",
        "tool_profile": "safe_fix",
    })
    return report


def _print_risk_report(report: dict) -> None:
    dod = report.get("definition_of_done", {})
    print(f"Task: {report.get('task_id', '?')}")
    if report.get("title"):
        print(f"Title: {report['title']}")
    print(f"CWD: {report.get('cwd', '?')}")
    print(f"Git state: {report.get('git_state', 'unknown')}")
    print(f"Dirty policy: {report.get('dirty_worktree_policy', 'isolated_worktree')}")
    print("Writable allowlist:")
    for item in report.get("allowlist") or ["<unrestricted: requires allowlist_optional>"]:
        print(f"  - {item}")
    print("Read-only context:")
    for item in report.get("read_context") or ["<none>"]:
        print(f"  - {item}")
    print("DoD:")
    print(f"  command: {dod.get('command', '(none)')}")
    print(f"  assertion: {dod.get('assertion', '(none)')}")
    print(f"Backend: {report.get('backend', '?')}")
    print(f"Composition mode: {report.get('composition_mode', 'minimal')}")
    print(f"Output dir: {report.get('output_dir', '?')}")
    print("Danger flags:")
    for flag in report.get("danger_flags") or ["<none>"]:
        print(f"  - {flag}")
    if report.get("warnings"):
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")


# ── Git Integration (autoresearch pattern) ───────────────────────────


def git_snapshot(cwd: str) -> str:
    """Return current HEAD commit hash."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_stash_save(cwd: str) -> bool:
    """Stash uncommitted changes before code-runner starts. Returns True if stashed.

    Only stashes tracked modifications (not untracked files) to avoid conflicts
    when code-runner commits new files that overlap with stashed untracked files.
    """
    proc = subprocess.run(
        ["git", "stash", "push", "-m", "code-runner-pre-run-stash"],
        capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    stashed = "Saved working directory" in proc.stdout
    if stashed:
        logger.info("Stashed pre-existing changes (tracked only)")
    return stashed


def git_stash_pop(cwd: str) -> None:
    """Restore stashed changes after code-runner finishes.

    Falls back to git stash drop if pop conflicts (e.g., code-runner committed
    files that overlap with stashed content).
    """
    proc = subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT)
    if proc.returncode != 0:
        # Conflict: code-runner committed files that clash with stash
        if "conflict" in proc.stderr.lower() or "already exists" in proc.stderr.lower():
            logger.warning("git stash pop conflict — dropping stash (code-runner committed overlapping files)")
            subprocess.run(["git", "stash", "drop"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT)
        else:
            logger.error("git stash pop FAILED — user changes may be trapped in stash: {}", proc.stderr[:300])
    else:
        logger.info("Restored stashed changes")


def git_commit_round(cwd: str, task_id: str, round_num: int, score: float,
                     written_files: list[str]) -> str:
    """Commit ONLY written files with code-runner metadata. Returns commit hash."""
    if not written_files:
        return ""
    # Stage only the files we wrote — not unrelated changes
    subprocess.run(["git", "add", "--"] + written_files, cwd=cwd, capture_output=True, timeout=GIT_TIMEOUT)
    msg = f"code-runner: {task_id} round {round_num} (score={score:.3f})"
    proc = subprocess.run(
        ["git", "commit", "-m", msg, "--no-verify"],
        capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    if proc.returncode != 0:
        logger.warning("git commit failed: {}", proc.stderr[:200])
        return ""
    return git_snapshot(cwd)


def git_revert_to(cwd: str, commit_hash: str, written_files: list[str]) -> None:
    """Revert ONLY written files to their state at commit_hash. Non-destructive.

    Handles both modified files (checkout) and NEW files created by the LLM
    that don't exist in best_commit (delete them).
    """
    if not commit_hash or not written_files:
        return
    # Separate files that exist in best_commit from new files
    existing_in_commit: list[str] = []
    new_files: list[str] = []
    for f in written_files:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{commit_hash}:{f}"],
            capture_output=True, cwd=cwd, timeout=GIT_TIMEOUT,
        )
        if proc.returncode == 0:
            existing_in_commit.append(f)
        else:
            new_files.append(f)

    # Restore modified files to their state at best_commit
    if existing_in_commit:
        subprocess.run(
            ["git", "checkout", commit_hash, "--"] + existing_in_commit,
            capture_output=True, cwd=cwd, timeout=GIT_TIMEOUT,
        )
    # Delete new files that don't exist in best_commit (LLM created them this round)
    for f in new_files:
        fpath = Path(cwd) / f
        try:
            if fpath.is_file() or fpath.is_symlink():
                fpath.unlink()
                logger.info("  Removed new file: {}", f)
            elif fpath.is_dir():
                logger.warning("  Skipped directory removal: {}", f)
        except OSError as e:
            logger.warning("  Failed to remove {}: {}", f, e)
    logger.info("Reverted {} files to {} (removed {} new)", len(existing_in_commit), commit_hash[:8], len(new_files))


# ── Experiment Log ───────────────────────────────────────────────────


def log_round(output_dir: Path, task_id: str, entry: dict, session_key: str = "") -> None:
    """Append round result to the local experiment log only."""
    # Local log (always — full history for debugging)
    log_file = output_dir / f"{task_id}.rounds.jsonl"
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")



# ── Dogpile Research (last resort before escalate) ───────────────────


def _call_llm(prompt: str, backend: str, cwd: str, temperature: float = 0.2,
              reasoning: str = "low", system_prompt: str = "",
              task_id: str = "", round_num: int = 0, strategy: str = "") -> str:
    """Call LLM backend to propose or fix code. Returns response text.

    ALL backends route through /scillm API (text in, text out). The agent
    controls what goes to disk via apply.py's allowlist enforcement.

    Temperature increases on repeated failures (LLMLOOP pattern) to break local minima.
    Reasoning escalation (low/medium/high) adjusts prompt strategy and depth.
    """
    model = {
        "codex": "gpt-5.5",
        "claude": "claude-sonnet-4-6",  # Fixed: was text-claude (invalid)
        "text": "text",
        "gemini": "text-gemini",
        "deepseek": "text",
    }.get(backend, "text")

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "messages": messages,
        "reasoning_effort": reasoning,
    }
    if not model.startswith("gpt-"):
        payload["temperature"] = min(temperature, 1.0)

    # scillm_metadata for llm_call_log correlation (round-trips untouched)
    if task_id:
        payload["scillm_metadata"] = {
            "task_id": task_id,
            "round": round_num,
            "strategy": strategy,
            "backend": backend,
            "reasoning": reasoning,
        }

    # Retry with backoff + jitter on transient errors
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # Build enhanced caller header: code-runner:{task_id}:{round}
            # Sanitize task_id to remove any chars that could break HTTP headers
            safe_task_id = "".join(c for c in task_id if c.isalnum() or c in "-_") if task_id else "unknown"
            caller_header = f"code-runner:{safe_task_id}:{round_num}"

            data = _stream_chat_completion(
                payload,
                headers={
                    "Authorization": f"Bearer {SCILLM_KEY}",
                    "X-Caller-Skill": caller_header,
                },
                event_emitter=None,
                round_num=round_num,
                idle_timeout=float(os.environ.get("CODE_RUNNER_IDLE_TIMEOUT", "90")),
                hard_wall_timeout=float(os.environ.get("CODE_RUNNER_ROUND_TIMEOUT", "180")),
            )
            return data["choices"][0]["message"].get("content", "")
        except (httpx.TimeoutException, TimeoutError):
            if attempt < max_retries:
                base = min(0.5 * (2 ** attempt), 32.0)
                wait = base + random.random() * 0.25 * base
                logger.warning("/scillm timeout (attempt {}/{}) — retrying in {:.1f}s",
                               attempt, max_retries, wait)
                time.sleep(wait)
                continue
            logger.error("/scillm timeout after {} attempts", max_retries)
            return f"ERROR: /scillm timeout after {max_retries} attempts"
        except Exception as e:
            logger.error("/scillm call failed: {}", e)
            return f"ERROR: /scillm call failed: {e}"
    return "ERROR: /scillm exhausted retries"


# ── Minimal Prompt Assembly ───────────────────────────────────────────


def _build_system_prompt(
    task_id: str,
    session_key: str,
    original_request: str,
    round_num: int,
    dod_desc: str = "",
    allowlist: list[str] | None = None,
    recent_rounds: list[dict] | None = None,
    skills_used: list[str] | None = None,
) -> str:
    """Build the self-contained runner prompt without optional composition."""

    recent = recent_rounds or []
    history = []
    for item in recent[-2:]:
        history.append(
            {
                "round": item.get("round"),
                "score": item.get("score"),
                "dod_passed": item.get("dod_passed"),
                "error_severity": item.get("error_severity"),
                "stderr": str(item.get("stderr", ""))[:1200],
                "stdout": str(item.get("stdout", ""))[:1200],
            }
        )
    return (
        "You are code-runner, a bounded code editing agent.\n"
        "Operate only through the provided tools. Edit only allowlisted paths. "
        "Do not modify the source repository directly; you are inside a disposable worktree.\n\n"
        f"Task id: {task_id}\n"
        f"Round: {round_num}\n"
        f"Original request:\n{original_request}\n\n"
        f"Definition of done:\n{dod_desc or '(none)'}\n\n"
        f"Writable allowlist:\n{json.dumps(allowlist or [])}\n\n"
        f"Recent evidence:\n{json.dumps(history, indent=2)}\n"
    )


# ── Main Loop (autoresearch pattern) ─────────────────────────────────


@app.command()
def run(
    spec_file: str = typer.Argument(..., help="Path to task spec JSON"),
    max_rounds: int = typer.Option(5, help="Max self-improvement rounds"),
    backend: str = typer.Option("", help="Override LLM backend"),
    debug: bool = typer.Option(False, "--debug", help="Generate debug HTML dashboard"),
) -> None:
    """Run task with autoresearch-pattern self-improvement loop."""
    # Wrap spec read in error handling — crash here = no stash to restore, but produce structured error
    try:
        raw_spec = json.loads(Path(spec_file).read_text())
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        logger.error("Cannot read spec file {}: {}", spec_file, e)
        sys.exit(1)

    # ── Misuse detection (catches common mistakes before Pydantic) ──────────────
    task_id = raw_spec.get("task_id", "unknown")
    output_dir = Path(raw_spec.get("output_dir", "/tmp/code-runner"))

    # Initialize event emitter for normalized events.jsonl output
    output_dir.mkdir(parents=True, exist_ok=True)
    emitter = EventEmitter(output_dir, task_id)
    emitter.emit(EventType.run_queued, payload={"spec_file": spec_file})
    emitter.emit(EventType.preflight_started)

    # Debug trace collector (only initialized when --debug is passed)
    trace_collector: TraceCollector | None = None
    if debug:
        trace_collector = TraceCollector(task_id=task_id)
        trace_collector.set_task_spec(raw_spec)

    misuse_errors, misuse_warnings = validate_task_spec(raw_spec, task_id)

    # Log warnings (non-fatal)
    for warn in misuse_warnings:
        logger.warning("[{}] {}", warn.field, warn.message)
        logger.warning("  SUGGESTION: {}", warn.suggestion)

    # Track preflight in debug trace
    if trace_collector:
        trace_collector.add_preflight(
            errors=[{"field": e.field, "message": e.message, "suggestion": e.correct_value} for e in misuse_errors],
            warnings=[{"field": w.field, "message": w.message, "suggestion": w.suggestion} for w in misuse_warnings],
        )

    # Fail on misuse errors (before Pydantic validation)
    if misuse_errors:
        logger.error("=== TASK SPEC MISUSE DETECTED for {} ({} issues) ===", task_id, len(misuse_errors))
        print(format_misuse_errors(misuse_errors, misuse_warnings), file=sys.stderr)

        output_dir.mkdir(parents=True, exist_ok=True)
        preflight_errors = [
            PreflightError(
                field=err.field,
                error=err.message,
                fix=err.correct_value or "See SKILL.md for correct usage.",
            )
            for err in misuse_errors
        ]
        result = TaskResult(
            task_id=task_id, title=raw_spec.get("title", ""),
            status="preflight_fail",
            preflight_errors=preflight_errors,
        )
        emitter.emit(
            EventType.preflight_failed,
            state_after=RunState.preflight_failed,
            reason_code=ReasonCode.bad_spec,
            payload={"errors": [e.model_dump() for e in preflight_errors]},
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)

    # ── Pydantic validation (declarative preflight) ──────────────
    try:
        spec = TaskSpec.model_validate(raw_spec)
    except Exception as e:
        # Convert Pydantic errors to actionable preflight errors
        preflight_errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                field = ".".join(str(x) for x in err.get("loc", []))
                preflight_errors.append(PreflightError(
                    field=field or "spec",
                    error=err.get("msg", str(e)),
                    fix=_preflight_fix_advice(field, err.get("msg", "")),
                ))
        else:
            preflight_errors.append(PreflightError(
                field="spec", error=str(e),
                fix="Check the task spec JSON against the TaskSpec schema.",
            ))

        logger.error("=== PRE-FLIGHT FAILED for {} ({} issues) ===", task_id, len(preflight_errors))
        for pf in preflight_errors:
            logger.error("  [{}] {}", pf.field, pf.error)
            logger.error("    FIX: {}", pf.fix)

        output_dir.mkdir(parents=True, exist_ok=True)
        result = TaskResult(
            task_id=task_id, title=raw_spec.get("title", ""),
            status="preflight_fail",
            preflight_errors=preflight_errors,
        )
        emitter.emit(
            EventType.preflight_failed,
            state_after=RunState.preflight_failed,
            reason_code=ReasonCode.bad_spec,
            payload={"errors": [e.model_dump() for e in preflight_errors]},
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)

    # Warn on weak DoD (not a failure, but logged)
    if spec.has_weak_dod:
        logger.warning("DoD has no assertion and doesn't run tests — LLM may game it")

    # FAIL on silent DoD mismatch (assertion will never match empty stdout)
    if spec.has_silent_dod_mismatch:
        logger.error("=== PRE-FLIGHT FAILED: DoD assertion will never match ===")
        logger.error("  {}", spec.silent_dod_detail)
        output_dir = Path(spec.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = TaskResult(
            task_id=spec.task_id, title=spec.title, status="preflight_fail",
            preflight_errors=[PreflightError(
                field="definition_of_done.assertion",
                error=spec.silent_dod_detail,
                fix="Use 'exit_code == 0' for commands that output nothing on success. "
                    "Or use a command that produces output (e.g., 'npx tsc --noEmit && echo passed').",
            )],
        )
        emitter.emit(
            EventType.preflight_failed,
            state_after=RunState.preflight_failed,
            reason_code=ReasonCode.bad_dod,
            payload={"error": spec.silent_dod_detail},
        )
        (output_dir / f"{spec.task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)

    # Extract validated fields
    task_id = spec.task_id
    title = spec.title
    prompt = spec.prompt
    llm_backend = backend or spec.backend
    lang = spec.lang  # Language profile: python, rust, typescript, or empty for auto-detect
    cwd = spec.cwd
    output_dir = Path(spec.output_dir)
    dod_command = spec.definition_of_done.command
    dod_assertion = spec.definition_of_done.assertion
    allowlist = spec.allowlist
    read_context = spec.read_context
    skills_used = spec.skills_used
    task_timeout_seconds = spec.timeout_seconds
    apply_to_source = spec.apply_to_source
    commit_on_success = spec.commit_on_success
    rollback_on_failure = spec.rollback_on_failure
    source_cwd = cwd
    source_status_baseline = _git_status_porcelain(source_cwd)
    previous_source_guard = os.environ.get("CODE_RUNNER_SOURCE_CWD")
    execution_mode = "isolated_worktree"
    worktree_info: WorktreeInfo | None = None
    worktree_path_for_result = ""
    worktree_removed = False
    patch_artifact = output_dir / f"{task_id}.patch"

    # Bug fix: spec max_rounds should override CLI default (5)
    # CLI --max-rounds only wins if explicitly passed (typer sets default=5)
    if spec.max_rounds != 5 and max_rounds == 5:
        max_rounds = spec.max_rounds

    # ── Preflight warnings (not hard failures, but logged for project agent) ──

    # Design decision detection — code-runner is an executor, not an architect
    if spec.is_design_decision:
        logger.error("PRE-FLIGHT WARNING: Prompt asks code-runner to make a DESIGN DECISION")
        logger.error("  Code-runner is a bounded executor. Architecture choices belong in /plan.")
        logger.error("  FIX: Choose the approach in /plan, then tell code-runner 'implement X using Y'.")

    # Unseen dependencies (empirical: 3+ unseen deps = ~50% fail rate on text backend)
    if spec.unseen_dep_count >= 3:
        logger.error("PRE-FLIGHT WARNING: {} modules referenced but not in allowlist or read_context: {}",
                     spec.unseen_dep_count, spec.unseen_deps)
        logger.error("  FIX: Add them to read_context so code-runner can extract interface maps.")

    # One backend per run. Health probing and provider fallback are intentionally
    # outside the core runner so deterministic preflight never makes a model call.
    escalation_chain: list[list[str]] = _default_escalation_chain(llm_backend)
    escalation_idx = 0

    logger.info("=== CODE-RUNNER v2: {} ===", title)
    logger.info("  Backend: {}", llm_backend)
    logger.info("  DoD: {}", dod_command[:100] if dod_command else "(none)")
    logger.info("  Max rounds: {}", max_rounds)

    dirty_policy = "isolated_worktree"
    if not allowlist:
            preflight_error = PreflightError(
                field="allowlist",
                error="isolated_worktree mode requires a non-empty allowlist.",
                fix="Provide the exact file paths code-runner may modify.",
            )
            result = TaskResult(
                task_id=task_id,
                title=title,
                status="preflight_fail",
                preflight_errors=[preflight_error],
                error=preflight_error.error,
                execution_mode="isolated_worktree",
            )
            (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
            sys.exit(1)
    try:
        dirty_overlap = dirty_paths_for_allowlist(source_cwd, allowlist)
    except WorktreeRuntimeError as exc:
        preflight_error = PreflightError(
            field="dirty_worktree_policy",
            error=f"Could not inspect source worktree dirty paths: {exc}",
            fix="Run from a valid git repository and provide allowlist paths inside that repository.",
        )
        result = TaskResult(
            task_id=task_id,
            title=title,
            status="preflight_fail",
            preflight_errors=[preflight_error],
            error=preflight_error.error,
            execution_mode="isolated_worktree",
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)
    if dirty_overlap:
        preflight_error = PreflightError(
            field="dirty_worktree_policy",
            error="Source worktree has uncommitted changes overlapping the code-runner allowlist.",
            fix=(
                "Commit, move, or explicitly review these paths before delegating: "
                + ", ".join(dirty_overlap[:20])
            ),
        )
        result = TaskResult(
            task_id=task_id,
            title=title,
            status="preflight_fail",
            preflight_errors=[preflight_error],
            error=preflight_error.error,
            execution_mode="isolated_worktree",
        )
        emitter.emit(
            EventType.dirty_worktree_detected,
            state_after=RunState.preflight_failed,
            reason_code=ReasonCode.dirty_worktree,
            payload={"dirty_paths": dirty_overlap},
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)
    try:
        worktree_info = create_disposable_worktree(source_cwd, task_id=task_id)
    except WorktreeRuntimeError as exc:
        preflight_error = PreflightError(
            field="dirty_worktree_policy",
            error=f"Could not create disposable worktree: {exc}",
            fix="Run from a valid git repository with a commit checked out and working git worktree support.",
        )
        result = TaskResult(
            task_id=task_id,
            title=title,
            status="preflight_fail",
            preflight_errors=[preflight_error],
            error=preflight_error.error,
            execution_mode="isolated_worktree",
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)
    cwd = str(worktree_info.path)
    worktree_path_for_result = cwd
    os.environ["CODE_RUNNER_SOURCE_CWD"] = str(Path(source_cwd).resolve())
    logger.info("  Worktree: {}", cwd)

    # Validate git repo — keep/discard pattern requires git
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    is_git_repo = git_dir_proc.returncode == 0
    git_dir = Path(cwd) / git_dir_proc.stdout.strip() if is_git_repo else None
    if not is_git_repo:
        logger.warning("cwd is NOT a git repo — keep/discard disabled, no hunk review")
    dirty_entries = _git_status_porcelain(cwd) if is_git_repo else []
    if dirty_entries:
        emitter.emit(
            EventType.dirty_worktree_detected,
            payload={"policy": dirty_policy, "entries": dirty_entries},
        )

    # ── DoD dry-run: verify the command is syntactically valid and runnable ──
    # Runs the DoD against the CURRENT cwd (before any LLM changes).
    # Expected to fail (code isn't fixed yet) but should NOT crash with syntax errors.
    dod_cmd = spec.definition_of_done.command
    if dod_cmd:
        try:
            dod_check = subprocess.run(
                ["bash", "-lc", dod_cmd],
                capture_output=True, text=True, timeout=15, cwd=cwd,
            )
            # If it crashes with bash/python syntax error (not assertion failure), warn
            if dod_check.returncode != 0 and "SyntaxError" in dod_check.stderr:
                logger.error("DoD command has SYNTAX ERROR — the command itself is broken:")
                logger.error("  {}", dod_check.stderr.strip().splitlines()[-1][:200] if dod_check.stderr.strip() else "unknown")
                output_dir = Path(spec.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                result = TaskResult(
                    task_id=spec.task_id, title=spec.title, status="preflight_fail",
                    preflight_errors=[PreflightError(
                        field="definition_of_done.command",
                        error=f"DoD command has Python SyntaxError: {dod_check.stderr.strip().splitlines()[-1][:200]}",
                        fix="Fix the syntax in the DoD command. Multi-line Python in -c requires proper escaping. "
                            "Consider using a test file instead of inline python3 -c.",
                    )],
                )
                emitter.emit(
                    EventType.preflight_failed,
                    state_after=RunState.preflight_failed,
                    reason_code=ReasonCode.bad_dod,
                    payload={"error": "DoD command has Python SyntaxError"},
                )
                (output_dir / f"{spec.task_id}.result.json").write_text(result.model_dump_json(indent=2))
                if worktree_info is not None:
                    remove_disposable_worktree(worktree_info)
                    worktree_removed = True
                    worktree_info = None
                sys.exit(1)
        except subprocess.TimeoutExpired:
            logger.warning("DoD dry-run timed out (15s) — proceeding anyway")
        except Exception:
            pass  # DoD may legitimately fail before code is written

    # Extract validated fields
    task_id = spec.task_id
    title = spec.title
    prompt = spec.prompt
    llm_backend = backend or spec.backend
    lang = spec.lang  # Language profile: python, rust, typescript, or empty for auto-detect
    cwd = spec.cwd
    output_dir = Path(spec.output_dir)
    dod_command = spec.definition_of_done.command
    dod_assertion = spec.definition_of_done.assertion
    allowlist = spec.allowlist
    read_context = spec.read_context
    skills_used = spec.skills_used

    # Bug fix: spec max_rounds should override CLI default (5)
    # CLI --max-rounds only wins if explicitly passed (typer sets default=5)
    if spec.max_rounds != 5 and max_rounds == 5:
        max_rounds = spec.max_rounds

    # ── Preflight warnings (not hard failures, but logged for project agent) ──

    # Design decision detection — code-runner is an executor, not an architect
    if spec.is_design_decision:
        logger.error("PRE-FLIGHT WARNING: Prompt asks code-runner to make a DESIGN DECISION")
        logger.error("  Code-runner is a bounded executor. Architecture choices belong in /plan.")
        logger.error("  FIX: Choose the approach in /plan, then tell code-runner 'implement X using Y'.")

    # Unseen dependencies (empirical: 3+ unseen deps = ~50% fail rate on text backend)
    if spec.unseen_dep_count >= 3:
        logger.error("PRE-FLIGHT WARNING: {} modules referenced but not in allowlist or read_context: {}",
                     spec.unseen_dep_count, spec.unseen_deps)
        logger.error("  FIX: Add them to read_context so code-runner can extract interface maps.")

    # Escalation chain
    default_chain = [
        [llm_backend, "medium"],
        [llm_backend, "high"],
        ["claude", "high"],
    ]
    escalation_chain: list[list[str]] = spec.escalation_chain or default_chain
    escalation_idx = 0

    logger.info("=== CODE-RUNNER v2: {} ===", title)
    logger.info("  Backend: {}", llm_backend)
    logger.info("  DoD: {}", dod_command[:100] if dod_command else "(none)")
    logger.info("  Max rounds: {}", max_rounds)

    # Validate git repo — keep/discard pattern requires git
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    is_git_repo = git_dir_proc.returncode == 0
    git_dir = Path(cwd) / git_dir_proc.stdout.strip() if is_git_repo else None
    if not is_git_repo:
        logger.warning("cwd is NOT a git repo — keep/discard disabled, no hunk review")

    # Repo lock: prevent concurrent code-runner runs in same repo
    lock_file = None
    if is_git_repo and git_dir:
        lock_path = git_dir / "code-runner.lock"
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error("Another code-runner is already running in {}. Aborting.", cwd)
            emitter.emit(
                EventType.run_blocked,
                state_after=RunState.blocked,
                reason_code=ReasonCode.repo_lock_conflict,
                payload={"cwd": cwd},
            )
            lock_file.close()
            if worktree_info is not None:
                remove_disposable_worktree(worktree_info)
                worktree_removed = True
                worktree_info = None
            sys.exit(1)

    # Session key links local artifacts for one invocation.
    session_key = f"cr-{task_id}-{int(time.time())}"
    failure_reason = ""  # populated on timeout, zero-writes, stash conflict
    run_start_time = time.monotonic()

    stashed = False

    # Create output dir AFTER stash — if output_dir is inside cwd, stash would remove it
    output_dir.mkdir(parents=True, exist_ok=True)
    verifier_log = output_dir / f"{task_id}.verifier.log"
    verifier_log.write_text(f"task_id={task_id}\nbackend={llm_backend}\ndod_command={dod_command}\n")

    # Git snapshot (autoresearch: remember where we started)
    snapshot = git_snapshot(cwd)

    rounds_history: list[dict] = []
    best_score = 0.0
    best_commit = snapshot

    # Emit run_started after all preflight checks pass
    emitter.emit(
        EventType.run_started,
        state_after=RunState.running,
        payload={"max_rounds": max_rounds, "backend": llm_backend, "cwd": cwd},
    )

    try:  # try/finally guarantees stash pop + lock release even on crash
        # Staged context escalation: start with interface maps for read_context,
        # then promote specific files to full content after failure.
        escalated_files: set[str] = set()  # read_context files promoted to full content after failure
        file_context = build_file_context(allowlist, cwd, read_context, escalated_files)

        # Format instructions are in system prompt (v2) — user prompt is just task + files
        current_prompt = prompt + "\n\n" + file_context
        final_response = ""
        temperature = 0.2  # Dynamic: increments by 0.1 on repeated same-error (LLMLOOP pattern)
        grounding_reminder = ""  # source grounding reminder for next round (if LLM didn't reference actual error)
        last_error_ev = None  # ErrorEvidence from previous round for grounding verification

        # Self-contained system prompt: fixed context plus local round history.
        # Original request + DoD are embedded as immutable anchors to prevent drift
        dod_desc = f"Command: {dod_command}\nAssertion: {dod_assertion}" if dod_command else ""
        system_prompt = _build_system_prompt(
            task_id, session_key, prompt, round_num=1,
            dod_desc=dod_desc, allowlist=allowlist, recent_rounds=[],
            skills_used=skills_used)

        consecutive_zero_writes = 0
        MAX_CONSECUTIVE_ZERO_WRITES = 3

        for round_num in range(1, max_rounds + 1):
            # 1. Determine strategy (deterministic)
            # Classify from both stderr AND stdout — many tools (pytest, custom scripts) print failures to stdout
            prev_output = (rounds_history[-1].get("stderr", "") + "\n" + rounds_history[-1].get("stdout", "")) if rounds_history else ""
            classification = classify_errors(prev_output) if rounds_history else {"severity": "unknown", "total": 0, "error_types": {}}
            strategy = get_strategy(round_num, classification, rounds_history)

            # Dynamic temperature + escalation on stagnation (same error OR no score improvement)
            same_error_repeating = False
            score_stagnant = False
            if len(rounds_history) >= 2:
                prev_sev = rounds_history[-1].get("error_severity", "")
                prev_prev_sev = rounds_history[-2].get("error_severity", "")
                same_error_repeating = bool(prev_sev and prev_sev == prev_prev_sev)
                score_stagnant = rounds_history[-1].get("score", 0) <= rounds_history[-2].get("score", 0)

            if same_error_repeating or score_stagnant:
                temperature = min(temperature + 0.1, 1.0)
                escalation_idx = min(escalation_idx + 1, len(escalation_chain) - 1)

            cur_backend, cur_reasoning = escalation_chain[escalation_idx]
            round_start_time = time.time()
            _emit_event("round_start", task_id=task_id, round=round_num,
                        max_rounds=max_rounds, strategy=strategy,
                        backend=cur_backend, reasoning=cur_reasoning,
                        temperature=round(temperature, 2))
            emitter.emit(
                EventType.round_started,
                round=round_num,
                payload={"strategy": strategy, "backend": cur_backend, "temperature": round(temperature, 2)},
            )
            if trace_collector:
                trace_collector.add_round_start(round_num)
            if same_error_repeating:
                logger.info("── Round {}/{} [strategy={} temp={:.1f}↑ {}:{}] ──",
                            round_num, max_rounds, strategy, temperature, cur_backend, cur_reasoning)
            else:
                logger.info("── Round {}/{} [strategy={} {}:{}] ──",
                            round_num, max_rounds, strategy, cur_backend, cur_reasoning)

            if strategy == "escalate":
                # Dogpile already ran on first repeated error (round 3+).
                # If we're here, previous bounded strategies did not pass DoD.
                last = rounds_history[-1] if rounds_history else {}
                diagnosis = {
                    "escalation": "all strategies exhausted",
                    "rounds_attempted": len(rounds_history),
                    "persistent_error": last.get("error_severity", "unknown"),
                    "error_evidence": last.get("error_evidence"),
                    "strategies_tried": [r.get("strategy") for r in rounds_history],
                    "external_research_used": False,
                    "best_score": best_score,
                    "recommendation": "Task needs project agent intervention or decomposition into smaller subtasks.",
                }
                (output_dir / f"{task_id}.diagnosis.json").write_text(
                    json.dumps(diagnosis, indent=2, default=str))
                logger.warning("Strategy: ESCALATE — diagnosis written to {}.diagnosis.json", task_id)
                break

            # 2. Call LLM (the 10% agent part)
            if round_num > 1:
                evidence = rounds_history[-1]

                # Staged context escalation: if error references a read_context file, promote to full content
                err_ev = evidence.get("error_evidence") or {}
                err_loc = err_ev.get("primary_location") or {}
                err_file = err_loc.get("file", "")
                if err_file and read_context:
                    for rc in read_context:
                        if err_file.endswith(rc) or rc.endswith(err_file) or Path(err_file).name == Path(rc).name:
                            if rc not in escalated_files:
                                escalated_files.add(rc)
                                logger.info("  Context escalation: {} promoted to full content", rc)

                file_context = build_file_context(allowlist, cwd, read_context, escalated_files)

                from stderr_parser import condense_stderr, grounding_reminder_prompt, verify_fix_grounding
                error_ev_obj = condense_stderr(
                    evidence.get("stderr", ""), evidence.get("stdout", ""),
                )
                last_error_ev = error_ev_obj  # Store for grounding verification after LLM response
                current_prompt = build_fix_prompt(
                    evidence,
                    rounds_history,
                    strategy,
                    prompt,
                    file_context,
                    allowlist=allowlist,
                )

                # Add grounding reminder if previous fix didn't reference actual error
                if grounding_reminder:
                    current_prompt += "\n\n" + grounding_reminder

            # Refresh system prompt every round with latest round history
            if round_num > 1:
                system_prompt = _build_system_prompt(
                    task_id, session_key, prompt, round_num,
                    dod_desc=dod_desc, allowlist=allowlist,
                    recent_rounds=rounds_history)

            # 2. Call LLM via tool_use agent loop
            model_name = _backend_model_name(cur_backend)

            if os.environ.get("CODE_RUNNER_ROUND_TIMEOUT"):
                ROUND_TIMEOUT = int(os.environ["CODE_RUNNER_ROUND_TIMEOUT"])
            else:
                ROUND_TIMEOUT = min(max(task_timeout_seconds, 60), 600)
                logger.info("  Round timeout: {}s", ROUND_TIMEOUT)
            try:
                written, tool_messages = run_tool_use_loop(
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                    model=model_name,
                    cwd=cwd,
                    allowlist=allowlist,
                    read_context=read_context,
                    temperature=temperature,
                    reasoning=cur_reasoning,
                    max_tokens=min(
                        {"low": 4000, "medium": 8000, "high": 16000}.get(cur_reasoning, 4000),
                        int(os.environ.get(
                            "CODE_RUNNER_TOOL_MAX_TOKENS",
                            os.environ.get("CODE_RUNNER_MAX_TOKENS", "2048"),
                        )),
                    ),
                    dod_command=dod_command,
                    event_emitter=emitter,
                    round_num=round_num,
                    task_id=task_id,
                    idle_timeout=float(os.environ.get("CODE_RUNNER_IDLE_TIMEOUT", "90")),
                    hard_wall_timeout=float(ROUND_TIMEOUT),
                )
            except TimeoutError as exc:
                _emit_event("round_timeout", task_id=task_id, round=round_num,
                            timeout_seconds=ROUND_TIMEOUT, error=str(exc))
                emitter.emit(
                    EventType.round_timeout,
                    round=round_num,
                    state_after=RunState.timed_out,
                    reason_code=ReasonCode.backend_timeout,
                    payload={"timeout_seconds": ROUND_TIMEOUT, "error": str(exc)},
                )
                logger.error("  ROUND TIMEOUT: {}", exc)
                failure_reason = (f"Round {round_num} timed out after {ROUND_TIMEOUT}s. "
                                  "The SSE transport did not produce progress before its idle or wall-clock budget.")
                written, tool_messages = [], []

            # Compress tool trace for inter-round context persistence
            trace_events, trace_text = compress_tool_trace(tool_messages)
            trace_events_json = trace_events_to_dict(trace_events)

            source_status_after_tools = _source_status_changed(source_cwd, source_status_baseline)
            if source_status_after_tools:
                failure_reason = (
                    "Source repository changed during isolated code-runner execution. "
                    "This usually means a tool command wrote outside the disposable worktree."
                )
                emitter.emit(
                    EventType.run_blocked,
                    round=round_num,
                    state_after=RunState.blocked,
                    reason_code=ReasonCode.dirty_worktree,
                    payload={"source_status": source_status_after_tools},
                )
                logger.error("  SOURCE MUTATION DETECTED: {}", source_status_after_tools)
                _restore_round_state(
                    cwd,
                    snapshot,
                    written,
                    patch_artifact if patch_artifact.exists() else None,
                    worktree_info=worktree_info,
                )
                break

            # Extract final text response (last assistant message without tool_calls)
            response = ""
            for m in reversed(tool_messages):
                if m.get("role") == "assistant" and not m.get("tool_calls"):
                    response = m.get("content", "")
                    break
            final_response = response
            llm_metadata = {"summary": response[:200], "approach": strategy}
            tool_call_count = sum(1 for m in tool_messages if m.get("role") == "assistant" and m.get("tool_calls"))
            _emit_event("tool_use_complete", task_id=task_id, round=round_num,
                        files_written=len(written), tool_calls=tool_call_count)

            # Source grounding verification: check if fix references actual error
            grounding_score = 1.0  # Default: assume grounded (round 1 has no prior error)
            if round_num > 1 and last_error_ev and response:
                grounding_result = verify_fix_grounding(last_error_ev, response, threshold=0.5)
                grounding_score = grounding_result.score
                if not grounding_result.is_grounded:
                    logger.warning("  GROUNDING LOW: {:.2f} — fix may not address actual error", grounding_score)
                    logger.warning("    Matched: {}; Missing: {}",
                                   grounding_result.matched_terms[:3],
                                   grounding_result.missing_terms[:3])
                    grounding_reminder = grounding_reminder_prompt(grounding_result, last_error_ev)
                    _emit_event("grounding_low", task_id=task_id, round=round_num,
                                score=grounding_score,
                                matched=grounding_result.matched_terms[:3],
                                missing=grounding_result.missing_terms[:3])
                else:
                    grounding_reminder = ""  # Clear reminder if grounding is now good
                    logger.info("  Grounding: {:.2f} (terms: {})", grounding_score,
                                grounding_result.matched_terms[:3])
            llm_metadata["grounding_score"] = grounding_score

            # Track LLM response in debug trace
            if trace_collector:
                # Extract tool calls from messages
                all_tool_calls = []
                for m in tool_messages:
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            all_tool_calls.append({
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", ""),
                            })
                trace_collector.add_llm_response(
                    round_num=round_num,
                    content=response[:500] if response else None,
                    tool_calls=all_tool_calls,
                    finish_reason="tool_calls" if all_tool_calls else "stop",
                )

            # Save round response
            round_file = output_dir / f"{task_id}.round_{round_num}.txt"
            if response:
                round_file.write_text(response)
            else:
                round_file.write_text(json.dumps({"tool_iterations": len(tool_messages)}))

            if written:
                logger.info("  Applied {} files: {}", len(written), written)
                consecutive_zero_writes = 0

            else:
                consecutive_zero_writes += 1
                emitter.emit(
                    EventType.zero_write_detected,
                    round=round_num,
                    payload={"consecutive_count": consecutive_zero_writes},
                )
                if consecutive_zero_writes >= MAX_CONSECUTIVE_ZERO_WRITES:
                    _emit_event("early_abort", task_id=task_id, round=round_num,
                                reason=f"{consecutive_zero_writes} consecutive rounds wrote 0 files")
                    emitter.emit(
                        EventType.run_blocked,
                        round=round_num,
                        state_after=RunState.blocked,
                        reason_code=ReasonCode.zero_write,
                        payload={"consecutive_count": consecutive_zero_writes},
                    )
                    logger.error("  EARLY ABORT: {} consecutive rounds wrote 0 files — LLM not producing edits",
                                 consecutive_zero_writes)
                    failure_reason = (f"LLM wrote 0 files for {consecutive_zero_writes} consecutive rounds. "
                                      f"Backend '{llm_backend}' may not be executing tool calls. "
                                      f"Try backend 'codex' or check scillm health.")
                    break

            actual_changed_paths: list[str] = []
            if is_git_repo and execution_mode == "isolated_worktree" and worktree_info is not None:
                changed_entries = changed_path_statuses(worktree_info)
                actual_changed_paths = sorted({path for _status, path in changed_entries})
                allowlist_ok, allowlist_violations = paths_within_allowlist(actual_changed_paths, allowlist)
                if not allowlist_ok:
                    untracked_violations = [
                        path for status, path in changed_entries
                        if status == "??" and path in allowlist_violations
                    ]
                    if untracked_violations:
                        logger.warning(
                            "  Removing untracked non-allowlist byproducts from disposable worktree: {}",
                            untracked_violations,
                        )
                        remove_untracked_paths(worktree_info, untracked_violations)
                        changed_entries = changed_path_statuses(worktree_info)
                        actual_changed_paths = sorted({path for _status, path in changed_entries})
                        allowlist_ok, allowlist_violations = paths_within_allowlist(
                            actual_changed_paths,
                            allowlist,
                        )
                if not allowlist_ok:
                    failure_reason = (
                        "Non-allowlist changes detected in isolated worktree: "
                        + ", ".join(allowlist_violations)
                    )
                    emitter.emit(
                        EventType.run_blocked,
                        round=round_num,
                        state_after=RunState.blocked,
                        reason_code=ReasonCode.bad_spec,
                        payload={
                            "changed_paths": actual_changed_paths,
                            "allowlist_violations": allowlist_violations,
                        },
                    )
                    _restore_round_state(
                        cwd,
                        snapshot,
                        written,
                        patch_artifact if patch_artifact.exists() else None,
                        worktree_info=worktree_info,
                    )
                    break
                if actual_changed_paths and not written:
                    logger.warning(
                        "  Detected filesystem changes not reported by tool loop: {}",
                        actual_changed_paths,
                    )
                    written = actual_changed_paths

            # 3. T0 deterministic evidence collection (NOW evaluates changed files)
            evidence_raw = collect_evidence(cwd, dod_command, dod_assertion, lang=lang)
            score = evidence_raw["score"]
            emitter.emit(
                EventType.evidence_collected,
                round=round_num,
                payload={
                    "score": round(score, 4),
                    "dod_passed": evidence_raw["dod_passed"],
                    "error_count": evidence_raw["error_count"],
                    "lint_violations": evidence_raw["lint_violations"],
                },
            )

            # If LLM wrote zero files AND DoD didn't pass, force score to 0.
            # But if DoD genuinely passes (work already done, or read-only task),
            # respect that — don't override a real pass.
            if not written:
                if not evidence_raw["dod_passed"]:
                    score = 0.0
                    evidence_raw["score"] = 0.0
                    evidence_raw["_zero_files_override"] = True
                evidence_raw["_zero_write_reason"] = "tool_use_no_writes"
            _emit_event("round_score", task_id=task_id, round=round_num,
                        score=round(score, 4), dod_passed=evidence_raw["dod_passed"],
                        errors=evidence_raw["error_count"], lint=evidence_raw["lint_violations"],
                        files_written=len(written),
                        zero_write_reason=evidence_raw.get("_zero_write_reason", ""))
            emitter.emit(
                EventType.round_scored,
                round=round_num,
                payload={
                    "score": round(score, 4),
                    "dod_passed": evidence_raw["dod_passed"],
                    "error_count": evidence_raw["error_count"],
                    "files_written": len(written),
                },
            )
            emitter.set_score(score)  # Track best score in run.json
            logger.info("  Score: {:.3f} (DoD:{} errors:{} lint:{} bp:{})",
                         score, evidence_raw["dod_passed"], evidence_raw["error_count"],
                         evidence_raw["lint_violations"], len(evidence_raw["bp_violations"]))

            # Save full stdout/stderr per round (untruncated, for debugging)
            log_dir = output_dir / "logs"
            log_dir.mkdir(exist_ok=True)
            (log_dir / f"round_{round_num}_stdout.txt").write_text(evidence_raw.get("stdout_full", evidence_raw["stdout"]))
            (log_dir / f"round_{round_num}_stderr.txt").write_text(evidence_raw.get("stderr_full", evidence_raw["stderr"]))
            with verifier_log.open("a") as verifier:
                verifier.write(f"\n=== round {round_num} ===\n")
                verifier.write(f"score={score:.4f}\n")
                verifier.write(f"dod_passed={evidence_raw['dod_passed']}\n")
                verifier.write("stdout:\n")
                verifier.write(evidence_raw.get("stdout_full", evidence_raw["stdout"]))
                verifier.write("\nstderr:\n")
                verifier.write(evidence_raw.get("stderr_full", evidence_raw["stderr"]))
                verifier.write("\n")

            # Condense stderr into structured evidence for logging
            from stderr_parser import condense_stderr
            error_ev = condense_stderr(evidence_raw["stderr"], evidence_raw["stdout"])
            evidence_raw["error_evidence"] = {
                "failure_type": error_ev.failure_type,
                "summary": error_ev.summary,
                "primary_location": {
                    "file": error_ev.primary_location.file,
                    "line": error_ev.primary_location.line,
                } if error_ev.primary_location else None,
                "root_cause_lines": error_ev.root_cause_lines,
                "failing_tests": error_ev.failing_tests,
            }

            # 4. Keep/discard (autoresearch pattern) — epsilon threshold avoids churn
            EPSILON = 0.01
            prev_best = best_score
            if score > best_score + EPSILON:
                if execution_mode == "isolated_worktree":
                    if is_git_repo and actual_changed_paths:
                        export_allowlist_patch(worktree_info, allowlist, patch_artifact)  # type: ignore[arg-type]
                    best_score = score
                    best_commit = snapshot
                    status = "keep"
                    logger.info("  KEEP (score {:.3f} > previous {:.3f}; exported patch, no commit)", score, prev_best)
                else:
                    commit = git_commit_round(cwd, task_id, round_num, score, written) if is_git_repo else ""
                    if is_git_repo and not commit:
                        # Git commit failed — revert files to maintain filesystem/score consistency
                        git_revert_to(cwd, best_commit, written)
                        status = "discard"
                        logger.warning("  DISCARD (score improved but git commit failed — reverted files)")
                    else:
                        best_score = score
                        best_commit = commit or best_commit
                        status = "keep"
                        logger.info("  KEEP (score {:.3f} > previous {:.3f})", score, prev_best)
            else:
                if is_git_repo and execution_mode == "isolated_worktree":
                    _restore_round_state(
                        cwd,
                        snapshot,
                        written,
                        patch_artifact if patch_artifact.exists() else None,
                        worktree_info=worktree_info,
                    )
                elif is_git_repo:
                    git_revert_to(cwd, best_commit, written)
                status = "discard"
                logger.info("  DISCARD (score {:.3f} <= best {:.3f})", score, best_score)

            _emit_event("round_decision", task_id=task_id, round=round_num,
                        status=status, score=round(score, 4), best_score=round(best_score, 4))
            if status == "keep":
                emitter.emit(
                    EventType.round_kept,
                    round=round_num,
                    payload={"score": round(score, 4), "prev_best": round(prev_best, 4)},
                )
            else:
                emitter.emit(
                    EventType.round_discarded,
                    round=round_num,
                    payload={"score": round(score, 4), "best_score": round(best_score, 4)},
                )

            # 5. Log round — structured context for next iteration and audit trail
            round_entry = {
                # Identity
                "round": round_num,
                "task_id": task_id,
                # Scoring
                "score": score,
                "prev_score": rounds_history[-1]["score"] if rounds_history else 0,
                "delta": score - (rounds_history[-1]["score"] if rounds_history else 0),
                "dod_passed": evidence_raw["dod_passed"],
                # Decision
                "status": status,
                "strategy": strategy,
                # Errors (fed back to LLM in fix prompt)
                "error_count": evidence_raw["error_count"],
                "error_severity": evidence_raw["error_severity"],
                "errors_by_type": evidence_raw["errors_by_type"],
                "lint_violations": evidence_raw["lint_violations"],
                "bp_violations": evidence_raw["bp_violations"],
                # Condensed error evidence (structured, not raw dump)
                "error_evidence": evidence_raw.get("error_evidence"),
                # Output (truncated for prompt; full logs in output/logs/)
                "stdout": evidence_raw["stdout"][:1000],
                "stderr": evidence_raw["stderr"][:1000],
                # Files
                "written_files": written,
                "commit": best_commit[:8] if best_commit else "",
                "backend": cur_backend, "reasoning": cur_reasoning,
                "temperature": round(temperature, 1),
                "timestamp": evidence_raw["timestamp"],
                # v2 JSON header: LLM's self-reported summary/approach
                "llm_summary": (llm_metadata or {}).get("summary", ""),
                "llm_approach": (llm_metadata or {}).get("approach", ""),
                # Zero-write diagnosis (only present when LLM wrote nothing)
                "zero_write_reason": evidence_raw.get("_zero_write_reason", ""),
                # Tool call trace (compressed text for prompt and local artifacts)
                "tool_trace": trace_text,
                "tool_trace_events": trace_events_json,
                "model": cur_backend,
                "duration_ms": int((time.time() - round_start_time) * 1000),
                "prompt_snippet": f"{title}: {strategy}",
                "response_snippet": (llm_metadata or {}).get("summary", "")[:200] or trace_text[:200],
            }
            rounds_history.append(round_entry)

            # Save structured context JSON per round (debuggable inter-round contract)
            (log_dir / f"round_{round_num}_context.json").write_text(
                json.dumps(round_entry, indent=2, default=str))

            log_round(output_dir, task_id, round_entry, session_key=session_key)

            # 6. Check if DoD passed
            if evidence_raw["dod_passed"]:
                _emit_event("dod_passed", task_id=task_id, round=round_num,
                            score=round(score, 4), total_rounds=round_num)
                emitter.emit(
                    EventType.dod_passed,
                    round=round_num,
                    payload={"score": round(score, 4), "total_rounds": round_num},
                )
                logger.info("=== DoD PASSED on round {} (score={:.3f}) ===", round_num, score)
                break

        # Final outputs
        response_file = output_dir / f"{task_id}.response.txt"
        response_file.write_text(final_response)

        status = "pass" if rounds_history and rounds_history[-1]["dod_passed"] else "fail"
        source_apply_state = {
            "source_patch_applied": False,
            "source_commit": "",
            "source_dod_passed": False,
            "source_rollback_applied": False,
            "source_apply_error": "",
        }
        if not rounds_history:
            failure_reason = failure_reason or "No rounds completed. Check git state and scillm connectivity."
        elif not failure_reason and status == "fail":
            last = rounds_history[-1]
            failure_reason = (f"DoD failed after {len(rounds_history)} rounds. "
                              f"Best score: {best_score:.3f}. Last strategy: {last.get('strategy', '?')}.")
        if status == "pass" and apply_to_source:
            source_apply_state = _finalize_source_apply(
                source_cwd=source_cwd,
                patch_artifact=patch_artifact,
                allowlist=allowlist or [],
                dod_command=dod_command,
                dod_assertion=dod_assertion,
                lang=lang,
                task_id=task_id,
                title=title,
                commit_on_success=commit_on_success,
                rollback_on_failure=rollback_on_failure,
            )
            if not source_apply_state["source_patch_applied"] or not source_apply_state["source_dod_passed"]:
                status = "fail"
                failure_reason = source_apply_state["source_apply_error"] or "source apply failed"
            elif commit_on_success and not source_apply_state["source_commit"]:
                status = "fail"
                failure_reason = "commit_on_success requested but no source commit was created"
        result = TaskResult(
            task_id=task_id, title=title,
            status=status,
            rounds=len(rounds_history), best_score=best_score,
            dod_passed=(rounds_history[-1]["dod_passed"] if rounds_history else False) and status == "pass",
            backend=llm_backend,
            best_commit=best_commit[:8] if best_commit else "",
            error=failure_reason,
            round_details=rounds_history,
            execution_mode=execution_mode,
            patch_artifact=str(patch_artifact) if patch_artifact.exists() else "",
            worktree_path=worktree_path_for_result,
            worktree_removed=False,
            apply_to_source=apply_to_source,
            source_patch_applied=source_apply_state["source_patch_applied"],
            source_commit=source_apply_state["source_commit"],
            source_dod_passed=source_apply_state["source_dod_passed"],
            source_rollback_applied=source_apply_state["source_rollback_applied"],
            source_apply_error=source_apply_state["source_apply_error"],
        )
        result_file = output_dir / f"{task_id}.result.json"
        result_file.write_text(result.model_dump_json(indent=2))

        _emit_event("run_complete", task_id=task_id, status=result.status,
                    score=round(best_score, 4), rounds=len(rounds_history),
                    dod_passed=result.dod_passed, backend=llm_backend)
        if result.dod_passed:
            emitter.emit(
                EventType.run_passed,
                state_after=RunState.passed,
                payload={"score": round(best_score, 4), "rounds": len(rounds_history)},
            )
        else:
            emitter.emit(
                EventType.run_failed,
                state_after=RunState.failed,
                reason_code=ReasonCode.max_rounds_exhausted,
                payload={"score": round(best_score, 4), "rounds": len(rounds_history), "error": failure_reason},
            )
        logger.info("=== RESULT: {} | score={:.3f} | {} rounds ===",
                     result.status.upper(), best_score, len(rounds_history))

        if execution_mode == "isolated_worktree":
            hunk_file = output_dir / f"{task_id}.hunk.md"
            patch_text = patch_artifact.read_text() if patch_artifact.exists() else ""
            hunk_file.write_text(
                f"# Code-Runner Review: {task_id}\n\n"
                f"**Task:** {title}\n"
                f"**Mode:** isolated_worktree\n"
                f"**DoD passed:** {result.dod_passed}\n"
                f"**Patch artifact:** {patch_artifact if patch_artifact.exists() else '(none)'}\n\n"
                "## Allowlist-Scoped Patch\n\n"
                "```diff\n"
                f"{patch_text}"
                "\n```\n"
            )
            logger.info("Review with: hunk patch {}", hunk_file)
        elif is_git_repo:
            generate_hunk_review(output_dir, task_id, cwd, rounds_history, snapshot)

        # Generate debug dashboard if --debug was passed
        if trace_collector:
            trace_collector.set_result(
                success=result.dod_passed,
                dod_passed=result.dod_passed,
                files_written=[f for r in rounds_history for f in r.get("written_files", [])],
                error_message=failure_reason if not result.dod_passed else None,
            )
            dashboard_html = generate_dashboard(trace_collector)
            dashboard_path = output_dir / f"{task_id}.debug.html"
            dashboard_path.write_text(dashboard_html)
            logger.info("Debug dashboard: {}", dashboard_path)

        print(final_response)

        if not result.dod_passed:
            sys.exit(1)
    except Exception as exc:
        # ── Crash reporting: write result.json + structured event so failures are NEVER silent ──
        import traceback
        crash_msg = f"{type(exc).__name__}: {exc}"
        crash_tb = traceback.format_exc()
        logger.critical("CODE-RUNNER CRASHED: {}", crash_msg)
        logger.critical("Traceback:\n{}", crash_tb)
        _emit_event("crash", task_id=task_id, error=crash_msg,
                     traceback=crash_tb[-500:])
        # Emit normalized crash event (emitter may not exist if crash was early)
        if 'emitter' in dir():
            emitter.emit(
                EventType.run_crashed,
                state_after=RunState.crashed,
                reason_code=ReasonCode.runner_exception,
                payload={"error": crash_msg, "traceback": crash_tb[-500:]},
            )
        # Write result.json so orchestrator has structured failure data
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            crash_result = TaskResult(
                task_id=task_id, title=title,
                status="crash",
                rounds=len(rounds_history) if 'rounds_history' in dir() else 0,
                best_score=best_score if 'best_score' in dir() else 0,
                dod_passed=False,
                backend=llm_backend,
                error=f"CRASH: {crash_msg}",
                round_details=rounds_history if 'rounds_history' in dir() else [],
            )
            crash_result_file = output_dir / f"{task_id}.result.json"
            crash_result_file.write_text(crash_result.model_dump_json(indent=2))
            logger.info("Crash result written to {}", crash_result_file)
        except Exception as write_exc:
            logger.error("Failed to write crash result: {}", write_exc)
        raise  # re-raise so exit code is still non-zero
    finally:
        if previous_source_guard is None:
            os.environ.pop("CODE_RUNNER_SOURCE_CWD", None)
        else:
            os.environ["CODE_RUNNER_SOURCE_CWD"] = previous_source_guard
        if worktree_info is not None:
            try:
                remove_disposable_worktree(worktree_info)
                worktree_removed = True
                result_path = output_dir / f"{task_id}.result.json"
                if result_path.exists():
                    result_data = json.loads(result_path.read_text())
                    result_data["worktree_removed"] = True
                    result_data["worktree_path"] = worktree_path_for_result
                    result_data["patch_artifact"] = str(patch_artifact) if patch_artifact.exists() else ""
                    result_path.write_text(json.dumps(result_data, indent=2))
            finally:
                worktree_info = None
        # Always restore stashed changes, even on crash
        if stashed:
            git_stash_pop(cwd)
        # Release repo lock and remove lock file
        if lock_file:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
                lock_path = git_dir / "code-runner.lock" if git_dir else None
                if lock_path and lock_path.exists():
                    lock_path.unlink()
            except Exception:
                pass  # best-effort cleanup


def _find_status_file(target: str) -> Path:
    candidate = Path(target)
    if candidate.is_file():
        return candidate
    if candidate.is_dir():
        status_files = sorted(candidate.glob("*.status.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if status_files:
            return status_files[0]
        legacy = candidate / "run.json"
        if legacy.exists():
            return legacy
    search_roots = [Path.cwd(), Path("/tmp/code-runner")]
    for root in search_roots:
        direct = root / f"{target}.status.json"
        if direct.exists():
            return direct
        if root.exists():
            matches = sorted(root.glob(f"**/{target}.status.json"), key=lambda path: path.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
    raise typer.BadParameter(f"Could not find status for {target}")


def _tail_events(events_file: Path, count: int) -> list[dict]:
    if count <= 0 or not events_file.exists():
        return []
    lines = events_file.read_text().splitlines()[-count:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})
    return events


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Print machine-readable diagnostics")) -> None:
    """Report environment readiness for code-runner."""
    checks = {
        "git": shutil.which("git") is not None,
        "bash": shutil.which("bash") is not None,
        "uv": shutil.which("uv") is not None,
        "scillm_url": SCILLM_URL,
        "scillm_key_present": bool(SCILLM_KEY),
        "skills_dir": str(SKILLS_DIR),
        "cwd": os.getcwd(),
        "cwd_is_git_repo": subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            cwd=os.getcwd(),
            timeout=GIT_TIMEOUT,
        ).returncode == 0,
        "tmp_output_writable": os.access("/tmp", os.W_OK),
        "status_protocol_version": "code-runner.status.v1",
    }
    checks["ok"] = bool(checks["git"] and checks["bash"] and checks["uv"] and checks["tmp_output_writable"])
    if json_output:
        print(json.dumps(checks, indent=2, default=_json_default))
        return
    for key, value in checks.items():
        print(f"{key}: {value}")


@app.command()
def status(
    target: str = typer.Argument(..., help="Output directory, status file, or task_id"),
    tail_events: int = typer.Option(0, "--tail-events", help="Print the last N events"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable status"),
) -> None:
    """Summarize a code-runner run from status/events artifacts."""
    status_file = _find_status_file(target)
    payload = json.loads(status_file.read_text())
    events_file = Path(payload.get("artifacts", {}).get("events") or status_file.with_name(status_file.name.replace(".status.json", ".events.jsonl")))
    events = _tail_events(events_file, tail_events)
    if json_output:
        enriched = dict(payload)
        if events:
            enriched["events_tail"] = events
        print(json.dumps(enriched, indent=2, default=_json_default))
        return
    print(f"task_id: {payload.get('task_id') or payload.get('run_id')}")
    print(f"state: {payload.get('state')}")
    print(f"reason_code: {payload.get('reason_code')}")
    print(f"current_round: {payload.get('current_round')}")
    print(f"best_score: {payload.get('best_score')}")
    print(f"status_file: {status_file}")
    print(f"events_file: {events_file}")
    for event in events:
        print(json.dumps(event, default=_json_default))


@app.command()
def watch(
    target: str = typer.Argument(..., help="Output directory, status file, or task_id"),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval in seconds"),
    tail_events: int = typer.Option(5, "--tail-events", help="Print the last N events on each refresh"),
) -> None:
    """Watch status until the run reaches a terminal state."""
    while True:
        status_file = _find_status_file(target)
        payload = json.loads(status_file.read_text())
        print(
            f"{time.strftime('%H:%M:%S')} state={payload.get('state')} "
            f"round={payload.get('current_round')} best={payload.get('best_score')}"
        )
        events_file = Path(payload.get("artifacts", {}).get("events") or status_file.with_name(status_file.name.replace(".status.json", ".events.jsonl")))
        for event in _tail_events(events_file, tail_events):
            print(f"  {event.get('event', event.get('raw'))}")
        if str(payload.get("state")) in TERMINAL_STATES:
            return
        time.sleep(interval)


@app.command(name="dry-run")
def dry_run(spec_file: str = typer.Argument(..., help="Path to task spec JSON")) -> None:
    """Show what would execute without calling LLM."""
    spec = json.loads(Path(spec_file).read_text())
    dod = spec.get("definition_of_done", {})
    print(f"Task:      {spec.get('title', '?')}")
    print(f"Backend:   {spec.get('backend', 'text')}")
    print(f"CWD:       {spec.get('cwd', os.getcwd())}")
    print(f"DoD cmd:   {dod.get('command', '(none)')}")
    print(f"DoD assert: {dod.get('assertion', '(none)')}")
    print(f"Prompt:    {spec.get('prompt', '')[:200]}...")


if __name__ == "__main__":
    app()
