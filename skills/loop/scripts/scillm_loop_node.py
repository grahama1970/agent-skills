#!/usr/bin/env python3
"""Run one Scillm/project-agent DAG node through the loop harness."""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
LOOP = SCRIPT_DIR / "loop.py"
VALIDATOR = SCRIPT_DIR / "validate_loop_receipt.py"
NODE_SCHEMA = "loop.scillm_node_result.v1"


def load_node(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read node JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("node JSON root must be an object")
    return data


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"node.{key}: expected non-empty string")
    return value


def optional_string(data: dict[str, Any], key: str, default: str | None = None) -> str | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"node.{key}: expected non-empty string")
    return value


def string_list(data: dict[str, Any], key: str, *, required: bool = False) -> list[str]:
    value = data.get(key, [])
    if required and not value:
        raise ValueError(f"node.{key}: expected non-empty list of strings")
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"node.{key}: expected list of non-empty strings")
    return value


def int_value(data: dict[str, Any], key: str, default: int, *, minimum: int = 1) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"node.{key}: expected integer >= {minimum}")
    return value


def bool_value(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"node.{key}: expected boolean")
    return value


def worktree_mode(data: dict[str, Any]) -> str:
    value = data.get("worktree", {"mode": "existing"})
    if not isinstance(value, dict):
        raise ValueError("node.worktree: expected object")
    mode = value.get("mode", "existing")
    if mode != "existing":
        raise ValueError("node.worktree.mode: only 'existing' is supported by the minimal runner")
    return mode


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def required_changed_missing(changed_files: list[str], required_globs: list[str]) -> list[str]:
    return [pattern for pattern in required_globs if not matches_any_any(changed_files, pattern)]


def matches_any_any(paths: list[str], pattern: str) -> bool:
    return any(fnmatch.fnmatch(path.replace("\\", "/"), pattern) for path in paths)


def run_json_command(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def parse_loop_stdout(stdout: str) -> dict[str, Any] | None:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def result_from_receipt(
    *,
    node_id: str,
    receipt: dict[str, Any],
    receipt_path: Path,
    validator: subprocess.CompletedProcess[str],
    loop_proc: subprocess.CompletedProcess[str],
    required_globs: list[str],
) -> dict[str, Any]:
    changed_files = [item for item in receipt.get("changed_files", []) if isinstance(item, str)]
    missing_required = required_changed_missing(changed_files, required_globs)
    receipt_status = receipt.get("final_verdict", "BLOCKED")
    status = receipt_status
    stop_reason = receipt.get("stop_reason", "INFRASTRUCTURE_FAILURE")
    if validator.returncode != 0:
        status = "BLOCKED"
        stop_reason = "INVALID_RECEIPT"
    elif missing_required:
        status = "BLOCKED"
        stop_reason = "REQUIRED_CHANGED_GLOB_MISSING"

    return {
        "schema": NODE_SCHEMA,
        "node_id": node_id,
        "status": status,
        "loop_final_verdict": receipt_status,
        "stop_reason": stop_reason,
        "loop_run_id": receipt.get("run_id"),
        "final_receipt": str(receipt_path),
        "changed_files": changed_files,
        "checks": receipt.get("checks", []),
        "reviewer": receipt.get("reviewer", {}),
        "required_changed_globs": required_globs,
        "required_changed_globs_satisfied": not missing_required,
        "missing_required_changed_globs": missing_required,
        "loop_exit_code": loop_proc.returncode,
        "receipt_valid": validator.returncode == 0,
        "validator_stdout": validator.stdout,
        "validator_stderr": validator.stderr,
    }


def infrastructure_result(node_id: str, reason: str, *, loop_proc: subprocess.CompletedProcess[str] | None = None) -> dict[str, Any]:
    return {
        "schema": NODE_SCHEMA,
        "node_id": node_id,
        "status": "BLOCKED",
        "loop_final_verdict": None,
        "stop_reason": "INFRASTRUCTURE_FAILURE",
        "loop_run_id": None,
        "final_receipt": "",
        "changed_files": [],
        "checks": [],
        "reviewer": {"verdict": "BLOCKED", "edited_files": False, "findings": [reason]},
        "required_changed_globs": [],
        "required_changed_globs_satisfied": False,
        "missing_required_changed_globs": [],
        "loop_exit_code": loop_proc.returncode if loop_proc else None,
        "receipt_valid": False,
        "validator_stdout": "",
        "validator_stderr": "",
        "stdout": loop_proc.stdout if loop_proc else "",
        "stderr": loop_proc.stderr if loop_proc else reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one loop DAG node and emit a normalized node result.")
    parser.add_argument("--node", required=True, help="Path to node JSON")
    parser.add_argument("--repo", default=".", help="Repository/worktree root. Default: current directory")
    parser.add_argument("--print-json", action="store_true", help="Print full node result JSON")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        node = load_node(Path(args.node))
        node_id = require_string(node, "node_id")
        objective = require_string(node, "objective")
        agent_config = require_string(node, "agent_config")
        allowed_globs = string_list(node, "allowed_globs", required=True)
        checks = string_list(node, "checks", required=True)
        required_globs = string_list(node, "required_changed_globs")
        max_attempts = int_value(node, "max_attempts", 3)
        check_timeout = int_value(node, "check_timeout", 300)
        run_root = optional_string(node, "run_root", ".loop/runs") or ".loop/runs"
        require_clean = bool_value(node, "require_clean", True)
        worktree_mode(node)
    except ValueError as exc:
        result = infrastructure_result("unknown", str(exc))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    cmd = [
        sys.executable,
        str(LOOP),
        "--objective",
        objective,
        "--agent-config",
        agent_config,
        "--max-attempts",
        str(max_attempts),
        "--check-timeout",
        str(check_timeout),
        "--run-root",
        run_root,
        "--print-json",
    ]
    cmd.append("--require-clean" if require_clean else "--no-require-clean")
    for pattern in allowed_globs:
        cmd.extend(["--allow", pattern])
    for check in checks:
        cmd.extend(["--check", check])

    loop_proc = run_json_command(cmd, repo)
    loop_receipt = parse_loop_stdout(loop_proc.stdout)
    if loop_receipt is None:
        result = infrastructure_result(node_id, "loop.py did not emit JSON", loop_proc=loop_proc)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    artifacts = loop_receipt.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("run_dir"), str):
        result = infrastructure_result(node_id, "loop receipt missing artifacts.run_dir", loop_proc=loop_proc)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    receipt_path = repo / artifacts["run_dir"] / "final-receipt.json"
    if not receipt_path.is_file():
        result = infrastructure_result(node_id, f"final receipt not found: {receipt_path}", loop_proc=loop_proc)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validator = run_json_command([sys.executable, str(VALIDATOR), str(receipt_path), "--print-summary"], repo)
    result = result_from_receipt(
        node_id=node_id,
        receipt=receipt,
        receipt_path=receipt_path,
        validator=validator,
        loop_proc=loop_proc,
        required_globs=required_globs,
    )
    print(json.dumps(result if args.print_json else {"node_id": node_id, "status": result["status"]}, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

