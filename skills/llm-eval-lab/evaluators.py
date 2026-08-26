"""Deterministic evaluators — replace LLM-as-judge where execution can decide.

Code-generation items are graded by executing the model's code against a unit
test suite; structured-extraction items are graded by parsing JSON and checking
schema/value equality. These are ground truth: the same wrong assumption cannot
author both the check and the answer (the check runs the code / parses the
bytes), unlike an LLM judge scoring free text.

Score contract (0-3), matching the LLM-judge scale used elsewhere:
    3 = fully correct (tests pass / JSON valid and matches)
    1 = partially correct (runs but assertion fails / valid JSON missing keys)
    0 = wrong (runtime error / unparseable)

eval_python_code runs the candidate in a SUBPROCESS with a finite timeout, not
in-process exec(): model output is untrusted and can hang or crash the runner,
and the design's per-item timeout can only be enforced across a process
boundary. This also isolates segfaults/infinite loops from the grid.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _strip_code_fence(text: str) -> str:
    """Remove a leading ```lang fence and trailing ``` if present."""
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line, then the trailing fence
        t = t.split("\n", 1)[-1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def eval_json_output(
    response_text: str,
    expected_keys: set[str] | None = None,
    expected_json: Any | None = None,
) -> tuple[int, str]:
    """Deterministically score JSON output 0-3.

    - unparseable -> 0
    - parses but missing required keys -> 1
    - expected_json given and unequal -> 1 (right shape, wrong values)
    - matches (or no stricter check requested) -> 3
    """
    text = _strip_code_fence(response_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        return 0, f"JSON parse failed: {err}"
    if expected_keys is not None:
        if not isinstance(data, dict):
            return 0, "JSON is not an object"
        missing = expected_keys - set(data.keys())
        if missing:
            return 1, f"valid JSON but missing keys: {sorted(missing)}"
    if expected_json is not None:
        if data != expected_json:
            return 1, "valid JSON, correct keys, but values differ from expected"
        return 3, "valid JSON exactly matching expected object"
    return 3, "valid JSON matching expected schema"


def eval_python_code(code_str: str, test_suite: str, timeout: int = 30) -> tuple[int, str]:
    """Execute candidate code + a test suite in an isolated subprocess.

    Returns (3, ..) if the process exits 0 (all asserts pass), (1, ..) on an
    AssertionError, (0, ..) on any other error/timeout. The candidate's code and
    the test suite are concatenated into one temp module run by a fresh
    interpreter with a finite timeout.
    """
    code = _strip_code_fence(code_str)
    program = code + "\n\n# --- test suite ---\n" + test_suite + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(program)
        path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 0, f"execution timed out after {timeout}s"
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass
    if proc.returncode == 0:
        return 3, "all unit tests passed"
    stderr = (proc.stderr or "").strip()
    last = stderr.rsplit("\n", 1)[-1] if stderr else ""
    if "AssertionError" in stderr:
        return 1, f"assertion failed: {last}"
    return 0, f"runtime error: {last or 'nonzero exit'}"


def evaluate_output(item: dict[str, Any], output: str) -> tuple[int, str]:
    """Dispatch to the deterministic evaluator named by item['eval']['method'].

    item['eval'] shapes:
      {"method": "json", "expected_keys": [...], "expected_json": {...}}
      {"method": "code", "test_suite": "assert ...", "timeout": 30}
    Returns (None, "no deterministic evaluator") when the item has no 'eval'
    block, so the caller can fall back to the LLM judge.
    """
    spec = item.get("eval")
    if not spec:
        return None, "no deterministic evaluator (use LLM judge)"
    method = spec.get("method")
    if method == "json":
        keys = spec.get("expected_keys")
        return eval_json_output(
            output,
            expected_keys=set(keys) if keys else None,
            expected_json=spec.get("expected_json"),
        )
    if method == "code":
        return eval_python_code(output, spec["test_suite"], timeout=int(spec.get("timeout", 30)))
    return None, f"unknown eval method: {method!r} (use LLM judge)"
