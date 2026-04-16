#!/usr/bin/env python3
"""codex.py — High-reasoning agentic bridge via OpenAI Codex CLI.

Purpose:
    Run gpt-5.3-codex with configurable reasoning effort and structured output.
    Provide watchdog stall detection for long-running reasoning tasks.
    Report progress to /task-monitor via TaskClient.
    Support concurrent execution for batch reasoning.

Inputs:
    User prompt (string), optional JSON schema for structured output.
    Timeout/watchdog configuration.

Outputs:
    LLM response text (stdout) or structured JSON.
    Task state file for /task-monitor visibility.

Failure modes:
    Codex CLI not installed → clear error message.
    API rate-limited/unavailable → returns error string, task marked failed.
    Stall (no output for watchdog_seconds) → graceful termination + error.
    Hard timeout exceeded → kill + error.
"""

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

import typer
from loguru import logger

# TaskClient from shared common module
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from task_monitor import TaskClient

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_TIMEOUT = 600       # 10 min hard kill (codex is slow)
DEFAULT_WATCHDOG = 300      # 5 min stall detection
WATCHDOG_POLL = 15          # Heartbeat interval (seconds)


def _terminate_process(proc: subprocess.Popen) -> None:
    """Gracefully terminate: SIGTERM → wait(10s) → SIGKILL."""
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
    except Exception:
        pass


def _pump_stream(stream, queue: Queue) -> None:
    """Read lines from stream into queue. Runs as daemon thread."""
    try:
        for line in iter(stream.readline, ""):
            queue.put(line)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _run_with_watchdog(
    cmd: list[str],
    stdin_data: str,
    env: dict,
    timeout: int = DEFAULT_TIMEOUT,
    watchdog: int = DEFAULT_WATCHDOG,
    monitor: Optional[TaskClient] = None,
) -> tuple[str, bool, float, bool, bool]:
    """Run subprocess with watchdog stall detection and heartbeat.

    Returns:
        (stdout, success, elapsed, stalled, timed_out)
    """
    start = time.time()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Write stdin and close
    if stdin_data:
        try:
            proc.stdin.write(stdin_data)
            proc.stdin.close()
        except BrokenPipeError:
            pass

    # Threaded pumps for stdout/stderr
    out_q: Queue = Queue()
    err_q: Queue = Queue()
    threading.Thread(target=_pump_stream, args=(proc.stdout, out_q), daemon=True).start()
    threading.Thread(target=_pump_stream, args=(proc.stderr, err_q), daemon=True).start()

    last_output = time.time()
    stalled = False
    timed_out = False

    while proc.poll() is None:
        got_output = False

        # Drain queues
        for _ in range(100):
            try:
                line = out_q.get_nowait()
                stdout_lines.append(line)
                got_output = True
            except Empty:
                break

        for _ in range(100):
            try:
                line = err_q.get_nowait()
                stderr_lines.append(line)
                got_output = True
            except Empty:
                break

        if got_output:
            last_output = time.time()

        elapsed = time.time() - start

        # Hard timeout
        if elapsed >= timeout:
            logger.warning("codex hard timeout after {:.0f}s", elapsed)
            _terminate_process(proc)
            timed_out = True
            break

        # Stall detection
        if watchdog > 0 and (time.time() - last_output) >= watchdog:
            logger.warning("codex stalled (no output for {:.0f}s)", watchdog)
            _terminate_process(proc)
            stalled = True
            break

        # Heartbeat
        if monitor and int(elapsed) % WATCHDOG_POLL == 0:
            monitor.heartbeat(item=f"running {elapsed:.0f}s")

        time.sleep(1)

    # Final drain
    for _ in range(1000):
        try:
            stdout_lines.append(out_q.get_nowait())
        except Empty:
            break
    for _ in range(1000):
        try:
            stderr_lines.append(err_q.get_nowait())
        except Empty:
            break

    elapsed = time.time() - start
    rc = proc.returncode or 0
    success = rc == 0 and not stalled and not timed_out

    stdout_text = "".join(stdout_lines).strip()
    stderr_text = "".join(stderr_lines).strip()

    if not success and stderr_text:
        stdout_text = stdout_text or f"Error: {stderr_text}"

    return stdout_text, success, elapsed, stalled, timed_out


def run_codex(
    prompt: str,
    model: str = "gpt-5.3-codex",
    reasoning: str = "high",
    sandbox: str = "workspace-write",
    json_mode: bool = False,
    output_schema: Optional[Path] = None,
    timeout: int = DEFAULT_TIMEOUT,
    watchdog: int = DEFAULT_WATCHDOG,
    monitor: Optional[TaskClient] = None,
) -> str:
    """Run a codex exec command with watchdog and task-monitor integration.

    Args:
        prompt: The prompt to send to Codex.
        model: Model to use (default: gpt-5.3-codex).
        reasoning: Reasoning effort level (low, medium, high).
        sandbox: Sandbox mode (workspace-write, etc.).
        json_mode: Whether to request JSON output.
        output_schema: Path to JSON schema for structured output.
        timeout: Hard timeout in seconds.
        watchdog: Stall detection timeout (0 to disable).
        monitor: Optional TaskClient for progress reporting.

    Returns:
        The response from Codex or an error message.
    """
    cmd = [
        "codex", "exec",
        "--model", model,
        "-c", f'reasoning_effort="{reasoning}"',
        "-s", sandbox,
        "--full-auto",
        "--skip-git-repo-check",
    ]

    if json_mode:
        cmd.append("--json")

    if output_schema and output_schema.exists():
        cmd.extend(["--output-schema", str(output_schema)])

    cmd.append("-")

    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))

    try:
        stdout, success, elapsed, stalled, timed_out = _run_with_watchdog(
            cmd, prompt, env,
            timeout=timeout,
            watchdog=watchdog,
            monitor=monitor,
        )

        if success:
            logger.info("codex completed in {:.1f}s", elapsed)
        elif timed_out:
            logger.error("codex timed out after {:.0f}s", elapsed)
            return f"Error: Timeout after {elapsed:.0f}s"
        elif stalled:
            logger.error("codex stalled after {:.0f}s", elapsed)
            return f"Error: Stalled (no output for {watchdog}s)"
        else:
            logger.warning("codex finished with errors in {:.1f}s", elapsed)

        return stdout

    except FileNotFoundError:
        return "Error: 'codex' CLI not found. Install with: npm install -g @openai/codex"
    except Exception as e:
        logger.error("codex unexpected error: {}", e)
        return f"Error: {e}"


app = typer.Typer(help="Codex Skill — gpt-5.3 High Reasoning Bridge")


@app.command()
def reason(
    prompt: str = typer.Argument(..., help="Reasoning prompt"),
    model: str = typer.Option("gpt-5.3-codex", "--model", help="Codex model"),
    reasoning: str = typer.Option("high", "--reasoning", help="Effort: low/medium/high"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Hard timeout (seconds)"),
    watchdog: int = typer.Option(DEFAULT_WATCHDOG, "--watchdog", help="Stall detection (seconds, 0=off)"),
    walkthrough: bool = typer.Option(False, "--walkthrough", help="Auto-invoke /create-walkthrough on output"),
    concurrent: int = typer.Option(1, "--concurrent", help="Run N prompts concurrently (pipe-separated)"),
) -> None:
    """Generic reasoning with watchdog and task-monitor."""
    prompts = prompt.split("|SPLIT|") if concurrent > 1 else [prompt]

    with TaskClient(
        "codex:reason", total=len(prompts),
        description=f"Codex reason: {prompt[:60]}",
        state_dir=str(SKILL_DIR),
    ) as monitor:
        if len(prompts) == 1:
            result = run_codex(
                prompts[0], model=model, reasoning=reasoning,
                timeout=timeout, watchdog=watchdog, monitor=monitor,
            )
            monitor.update(item="done")
            print(result)

            if walkthrough and not result.startswith("Error:"):
                _invoke_walkthrough(result)
        else:
            _run_concurrent(
                prompts, model=model, reasoning=reasoning,
                timeout=timeout, watchdog=watchdog, monitor=monitor,
                walkthrough=walkthrough,
            )


@app.command()
def extract(
    prompt: str = typer.Argument(..., help="Extraction prompt"),
    schema: Path = typer.Option(None, "--schema", help="Path to JSON Schema file"),
    model: str = typer.Option("gpt-5.3-codex", "--model", help="Codex model"),
    reasoning: str = typer.Option("high", "--reasoning", help="Effort: low/medium/high"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Hard timeout (seconds)"),
    watchdog: int = typer.Option(DEFAULT_WATCHDOG, "--watchdog", help="Stall detection (seconds, 0=off)"),
) -> None:
    """Structured extraction with watchdog and task-monitor."""
    with TaskClient(
        "codex:extract", total=1,
        description=f"Codex extract: {prompt[:60]}",
        state_dir=str(SKILL_DIR),
    ) as monitor:
        result = run_codex(
            prompt, model=model, reasoning=reasoning,
            output_schema=schema,
            timeout=timeout, watchdog=watchdog, monitor=monitor,
        )
        monitor.update(item="done")
        print(result)


def _run_concurrent(
    prompts: list[str],
    model: str,
    reasoning: str,
    timeout: int,
    watchdog: int,
    monitor: TaskClient,
    walkthrough: bool = False,
) -> None:
    """Run multiple prompts concurrently via ThreadPoolExecutor."""
    results: dict[int, str] = {}
    max_workers = min(len(prompts), 4)  # Cap at 4 concurrent codex calls

    logger.info("running {} prompts concurrently (max_workers={})", len(prompts), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                run_codex, p, model, reasoning,
                "workspace-write", False, None,
                timeout, watchdog, None,
            ): i
            for i, p in enumerate(prompts)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = f"Error: {e}"
            monitor.update(item=f"prompt {idx + 1}/{len(prompts)}")

    # Print results in order
    for i in range(len(prompts)):
        if len(prompts) > 1:
            print(f"\n--- Result {i + 1}/{len(prompts)} ---")
        print(results.get(i, "Error: no result"))

    if walkthrough:
        combined = "\n\n".join(
            r for r in results.values() if not r.startswith("Error:")
        )
        if combined.strip():
            _invoke_walkthrough(combined)


def _invoke_walkthrough(content: str) -> None:
    """Invoke /create-walkthrough on codex output."""
    walkthrough_dir = SKILL_DIR.parent / "create-walkthrough"
    run_sh = walkthrough_dir / "run.sh"
    if not run_sh.exists():
        logger.warning("create-walkthrough skill not found at {}", walkthrough_dir)
        return

    logger.info("invoking /create-walkthrough on codex output")
    try:
        proc = subprocess.run(
            [str(run_sh), "create", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            print("\n--- Walkthrough ---")
            print(proc.stdout)
        else:
            logger.warning("create-walkthrough failed: {}", proc.stderr[:200])
    except Exception as e:
        logger.warning("create-walkthrough invocation failed: {}", e)


if __name__ == "__main__":
    app()
