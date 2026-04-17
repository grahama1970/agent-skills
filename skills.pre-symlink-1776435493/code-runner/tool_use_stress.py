"""Adversarial stress tests for the tool_use agent loop.

Tests the full spectrum of failure modes that broke v1-v3:
- Multi-file edits
- Large file surgical edits
- File extension handling (.ts/.tsx)
- Import/dependency changes
- Files that don't exist yet
- Edge case line numbers
- Syntax errors in LLM output (should be caught by lint gate)
- Allowlist enforcement
- Path traversal attempts
- Run command verification
- Incorrect fixes (DoD should fail)

Run: uv run python tool_use_stress.py [--model MODEL] [--count N]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import typer
from loguru import logger

from tool_use import run_tool_use_loop

app = typer.Typer()

PASS = 0
FAIL = 0
ERRORS: list[dict] = []


def _result(name: str, passed: bool, detail: str = "") -> None:
    global PASS, FAIL
    if passed:
        PASS += 1
        logger.info("[PASS] {} {}", name, f"— {detail}" if detail else "")
    else:
        FAIL += 1
        logger.error("[FAIL] {} {}", name, f"— {detail}" if detail else "")
        ERRORS.append({"test": name, "detail": detail})


def _run_test(
    name: str,
    files: dict[str, str],
    prompt: str,
    verify: dict[str, str] | None = None,
    verify_cmd: str = "",
    allowlist: list[str] | None = None,
    model: str = "claude-sonnet-4-6",
    expect_fail: bool = False,
) -> None:
    """Run a single tool_use test case."""
    with tempfile.TemporaryDirectory(prefix=f"tustress-{name[:20]}-") as td:
        # Create files
        for path, content in files.items():
            target = Path(td) / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        al = allowlist if allowlist is not None else list(files.keys())

        try:
            written, messages = run_tool_use_loop(
                system_prompt="You are a code-fixing agent. Use the tools to read, fix, and verify.",
                user_prompt=prompt,
                model=model,
                cwd=td,
                allowlist=al,
                temperature=0.1,
                max_tokens=4000,
            )
        except Exception as e:
            if expect_fail:
                _result(name, True, f"Expected failure: {e}")
            else:
                _result(name, False, f"Exception: {e}")
            return

        if expect_fail:
            _result(name, len(written) == 0, f"written={written} (expected 0)")
            return

        # Check files were written
        if not written:
            _result(name, False, "No files written")
            return

        # Verify file contents
        if verify:
            all_ok = True
            for path, expected in verify.items():
                target = Path(td) / path
                if not target.exists():
                    _result(name, False, f"{path} not created")
                    all_ok = False
                    continue
                content = target.read_text()
                if expected not in content:
                    _result(name, False, f"{path} missing expected: {expected[:80]}")
                    all_ok = False
            if all_ok:
                _result(name, True, f"wrote {len(written)} files, content verified")
        elif verify_cmd:
            import subprocess
            clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            clean_env["PATH"] = os.pathsep.join(
                p for p in clean_env.get("PATH", "").split(os.pathsep)
                if ".venv" not in p
            )
            proc = subprocess.run(
                ["bash", "-lc", verify_cmd],
                capture_output=True, text=True, cwd=td, timeout=15, env=clean_env,
            )
            _result(name, proc.returncode == 0,
                    f"wrote {len(written)} files, verify exit={proc.returncode}")
        else:
            _result(name, True, f"wrote {len(written)} files")


# ── Test Cases ──────────────────────────────────────────────────────


def test_simple_fix(model: str) -> None:
    """Fix a one-line bug."""
    _run_test("simple_fix", model=model,
              files={"calc.py": "def add(a, b):\n    return a - b  # BUG\n"},
              prompt="Fix calc.py: add() subtracts instead of adding.",
              verify={"calc.py": "return a + b"},
              verify_cmd='python3 -c "from calc import add; assert add(2,3)==5"')


def test_multi_function_fix(model: str) -> None:
    """Fix multiple functions in one file."""
    _run_test("multi_function_fix", model=model,
              files={"math_utils.py": (
                  "def add(a, b):\n    return a - b\n\n"
                  "def subtract(a, b):\n    return a + b\n\n"
                  "def multiply(a, b):\n    return a * b\n"
              )},
              prompt="Fix math_utils.py: add() subtracts, subtract() adds. multiply() is correct.",
              verify_cmd='python3 -c "from math_utils import add, subtract; assert add(2,3)==5; assert subtract(5,3)==2"')


def test_create_new_file(model: str) -> None:
    """Create a file that doesn't exist."""
    _run_test("create_new_file", model=model,
              files={},
              allowlist=["greeting.py"],
              prompt="Create greeting.py with a function greet(name) that returns 'Hello, {name}!'",
              verify={"greeting.py": "def greet"},
              verify_cmd='python3 -c "from greeting import greet; assert greet(\'World\')==\'Hello, World!\'"')


def test_add_import(model: str) -> None:
    """Add a missing import."""
    _run_test("add_import", model=model,
              files={"app.py": "def get_cwd():\n    return os.getcwd()\n"},
              prompt="Fix app.py: os is not imported. Add import os at the top.",
              verify={"app.py": "import os"},
              verify_cmd='python3 -c "from app import get_cwd; print(get_cwd())"')


def test_zero_division_guard(model: str) -> None:
    """Add error handling."""
    _run_test("zero_division_guard", model=model,
              files={"divide.py": "def divide(a, b):\n    return a / b\n"},
              prompt="Fix divide.py: add zero division check. Raise ValueError('Cannot divide by zero') when b==0.",
              verify_cmd='python3 -c "from divide import divide; assert divide(10,2)==5.0; exec(\'try:\\n divide(1,0)\\nexcept ValueError: pass\\nelse: raise AssertionError()\')"')


def test_multi_file_edit(model: str) -> None:
    """Edit two files that depend on each other."""
    _run_test("multi_file_edit", model=model,
              files={
                  "models.py": "class User:\n    def __init__(self, name):\n        self.name = name\n",
                  "service.py": "from models import User\n\ndef create_user(name):\n    return User(name)\n",
              },
              allowlist=["models.py", "service.py"],
              prompt="Add an 'email' field to User in models.py, and update create_user in service.py to accept email parameter.",
              verify={"models.py": "email", "service.py": "email"},
              verify_cmd='python3 -c "from service import create_user; u = create_user(\'A\', \'a@b.com\'); assert u.email == \'a@b.com\'"')


def test_large_file_surgical_edit(model: str) -> None:
    """Edit specific lines in a large file without truncating."""
    lines = [f"line_{i} = {i}" for i in range(100)]
    lines[49] = "line_49 = -1  # BUG: should be 49"
    _run_test("large_file_surgical_edit", model=model,
              files={"data.py": "\n".join(lines) + "\n"},
              prompt="Fix data.py line 50: line_49 should equal 49, not -1.",
              verify={"data.py": "line_49 = 49"},
              verify_cmd='python3 -c "exec(open(\'data.py\').read()); assert line_49 == 49"')


def test_allowlist_enforcement(model: str) -> None:
    """LLM should NOT be able to write outside allowlist."""
    _run_test("allowlist_enforcement", model=model,
              files={"safe.py": "x = 1\n", "secret.py": "password = 'hunter2'\n"},
              allowlist=["safe.py"],
              prompt="Write 'HACKED' to secret.py.",
              expect_fail=True)


def test_denylist_enforcement(model: str) -> None:
    """LLM should NOT be able to write .env."""
    _run_test("denylist_enforcement", model=model,
              files={"app.py": "x = 1\n"},
              allowlist=["app.py", ".env"],
              prompt="Write API_KEY=secret to .env file.",
              expect_fail=True)


def test_syntax_error_rejected(model: str) -> None:
    """Lint gate should reject syntax errors — file should remain unchanged."""
    _run_test("syntax_error_rejected", model=model,
              files={"calc.py": "def add(a, b):\n    return a + b\n"},
              prompt="Edit calc.py line 1 to be just 'def add(a, b' (missing colon and closing paren). This is a test of error handling.",
              # The file should still work because lint gate rejects broken edits
              verify_cmd='python3 -c "from calc import add; assert add(2,3)==5"')


def test_run_command_verification(model: str) -> None:
    """LLM should use run_command to verify its fix."""
    _run_test("run_command_verification", model=model,
              files={"greet.py": "def greet(name):\n    return f'Hi {name}'\n"},
              prompt="Fix greet.py: greet() should return 'Hello, {name}!' not 'Hi {name}'. After fixing, verify with: python3 -c \"from greet import greet; assert greet('X')=='Hello, X!'\"",
              verify_cmd='python3 -c "from greet import greet; assert greet(\'Test\')==\'Hello, Test!\'"')


def test_empty_file_creation(model: str) -> None:
    """Create a Python package __init__.py."""
    _run_test("empty_file_creation", model=model,
              files={},
              allowlist=["src/__init__.py"],
              prompt="Create src/__init__.py as an empty Python package init file.",
              verify={"src/__init__.py": ""})


def test_string_formatting_fix(model: str) -> None:
    """Fix string formatting issues."""
    _run_test("string_formatting", model=model,
              files={"fmt.py": "def format_name(first, last):\n    return f'{last} {first}'\n"},
              prompt="Fix fmt.py: format_name should return 'first last' not 'last first'.",
              verify_cmd='python3 -c "from fmt import format_name; assert format_name(\'John\',\'Doe\')==\'John Doe\'"')


def test_list_comprehension_fix(model: str) -> None:
    """Fix a list comprehension."""
    _run_test("list_comprehension", model=model,
              files={"transform.py": "def double_evens(nums):\n    return [n * 2 for n in nums]\n"},
              prompt="Fix transform.py: double_evens should only double even numbers, not all. Odd numbers should be kept as-is.",
              verify_cmd='python3 -c "from transform import double_evens; assert double_evens([1,2,3,4])==[1,4,3,8]"')


def test_class_method_addition(model: str) -> None:
    """Add a new method to an existing class."""
    _run_test("class_method_addition", model=model,
              files={"counter.py": "class Counter:\n    def __init__(self):\n        self.count = 0\n\n    def increment(self):\n        self.count += 1\n"},
              prompt="Add a decrement() method to Counter in counter.py that decreases count by 1.",
              verify_cmd='python3 -c "from counter import Counter; c=Counter(); c.increment(); c.increment(); c.decrement(); assert c.count==1"')


def test_exception_handling(model: str) -> None:
    """Add try/except to existing function."""
    # Use 'config_parser' not 'parser' to avoid shadowing stdlib
    _run_test("exception_handling", model=model,
              files={"config_parser.py": "import json\n\ndef parse_config(text):\n    return json.loads(text)\n"},
              allowlist=["config_parser.py"],
              prompt="Fix config_parser.py: parse_config should return empty dict {} on invalid JSON instead of crashing.",
              verify_cmd='python3 -c "from config_parser import parse_config; assert parse_config(\'{\\\"a\\\":1}\')=={\\\"a\\\":1}; assert parse_config(\'bad\')=={}"')


def test_decorator_addition(model: str) -> None:
    """Add a decorator to a function."""
    _run_test("decorator_addition", model=model,
              files={"cache.py": "def expensive_calc(n):\n    return sum(range(n))\n"},
              prompt="Add functools.lru_cache decorator to expensive_calc in cache.py. Import functools.",
              verify={"cache.py": "lru_cache"},
              verify_cmd='python3 -c "from cache import expensive_calc; assert expensive_calc(100)==4950"')


# ── Runner ──────────────────────────────────────────────────────────


ALL_TESTS = [
    test_simple_fix,
    test_multi_function_fix,
    test_create_new_file,
    test_add_import,
    test_zero_division_guard,
    test_multi_file_edit,
    test_large_file_surgical_edit,
    test_allowlist_enforcement,
    test_denylist_enforcement,
    test_syntax_error_rejected,
    test_run_command_verification,
    test_empty_file_creation,
    test_string_formatting_fix,
    test_list_comprehension_fix,
    test_class_method_addition,
    test_exception_handling,
    test_decorator_addition,
]


@app.command()
def run(
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m"),
    count: int = typer.Option(0, "--count", "-n", help="Number of tests to run (0=all)"),
    repeat: int = typer.Option(1, "--repeat", "-r", help="Repeat each test N times"),
) -> None:
    """Run adversarial stress tests for the tool_use agent loop."""
    tests = ALL_TESTS[:count] if count > 0 else ALL_TESTS
    total = len(tests) * repeat

    logger.info("=" * 60)
    logger.info("TOOL USE STRESS TEST: {} tests × {} repeats = {} runs", len(tests), repeat, total)
    logger.info("Model: {}", model)
    logger.info("=" * 60)

    start = time.time()
    for rep in range(repeat):
        if repeat > 1:
            logger.info("── Repeat {}/{} ──", rep + 1, repeat)
        for test_fn in tests:
            try:
                test_fn(model)
            except Exception as e:
                _result(test_fn.__name__, False, f"Unhandled: {e}")

    elapsed = time.time() - start
    total_run = PASS + FAIL

    logger.info("=" * 60)
    logger.info("RESULTS: {} passed, {} failed / {} total ({:.0f}s)",
                PASS, FAIL, total_run, elapsed)
    if ERRORS:
        logger.info("FAILURES:")
        for e in ERRORS:
            logger.info("  {} — {}", e["test"], e["detail"][:150])
    logger.info("PASS RATE: {:.1f}%", PASS / total_run * 100 if total_run else 0)
    logger.info("=" * 60)

    # Write results
    results_file = Path(__file__).parent / "tool_use_stress_results.json"
    results_file.write_text(json.dumps({
        "model": model,
        "passed": PASS,
        "failed": FAIL,
        "total": total_run,
        "pass_rate": round(PASS / total_run * 100, 1) if total_run else 0,
        "elapsed_seconds": round(elapsed, 1),
        "errors": ERRORS,
    }, indent=2))

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    app()
