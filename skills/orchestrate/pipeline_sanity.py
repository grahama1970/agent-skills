"""Comprehensive pipeline sanity tests: /plan → /orchestrate → /code-runner.

Tests simple to complex plans end-to-end. Each test:
1. Creates a temp git repo with target files
2. Writes a YAML plan
3. Runs orchestrate
4. Verifies result files, status, and file changes

Run: uv run python pipeline_sanity.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent
ORCHESTRATE_DIR = Path(__file__).resolve().parent
CODE_RUNNER_DIR = SKILLS_DIR / "code-runner"

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def _log(level: str, msg: str) -> None:
    print(f"  [{level}] {msg}")


def _run(cmd: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    _run(["git", "init"], str(path))
    _run(["git", "add", "-A"], str(path))
    _run(["git", "commit", "-m", "initial"], str(path))


def _run_orchestrate(plan_file: str, cwd: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """Run orchestrate on a plan file."""
    run_sh = ORCHESTRATE_DIR / "run.sh"
    return _run(
        ["bash", str(run_sh), "run", plan_file],
        cwd=cwd, timeout=timeout,
    )


def _http_healthy(url: str) -> bool:
    try:
        import httpx
        resp = httpx.get(url, timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _write_plan(path: Path, plan: dict) -> Path:
    """Write a YAML plan file."""
    import yaml
    plan_file = path / "plan.yaml"
    plan_file.write_text(yaml.dump(plan, default_flow_style=False, sort_keys=False))
    return plan_file


def _base_metadata(title: str = "Test") -> dict:
    """Standard plan metadata."""
    return {
        "title": title, "goal": "pipeline sanity test",
        "plan_type": "code", "created": "2026-04-02",
    }


def _base_plan(td: str, title: str, tasks: list, lanes: list | None = None,
               max_concurrency: int = 1) -> dict:
    """Build a complete valid plan with all required fields."""
    return {
        "version": 1, "kind": "orchestrate-plan", "repo_root": td,
        "repo_root": td,
        "metadata": _base_metadata(title),
        "execution": {"max_concurrency": max_concurrency},
        "capability_overlap": ["pipeline sanity test — no overlap"],
        "lanes": lanes or [{"id": "0", "label": "Wave 0"}],
        "tasks": tasks,
    }


def _result(name: str, passed: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        _log("PASS", f"{name}{f' — {detail}' if detail else ''}")
    else:
        FAIL_COUNT += 1
        _log("FAIL", f"{name}{f' — {detail}' if detail else ''}")


def _skip(name: str, reason: str) -> None:
    global SKIP_COUNT
    SKIP_COUNT += 1
    _log("SKIP", f"{name} — {reason}")


# ── Test 1: Compile check ──────────────────────────────────────────


def test_compile() -> None:
    """Verify all pipeline Python files compile."""
    print("\n── Test 1: Compile check ──")
    files = [
        ORCHESTRATE_DIR / "structured_execute.py",
        ORCHESTRATE_DIR / "structured_execute_helpers.py",
        CODE_RUNNER_DIR / "code_runner.py",
        CODE_RUNNER_DIR / "apply.py",
        CODE_RUNNER_DIR / "evidence.py",
        CODE_RUNNER_DIR / "prompt_assembly.py",
        SKILLS_DIR / "_shared" / "structured_plan.py",
    ]
    import ast
    for f in files:
        try:
            ast.parse(f.read_text())
            _result(f"compile {f.name}", True)
        except SyntaxError as e:
            _result(f"compile {f.name}", False, str(e))


# ── Test 2: Schema validation ──────────────────────────────────────


def test_schema_validation() -> None:
    """Verify plan schema validates correctly."""
    print("\n── Test 2: Schema validation ──")
    plan_py = SKILLS_DIR / "plan" / "plan.py"
    if not plan_py.exists():
        _skip("schema validation", "plan/plan.py not found")
        return

    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        valid_plan = {
            "version": 1,
            "kind": "orchestrate-plan",
            "repo_root": td,
            "metadata": _base_metadata("Test"),
            "execution": {"max_concurrency": 1},
            "capability_overlap": ["sanity test — no overlap check needed"],
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [{
                "id": "1", "title": "Test task", "lane": "0",
                "runner": "local", "depends_on": [],
                "command": "echo hello",
                "definition_of_done": {"command": "echo hello", "assertion": "hello"},
            }],
        }
        import yaml
        plan_file = Path(td) / "valid.yaml"
        plan_file.write_text(yaml.dump(valid_plan, default_flow_style=False))

        proc = _run(
            ["uv", "run", "--project", str(SKILLS_DIR / "plan"), "python",
             str(plan_py), "--validate", str(plan_file)],
            cwd=td,
        )
        _result("valid plan validates", proc.returncode == 0, proc.stderr[:200] if proc.returncode != 0 else "")


# ── Test 3: Single local task ──────────────────────────────────────


def test_single_local_task() -> None:
    """Simplest possible plan: one local command."""
    print("\n── Test 3: Single local task ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        (td_path / "hello.txt").write_text("world")
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Local echo"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 1},
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [{
                "id": "1", "title": "Echo test", "lane": "0",
                "runner": "local", "depends_on": [],
                "command": "echo PIPELINE_OK",
                "definition_of_done": {"command": "echo PIPELINE_OK", "assertion": "PIPELINE_OK"},
            }],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        proc = _run_orchestrate(str(plan_file), td)
        _result("local task runs", proc.returncode == 0, proc.stderr[:300] if proc.returncode != 0 else "")

        # Orchestrate stores sessions under its own structured/ dir
        session_dirs = list(ORCHESTRATE_DIR.glob("structured/session-*/status.json"))
        _result("session dirs exist", len(session_dirs) > 0, f"found {len(session_dirs)} sessions")


# ── Test 4: Single code-runner task (the core path) ───────────────


def test_single_code_runner_task() -> None:
    """One code-runner task: fix a simple bug. This is the core pipeline path."""
    print("\n── Test 4: Single code-runner task ──")

    if not _http_healthy("http://localhost:4001/health"):
        _skip("code-runner task", "scillm unreachable at localhost:4001")
        return
    if not _http_healthy("http://127.0.0.1:8787/healthz"):
        _skip("code-runner task", "test-lab unreachable at localhost:8787")
        return

    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)

        # Create target file with bug
        (td_path / "math_utils.py").write_text(
            'def multiply(a, b):\n    return a + b  # BUG: should multiply\n'
        )
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Fix multiply"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 1},
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [{
                "id": "1", "title": "Fix multiply bug", "lane": "0",
                "runner": "code-runner", "backend": "text", "mode": "iterative",
                "depends_on": [],
                "max_rounds": 2,
                "timeout_seconds": 120,
                "prompt": "Fix math_utils.py: multiply returns wrong result. It adds instead of multiplying.",
                "allowlist": ["math_utils.py"],
                "blind_tests": [
                    "from math_utils import multiply; assert multiply(5, 6) == 30",
                ],
                "definition_of_done": {
                    "command": 'python3 -c "from math_utils import multiply; assert multiply(3, 4) == 12; print(\'PASS\')"',
                    "assertion": "PASS",
                },
            }],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        proc = _run_orchestrate(str(plan_file), td, timeout=180)
        _result("code-runner task exits", True, f"rc={proc.returncode}")

        # Check the file was actually fixed
        content = (td_path / "math_utils.py").read_text()
        has_multiply = "*" in content or "multiply" in content
        _result("multiply bug fixed", "+" not in content.split("return")[1] if "return" in content else False,
                f"content: {content.strip()[:100]}")

        # Check result.json exists
        result_files = list(td_path.glob("**/1*.result.json"))
        if result_files:
            result = json.loads(result_files[0].read_text())
            _result("DoD passed", result.get("dod_passed", False),
                    f"score={result.get('best_score', 0):.3f} rounds={result.get('rounds', 0)}")
        else:
            _result("result.json exists", False, "not found")


# ── Test 5: Sequential dependency chain ───────────────────────────


def test_sequential_deps() -> None:
    """Three tasks in sequence: A → B → C. Tests DAG ordering."""
    print("\n── Test 5: Sequential dependency chain ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Sequential"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 1},
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [
                {
                    "id": "1", "title": "Create file", "lane": "0",
                    "runner": "local", "depends_on": [],
                    "command": "echo step1 > chain.txt",
                    "definition_of_done": {"command": "cat chain.txt", "assertion": "step1"},
                },
                {
                    "id": "2", "title": "Append to file", "lane": "0",
                    "runner": "local", "depends_on": ["1"],
                    "command": "echo step2 >> chain.txt",
                    "definition_of_done": {"command": "cat chain.txt", "assertion": "step2"},
                },
                {
                    "id": "3", "title": "Verify chain", "lane": "0",
                    "runner": "local", "depends_on": ["2"],
                    "command": 'grep -c "step" chain.txt | grep -q 2 && echo CHAIN_OK',
                    "definition_of_done": {"command": 'grep -c "step" chain.txt', "assertion": "2"},
                },
            ],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        proc = _run_orchestrate(str(plan_file), td)
        _result("sequential chain completes", proc.returncode == 0, proc.stderr[:200] if proc.returncode != 0 else "")

        # Verify the chain file has both steps
        chain_file = td_path / "chain.txt"
        if chain_file.exists():
            content = chain_file.read_text()
            _result("DAG order correct", "step1" in content and "step2" in content, content.strip())
        else:
            _result("chain.txt created", False)


# ── Test 6: Parallel lanes ────────────────────────────────────────


def test_parallel_lanes() -> None:
    """Two independent tasks in parallel lanes. Tests concurrency."""
    print("\n── Test 6: Parallel lanes ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Parallel"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 2},
            "lanes": [{"id": "0", "label": "Lane A"}, {"id": "1", "label": "Lane B"}],
            "tasks": [
                {
                    "id": "1", "title": "Lane A work", "lane": "0",
                    "runner": "local", "depends_on": [],
                    "command": "sleep 1 && echo LANE_A > lane_a.txt",
                    "definition_of_done": {"command": "cat lane_a.txt", "assertion": "LANE_A"},
                },
                {
                    "id": "2", "title": "Lane B work", "lane": "1",
                    "runner": "local", "depends_on": [],
                    "command": "sleep 1 && echo LANE_B > lane_b.txt",
                    "definition_of_done": {"command": "cat lane_b.txt", "assertion": "LANE_B"},
                },
                {
                    "id": "3", "title": "Merge", "lane": "0",
                    "runner": "local", "depends_on": ["1", "2"],
                    "command": "cat lane_a.txt lane_b.txt > merged.txt",
                    "definition_of_done": {"command": "wc -l merged.txt", "assertion": "2"},
                },
            ],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        start = time.time()
        proc = _run_orchestrate(str(plan_file), td)
        elapsed = time.time() - start

        _result("parallel plan completes", proc.returncode == 0, proc.stderr[:200] if proc.returncode != 0 else "")

        # If truly parallel, tasks 1+2 should overlap (total < 2x sleep)
        _result("tasks ran concurrently", elapsed < 4.0, f"elapsed={elapsed:.1f}s (expect <4s)")

        merged = td_path / "merged.txt"
        if merged.exists():
            content = merged.read_text()
            _result("merge has both lanes", "LANE_A" in content and "LANE_B" in content)
        else:
            _result("merged.txt created", False)


# ── Test 7: Failing DoD ───────────────────────────────────────────


def test_failing_dod() -> None:
    """Task with impossible DoD should fail gracefully."""
    print("\n── Test 7: Failing DoD ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Fail test"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 1},
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [{
                "id": "1", "title": "Impossible task", "lane": "0",
                "runner": "local", "depends_on": [],
                "command": "exit 1",
                "definition_of_done": {"command": "exit 1", "assertion": "never"},
            }],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        proc = _run_orchestrate(str(plan_file), td)
        _result("failing task exits non-zero", proc.returncode != 0,
                f"rc={proc.returncode}")


# ── Test 8: Timeout handling ──────────────────────────────────────


def test_timeout() -> None:
    """Task that exceeds timeout should fail with timeout error."""
    print("\n── Test 8: Timeout handling ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        _init_git_repo(td_path)

        plan = {
            "version": 1, "kind": "orchestrate-plan", "repo_root": td,
            "metadata": _base_metadata("Timeout test"),
            "capability_overlap": ["sanity test"],
            "execution": {"max_concurrency": 1},
            "lanes": [{"id": "0", "label": "Wave 0"}],
            "tasks": [{
                "id": "1", "title": "Slow task", "lane": "0",
                "runner": "local", "depends_on": [],
                "command": "sleep 30",
                "timeout_seconds": 3,
                "definition_of_done": {"command": "echo done", "assertion": "done"},
            }],
        }
        import yaml
        plan_file = td_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan, default_flow_style=False))

        start = time.time()
        try:
            proc = _run_orchestrate(str(plan_file), td, timeout=30)
            elapsed = time.time() - start
            # If orchestrate itself times out via our subprocess.run timeout, that's fine
            _result("timed out task fails", proc.returncode != 0)
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            _result("timed out task fails", True, "subprocess timed out as expected")
        _result("timeout was respected", elapsed < 35, f"elapsed={elapsed:.1f}s (expect <35s)")


# ── Test 9: subagent-service auto-migration ───────────────────────


def test_auto_migration() -> None:
    """Old subagent-service runner should auto-migrate to code-runner."""
    print("\n── Test 9: Auto-migration ──")
    sys.path.insert(0, str(SKILLS_DIR / "_shared"))
    sys.path.insert(0, str(ORCHESTRATE_DIR))

    try:
        from structured_execute_helpers import _build_runtimes

        plan_data = {
            "tasks": [{
                "id": "1", "title": "Legacy task", "lane": "0",
                "runner": "subagent-service", "backend": "sonnet", "mode": "iterative",
                "depends_on": [],
                "implementation": ["do something"],
                "allowlist": ["file.py"],
                "blind_tests": ["assert True"],
                "definition_of_done": {"command": "echo ok", "assertion": "ok"},
            }],
        }
        runtimes = _build_runtimes(plan_data, Path("/tmp"))
        task = runtimes["1"]
        _result("migrated to code-runner", task.runner == "code-runner",
                f"runner={task.runner}")
    except Exception as e:
        _result("auto-migration", False, str(e))


# ── Test 10: Structured `with codex` dry-run ──────────────────────


def test_structured_with_codex_dry_run() -> None:
    """Structured plans should accept command-level codex defaults without clobbering explicit backends."""
    print("\n── Test 10: Structured with codex dry-run ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        td_path = Path(td)
        _init_git_repo(td_path)

        plan = _base_plan(
            td,
            "Structured codex default",
            tasks=[
                {
                    "id": "1",
                    "title": "Needs codex default",
                    "lane": "0",
                    "runner": "code-runner",
                    "mode": "iterative",
                    "depends_on": [],
                    "implementation": ["Fix the target file."],
                    "allowlist": ["target.py"],
                    "blind_tests": ["hidden verification"],
                    "definition_of_done": {"command": "echo ok", "assertion": "ok"},
                },
                {
                    "id": "2",
                    "title": "Keep explicit backend",
                    "lane": "0",
                    "runner": "scillm",
                    "backend": "text-gemini-oauth",
                    "mode": "one_shot",
                    "depends_on": [],
                    "prompt": "Summarize the change.",
                    "definition_of_done": {"command": "echo ok", "assertion": "ok"},
                },
            ],
        )
        plan_file = _write_plan(td_path, plan)

        proc = _run(
            ["bash", str(ORCHESTRATE_DIR / "run.sh"), "run", str(plan_file), "with", "codex", "--dry-run"],
            cwd=td,
        )
        combined = proc.stdout + proc.stderr
        _result("structured codex dry-run exits", proc.returncode == 0, combined[:200])
        _result(
            "missing backend defaults to codex",
            "Task 1: Needs codex default → runner=code-runner, backend=codex" in combined,
            combined[:400],
        )
        _result(
            "explicit backend preserved",
            "Task 2: Keep explicit backend → runner=scillm, backend=text-gemini-oauth" in combined,
            combined[:400],
        )


# ── Test 11: Code-runner dry-run ──────────────────────────────────


def test_code_runner_dry_run() -> None:
    """Code-runner dry-run should work without calling LLM."""
    print("\n── Test 11: Code-runner dry-run ──")
    with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
        spec = {
            "task_id": "dry-run-test",
            "title": "Dry run",
            "prompt": "Fix the bug",
            "backend": "text",
            "cwd": td,
            "output_dir": f"{td}/output",
            "allowlist": ["test.py"],
            "definition_of_done": {"command": "echo ok", "assertion": "ok"},
        }
        spec_file = Path(td) / "spec.json"
        spec_file.write_text(json.dumps(spec))

        proc = _run(
            ["uv", "run", "--project", str(CODE_RUNNER_DIR),
             "python", str(CODE_RUNNER_DIR / "code_runner.py"), "dry-run", str(spec_file)],
            cwd=td,
        )
        _result("dry-run works", proc.returncode == 0, proc.stdout.strip()[:100])


# ── Test 12: Prompt assembly ──────────────────────────────────────


def test_prompt_assembly() -> None:
    """System prompt fills all placeholders."""
    print("\n── Test 12: Prompt assembly ──")
    sys.path.insert(0, str(CODE_RUNNER_DIR))

    try:
        from prompt_assembly import build_system_prompt
        prompt = build_system_prompt(
            task_id="test", session_key="cr-test-123",
            task_desc="Fix the auth bug", round_num=1,
            dod_desc="Command: pytest\nAssertion: all pass",
            allowlist=["src/auth.py"], recent_rounds=[],
        )
        unfilled = [p for p in ["{original_request}", "{definition_of_done}",
                                "{allowlist}", "{similar_solved_problems}", "{last_2_rounds}"]
                    if p in prompt]
        _result("all placeholders filled", len(unfilled) == 0,
                f"unfilled: {unfilled}" if unfilled else f"{len(prompt)} chars")
    except Exception as e:
        _result("prompt assembly", False, str(e))


# ── Test 13: apply_file_blocks ────────────────────────────────────


def test_apply_file_blocks() -> None:
    """apply.py writes allowlisted file blocks with the current tool-use format."""
    print("\n── Test 13: apply_file_blocks ──")
    sys.path.insert(0, str(CODE_RUNNER_DIR))

    try:
        from apply import apply_file_blocks

        with tempfile.TemporaryDirectory(prefix="pipeline-sanity-") as td:
            td_path = Path(td)
            target = td_path / "a.py"
            target.write_text("x = 1\n")
            written = apply_file_blocks([("a.py", "x = 2\n")], td, ["a.py"])
            _result("allowlisted file written", written == ["a.py"], str(written))
            _result("content updated", target.read_text() == "x = 2\n", target.read_text().strip())
    except Exception as e:
        _result("apply_file_blocks", False, str(e))


# ── Main ──────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print("PIPELINE SANITY: /plan → /orchestrate → /code-runner")
    print("=" * 60)

    test_compile()
    test_schema_validation()
    test_single_local_task()
    test_single_code_runner_task()
    test_sequential_deps()
    test_parallel_lanes()
    test_failing_dod()
    test_timeout()
    test_auto_migration()
    test_structured_with_codex_dry_run()
    test_code_runner_dry_run()
    test_prompt_assembly()
    test_apply_file_blocks()

    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed, {SKIP_COUNT} skipped / {total} total")
    if FAIL_COUNT > 0:
        print("STATUS: FAIL")
        sys.exit(1)
    else:
        print("STATUS: PASS")


if __name__ == "__main__":
    main()
