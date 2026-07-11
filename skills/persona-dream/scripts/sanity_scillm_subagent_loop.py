#!/usr/bin/env python3
"""Minimal deterministic sanity check for Dreamer-style subagent loops.

This creates a disposable git repo with one intentionally failing Python
function, runs the `$loop` node adapter, validates the final receipt, and writes
a proof JSON. Use `--backend fixture` for deterministic CI and `--backend scillm`
    to exercise the real Scillm subagent path. Start with `--backend
    scillm-coder`, then increase to `--backend scillm-reviewer`, then
    `--backend scillm`:

  explorer      -> /v1/scillm/exec
  coder         -> /v1/scillm/opencode/runs
  code-reviewer -> /v1/scillm/exec
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "persona_dream.sanity_scillm_subagent_loop.v1"
REPO_ROOT = Path(__file__).resolve().parents[3]
LOOP_SKILL = REPO_ROOT / "skills" / "loop"
NODE_RUNNER = LOOP_SKILL / "scripts" / "scillm_loop_node.py"
VALIDATE_RECEIPT = LOOP_SKILL / "scripts" / "validate_loop_receipt.py"
FIXTURE_DIR = LOOP_SKILL / "tests" / "fixtures"
LOCAL_SCILLM_BASE_URLS = {"http://localhost:4001", "http://127.0.0.1:4001"}
PROVIDER_ENV_PREFIXES = ("KLING_", "NANO_BANANA_")
PROVIDER_ENV_NAMES = {"GOOGLE_API_KEY", "GEMINI_API_KEY"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def is_scillm_backend(backend: str) -> bool:
    return backend.startswith("scillm")


def local_scillm_base_url() -> str:
    return os.environ.get("SCILLM_BASE_URL", "http://localhost:4001").rstrip("/")


def provider_env_keys(env: dict[str, str]) -> list[str]:
    return sorted(
        key
        for key in env
        if any(key.startswith(prefix) for prefix in PROVIDER_ENV_PREFIXES) or key in PROVIDER_ENV_NAMES
    )


def scrubbed_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in provider_env_keys(env):
        env.pop(key, None)
    return env


def preflight_scillm_safety(work_dir: Path, backend: str) -> dict[str, Any]:
    if not is_scillm_backend(backend):
        return {
            "backend_uses_scillm": False,
            "status": "PASS",
            "checks": ["fixture backend does not call Scillm"],
        }

    checks: list[str] = []
    blockers: list[str] = []
    base_url = local_scillm_base_url()
    if base_url not in LOCAL_SCILLM_BASE_URLS:
        blockers.append(f"SCILLM_BASE_URL is not local: {base_url}")
    else:
        checks.append(f"scillm endpoint allowed: {base_url}")

    try:
        work_dir.resolve().relative_to(REPO_ROOT.resolve())
        checks.append("work_dir is under shared workspace")
    except ValueError:
        blockers.append(f"work_dir is outside shared workspace: {work_dir}")

    provider_env = provider_env_keys(os.environ)
    if provider_env:
        checks.append("provider/live env vars will be scrubbed from child process: " + ", ".join(provider_env))
    else:
        checks.append("no Kling/Gemini/Nano Banana/provider env vars visible")

    return {
        "backend_uses_scillm": True,
        "status": "PASS" if not blockers else "BLOCKED",
        "base_url": base_url,
        "work_dir": str(work_dir),
        "checks": checks,
        "blockers": blockers,
    }


def read_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_worker_provenance(repo: Path, node_result: dict[str, Any]) -> dict[str, Any]:
    final_receipt = node_result.get("final_receipt")
    if not isinstance(final_receipt, str) or not final_receipt:
        return {"available": False, "reason": "no final receipt"}
    receipt_path = Path(final_receipt)
    if not receipt_path.is_absolute():
        receipt_path = repo / receipt_path
    run_dir = receipt_path.parent
    coder_result = read_json_if_exists(run_dir / "attempts" / "01" / "coder-result.json")
    reviewer_result = read_json_if_exists(run_dir / "attempts" / "01" / "code-reviewer-result.json")
    explorer_result = read_json_if_exists(run_dir / "explorer" / "explorer-result.json")
    return {
        "available": True,
        "run_dir": str(run_dir),
        "final_receipt": str(receipt_path),
        "scillm_roles": {
            "explorer": explorer_result,
            "coder": coder_result,
            "code_reviewer": reviewer_result,
        },
    }


def init_fixture_repo(repo: Path) -> None:
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "dreamer-loop@example.test"], repo)
    run(["git", "config", "user.name", "Dreamer Loop Sanity"], repo)
    write_text(
        repo / "sample-target" / "src" / "time" / "parse_duration.py",
        "def parse_duration(value: str) -> int:\n    raise NotImplementedError\n",
    )
    write_text(
        repo / "sample-target" / "tests" / "test_parse_duration.py",
        textwrap.dedent(
            """
            import unittest

            from sample_target_bridge import parse_duration


            class ParseDurationTests(unittest.TestCase):
                def test_hours_and_minutes(self):
                    self.assertEqual(parse_duration("1h 30m"), 5400)

                def test_minutes_only(self):
                    self.assertEqual(parse_duration("45m"), 2700)
            """
        ).lstrip(),
    )
    write_text(
        repo / "sample-target" / "tests" / "sample_target_bridge.py",
        textwrap.dedent(
            """
            import importlib.util
            from pathlib import Path

            MODULE = Path(__file__).resolve().parents[1] / "src" / "time" / "parse_duration.py"
            spec = importlib.util.spec_from_file_location("parse_duration_module", MODULE)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            parse_duration = mod.parse_duration
            """
        ).lstrip(),
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "initial failing fixture"], repo)


def write_agent_config(repo: Path, backend: str) -> Path:
    path = repo / ".loop" / f"agents.{backend}.toml"
    if backend == "fixture":
        content = f"""
        [explorer]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'explorer_agent.py'}"]
        writes = false
        timeout_seconds = 60

        [coder]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'coder_agent.py'}"]
        writes = true
        timeout_seconds = 60

        [code-reviewer]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'code_reviewer_agent.py'}"]
        writes = false
        timeout_seconds = 60
        """
    elif backend == "scillm-coder":
        content = f"""
        [explorer]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'explorer_agent.py'}"]
        writes = false
        timeout_seconds = 60

        [coder]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "coder", "--surface", "opencode", "--opencode-agent", "build", "--opencode-skills", "scillm", "--timeout", "900"]
        writes = true
        timeout_seconds = 960

        [code-reviewer]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'code_reviewer_agent.py'}"]
        writes = false
        timeout_seconds = 60
        """
    elif backend == "scillm-reviewer":
        content = f"""
        [explorer]
        cmd = ["{sys.executable}", "{FIXTURE_DIR / 'explorer_agent.py'}"]
        writes = false
        timeout_seconds = 60

        [coder]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "coder", "--surface", "opencode", "--opencode-agent", "build", "--opencode-skills", "scillm", "--timeout", "900"]
        writes = true
        timeout_seconds = 960

        [code-reviewer]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "code-reviewer", "--surface", "exec", "--exec-profile", "codex-gpt-5.5", "--sandbox", "read-only", "--reasoning-effort", "low", "--timeout", "900"]
        writes = false
        timeout_seconds = 960
        """
    else:
        content = f"""
        [explorer]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "explorer", "--surface", "opencode", "--opencode-agent", "build", "--opencode-skills", "scillm", "--timeout", "900"]
        writes = false
        timeout_seconds = 960

        [coder]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "coder", "--surface", "opencode", "--opencode-agent", "build", "--opencode-skills", "scillm", "--timeout", "900"]
        writes = true
        timeout_seconds = 960

        [code-reviewer]
        cmd = ["{sys.executable}", "{LOOP_SKILL / 'scripts' / 'scillm_agent.py'}", "--role", "code-reviewer", "--surface", "exec", "--exec-profile", "codex-gpt-5.5", "--sandbox", "read-only", "--reasoning-effort", "low", "--timeout", "900"]
        writes = false
        timeout_seconds = 960
        """
    write_text(path, textwrap.dedent(content).strip() + "\n")
    return path


def write_node(repo: Path, agent_config: Path, backend: str) -> Path:
    node = {
        "node_type": "loop",
        "node_id": f"persona_dream_sanity_{backend}",
        "objective": (
            "Implement parse_duration(value: str) in sample-target/src/time/parse_duration.py. "
            "It must parse tokens like '1h 30m' and '45m' into seconds. Keep changes minimal."
        ),
        "agent_config": str(agent_config),
        "allowed_globs": [
            "sample-target/src/time/**",
            "sample-target/tests/**",
        ],
        "required_changed_globs": [
            "sample-target/src/time/parse_duration.py",
        ],
        "checks": [
            f"{sys.executable} -m unittest discover -s sample-target/tests",
        ],
        "max_attempts": 3,
        "check_timeout": 120,
        "run_root": ".loop/runs",
        "terminal_backend": "subprocess",
        "require_clean": False,
        "worktree": {"mode": "existing"},
    }
    path = repo / ".loop" / "nodes" / f"{backend}_sanity_node.json"
    atomic_json(path, node)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal Dreamer/Scillm subagent loop sanity check.")
    parser.add_argument("--backend", choices=("fixture", "scillm-coder", "scillm-reviewer", "scillm"), default="fixture")
    parser.add_argument("--work-dir", default=None, help="Keep/use this work dir instead of a temporary directory")
    parser.add_argument("--output", default=None, help="Proof JSON output path")
    parser.add_argument("--keep", action="store_true", help="Keep temporary fixture repo")
    parser.add_argument("--timeout-s", type=int, default=2400)
    args = parser.parse_args()

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
    else:
        if args.keep or is_scillm_backend(args.backend):
            work_dir = (REPO_ROOT / ".codex" / "persona-dream" / "sanity" / "workdirs" / f"{args.backend}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}").resolve()
            if work_dir.exists():
                shutil.rmtree(work_dir)
            work_dir.mkdir(parents=True)
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="persona-dream-loop-sanity-"))

    preflight = preflight_scillm_safety(work_dir, args.backend)
    if preflight["status"] != "PASS":
        output = Path(args.output).resolve() if args.output else REPO_ROOT / ".codex" / "persona-dream" / "sanity" / f"subagent_loop_{args.backend}_latest.json"
        proof = {
            "schema": SCHEMA,
            "created_at": now_iso(),
            "backend": args.backend,
            "preflight": preflight,
            "pass": False,
        }
        atomic_json(output, proof)
        print(json.dumps({"proof": str(output), "pass": False, "backend": args.backend, "preflight": preflight}, indent=2))
        return 2

    repo = work_dir / "repo"
    repo.mkdir(parents=True)
    init_fixture_repo(repo)
    agent_config = write_agent_config(repo, args.backend)
    node_path = write_node(repo, agent_config, args.backend)

    proc = run(
        [sys.executable, str(NODE_RUNNER), "--node", str(node_path), "--repo", str(repo), "--print-json"],
        repo,
        env=scrubbed_env() if is_scillm_backend(args.backend) else None,
        timeout=args.timeout_s,
    )
    try:
        node_result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        node_result = {"parse_error": True, "stdout": proc.stdout[-4000:]}

    final_receipt = node_result.get("final_receipt") if isinstance(node_result, dict) else None
    validator = None
    if isinstance(final_receipt, str) and final_receipt:
        validator = run([sys.executable, str(VALIDATE_RECEIPT), final_receipt, "--print-summary"], repo, timeout=120)

    proof = {
        "schema": SCHEMA,
        "created_at": now_iso(),
        "backend": args.backend,
        "repo": str(repo),
        "node": str(node_path),
        "agent_config": str(agent_config),
        "preflight": preflight,
        "child_env_scrubbed_keys": provider_env_keys(os.environ) if is_scillm_backend(args.backend) else [],
        "command": [sys.executable, str(NODE_RUNNER), "--node", str(node_path), "--repo", str(repo), "--print-json"],
        "returncode": proc.returncode,
        "node_result": node_result,
        "worker_provenance": collect_worker_provenance(repo, node_result) if isinstance(node_result, dict) else {"available": False},
        "validator": None
        if validator is None
        else {
            "returncode": validator.returncode,
            "stdout": validator.stdout,
            "stderr": validator.stderr,
        },
        "pass": (
            proc.returncode == 0
            and isinstance(node_result, dict)
            and node_result.get("status") == "PASS"
            and node_result.get("receipt_valid") is True
            and node_result.get("required_changed_globs_satisfied") is True
            and validator is not None
            and validator.returncode == 0
        ),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "temp_dir_kept": bool(args.keep or args.work_dir or is_scillm_backend(args.backend)),
    }
    output = Path(args.output).resolve() if args.output else REPO_ROOT / ".codex" / "persona-dream" / "sanity" / f"subagent_loop_{args.backend}_latest.json"
    atomic_json(output, proof)
    print(json.dumps({"proof": str(output), "pass": proof["pass"], "backend": args.backend, "repo": str(repo)}, indent=2))

    if not args.keep and not args.work_dir and not is_scillm_backend(args.backend):
        shutil.rmtree(work_dir, ignore_errors=True)
    return 0 if proof["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
