"""test-lab blind evaluation HTTP service.

Runs inside Docker so the coding agent cannot read test source.
Receives blind test assertions + target directory, executes them,
returns sanitized pass/fail. The agent never sees test code.

Endpoints:
  GET  /healthz              — liveness check
  POST /evaluate             — run blind tests against a mounted target dir
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel

app = FastAPI(title="test-lab blind evaluation service")


class BlindEvalRequest(BaseModel):
    task_id: str
    step_id: str = ""
    target_dir: str  # path inside container (mounted volume)
    blind_tests: list[str]  # assertions written by project agent at plan time
    language: str = "python"  # language for test execution


class BlindCheckResult(BaseModel):
    index: int  # opaque test number — assertion text NEVER returned to preserve information barrier
    passed: bool
    message: str  # sanitized failure message (no paths, no source)


class BlindEvalResponse(BaseModel):
    task_id: str
    step_id: str
    status: str  # "pass" or "fail"
    passed: int
    failed: int
    total: int
    checks: list[BlindCheckResult]


def _sanitize(text: str) -> str:
    """Strip identifying content from error output to preserve information barrier.

    Removes: file paths, module names from imports, string literals,
    expected/actual values from assertions, line numbers from tracebacks.
    """
    # Strip file paths
    text = re.sub(r"/[^\s:\"']+", "<path>", text)
    # Strip string literals (single and double quoted) to prevent leaking expected values
    text = re.sub(r"['\"][^'\"]{4,}['\"]", "<str>", text)
    # Strip line numbers from tracebacks (prevents pinpointing test assertions)
    text = re.sub(r", line \d+", "", text)
    # Strip module/function names from "from X import Y" patterns
    text = re.sub(r"from \S+ import \S+", "from <module> import <name>", text)
    # Keep only last 6 lines, cap at 500 chars
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-6:])[:500]


def _run_python_assertion(assertion: str, target_dir: str, _cwd: str = "") -> BlindCheckResult:
    """Run a single Python assertion against the target directory."""
    # Wrap the assertion in a test script that adds target_dir to sys.path
    test_code = "\n".join([
        "import sys",
        f"sys.path.insert(0, {target_dir!r})",
        assertion.strip(),
        'print("BLIND_PASS")',
    ])
    try:
        proc = subprocess.run(
            ["python3", "-c", test_code],
            capture_output=True, text=True, timeout=30,
            cwd=target_dir,
        )
        if proc.returncode == 0 and "BLIND_PASS" in proc.stdout:
            return BlindCheckResult(index=-1, passed=True, message="passed")
        else:
            combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
            return BlindCheckResult(
                index=-1, passed=False,
                message=_sanitize(combined) or "assertion failed",
            )
    except subprocess.TimeoutExpired:
        return BlindCheckResult(index=-1, passed=False, message="timed out (30s)")
    except Exception as e:
        return BlindCheckResult(index=-1, passed=False, message=_sanitize(str(e)))


def _run_shell_assertion(assertion: str, target_dir: str) -> BlindCheckResult:
    """Run a shell command assertion against the target directory."""
    # In Docker, the workspace is always mounted at /workspace
    # Map any host path to /workspace if running inside container
    cwd = "/workspace" if os.path.isdir("/workspace") else target_dir
    try:
        proc = subprocess.run(
            ["bash", "-c", assertion],
            capture_output=True, text=True, timeout=30,
            cwd=cwd,
        )
        if proc.returncode == 0:
            return BlindCheckResult(index=-1, passed=True, message="passed")
        else:
            combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
            return BlindCheckResult(
                index=-1, passed=False,
                message=_sanitize(combined) or "command failed",
            )
    except subprocess.TimeoutExpired:
        return BlindCheckResult(index=-1, passed=False, message="timed out (30s)")
    except Exception as e:
        return BlindCheckResult(index=-1, passed=False, message=_sanitize(str(e)))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=BlindEvalResponse)
def evaluate(req: BlindEvalRequest) -> BlindEvalResponse:
    logger.info("Blind eval: task={} tests={} target={}", req.task_id, len(req.blind_tests), req.target_dir)

    checks: list[BlindCheckResult] = []
    for idx, assertion in enumerate(req.blind_tests):
        # Detect if it's a shell command (starts with common shell patterns)
        if assertion.strip().startswith(("cd ", "test ", "grep ", "!", "[", "bash ")):
            result = _run_shell_assertion(assertion, req.target_dir)
        else:
            result = _run_python_assertion(assertion, req.target_dir)
        result.index = idx
        checks.append(result)
        # Log without assertion text — only index and pass/fail (barrier discipline)
        logger.info("  test[{}] {}: {}", idx, "PASS" if result.passed else "FAIL", result.message[:80])

    passed = sum(1 for c in checks if c.passed)
    failed = sum(1 for c in checks if not c.passed)
    status = "pass" if failed == 0 else "fail"

    return BlindEvalResponse(
        task_id=req.task_id,
        step_id=req.step_id,
        status=status,
        passed=passed,
        failed=failed,
        total=len(checks),
        checks=checks,
    )
