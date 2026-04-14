"""Structured plan executor for /orchestrate.

Executes JSON/YAML orchestration plans explicitly by runner type:
- local: deterministic shell command
- skill: compiled skill invocation via run.sh (no LLM, deterministic subprocess)
- scillm: one-shot HTTP completion
- code-runner: iterative run-and-debug loop via /code-runner skill

Note: subagent-service is deprecated. Tasks with runner=subagent-service are
auto-migrated to code-runner or scillm by structured_execute_helpers._build_runtimes().
Any remaining subagent-service tasks fall back to scillm at execution time.

Fully async — all runners use asyncio so the event loop can:
- Kill any task mid-stream via cancel events
- React to PAUSE/KILL/ABORT files within 2 seconds

Intervention (Factory Droid pattern):
- Touch PAUSE in session dir → halts after current task OR mid-stream
- Touch KILL_<task_id> → kills that task's subprocess immediately
- Touch ABORT → kills all running tasks and stops the plan

There is no markdown fallback here. If a structured task lacks the fields needed
for its runner, execution fails fast.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from _shared.structured_plan import load_structured_plan, validate_structured_plan  # type: ignore

from structured_execute_helpers import (  # noqa: E402
    SCILLM_KEY,
    SCILLM_URL,
    SKILLS_DIR,
    STATE_ROOT,
    WATCHDOG_POLL_S,
    TaskRuntime,
    _build_runtimes,
    _build_system_prompt,
    _compile_skill_task,
    _dependency_graph,
    _render_state,
    _subagent_backend_name,
    render_report,
)

app = typer.Typer(add_completion=False)


# ---------------------------------------------------------------------------
# Async runners
# ---------------------------------------------------------------------------

async def _run_subagent_via_scillm(task: TaskRuntime, session_dir: Path) -> str:
    """Fallback for deprecated subagent-service tasks -- routes through scillm."""
    logger.warning(
        "Task {} uses deprecated runner 'subagent-service' — falling back to scillm",
        task.task_id,
    )
    # Delegate to _run_scillm which handles the HTTP completion
    return await _run_scillm(task, session_dir)




async def _run_local(task: TaskRuntime, session_dir: Path) -> str:
    """Run a shell command with cancel support via process kill."""
    # Strip .venv paths so local commands use system/project tools
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    clean_env["PATH"] = os.pathsep.join(
        p for p in clean_env.get("PATH", "").split(os.pathsep)
        if ".venv" not in p
    )
    proc = await asyncio.create_subprocess_shell(
        task.command, cwd=task.cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=clean_env,
    )
    task._proc = proc

    # Wait for completion or cancel
    cancel_task = asyncio.create_task(_wait_for_cancel(task))
    try:
        stdout, stderr = await proc.communicate()
    finally:
        cancel_task.cancel()
        task._proc = None

    if task._cancel_event.is_set():
        raise RuntimeError(f"Task {task.task_id} cancelled by operator")

    output = (stdout.decode() if stdout else "") + (("\n" + stderr.decode()) if stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {task.command}\n{output}".strip())
    output_path = session_dir / f"{task.task_id}.stdout.txt"
    output_path.write_text(output)
    task.output_path = output_path
    return output


async def _run_skill(task: TaskRuntime, session_dir: Path) -> str:
    """Run a compiled skill invocation via run.sh subprocess.

    Like _run_local but the command is built from skill/skill_command/skill_args
    at compile time by _compile_skill_task(). The skill's run.sh is invoked
    directly — no LLM involved, just deterministic subprocess execution.
    """
    skill_dir = SKILLS_DIR / task.skill
    run_sh = skill_dir / "run.sh"
    cmd_parts = ["bash", str(run_sh)]
    if task.skill_command:
        cmd_parts.append(task.skill_command)
    cmd_parts.extend(task.skill_args)

    logger.info("Running skill /{} {} {}", task.skill, task.skill_command, " ".join(task.skill_args))

    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    clean_env["PATH"] = os.pathsep.join(
        p for p in clean_env.get("PATH", "").split(os.pathsep)
        if ".venv" not in p
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd_parts, cwd=str(task.cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=clean_env,
    )
    task._proc = proc

    cancel_task = asyncio.create_task(_wait_for_cancel(task))
    try:
        stdout, stderr = await proc.communicate()
    finally:
        cancel_task.cancel()
        task._proc = None

    if task._cancel_event.is_set():
        raise RuntimeError(f"Task {task.task_id} cancelled by operator")

    output = (stdout.decode() if stdout else "") + (("\n" + stderr.decode()) if stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(
            f"Skill /{task.skill} {task.skill_command} failed ({proc.returncode}):\n{output}".strip()
        )
    output_path = session_dir / f"{task.task_id}.stdout.txt"
    output_path.write_text(output)
    task.output_path = output_path
    return output


async def _run_scillm(task: TaskRuntime, session_dir: Path) -> str:
    """One-shot LLM completion via scillm with cancel support."""
    if not task.prompt:
        raise RuntimeError("scillm task has no prompt")
    async with httpx.AsyncClient(timeout=120.0) as client:
        request_task = asyncio.create_task(client.post(
            SCILLM_URL,
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={"model": task.backend or "text",
                  "messages": [{"role": "user", "content": task.prompt}],
                  "max_tokens": 1200},
        ), name=f"scillm-{task.task_id}")
        cancel_task = asyncio.create_task(task._cancel_event.wait(), name="cancel-wait")

        done, pending = await asyncio.wait(
            [request_task, cancel_task], return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

        if task._cancel_event.is_set():
            raise RuntimeError(f"Task {task.task_id} cancelled by operator")

        # HTTP request won the race — extract response while client is still open
        response = request_task.result()
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

    output_path = session_dir / f"{task.task_id}.response.txt"
    output_path.write_text(content)
    task.output_path = output_path
    return content


async def _wait_for_cancel(task: TaskRuntime) -> None:
    """Block until cancel event is set, then kill the task's subprocess."""
    await task._cancel_event.wait()
    proc = task._proc  # local ref — avoids race if _proc set to None concurrently
    if proc and proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def _execute_task(task: TaskRuntime, session_dir: Path) -> None:
    task.status = "running"
    task.started_at = time.time()
    try:
        if task.runner == "local":
            await _run_local(task, session_dir)
        elif task.runner == "scillm":
            await _run_scillm(task, session_dir)
        elif task.runner == "subagent-service":
            # Deprecated: fall back to scillm
            await _run_subagent_via_scillm(task, session_dir)
        elif task.runner == "skill":
            # Compiled skill invocation — deterministic subprocess via run.sh
            await _run_skill(task, session_dir)
        elif task.runner == "code-runner":
            # Deterministic run-and-debug loop via /code-runner skill
            await _run_code_runner(task, session_dir)
        else:
            raise RuntimeError(f"Unsupported runner: {task.runner}")
        # code-runner sets review_status + error but doesn't raise.
        # If review_status is "fail" or error is set, the task FAILED.
        if task.review_status == "fail" or (task.error and task.runner == "code-runner"):
            task.status = "failed"
            if not task.error:
                task.error = f"code-runner review_status=fail: {task.review_output[:200]}"
            raise RuntimeError(task.error)
        task.status = "completed"
    except Exception as exc:
        task.status = "failed"
        if not task.error:
            task.error = str(exc)
        raise
    finally:
        task.finished_at = time.time()


async def _setup_worktree(task_cwd: Path, task_id: str) -> tuple[Path, str]:
    """Create a git worktree for isolated parallel code-runner execution."""
    import tempfile
    branch = f"cr-{task_id}-{int(time.time())}"
    worktree_dir = Path(tempfile.mkdtemp(prefix=f"cr-wt-{task_id}-"))

    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", "-b", branch, str(worktree_dir),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(task_cwd),
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {stderr.decode()[:300]}")
    logger.info("  Worktree: {} (branch: {})", worktree_dir, branch)
    return worktree_dir, branch


async def _merge_worktree(task_cwd: Path, branch: str, task_id: str) -> bool:
    """Merge worktree branch back to the original branch. Returns True on success."""
    proc = await asyncio.create_subprocess_exec(
        "git", "merge", "--no-edit", branch,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(task_cwd),
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("  Merge failed for {}: {}", task_id, stderr.decode()[:300])
        abort = await asyncio.create_subprocess_exec(
            "git", "merge", "--abort",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(task_cwd),
        )
        await abort.communicate()
        return False
    logger.info("  Merged {} back", branch)
    return True


async def _cleanup_worktree(task_cwd: Path, worktree_dir: Path, branch: str) -> None:
    """Remove worktree and its branch."""
    import shutil
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "remove", "--force", str(worktree_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(task_cwd),
        )
        await proc.communicate()
    except Exception:
        pass
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir, ignore_errors=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "-D", branch,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(task_cwd),
        )
        await proc.communicate()
    except Exception:
        pass


async def _run_code_runner(task: TaskRuntime, session_dir: Path) -> None:
    """Delegate to /code-runner with worktree isolation + blind eval retry loop.

    Each code-runner task runs in its own git worktree, enabling parallel execution
    across tasks targeting the same repo. Changes merge back on success.
    """
    code_runner = SKILLS_DIR / "code-runner" / "run.sh"
    if not code_runner.exists():
        raise RuntimeError(f"/code-runner skill not found at {code_runner}")

    # Worktree isolation — off by default. Set CR_WORKTREE=1 to enable.
    # Worktrees break projects needing built bindings (Rust/maturin, C extensions).
    original_cwd = task.cwd
    worktree_dir: Path | None = None
    worktree_branch = ""
    use_worktree = os.environ.get("CR_WORKTREE", "0") == "1"
    if use_worktree:
        try:
            worktree_dir, worktree_branch = await _setup_worktree(original_cwd, task.task_id)
            work_cwd = worktree_dir
        except Exception as exc:
            logger.warning("Worktree setup failed ({}), running in-place", exc)
            work_cwd = original_cwd
    else:
        work_cwd = original_cwd

    # Clean env: strip .venv paths so DoD/commands use system Python
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    clean_env["PATH"] = os.pathsep.join(
        p for p in clean_env.get("PATH", "").split(os.pathsep)
        if ".venv" not in p
    )
    # Forward per-round timeout to code-runner (uses max of this and static floor)
    if "CODE_RUNNER_ROUND_TIMEOUT" not in clean_env and task.timeout_seconds:
        per_round = min(task.timeout_seconds // task.max_rounds, 600)
        clean_env["CODE_RUNNER_ROUND_TIMEOUT"] = str(max(per_round, 180))

    max_blind_attempts = 3
    accumulated_feedback: list[str] = []
    blind_passed = False

    try:
        for attempt in range(1, max_blind_attempts + 1):
            attempt_tag = f"a{attempt}" if attempt > 1 else ""

            blind_feedback_prompt = ""
            if accumulated_feedback:
                blind_feedback_prompt = (
                    f"\n\n--- Hidden evaluation feedback (attempt {attempt}/{max_blind_attempts}) ---\n"
                    f"Your code passed visible tests but failed hidden quality checks:\n"
                    + "\n".join(accumulated_feedback)
                    + "\nFix ALL issues above. You cannot see the hidden tests.\n"
                )

            spec: dict = {
                "task_id": f"{task.task_id}{attempt_tag}",
                "title": task.title,
                "prompt": task.prompt + blind_feedback_prompt,
                "backend": task.backend or "codex",
                "cwd": str(work_cwd),
                "output_dir": str(session_dir),
            }
            if task.definition_of_done:
                spec["definition_of_done"] = task.definition_of_done
            if task.allowlist is not None:
                spec["allowlist"] = task.allowlist
            if task.read_context:
                spec["read_context"] = task.read_context
            if task.max_rounds != 5:
                spec["max_rounds"] = task.max_rounds
            if task.lang:
                spec["lang"] = task.lang

            spec_file = session_dir / f"{task.task_id}{attempt_tag}.code-runner-spec.json"
            spec_file.write_text(json.dumps(spec, indent=2))

            proc = await asyncio.create_subprocess_exec(
                "bash", str(code_runner), "run", str(spec_file),
                f"--max-rounds={task.max_rounds}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_cwd),
                env=clean_env,
            )

            # Stream stderr line-by-line so project agent sees live progress.
            # stdout is collected in full (it's the LLM response text).
            async def _stream_stderr(proc_stderr, task_id: str, lines: list[str]):
                async for raw_line in proc_stderr:
                    line = raw_line.decode(errors="replace").rstrip()
                    lines.append(line)
                    if line:
                        logger.info("[cr:{}] {}", task_id, line)

            stderr_lines: list[str] = []
            stream_task = asyncio.create_task(
                _stream_stderr(proc.stderr, task.task_id, stderr_lines))

            try:
                stdout = await asyncio.wait_for(proc.stdout.read(), timeout=task.timeout_seconds)
                await proc.wait()
                stream_task.cancel()
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stream_task.cancel()
                task.review_status = "fail"
                task.error = f"code-runner timed out after {task.timeout_seconds}s"
                break

            stdout_text = stdout.decode(errors="replace")
            stderr_text = "\n".join(stderr_lines)

            output_path = session_dir / f"{task.task_id}{attempt_tag}.response.txt"
            output_path.write_text(stdout_text)
            task.output_path = output_path

            if stderr_text.strip():
                (session_dir / f"{task.task_id}{attempt_tag}.stderr.txt").write_text(stderr_text)

            # Check returncode FIRST — if code-runner crashed, result.json won't exist
            if proc.returncode != 0:
                task.review_status = "fail"
                task.error = f"/code-runner exit {proc.returncode}: {stderr_text[:500]}"
                logger.error("code-runner failed for {}: {}", task.task_id, task.error[:200])
                break

            result_file = session_dir / f"{task.task_id}{attempt_tag}.result.json"
            if result_file.exists():
                try:
                    result = json.loads(result_file.read_text())
                    task.review_status = "pass" if result.get("dod_passed") else "fail"
                    task.review_output = (
                        f"attempt={attempt}/{max_blind_attempts} "
                        f"score={result.get('best_score', 0):.3f} "
                        f"rounds={result.get('rounds', 0)} "
                        f"dod={'PASS' if result.get('dod_passed') else 'FAIL'}"
                    )
                except (json.JSONDecodeError, KeyError) as exc:
                    task.review_status = "fail"
                    task.error = f"result.json parse error: {exc}"
                    break
            else:
                task.review_status = "fail"
                task.error = f"result.json missing. stderr: {stderr_text[:300]}"
                break

            if not task.blind_tests or task.review_status != "pass":
                break

            blind_result = await _run_blind_eval(task, session_dir, attempt_tag)

            if blind_result is None:
                task.review_status = "fail"
                task.error = "blind eval FAILED: test-lab unreachable but blind_tests declared"
                task.review_output += "\n--- blind eval: FAILED (test-lab unreachable) ---"
                break

            if blind_result.get("status") == "pass":
                blind_passed = True
                break

            new_failures = [
                f"  - Check failed: {c['message']}"
                for c in blind_result.get("checks", []) if not c["passed"]
            ]
            accumulated_feedback.extend(new_failures)
            if len(accumulated_feedback) > 20:
                accumulated_feedback = accumulated_feedback[-20:]

            logger.warning("Blind eval FAILED for {} attempt {}/{} ({}/{})",
                           task.task_id, attempt, max_blind_attempts,
                           blind_result.get("failed", 0), blind_result.get("total", 0))

            if attempt >= max_blind_attempts:
                task.review_status = "fail"
                task.error = f"blind eval exhausted after {max_blind_attempts} attempts"
                task.review_output += (
                    f"\n--- blind eval: EXHAUSTED ({max_blind_attempts} attempts) ---\n"
                    + "\n".join(new_failures)
                )

        # Merge worktree back on success
        if worktree_dir and task.review_status == "pass":
            merged = await _merge_worktree(original_cwd, worktree_branch, task.task_id)
            if not merged:
                task.review_status = "fail"
                task.error = "merge conflict merging worktree back to main branch"

    finally:
        # Always clean up worktree
        if worktree_dir:
            await _cleanup_worktree(original_cwd, worktree_dir, worktree_branch)

    # T2 review only if BOTH DoD and blind eval passed (or no blind tests)
    if task.review_status == "pass" and (blind_passed or not task.blind_tests):
        await _review_code_runner_output(task, session_dir)


async def _run_blind_eval(task: TaskRuntime, session_dir: Path,
                          attempt_tag: str = "") -> dict | None:
    """Call test-lab Docker service with blind tests. Returns result dict or None.

    The information barrier: code-runner never sees blind_tests.
    Only orchestrate has them (from the plan YAML) and sends them directly to test-lab.
    Code-runner only gets sanitized failure messages if orchestrate retries the task.

    Returns None ONLY on connection failure (test-lab unreachable).
    HTTP errors and malformed responses raise to caller.
    """
    test_lab_url = os.environ.get("TEST_LAB_URL", "http://127.0.0.1:8787")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{test_lab_url.rstrip('/')}/evaluate",
                json={
                    "task_id": task.task_id,
                    "target_dir": str(task.cwd),
                    "blind_tests": task.blind_tests,
                },
            )
            resp.raise_for_status()
            result = resp.json()

            # Save per-attempt blind eval result — strip indices to prevent
            # oracle-guided test reconstruction (#9 fix)
            eval_file = session_dir / f"{task.task_id}{attempt_tag}.blind-eval.json"
            safe_result = {
                "status": result.get("status"),
                "passed": result.get("passed"),
                "failed": result.get("failed"),
                "total": result.get("total"),
                "checks": [
                    {"passed": c["passed"], "message": c["message"]}
                    for c in result.get("checks", [])
                ],
            }
            eval_file.write_text(json.dumps(safe_result, indent=2))
            return result
    except httpx.ConnectError:
        logger.warning("test-lab not reachable at {} — blind eval FAILED", test_lab_url)
        return None
    except Exception as e:
        # Non-connection errors (HTTP 500, parse failure) → return failure, not None
        logger.error("Blind eval error: {}", e)
        return {"status": "fail", "passed": 0, "failed": 1, "total": 1,
                "checks": [{"passed": False, "message": f"blind eval error: {e}"}]}


async def _review_code_runner_output(task: TaskRuntime, session_dir: Path) -> None:
    """T2 gate: invoke /code-review-runner on code-runner's changes (best-effort).

    Builds a review spec from the task, runs T0 validators + LLM review,
    and stores structured findings. Non-fatal — code-runner result stands if
    code-review-runner is unavailable or fails.

    Falls back to /review-code if code-review-runner is not available.
    """
    review_runner = SKILLS_DIR / "code-review-runner" / "run.sh"
    review_code = SKILLS_DIR / "review-code" / "run.sh"

    # Collect files changed by code-runner
    changed_files = []
    result_file = None
    for p in session_dir.iterdir():
        if p.name.startswith(task.task_id) and p.name.endswith(".result.json"):
            result_file = p
            break
    if result_file and result_file.exists():
        try:
            result_data = json.loads(result_file.read_text())
            for rd in result_data.get("round_details", []):
                changed_files.extend(rd.get("written_files", []))
            changed_files = list(set(changed_files))
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: get changed files from git diff
    if not changed_files:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--name-only", "HEAD~1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task.cwd),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            changed_files = [f.strip() for f in stdout.decode().splitlines() if f.strip()]
        except Exception:
            pass

    if not changed_files:
        logger.info("T2: no changed files found for {}, skipping review", task.task_id)
        return

    # Prefer code-review-runner (structured findings)
    if review_runner.exists():
        spec = {
            "task_id": task.task_id,
            "files": changed_files[:20],  # Cap at 20 files
            "cwd": str(task.cwd),
            "context": f"Code-runner output for task: {task.title}",
            "dod_command": task.definition_of_done.get("command", "") if isinstance(task.definition_of_done, dict) else "",
            "backend": "codex",
            "output_dir": str(session_dir),
            "max_rounds": 1,  # Single round for T2 gate (fast)
        }
        spec_file = session_dir / f"{task.task_id}.review-spec.json"
        spec_file.write_text(json.dumps(spec, indent=2))

        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", str(review_runner), "review", str(spec_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task.cwd),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
            review_text = stdout.decode(errors="replace")

            # Parse structured result
            try:
                review_data = json.loads(review_text)
                score = review_data.get("score", 0)
                findings_total = review_data.get("findings_total", 0)
                findings_critical = review_data.get("findings_critical", 0)
                t0_count = review_data.get("t0_violation_count", 0)
                summary = review_data.get("summary", "")

                task.review_output += (
                    f"\n--- T2 code-review-runner ---\n"
                    f"score={score:.3f} | findings={findings_total} "
                    f"(critical={findings_critical}) | t0={t0_count}\n"
                    f"{summary}"
                )

                # Fail T2 if critical findings
                if findings_critical > 0:
                    task.review_status = "fail"
                    task.review_output += f"\nT2 FAIL: {findings_critical} critical finding(s)"

            except json.JSONDecodeError:
                task.review_output += f"\n--- T2 code-review-runner (raw) ---\n{review_text[:500]}"

            logger.info("T2 code-review-runner completed for {}", task.task_id)
            return
        except asyncio.TimeoutError:
            logger.error("T2 code-review-runner timed out for {} — marking fail", task.task_id)
            task.review_status = "fail"
            task.error = "T2 review timed out (180s)"
            return
        except Exception as exc:
            logger.warning("T2 code-review-runner failed for {} (falling back): {}", task.task_id, exc)

    # Fallback: /review-code (legacy path)
    if review_code.exists():
        hunk_file = session_dir / f"{task.task_id}.hunk.md"
        if not hunk_file.exists():
            return

        hunk_content = hunk_file.read_text()
        request_file = session_dir / f"{task.task_id}.review-request.md"
        request_file.write_text(
            f"# Code Review Request: {task.title}\n\n"
            f"## Context\n"
            f"Auto-generated by /code-runner self-improvement loop.\n"
            f"Review the changes for correctness, security, and best-practices.\n\n"
            f"## Changes\n\n{hunk_content}\n"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", str(review_code), "quick-review",
                "--file", str(request_file),
                "--add-dir", str(task.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task.cwd),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            review_text = stdout.decode(errors="replace")

            review_output = session_dir / f"{task.task_id}.review-output.txt"
            review_output.write_text(review_text)
            task.review_output += f"\n--- T2 review-code (fallback) ---\n{review_text[:500]}"
            logger.info("T2 review-code (fallback) completed for {}", task.task_id)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("T2 review-code failed for {} (non-fatal): {}", task.task_id, exc)


# ---------------------------------------------------------------------------
# Watchdog (async coroutine, not a thread)
# ---------------------------------------------------------------------------

async def _watchdog(session_dir: Path, runtimes: dict[str, TaskRuntime],
                    aborted: asyncio.Event, paused: asyncio.Event) -> None:
    """Poll for ABORT/KILL/PAUSE files every WATCHDOG_POLL_S seconds."""
    while True:
        try:
            # ABORT
            abort_file = session_dir / "ABORT"
            if abort_file.exists():
                logger.error("ABORT file detected — killing all running tasks")
                abort_file.unlink(missing_ok=True)
                aborted.set()
                for task in runtimes.values():
                    if task.status == "running":
                        task._cancel_event.set()
                return

            # KILL_<task_id>
            for kill_file in session_dir.glob("KILL_*"):
                kill_id = kill_file.name[5:]
                kill_file.unlink(missing_ok=True)
                task = runtimes.get(kill_id)
                if task and task.status == "running":
                    logger.warning("KILL_{} — cancelling {}: {}", kill_id, kill_id, task.title)
                    task._cancel_event.set()
                else:
                    logger.warning("KILL_{} ignored (status={})",
                                   kill_id, task.status if task else "unknown")

            # PAUSE
            pause_file = session_dir / "PAUSE"
            if pause_file.exists():
                if not paused.is_set():
                    logger.warning("PAUSE detected")
                    paused.set()
            else:
                if paused.is_set():
                    paused.clear()

        except Exception as exc:
            logger.warning("Watchdog error: {}", exc)

        await asyncio.sleep(WATCHDOG_POLL_S)


# ---------------------------------------------------------------------------
# Session resume
# ---------------------------------------------------------------------------

def _find_latest_session(plan_path: Path) -> Path | None:
    structured_dir = STATE_ROOT / "structured"
    if not structured_dir.exists():
        return None
    try:
        current_plan = load_structured_plan(plan_path)
        current_ids = {str(t.get("id")) for t in current_plan.get("tasks", []) if isinstance(t, dict)}
    except Exception:
        return None
    for session_dir in sorted(
        (d for d in structured_dir.iterdir() if d.is_dir()), reverse=True
    ):
        status_file = session_dir / "status.json"
        if not status_file.exists():
            continue
        try:
            status = json.loads(status_file.read_text())
            session_ids = {t.get("id") for t in status.get("tasks", [])}
            if not current_ids or not session_ids.issubset(current_ids):
                continue
            if any(t.get("status") == "completed" for t in status.get("tasks", [])) or status.get("failed"):
                return session_dir
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _load_completed_tasks(session_dir: Path) -> set[str]:
    status_file = session_dir / "status.json"
    if not status_file.exists():
        return set()
    try:
        status = json.loads(status_file.read_text())
        return {t["id"] for t in status.get("tasks", []) if t.get("status") == "completed"}
    except (json.JSONDecodeError, KeyError):
        return set()


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

async def _execute_plan_async(path: Path, repo_root: Path | None = None, resume: bool = False) -> int:
    plan = load_structured_plan(path)
    validation = validate_structured_plan(plan)
    if not validation["valid"]:
        for issue in validation["issues"]:
            logger.error(issue)
        return 1

    # repo_root from plan file takes precedence (required field since schema v1)
    plan_repo_root = plan.get("repo_root")
    if plan_repo_root:
        repo_root = Path(plan_repo_root)
    elif repo_root is None:
        repo_root = path.resolve().parent
        logger.warning("Plan missing repo_root, falling back to plan file parent: {}", repo_root)

    completed_prior: set[str] = set()
    if resume:
        prior = _find_latest_session(path)
        if prior:
            completed_prior = _load_completed_tasks(prior)
            if completed_prior:
                logger.info("Resuming: {} tasks completed from {}", len(completed_prior), prior.name)

    session_dir = STATE_ROOT / "structured" / f"session-{int(time.time())}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "plan.json").write_text(json.dumps(plan, indent=2))

    # Machine-readable session announcement — the project agent reads this to
    # know where to write KILL/ABORT/PAUSE files for intervention.
    # Format: JSON line on stdout, parseable by pi-task.ts or any supervisor.
    print(json.dumps({"event": "session_started", "session_dir": str(session_dir),
                       "status_file": str(session_dir / "status.json"),
                       "task_count": len(plan.get("tasks", []))}))

    runtimes = _build_runtimes(plan, repo_root)
    deps, indegree = _dependency_graph(plan)
    reverse: dict[str, list[str]] = {tid: [] for tid in runtimes}
    for tid, tdeps in deps.items():
        for dep in tdeps:
            reverse.setdefault(dep, []).append(tid)

    for tid in completed_prior:
        if tid in runtimes:
            runtimes[tid].status = "completed"
            runtimes[tid].finished_at = 0.0
            for child in reverse.get(tid, []):
                indegree[child] -= 1

    max_conc = int((plan.get("execution") or {}).get("max_concurrency") or 1)
    ready = [tid for tid, deg in indegree.items() if deg == 0 and tid not in completed_prior]
    active_by_lane: dict[str, str] = {}

    if completed_prior:
        logger.info("Executing {} remaining tasks", len(runtimes) - len(completed_prior))

    # Write intervention instructions
    (session_dir / "INTERVENTION.md").write_text(
        f"# Intervention Controls\n\nSession: {session_dir.name}\n\n"
        f"| File | Effect | Latency |\n|------|--------|---------|\n"
        f"| `PAUSE` | Pause after current tasks | <{WATCHDOG_POLL_S}s |\n"
        f"| `KILL_<task_id>` | Kill specific task mid-stream | <{WATCHDOG_POLL_S}s |\n"
        f"| `ABORT` | Kill ALL, stop plan | <{WATCHDOG_POLL_S}s |\n"
        f"| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |\n\n"
        f"## Task IDs\n\n"
        + "\n".join(f"- `{tid}`: {rt.title} ({rt.runner}/{rt.lane})" for tid, rt in runtimes.items())
        + "\n"
    )
    _render_state(session_dir, runtimes, deps, failed=False)

    # Start watchdog as an async task (not a thread)
    aborted = asyncio.Event()
    paused = asyncio.Event()
    wd_task = asyncio.create_task(_watchdog(session_dir, runtimes, aborted, paused))

    try:
        return await _execute_loop(
            path, session_dir, runtimes, deps, indegree, reverse,
            completed_prior, max_conc, ready, active_by_lane, aborted, paused,
        )
    finally:
        wd_task.cancel()
        try:
            await wd_task
        except asyncio.CancelledError:
            pass


async def _execute_loop(
    plan_path: Path, session_dir: Path,
    runtimes: dict[str, TaskRuntime], deps: dict[str, list[str]],
    indegree: dict[str, int], reverse: dict[str, list[str]],
    completed_prior: set[str], max_conc: int, ready: list[str],
    active_by_lane: dict[str, str],
    aborted: asyncio.Event, paused: asyncio.Event,
) -> int:
    task_map: dict[asyncio.Task, str] = {}

    while ready or task_map:
        # ── Abort ──
        if aborted.is_set():
            logger.error("ABORTED — stopping all execution")
            for t in task_map:
                t.cancel()
            _render_state(session_dir, runtimes, deps, failed=True)
            return 1

        # ── Pause (only when no tasks running) ──
        if paused.is_set() and not task_map:
            logger.warning("PAUSED — edit plan, add SKIP/KILL files, then remove PAUSE.")
            _render_state(session_dir, runtimes, deps, failed=False)
            while paused.is_set() and not aborted.is_set():
                await asyncio.sleep(1)
            if aborted.is_set():
                return 1
            logger.info("RESUMED")
            load_structured_plan(plan_path)
            for skip_file in session_dir.glob("SKIP_*"):
                skip_id = skip_file.name[5:]
                if skip_id in runtimes and runtimes[skip_id].status == "queued":
                    runtimes[skip_id].status = "skipped"
                    logger.info("Skipping task {}", skip_id)
                    for child in reverse.get(skip_id, []):
                        indegree[child] -= 1
                        if indegree[child] == 0 and child not in completed_prior:
                            ready.append(child)
                skip_file.unlink(missing_ok=True)

        # ── Schedule ready tasks ──
        scheduled = False
        for task_id in list(ready):
            task = runtimes[task_id]
            if task.status == "skipped":
                ready.remove(task_id)
                continue
            if task.lane in active_by_lane:
                continue
            if len(task_map) >= max_conc:
                break
            ready.remove(task_id)
            active_by_lane[task.lane] = task_id
            atask = asyncio.create_task(_execute_task(task, session_dir), name=f"task-{task_id}")
            task_map[atask] = task_id
            _render_state(session_dir, runtimes, deps, failed=False)
            scheduled = True

        if not task_map and not scheduled and ready:
            raise RuntimeError("Lane scheduling deadlocked")
        if not task_map:
            continue

        # ── Wait for any task to finish (with timeout for watchdog responsiveness) ──
        done, _ = await asyncio.wait(task_map.keys(), timeout=WATCHDOG_POLL_S,
                                     return_when=asyncio.FIRST_COMPLETED)
        if not done:
            continue

        for atask in done:
            task_id = task_map.pop(atask)
            task = runtimes[task_id]
            active_by_lane.pop(task.lane, None)
            try:
                atask.result()
            except (Exception, asyncio.CancelledError) as exc:
                if task._cancel_event.is_set():
                    logger.warning("Task {} cancelled: {}", task_id, exc)
                    task.status = "cancelled"
                    task.error = "cancelled by operator"
                else:
                    logger.error("Task {} failed: {}", task_id, exc)
                    task.status = "failed"
                    task.error = str(exc)
                    # Mark downstream dependents as blocked (they can't run)
                    def _mark_blocked(parent_id: str) -> None:
                        for child_id in reverse.get(parent_id, []):
                            child = runtimes[child_id]
                            if child.status == "pending":
                                child.status = "blocked"
                                child.error = f"blocked by failed parent: {parent_id}"
                                logger.warning("  Task {} blocked (parent {} failed)", child_id, parent_id)
                                _mark_blocked(child_id)
                    _mark_blocked(task_id)
                task.finished_at = time.time()
            # Release children ONLY when parent completed successfully.
            # Cancelled/failed parents must NOT unblock dependents — missing prerequisites.
            if task.status == "completed":
                for child in reverse.get(task_id, []):
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        ready.append(child)
            _render_state(session_dir, runtimes, deps, failed=False)

    # Summary: human-readable report
    failed_tasks = [t for t in runtimes.values() if t.status == "failed"]

    # Print human-readable report
    report = render_report(session_dir, runtimes, plan, verbose=bool(failed_tasks))
    print("\n" + report)

    # Also write report to file
    (session_dir / "report.txt").write_text(report)

    return 1 if failed_tasks else 0


def execute_plan(path: Path, repo_root: Path | None = None, resume: bool = False) -> int:
    """Sync entry point — runs the async executor."""
    return asyncio.run(_execute_plan_async(path, repo_root, resume))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@app.command()
def run(
    plan_file: Path,
    resume: bool = typer.Option(False, "--resume", help="Resume from last completed task"),
) -> None:
    """Execute a structured plan file with explicit runner dispatch."""
    # repo_root is read from the plan file's repo_root field (required since schema v1).
    # Falls back to plan file parent if field is missing (legacy plans).
    raise typer.Exit(execute_plan(plan_file.resolve(), resume=resume))


@app.command()
def status(plan_file: Path = typer.Argument(None)) -> None:
    """Show execution status for the most recent session."""
    structured_dir = STATE_ROOT / "structured"
    if not structured_dir.exists():
        print("No sessions found.")
        raise typer.Exit(0)
    sessions = sorted(
        [d for d in structured_dir.iterdir() if d.is_dir() and (d / "status.json").exists()],
        reverse=True,
    )
    if not sessions:
        print("No sessions found.")
        raise typer.Exit(0)
    session_dir = sessions[0]
    data = json.loads((session_dir / "status.json").read_text())
    tasks = data.get("tasks", [])
    completed = [t for t in tasks if t.get("status") == "completed"]
    failed = [t for t in tasks if t.get("status") == "failed"]
    queued = [t for t in tasks if t.get("status") == "queued"]
    print(f"Session: {session_dir.name}")
    print(f"Tasks: {len(completed)}/{len(tasks)} completed", end="")
    if failed:
        print(f", {len(failed)} FAILED", end="")
    if queued:
        print(f", {len(queued)} remaining", end="")
    print()
    if failed:
        print("\nFailed:")
        for t in failed:
            print(f"  Task {t['id']}: {t.get('title', '')} — {t.get('error', '')[:80]}")
    if queued:
        print("\nRemaining:")
        for t in queued:
            print(f"  Task {t['id']}: {t.get('title', '')}")
    if failed or queued:
        print(f"\nResume: structured_execute.py run {plan_file or '<plan.yaml>'} --resume")


if __name__ == "__main__":
    app()
