#!/usr/bin/env python3
"""Comprehensive stress tests for /code-runner.

12 end-to-end tests covering:
  - Code generation (Python, multi-file)
  - Bug fixing (logic errors, edge cases)
  - Compliance (best-practices enforcement)
  - Preflight rejection (vague specs, missing fields)
  - Off-topic rejection (non-code tasks)
  - Multi-round recovery (mock LLM fail-then-pass)
  - Allowlist enforcement (write outside scope)
  - Denylist enforcement (write to protected files)
  - Non-git graceful degradation
  - Directory allowlist scope
  - Pre-write lint gate (syntax errors rejected)
  - DoD assertion types (exit_code, substring)

Each test sets up a temp git repo, builds a spec, mocks _call_llm,
runs code-runner, and asserts on result.json + filesystem state.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# Use system Python to avoid project venv loguru circular import bug
PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
PASS_COUNT = 0
FAIL_COUNT = 0
ERRORS: list[str] = []


def _setup_repo(tmp: Path, files: dict[str, str] | None = None) -> Path:
    """Create a temp git repo with optional initial files."""
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    for name, content in (files or {}).items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


def _run_with_mock(spec: dict, mock_responses: dict[str, str], tmp: Path,
                   max_rounds: int = 3) -> dict:
    """Run code-runner with mocked _call_llm. Returns result dict."""
    out = tmp / "output"
    spec["output_dir"] = str(out)
    spec_file = tmp / "spec.json"
    spec_file.write_text(json.dumps(spec))
    resp_file = tmp / "responses.json"
    resp_file.write_text(json.dumps(mock_responses))

    runner = tmp / "run.py"
    runner.write_text(
        f"import sys, json\n"
        f"sys.path.insert(0, {str(SCRIPT_DIR)!r})\n"
        f"import code_runner\n"
        f"_c=[0]\n"
        f"_r=json.loads(open({str(resp_file)!r}).read())\n"
        f"def mock(p,b,c,**kw):\n"
        f"    _c[0]+=1; return _r.get(str(_c[0]),'')\n"
        f"code_runner._call_llm=mock\n"
        f"try:\n"
        f"    code_runner.app(['run',{str(spec_file)!r},'--max-rounds','{max_rounds}'])\n"
        f"except SystemExit:\n"
        f"    pass\n"
    )
    proc = subprocess.run(
        [PYTHON, str(runner)],
        capture_output=True, text=True, timeout=60,
        cwd=spec.get("cwd", str(tmp)),
    )
    # Find result.json
    for f in out.rglob("*.result.json"):
        return json.loads(f.read_text())
    return {"status": "no_result", "stderr": proc.stderr[-500:]}


def _run_direct(spec: dict, tmp: Path, max_rounds: int = 1) -> dict:
    """Run code-runner directly (no mock) for preflight tests. Returns result dict."""
    out = tmp / "output"
    spec["output_dir"] = str(out)
    spec_file = tmp / "spec.json"
    spec_file.write_text(json.dumps(spec))

    proc = subprocess.run(
        [PYTHON, str(SCRIPT_DIR / "code_runner.py"), "run", str(spec_file),
         "--max-rounds", str(max_rounds)],
        capture_output=True, text=True, timeout=30,
        cwd=spec.get("cwd", str(tmp)),
    )
    for f in out.rglob("*.result.json"):
        return json.loads(f.read_text())
    return {"status": "no_result", "returncode": proc.returncode, "stderr": proc.stderr[-300:]}


def _assert(test_name: str, condition: bool, msg: str):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        ERRORS.append(f"[{test_name}] {msg}")


# ══════════════════════════════════════════════════════════════════════
# TEST 1: Simple code generation — write a new Python file
# ══════════════════════════════════════════════════════════════════════
def test_01_simple_code_generation():
    name = "01_simple_code_gen"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp)
        spec = {
            "task_id": name, "title": "Write a fibonacci function",
            "prompt": "Create fib.py with a fibonacci(n) function that returns the nth fibonacci number. fib(0)=0, fib(1)=1.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["fib.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from fib import fibonacci; assert fibonacci(10)==55; print('OK')\"",
                "assertion": "OK",
            },
        }
        mock = {"1": '### FILE: fib.py\n```python\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    a, b = 0, 1\n    for _ in range(2, n + 1):\n        a, b = b, a + b\n    return b\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"expected dod_passed=True, got {result.get('dod_passed')}")
        _assert(name, result.get("status") == "pass", f"expected pass, got {result.get('status')}")
        _assert(name, (repo / "fib.py").exists(), "fib.py not created")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 2: Bug fix — fix an existing file with a logic error
# ══════════════════════════════════════════════════════════════════════
def test_02_bug_fix():
    name = "02_bug_fix"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"calc.py": "def add(a, b):\n    return a - b  # BUG\n"})
        spec = {
            "task_id": name, "title": "Fix add function",
            "prompt": "Read calc.py. add(a,b) returns a-b instead of a+b. Fix it.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["calc.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from calc import add; assert add(2,3)==5; print('OK')\"",
                "assertion": "OK",
            },
        }
        mock = {"1": '### FILE: calc.py\n```python\ndef add(a, b):\n    return a + b\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        code = (repo / "calc.py").read_text()
        _assert(name, "a + b" in code, "fix not applied")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 3: Multi-round recovery — round 1 fails, round 2 passes
# ══════════════════════════════════════════════════════════════════════
def test_03_multiround_recovery():
    name = "03_multiround"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"counter.py": "class Counter:\n    def __init__(self):\n        self.value = 0\n    def reset(self):\n        pass  # BUG\n"})
        spec = {
            "task_id": name, "title": "Fix counter reset",
            "prompt": "Fix counter.py: reset() must set self.value = 0. Also add increment() and decrement().",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["counter.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from counter import Counter; c=Counter(); assert c.value==0, f'init:{{c.value}}'; c.value=5; c.reset(); assert c.value==0; print('OK')\"",
                "assertion": "OK",
            },
        }
        # Round 1: fixes reset but breaks init
        bad = '### FILE: counter.py\n```python\nclass Counter:\n    def __init__(self):\n        self.value = "zero"  # BUG\n    def reset(self):\n        self.value = 0\n```\n'
        # Round 2: correct
        good = '### FILE: counter.py\n```python\nclass Counter:\n    def __init__(self):\n        self.value = 0\n    def reset(self):\n        self.value = 0\n    def increment(self):\n        self.value += 1\n    def decrement(self):\n        self.value -= 1\n```\n'
        result = _run_with_mock(spec, {"1": bad, "2": good, "3": good}, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        _assert(name, result.get("rounds", 0) >= 2, f"expected >=2 rounds, got {result.get('rounds')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 4: Preflight rejects vague prompt
# ══════════════════════════════════════════════════════════════════════
def test_04_preflight_vague():
    name = "04_preflight_vague"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        spec = {
            "task_id": name, "title": "bad",
            "prompt": "fix it",
            "backend": "test", "cwd": str(tmp),
        }
        result = _run_direct(spec, tmp)
        _assert(name, result.get("status") == "preflight_fail", f"expected preflight_fail, got {result.get('status')}")
        errors = result.get("preflight_errors", [])
        fields = [e.get("field") for e in errors]
        _assert(name, "prompt" in fields, "should flag vague prompt")
        _assert(name, any("definition_of_done" in f for f in fields), "should flag missing DoD")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 5: Preflight rejects missing allowlist
# ══════════════════════════════════════════════════════════════════════
def test_05_preflight_no_allowlist():
    name = "05_preflight_allowlist"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        spec = {
            "task_id": name, "title": "has DoD but no allowlist",
            "prompt": "Read main.py and fix the TypeError on line 12 where name is None",
            "backend": "test", "cwd": str(tmp),
            "definition_of_done": {"command": "python3 main.py", "assertion": "OK"},
        }
        result = _run_direct(spec, tmp)
        _assert(name, result.get("status") == "preflight_fail", f"expected preflight_fail, got {result.get('status')}")
        errors = result.get("preflight_errors", [])
        has_allowlist_error = any("allowlist" in (e.get("error", "") + e.get("field", "")) for e in errors)
        _assert(name, has_allowlist_error, "should flag missing allowlist")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 6: Allowlist enforcement — LLM tries to write outside scope
# ══════════════════════════════════════════════════════════════════════
def test_06_allowlist_enforcement():
    name = "06_allowlist"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"allowed.py": "x = 1\n"})
        spec = {
            "task_id": name, "title": "Test allowlist",
            "prompt": "Write allowed.py with x=42. Do not write anything else.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["allowed.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from allowed import x; assert x==42; print('OK')\"",
                "assertion": "OK",
            },
        }
        # LLM tries to write both allowed.py AND secret.py
        mock = {"1": '### FILE: allowed.py\n```python\nx = 42\n```\n\n### FILE: secret.py\n```python\nprint("leaked")\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        _assert(name, not (repo / "secret.py").exists(), "secret.py should NOT have been written (allowlist violation)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 7: Denylist enforcement — LLM tries to write .env
# ══════════════════════════════════════════════════════════════════════
def test_07_denylist_enforcement():
    name = "07_denylist"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"app.py": "x = 1\n"})
        spec = {
            "task_id": name, "title": "Test denylist",
            "prompt": "Write app.py with x=42.",
            "backend": "test", "cwd": str(repo),
            "allowlist_optional": True,
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from app import x; assert x==42; print('OK')\"",
                "assertion": "OK",
            },
        }
        # LLM tries to write .env (denylisted)
        mock = {"1": '### FILE: app.py\n```python\nx = 42\n```\n\n### FILE: .env\n```\nSECRET=leaked\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, not (repo / ".env").exists(), ".env should NOT have been written (denylist)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 8: Pre-write lint gate — LLM returns invalid Python
# ══════════════════════════════════════════════════════════════════════
def test_08_prewrite_lint_gate():
    name = "08_lint_gate"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"broken.py": "x = 1\n"})
        spec = {
            "task_id": name, "title": "Lint gate test",
            "prompt": "Fix broken.py to print hello. The file must be valid Python.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["broken.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 broken.py",
                "assertion": "hello",
            },
        }
        # Round 1: syntax error (compile() should reject before writing)
        # Round 2: valid
        bad_syntax = '### FILE: broken.py\n```python\ndef broken(\n    print("hello"\n```\n'
        good = '### FILE: broken.py\n```python\nprint("hello")\n```\n'
        result = _run_with_mock(spec, {"1": bad_syntax, "2": good, "3": good}, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        code = (repo / "broken.py").read_text()
        _assert(name, "def broken(" not in code, "syntax-error code should have been rejected")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 9: Non-git graceful degradation
# ══════════════════════════════════════════════════════════════════════
def test_09_non_git():
    name = "09_non_git"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        # No git init — just a plain directory
        (tmp / "hello.py").write_text("# empty\n")
        spec = {
            "task_id": name, "title": "Non-git test",
            "prompt": "Write hello.py that prints hello world to stdout.",
            "backend": "test", "cwd": str(tmp),
            "allowlist": ["hello.py"],
            "definition_of_done": {
                "command": f"cd {tmp} && python3 hello.py",
                "assertion": "hello world",
            },
        }
        mock = {"1": '### FILE: hello.py\n```python\nprint("hello world")\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        _assert(name, result.get("status") == "pass", f"status={result.get('status')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 10: Directory allowlist scope — "scripts/" allows scripts/foo.py
# ══════════════════════════════════════════════════════════════════════
def test_10_directory_allowlist():
    name = "10_dir_allowlist"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"scripts/placeholder": ""})
        spec = {
            "task_id": name, "title": "Directory allowlist",
            "prompt": "Create scripts/hello.py that prints hello.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["scripts/"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 scripts/hello.py",
                "assertion": "hello",
            },
        }
        mock = {"1": '### FILE: scripts/hello.py\n```python\nprint("hello")\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        _assert(name, (repo / "scripts" / "hello.py").exists(), "scripts/hello.py not created")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 11: Compliance — best-practices violations detected
# ══════════════════════════════════════════════════════════════════════
def test_11_best_practices():
    name = "11_compliance"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"app.py": "# placeholder\n"})
        spec = {
            "task_id": name, "title": "Compliance test",
            "prompt": "Write app.py that fetches a URL and logs the result. Use proper libraries.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["app.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"import ast; ast.parse(open('app.py').read()); print('OK')\"",
                "assertion": "OK",
            },
        }
        # LLM uses import requests and import logging (both violate best-practices)
        bad_bp = '### FILE: app.py\n```python\nimport requests\nimport logging\n\nlogger = logging.getLogger(__name__)\n\ndef fetch(url):\n    resp = requests.get(url)\n    logger.info(resp.text)\n    return resp.text\n```\n'
        result = _run_with_mock(spec, {"1": bad_bp}, tmp)
        # DoD passes (valid Python) but score should be < 1.0 due to BP violations
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
        details = result.get("round_details", [{}])
        bp = details[0].get("bp_violations", [])
        _assert(name, len(bp) >= 2, f"expected >=2 bp_violations (requests + logging), got {bp}")
        _assert(name, details[0].get("score", 1.0) < 1.0, "score should be <1.0 with BP violations")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST 12: DoD with exit_code assertion
# ══════════════════════════════════════════════════════════════════════
def test_12_exit_code_assertion():
    name = "12_exit_code"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp)
        spec = {
            "task_id": name, "title": "Exit code test",
            "prompt": "Create check.py that exits with code 0 if all checks pass, code 1 otherwise.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["check.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 check.py",
                "assertion": "exit_code == 0",
            },
        }
        mock = {"1": '### FILE: check.py\n```python\nimport sys\nprint("all checks passed")\nsys.exit(0)\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        _assert(name, result.get("dod_passed") is True, f"dod_passed={result.get('dod_passed')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# TEST METADATA (for table report)
# ══════════════════════════════════════════════════════════════════════
TEST_META = {
    "test_01_simple_code_generation":  {"category": "Code Gen",   "desc": "Write new Python file, DoD verifies output"},
    "test_02_bug_fix":                 {"category": "Bug Fix",    "desc": "Fix existing file logic error"},
    "test_03_multiround_recovery":     {"category": "Recovery",   "desc": "Round 1 fails DoD → round 2 passes"},
    "test_04_preflight_vague":         {"category": "Preflight",  "desc": "Rejects vague prompt (<20 chars)"},
    "test_05_preflight_no_allowlist":  {"category": "Preflight",  "desc": "Rejects missing allowlist"},
    "test_06_allowlist_enforcement":   {"category": "Security",   "desc": "Blocks writes outside allowlist"},
    "test_07_denylist_enforcement":    {"category": "Security",   "desc": "Blocks writes to .env (denylisted)"},
    "test_08_prewrite_lint_gate":      {"category": "Lint Gate",  "desc": "Rejects syntax errors before disk write"},
    "test_09_non_git":                 {"category": "Graceful",   "desc": "Works in non-git directory"},
    "test_10_directory_allowlist":     {"category": "Security",   "desc": "Dir scope scripts/ allows scripts/hello.py"},
    "test_11_best_practices":         {"category": "Compliance",  "desc": "Detects import requests + import logging"},
    "test_12_exit_code_assertion":     {"category": "DoD",        "desc": "exit_code == 0 expression evaluation"},
}

ALL_TESTS = [
    test_01_simple_code_generation,
    test_02_bug_fix,
    test_03_multiround_recovery,
    test_04_preflight_vague,
    test_05_preflight_no_allowlist,
    test_06_allowlist_enforcement,
    test_07_denylist_enforcement,
    test_08_prewrite_lint_gate,
    test_09_non_git,
    test_10_directory_allowlist,
    test_11_best_practices,
    test_12_exit_code_assertion,
]


def _print_table(results: list[dict]) -> None:
    """Print Rich table if available, otherwise ASCII fallback."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="/code-runner Stress Test Report", show_lines=True)
        table.add_column("#", style="dim", min_width=3)
        table.add_column("Category", style="cyan", min_width=10)
        table.add_column("Test", min_width=20)
        table.add_column("Description", min_width=30)
        table.add_column("Status", min_width=6, justify="center")
        table.add_column("Error", min_width=20)

        for r in results:
            status_style = "green" if r["status"] == "PASS" else ("red" if r["status"] == "FAIL" else "yellow")
            table.add_row(
                r["num"], r["category"], r["name"], r["desc"],
                f"[{status_style}]{r['status']}[/{status_style}]",
                r.get("error", ""),
            )

        passed = sum(1 for r in results if r["status"] == "PASS")
        total = len(results)
        console.print(table)
        console.print(f"\n[bold]{'[green]ALL PASSED' if passed == total else f'[red]{total - passed} FAILED'}[/bold] — {passed}/{total} tests, {PASS_COUNT} assertions")
    except ImportError:
        # ASCII fallback
        print(f"\n{'#':<4} {'Category':<12} {'Test':<30} {'Status':<8} {'Error'}")
        print("-" * 90)
        for r in results:
            err = r.get("error", "")[:40]
            print(f"{r['num']:<4} {r['category']:<12} {r['name']:<30} {r['status']:<8} {err}")
        print(f"\n{PASS_COUNT} assertions passed, {FAIL_COUNT} failed")


if __name__ == "__main__":
    results: list[dict] = []

    for test_fn in ALL_TESTS:
        test_name = test_fn.__name__
        meta = TEST_META.get(test_name, {"category": "?", "desc": "?"})
        num = test_name.split("_")[1] if "_" in test_name else "?"
        entry = {
            "num": num, "name": test_name, "status": "PASS",
            "category": meta["category"], "desc": meta["desc"], "error": "",
        }
        try:
            errors_before = len(ERRORS)
            test_fn()
            new_errors = ERRORS[errors_before:]
            if new_errors:
                entry["status"] = "FAIL"
                entry["error"] = new_errors[0].split("] ", 1)[-1][:60]
        except Exception as e:
            FAIL_COUNT += 1
            entry["status"] = "CRASH"
            entry["error"] = str(e)[:60]
            ERRORS.append(f"[{test_name}] CRASHED: {e}")

        results.append(entry)

    _print_table(results)

    # Write JSON report for CI/monitoring
    report_file = SCRIPT_DIR / "stress_test_report.json"
    report_file.write_text(json.dumps({
        "timestamp": __import__("time").time(),
        "passed": PASS_COUNT, "failed": FAIL_COUNT,
        "total_tests": len(ALL_TESTS), "total_assertions": PASS_COUNT + FAIL_COUNT,
        "results": results,
    }, indent=2))

    sys.exit(1 if FAIL_COUNT else 0)
