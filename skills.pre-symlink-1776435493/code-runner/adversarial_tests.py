#!/usr/bin/env python3
"""Adversarial tests for /code-runner — designed to find the limits.

These tests are EXPECTED to fail or partially fail. They test scenarios
that push beyond what a bounded subagent should handle:
  - Multi-file refactors requiring architecture decisions
  - Vague prompts that need clarification
  - Tasks requiring external knowledge
  - Cross-file dependency chains
  - Tasks where DoD is gameable

The goal is to map the boundary between "code-runner handles this" and
"this needs a project agent."
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
PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable


def _setup_repo(tmp: Path, files: dict[str, str] | None = None) -> Path:
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
    for f in out.rglob("*.result.json"):
        return json.loads(f.read_text())
    return {"status": "no_result", "returncode": proc.returncode, "stderr": proc.stderr[-300:]}


# ══════════════════════════════════════════════════════════════════════
# ADV 1: Multi-file refactor — LLM must edit 3 files consistently
# Expected: LIKELY FAIL — LLM generates inconsistent interfaces across files
# ══════════════════════════════════════════════════════════════════════
def test_adv_01_multi_file_refactor():
    name = "adv_01_multifile"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {
            "models.py": "class User:\n    def __init__(self, name):\n        self.name = name\n",
            "service.py": "from models import User\n\ndef get_user(name):\n    return User(name)\n",
            "api.py": "from service import get_user\n\ndef handler(request):\n    user = get_user(request['name'])\n    return {'name': user.name}\n",
        })
        spec = {
            "task_id": name, "title": "Add email field across 3 files",
            "prompt": "Add an 'email' field to User in models.py. Update service.py get_user to accept email param. Update api.py handler to pass email from request and return it.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["models.py", "service.py", "api.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from api import handler; r = handler({{'name': 'Alice', 'email': 'a@b.com'}}); assert r == {{'name': 'Alice', 'email': 'a@b.com'}}, f'got: {{r}}'; print('OK')\"",
                "assertion": "OK",
            },
        }
        # Mock: LLM returns all 3 files correctly (best case)
        mock = {"1": (
            '### FILE: models.py\n```python\nclass User:\n    def __init__(self, name, email=""):\n        self.name = name\n        self.email = email\n```\n\n'
            '### FILE: service.py\n```python\nfrom models import User\n\ndef get_user(name, email=""):\n    return User(name, email)\n```\n\n'
            '### FILE: api.py\n```python\nfrom service import get_user\n\ndef handler(request):\n    user = get_user(request["name"], request.get("email", ""))\n    return {"name": user.name, "email": user.email}\n```\n'
        )}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0), "expected": "PASS (but multi-file is fragile with real LLM)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# ADV 2: Architecture decision — LLM must choose between approaches
# Expected: LIKELY FAIL — code-runner is an executor, not an architect
# ══════════════════════════════════════════════════════════════════════
def test_adv_02_architecture_decision():
    name = "adv_02_architecture"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"cache.py": "# TODO: implement caching\ndata = {}\n"})
        spec = {
            "task_id": name, "title": "Implement caching with TTL",
            "prompt": "Implement a cache in cache.py with TTL expiry. Choose the best approach: dict with timestamps, OrderedDict LRU, or functools.lru_cache wrapper. The cache must support get(key), set(key, value, ttl_seconds), and auto-expire.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["cache.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"import time; from cache import Cache; c = Cache(); c.set('k', 'v', 0.1); assert c.get('k') == 'v'; time.sleep(0.2); assert c.get('k') is None; print('OK')\"",
                "assertion": "OK",
            },
        }
        # Mock: LLM chooses dict+timestamps approach
        mock = {"1": '### FILE: cache.py\n```python\nimport time\n\nclass Cache:\n    def __init__(self):\n        self._data = {}\n    def set(self, key, value, ttl_seconds=60):\n        self._data[key] = (value, time.time() + ttl_seconds)\n    def get(self, key):\n        if key not in self._data:\n            return None\n        value, expires = self._data[key]\n        if time.time() > expires:\n            del self._data[key]\n            return None\n        return value\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0), "expected": "PASS with mock (but asks LLM to make design choice)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# ADV 3: Gameable DoD — LLM can pass by cheating
# Expected: PASS (the DoD is weak — code-runner can't detect gaming)
# ══════════════════════════════════════════════════════════════════════
def test_adv_03_gameable_dod():
    name = "adv_03_gameable"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"sort.py": "def sort_list(lst):\n    pass\n"})
        spec = {
            "task_id": name, "title": "Implement sort",
            "prompt": "Implement sort_list in sort.py that sorts a list of integers.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["sort.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from sort import sort_list; print(sort_list([3,1,2]))\"",
                "assertion": "[1, 2, 3]",
            },
        }
        # Mock: LLM "cheats" by hardcoding the expected output
        mock = {"1": '### FILE: sort.py\n```python\ndef sort_list(lst):\n    return [1, 2, 3]  # hardcoded cheat\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0),
                "expected": "PASS (DoD is gameable — this is why blind_tests exist)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# ADV 4: External dependency — requires pip install
# Expected: FAIL — code-runner doesn't install packages
# ══════════════════════════════════════════════════════════════════════
def test_adv_04_external_dependency():
    name = "adv_04_dependency"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"fetch.py": "# TODO: fetch URL\n"})
        spec = {
            "task_id": name, "title": "Fetch URL with httpx",
            "prompt": "Write fetch.py with a fetch(url) function that returns the response text using httpx.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["fetch.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from fetch import fetch; print('OK')\"",
                "assertion": "OK",
            },
        }
        # Mock: LLM writes code that imports httpx (may not be installed in test env)
        mock = {"1": '### FILE: fetch.py\n```python\nimport httpx\n\ndef fetch(url):\n    return httpx.get(url).text\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0),
                "expected": "DEPENDS — passes if httpx installed in python path, fails otherwise"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# ADV 5: Vague prompt that passes preflight but confuses LLM
# Expected: FAIL or low score — prompt is technically 20+ chars but meaningless
# ══════════════════════════════════════════════════════════════════════
def test_adv_05_vague_but_passes_preflight():
    name = "adv_05_vague_passes"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        repo = _setup_repo(tmp, {"main.py": "# placeholder\n"})
        spec = {
            "task_id": name, "title": "Do the thing with the stuff",
            "prompt": "Make main.py better and more robust and production ready please fix all the issues.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["main.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 main.py",
                "assertion": "exit_code == 0",
            },
        }
        # Mock: LLM returns something that runs but is useless
        mock = {"1": '### FILE: main.py\n```python\n# Production ready\nprint("Hello")\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0),
                "expected": "PASS (vague prompt + weak DoD = false positive — preflight should catch this)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# ADV 6: Large file edit — LLM must modify a 200-line file precisely
# Expected: FRAGILE — diff application may fail on large files
# ══════════════════════════════════════════════════════════════════════
def test_adv_06_large_file_edit():
    name = "adv_06_large_file"
    tmp = Path(tempfile.mkdtemp(prefix=f"cr-{name}-"))
    try:
        # Generate a 200-line file
        lines = [f"def func_{i}():\n    return {i}\n" for i in range(100)]
        repo = _setup_repo(tmp, {"big.py": "\n".join(lines)})
        spec = {
            "task_id": name, "title": "Fix func_42 in big.py",
            "prompt": "In big.py, func_42() returns 42. Change it to return 42 * 2 (84). Do not modify any other function.",
            "backend": "test", "cwd": str(repo),
            "allowlist": ["big.py"],
            "definition_of_done": {
                "command": f"cd {repo} && python3 -c \"from big import func_42, func_41, func_43; assert func_42()==84; assert func_41()==41; assert func_43()==43; print('OK')\"",
                "assertion": "OK",
            },
        }
        # Mock: LLM returns full file (common mistake for large files)
        fixed_lines = list(lines)
        fixed_lines[42] = "def func_42():\n    return 84\n"
        mock = {"1": '### FILE: big.py\n```python\n' + "\n".join(fixed_lines) + '\n```\n'}
        result = _run_with_mock(spec, mock, tmp)
        return {"name": name, "status": result.get("status"), "dod_passed": result.get("dod_passed"),
                "rounds": result.get("rounds", 0),
                "expected": "PASS with mock (but real LLM often truncates large files)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_adv_01_multi_file_refactor,
    test_adv_02_architecture_decision,
    test_adv_03_gameable_dod,
    test_adv_04_external_dependency,
    test_adv_05_vague_but_passes_preflight,
    test_adv_06_large_file_edit,
]

if __name__ == "__main__":
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="/code-runner Adversarial Test Report", show_lines=True)
        table.add_column("#", min_width=3)
        table.add_column("Test", min_width=25)
        table.add_column("Status", min_width=6, justify="center")
        table.add_column("DoD", min_width=5, justify="center")
        table.add_column("Rounds", min_width=3, justify="center")
        table.add_column("Expected Outcome", min_width=40)

        for i, test_fn in enumerate(ALL_TESTS, 1):
            try:
                result = test_fn()
                status = result.get("status", "?")
                dod = result.get("dod_passed", False)
                s_style = "green" if status == "pass" else ("red" if status == "fail" else "yellow")
                d_style = "green" if dod else "red"
                table.add_row(
                    str(i), result["name"],
                    f"[{s_style}]{status}[/{s_style}]",
                    f"[{d_style}]{dod}[/{d_style}]",
                    str(result.get("rounds", 0)),
                    result.get("expected", ""),
                )
            except Exception as e:
                table.add_row(str(i), test_fn.__name__, "[red]CRASH[/red]", "", "", str(e)[:60])

        console.print(table)
    except ImportError:
        for i, test_fn in enumerate(ALL_TESTS, 1):
            try:
                result = test_fn()
                print(f"{i}. {result['name']}: status={result['status']} dod={result['dod_passed']} rounds={result['rounds']} | {result['expected']}")
            except Exception as e:
                print(f"{i}. {test_fn.__name__}: CRASH: {e}")
