"""Typer CLI for the replacement code-runner.

The CLI is intentionally thin: it validates a spec, owns run lifecycle, and
delegates git, DoD, artifacts, tools, and scillm work to focused modules.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from pydantic import ValidationError
from rich.console import Console

from .adapters import run_backend_tool_loop
from .artifacts import RunArtifacts, append_event, json_default, write_json
from .dod import run_dod
from .spec import RoundDetail, TaskResult, TaskSpec
from .worktree import (
    all_allowed,
    apply_patch,
    changed_paths,
    commit_allowlist,
    create,
    dirty_paths_for_allowlist,
    export_patch,
    head,
    mirror_dependency_dirs,
    remove,
    repo_root,
    restore_allowlist,
    status,
)


app = typer.Typer(no_args_is_help=True)
console = Console()


def is_ignored_byproduct(path: str) -> bool:
    """Return true for generated files ignored by allowlist checks."""

    parts = Path(path).parts
    return (
        "__pycache__" in parts
        or path.endswith((".pyc", ".pyo"))
        or path in {"package-lock.json", "npm-shrinkwrap.json"}
        or any(part.endswith(".egg-info") for part in parts)
    )


def load_spec(spec_file: str) -> tuple[dict[str, Any], TaskSpec]:
    """Load and validate a task spec."""

    raw = json.loads(Path(spec_file).read_text())
    return raw, TaskSpec.model_validate(raw)


def system_prompt(spec: TaskSpec) -> str:
    """Build a compact backend system prompt."""

    return (
        "You are code-runner. Use tools to make the smallest allowlisted change.\n"
        f"Editable files: {', '.join(spec.allowlist)}\n"
        f"Read context: {', '.join(spec.read_context) or '(none)'}\n"
        f"DoD command: {spec.definition_of_done.command}\n"
        f"DoD assertion: {spec.definition_of_done.assertion}\n"
        "Never edit outside the allowlist. Stop when the DoD passes.\n"
    )


def file_context(root: Path, paths: list[str]) -> str:
    """Return bounded context for allowlist/read-context paths."""

    blocks: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_absolute():
            continue
        target = root / path
        if not target.exists() or target.is_dir():
            continue
        text = target.read_text(errors="replace")[:8000]
        blocks.append(f"--- {raw_path} ---\n{text}")
    return "\n\n".join(blocks)


def round_prompt(spec: TaskSpec, previous: dict[str, Any] | None, context: str) -> str:
    """Build the user prompt for a round."""

    instruction = (
        "This is an implementation task. You must make at least one allowlisted "
        "write with write_file or edit_file, then verify the DoD. "
        "Do not answer with prose only.\n"
    )
    if previous is None:
        return f"{spec.prompt}\n\n{instruction}\nCurrent file context:\n{context}"
    return (
        f"{spec.prompt}\n\n"
        f"{instruction}\n"
        "Previous DoD evidence:\n"
        f"exit_code={previous.get('exit_code')}\n"
        f"stdout:\n{str(previous.get('stdout') or '')[-3000:]}\n"
        f"stderr:\n{str(previous.get('stderr') or '')[-3000:]}\n"
        f"\nCurrent file context:\n{context}"
    )


def write_preflight_failure(raw: dict[str, Any], spec_file: str, error: str) -> int:
    """Write a preflight failure result without backend calls."""

    task_id = str(raw.get("task_id") or "unknown")
    output_dir = str(raw.get("output_dir") or "/tmp/code-runner")
    artifacts = RunArtifacts(output_dir, task_id)
    write_json(artifacts.request, {"spec_file": spec_file, "raw_spec": raw})
    artifacts.write_status("preflight_fail", error=error)
    result = TaskResult(
        task_id=task_id,
        title=str(raw.get("title") or ""),
        status="preflight_fail",
        dod_passed=False,
        backend=str(raw.get("backend") or ""),
        rounds=0,
        best_score=0,
        error=error,
    )
    write_json(artifacts.result, result.model_dump())
    console.print_json(data=result.model_dump())
    return 1


def source_apply(spec: TaskSpec, patch: Path) -> dict[str, Any]:
    """Apply a passing patch to source for explicit complete-task specs."""

    state: dict[str, Any] = {
        "source_patch_applied": False,
        "source_dod_passed": False,
        "source_commit": "",
        "source_rollback_applied": False,
        "source_apply_error": "",
    }
    if not spec.apply_to_source:
        return state
    try:
        if not patch.read_text().strip():
            state["source_apply_error"] = "empty patch; no allowlisted changes produced"
            return state
        dirty = dirty_paths_for_allowlist(spec.cwd, spec.allowlist)
        if dirty:
            state["source_apply_error"] = f"dirty source paths overlap allowlist: {', '.join(dirty)}"
            return state
        apply_patch(spec.cwd, patch)
        state["source_patch_applied"] = bool(patch.read_text().strip())
        dod = run_dod(
            spec.cwd,
            spec.definition_of_done.command,
            spec.definition_of_done.assertion,
            timeout=min(spec.timeout_seconds, 600),
        )
        state["source_dod_passed"] = dod.passed
        if not dod.passed:
            state["source_apply_error"] = dod.stderr or dod.stdout or "source DoD failed"
            if spec.rollback_on_failure:
                restore_allowlist(spec.cwd, spec.allowlist)
                state["source_rollback_applied"] = True
            return state
        if spec.commit_on_success:
            state["source_commit"] = commit_allowlist(
                spec.cwd,
                spec.allowlist,
                f"code-runner: {spec.title}",
            )
    except Exception as exc:
        logger.error("source apply failed: {}", exc)
        state["source_apply_error"] = str(exc)
        if spec.rollback_on_failure:
            restore_allowlist(spec.cwd, spec.allowlist)
            state["source_rollback_applied"] = True
    return state


def finish_result(
    spec: TaskSpec,
    artifacts: RunArtifacts,
    backend: str,
    rounds: list[dict[str, Any]],
    best_score: float,
    error: str,
    status_text: str,
    work: Any,
    source_head_before: str,
    source_status_before: list[str],
    source_state: dict[str, Any],
) -> TaskResult:
    """Remove the disposable worktree and write the final result artifact."""

    worktree_removed = False
    if work is not None:
        worktree_removed = remove(work)
    source_head_after = head(work.repo if work is not None else spec.cwd)
    source_status_after = status(work.repo if work is not None else spec.cwd)
    source_unchanged = (
        source_head_before == source_head_after
        and source_status_before == source_status_after
    )
    if spec.apply_to_source and status_text == "pass":
        source_unchanged = source_status_after == []
    result = TaskResult(
        task_id=spec.task_id,
        title=spec.title,
        status=status_text,
        dod_passed=status_text == "pass",
        backend=backend,
        rounds=len(rounds),
        best_score=best_score,
        error=error,
        patch_artifact=str(artifacts.patch),
        worktree_path=str(work.path) if work is not None else "",
        worktree_removed=worktree_removed,
        source_head_before=source_head_before,
        source_head_after=source_head_after,
        source_status_before=source_status_before,
        source_status_after=source_status_after,
        source_unchanged=source_unchanged,
        round_details=rounds,
        apply_to_source=spec.apply_to_source,
        **source_state,
    )
    write_json(artifacts.result, result.model_dump())
    artifacts.write_status(status_text, error=error)
    append_event(artifacts.events, "run_finished", task_id=spec.task_id, status=status_text, error=error)
    return result


def run_task(spec: TaskSpec, raw: dict[str, Any], spec_file: str, backend_override: str = "", max_rounds_override: int = 0) -> TaskResult:
    """Run one task through isolated worktree and optional source apply."""

    artifacts = RunArtifacts(spec.output_dir, spec.task_id)
    try:
        source_root = repo_root(spec.cwd)
    except Exception as exc:
        error = str(exc)
        write_json(artifacts.request, {"spec_file": spec_file, "raw_spec": raw})
        artifacts.write_status("preflight_fail", error=error)
        result = TaskResult(
            task_id=spec.task_id,
            title=spec.title,
            status="preflight_fail",
            dod_passed=False,
            backend=backend_override or spec.backend,
            rounds=0,
            best_score=0,
            error=error,
            source_unchanged=True,
        )
        write_json(artifacts.result, result.model_dump())
        append_event(artifacts.events, "preflight_failed", task_id=spec.task_id, error=error)
        return result
    source_head_before = head(source_root)
    source_status_before = status(source_root)
    backend = backend_override or spec.backend
    max_rounds = max_rounds_override if max_rounds_override > 0 else spec.max_rounds
    write_json(artifacts.request, {"spec_file": spec_file, "raw_spec": raw})
    artifacts.write_status("running")
    append_event(artifacts.events, "run_started", task_id=spec.task_id)

    work = None
    worktree_removed = False
    rounds: list[dict[str, Any]] = []
    best_score = 0.0
    error = ""
    status_text = "fail"
    source_state: dict[str, Any] = {}
    try:
        work = create(source_root, spec.task_id)
        mirrored = mirror_dependency_dirs(source_root, work.path)
        os.environ["CODE_RUNNER_SOURCE_CWD"] = str(source_root)
        append_event(
            artifacts.events,
            "worktree_created",
            task_id=spec.task_id,
            worktree_path=str(work.path),
            mirrored_dependency_dirs=mirrored,
        )
        evidence = run_dod(
            work.path,
            spec.definition_of_done.command.replace(str(source_root), str(work.path)),
            spec.definition_of_done.assertion,
            timeout=min(spec.timeout_seconds, 600),
        )
        artifacts.verifier.write_text(json.dumps(evidence.to_dict(), indent=2) + "\n")
        if evidence.passed:
            export_patch(work.path, spec.allowlist, artifacts.patch)
            artifacts.hunk.write_text("# code-runner patch\n\n```diff\n" + artifacts.patch.read_text(errors="replace") + "\n```\n")
            status_text = "pass"
            best_score = evidence.score
            source_state = {
                "source_patch_applied": False,
                "source_dod_passed": bool(spec.apply_to_source),
                "source_commit": "",
                "source_rollback_applied": False,
                "source_apply_error": "",
            }
            append_event(
                artifacts.events,
                "already_satisfied",
                task_id=spec.task_id,
                dod_passed=True,
                source_dod_passed=bool(spec.apply_to_source),
            )
            return finish_result(
                spec,
                artifacts,
                backend,
                rounds,
                best_score,
                error,
                status_text,
                work,
                source_head_before,
                source_status_before,
                source_state,
            )
        previous = evidence.to_dict()
        best_score = evidence.score
        context = file_context(work.path, spec.allowlist + spec.read_context)
        for round_num in range(1, max_rounds + 1):
            written, messages = run_backend_tool_loop(
                system_prompt(spec),
                round_prompt(spec, previous, context),
                backend,
                str(work.path),
                spec.allowlist,
                spec.read_context,
                spec.task_id,
                round_num,
            )
            assistant_text = ""
            for message in reversed(messages):
                if message.get("role") == "assistant":
                    assistant_text = str(message.get("content") or "")[:1000]
                    break
            artifacts.response.write_text(json.dumps(messages[-8:], indent=2, default=json_default))
            paths = [path for path in changed_paths(work.path) if not is_ignored_byproduct(path)]
            allowed, violations = all_allowed(paths, spec.allowlist)
            if violations:
                restore_allowlist(work.path, violations)
                paths = [path for path in changed_paths(work.path) if not is_ignored_byproduct(path)]
                allowed, violations = all_allowed(paths, spec.allowlist)
            evidence = run_dod(
                work.path,
                spec.definition_of_done.command.replace(str(source_root), str(work.path)),
                spec.definition_of_done.assertion,
                timeout=min(spec.timeout_seconds, 600),
            )
            previous = evidence.to_dict()
            best_score = max(best_score, evidence.score)
            round_error = ""
            if not allowed:
                round_error = f"allowlist violations: {', '.join(violations)}"
            elif evidence.passed and not paths:
                round_error = "no allowlisted changes produced"
            detail = RoundDetail(
                round=round_num,
                status="pass" if allowed and evidence.passed and paths else "fail",
                dod_passed=evidence.passed,
                score=evidence.score,
                written_files=written,
                changed_paths=paths,
                error=round_error,
            ).model_dump()
            detail["assistant_response_snippet"] = assistant_text
            detail["exit_code"] = evidence.exit_code
            detail["stdout_tail"] = evidence.stdout[-3000:]
            detail["stderr_tail"] = evidence.stderr[-3000:]
            rounds.append(detail)
            append_event(artifacts.rounds, "round", **detail)
            artifacts.verifier.write_text(json.dumps(evidence.to_dict(), indent=2) + "\n")
            if allowed and evidence.passed and paths:
                status_text = "pass"
                break
            restore_allowlist(work.path, spec.allowlist)
            context = file_context(work.path, spec.allowlist + spec.read_context)
        if status_text != "pass":
            if any(detail.get("error") == "no allowlisted changes produced" for detail in rounds):
                error = "no allowlisted changes produced"
            else:
                error = "definition_of_done did not pass"
        export_patch(work.path, spec.allowlist, artifacts.patch)
        artifacts.hunk.write_text("# code-runner patch\n\n```diff\n" + artifacts.patch.read_text(errors="replace") + "\n```\n")
        if status_text == "pass":
            source_state = source_apply(spec, artifacts.patch)
            if spec.apply_to_source and (
                not source_state.get("source_dod_passed")
                or source_state.get("source_apply_error")
            ):
                status_text = "fail"
                error = str(source_state.get("source_apply_error") or "source DoD failed")
    except Exception as exc:
        logger.error("run failed: {}", exc)
        error = str(exc)
        status_text = "fail"
    finally:
        os.environ.pop("CODE_RUNNER_SOURCE_CWD", None)
        if work is not None:
            worktree_removed = remove(work)

    source_head_after = head(source_root)
    source_status_after = status(source_root)
    source_unchanged = (
        source_head_before == source_head_after
        and source_status_before == source_status_after
    )
    if spec.apply_to_source and status_text == "pass":
        source_unchanged = source_status_after == []
    result = TaskResult(
        task_id=spec.task_id,
        title=spec.title,
        status=status_text,
        dod_passed=status_text == "pass",
        backend=backend,
        rounds=len(rounds),
        best_score=best_score,
        error=error,
        patch_artifact=str(artifacts.patch),
        worktree_path=str(work.path) if work is not None else "",
        worktree_removed=worktree_removed,
        source_head_before=source_head_before,
        source_head_after=source_head_after,
        source_status_before=source_status_before,
        source_status_after=source_status_after,
        source_unchanged=source_unchanged,
        round_details=rounds,
        apply_to_source=spec.apply_to_source,
        **source_state,
    )
    write_json(artifacts.result, result.model_dump())
    artifacts.write_status(status_text, error=error)
    append_event(artifacts.events, "run_finished", task_id=spec.task_id, status=status_text, error=error)
    return result


@app.command()
def run(
    spec_file: str = typer.Argument(...),
    max_rounds: int = typer.Option(0, "--max-rounds"),
    backend: str = typer.Option("", "--backend"),
) -> None:
    """Run one code-runner task."""

    try:
        raw, spec = load_spec(spec_file)
    except FileNotFoundError as exc:
        raise typer.Exit(write_preflight_failure({}, spec_file, f"spec file could not be read: {exc}"))
    except json.JSONDecodeError as exc:
        raise typer.Exit(write_preflight_failure({}, spec_file, f"spec file is not valid JSON: {exc}"))
    except ValidationError as exc:
        try:
            raw = json.loads(Path(spec_file).read_text())
        except Exception:
            raw = {}
        raise typer.Exit(write_preflight_failure(raw, spec_file, str(exc)))
    result = run_task(spec, raw, spec_file, backend_override=backend, max_rounds_override=max_rounds)
    console.print_json(data=result.model_dump())
    raise typer.Exit(0 if result.status == "pass" else 1)


@app.command("dry-run")
def dry_run(spec_file: str = typer.Argument(...), json_output: bool = typer.Option(False, "--json")) -> None:
    """Validate and summarize a spec without execution."""

    raw, spec = load_spec(spec_file)
    data = {"ok": True, "task_id": spec.task_id, "backend": spec.backend, "allowlist": spec.allowlist, "raw_spec_keys": sorted(raw)}
    if json_output:
        console.print_json(data=data)
    else:
        console.print_json(data=data)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    """Print environment diagnostics."""

    data = {"runner": "src-code-runner", "python": sys.version.split()[0], "scillm": os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1/chat/completions")}
    if json_output:
        console.print_json(data=data)
    else:
        console.print_json(data=data)


if __name__ == "__main__":
    app()
