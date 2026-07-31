"""Project-native quality gate cleanup lane."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from cleanup_core import get_all_tracked_files, read_file_content


QUALITY_GATE_SCHEMA = "cleanup.quality_gate.v1"
QUALITY_GATE_TIMEOUT_SECONDS = 180
QUALITY_GATE_REQUIRED_STATUSES = {"failed", "missing_required_tool", "not_established"}
PYTHON_SUFFIX = ".py"
SHELL_SUFFIXES = {".sh", ".bash", ".zsh"}
TS_JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


def _tracked_by_suffix(tracked: Iterable[str], suffixes: set[str]) -> List[str]:
    return sorted(path for path in tracked if Path(path).suffix in suffixes)


def _load_package_scripts() -> Dict[str, str]:
    path = Path("package.json")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def _ruff_is_configured() -> bool:
    pyproject = read_file_content("pyproject.toml") if Path("pyproject.toml").exists() else ""
    return any(Path(path).exists() for path in ["ruff.toml", ".ruff.toml"]) or "[tool.ruff" in pyproject


def _run_command(command: List[str], timeout: int = QUALITY_GATE_TIMEOUT_SECONDS) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "tool_missing",
            "exit_code": None,
            "stdout_excerpt": "",
            "stderr_excerpt": f"{command[0]} executable was not found",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "exit_code": None,
            "stdout_excerpt": (exc.stdout or "")[-1000:],
            "stderr_excerpt": (exc.stderr or "")[-1000:],
        }
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "stdout_excerpt": proc.stdout[-1000:],
        "stderr_excerpt": proc.stderr[-1000:],
    }


def _python_parse_check(paths: List[str]) -> Dict[str, Any]:
    failures = []
    for path in paths:
        content = read_file_content(path)
        if not content:
            continue
        try:
            ast.parse(content, filename=path)
        except SyntaxError as exc:
            failures.append({
                "path": path,
                "line": exc.lineno,
                "message": exc.msg,
            })
    return {
        "id": "python_parse",
        "family": "python",
        "status": "passed" if not failures else "failed",
        "configured": True,
        "required": True,
        "command": "ast.parse tracked Python files",
        "checked_files": len(paths),
        "failures": failures,
        "proves": "tracked Python files parse without writing bytecode",
        "does_not_prove": "runtime behavior, imports, formatting, lint cleanliness, or tests",
    }


def _command_gate(
    gate_id: str,
    family: str,
    command: List[str],
    configured: bool,
    required: bool,
    run_checks: bool,
    proof: str,
    non_claim: str,
) -> Dict[str, Any]:
    if not configured:
        return {
            "id": gate_id,
            "family": family,
            "status": "not_applicable",
            "configured": False,
            "required": False,
            "command": command,
            "proves": "nothing; gate is not configured for this repository",
            "does_not_prove": non_claim,
        }
    if shutil.which(command[0]) is None:
        return {
            "id": gate_id,
            "family": family,
            "status": "missing_required_tool" if required else "tool_missing_optional",
            "configured": True,
            "required": required,
            "command": command,
            "proves": "nothing; required tool was not available",
            "does_not_prove": non_claim,
        }
    if not run_checks:
        return {
            "id": gate_id,
            "family": family,
            "status": "not_established" if required else "not_run_optional",
            "configured": True,
            "required": required,
            "command": command,
            "proves": "nothing; selected quality-gate execution did not run",
            "does_not_prove": non_claim,
        }
    result = _run_command(command)
    result.update({
        "id": gate_id,
        "family": family,
        "configured": True,
        "required": required,
        "command": command,
        "proves": proof if result["status"] == "passed" else "nothing; command did not pass",
        "does_not_prove": non_claim,
    })
    return result


def _python_gates(paths: List[str], run_checks: bool) -> List[Dict[str, Any]]:
    if not paths:
        return []
    gates = [_python_parse_check(paths)]
    ruff_configured = _ruff_is_configured()
    gates.append(_command_gate(
        "ruff_check",
        "python",
        ["ruff", "check", "--no-cache", "."],
        configured=ruff_configured,
        required=ruff_configured,
        run_checks=run_checks,
        proof="configured Ruff lint gate passed",
        non_claim="type correctness, runtime behavior, tests, or full release readiness",
    ))
    gates.append(_command_gate(
        "ruff_format_check",
        "python",
        ["ruff", "format", "--check", "--no-cache", "."],
        configured=ruff_configured,
        required=ruff_configured,
        run_checks=run_checks,
        proof="configured Ruff format check passed",
        non_claim="lint correctness, runtime behavior, tests, or full release readiness",
    ))
    return gates


def _shell_gates(paths: List[str], run_checks: bool) -> List[Dict[str, Any]]:
    if not paths:
        return []
    gates: List[Dict[str, Any]] = []
    failures = []
    for path in paths:
        if not run_checks:
            continue
        result = _run_command(["bash", "-n", path], timeout=30)
        if result["status"] != "passed":
            failures.append({"path": path, "result": result})
    gates.append({
        "id": "bash_syntax",
        "family": "shell",
        "status": "not_established" if not run_checks else ("passed" if not failures else "failed"),
        "configured": True,
        "required": True,
        "command": "bash -n tracked shell scripts",
        "checked_files": len(paths) if run_checks else 0,
        "failures": failures,
        "proves": "tracked shell scripts parse with bash -n" if run_checks and not failures else "nothing; bash syntax gate did not pass",
        "does_not_prove": "shellcheck lint, runtime behavior, environment availability, or destructive safety",
    })
    shellcheck_configured = Path(".shellcheckrc").exists()
    gates.append(_command_gate(
        "shellcheck",
        "shell",
        ["shellcheck", *paths],
        configured=shellcheck_configured,
        required=shellcheck_configured,
        run_checks=run_checks,
        proof="configured shellcheck gate passed",
        non_claim="runtime behavior, environment availability, or destructive safety",
    ))
    return gates


def _node_gates(scripts: Dict[str, str], run_checks: bool) -> List[Dict[str, Any]]:
    gates: List[Dict[str, Any]] = []
    package_manager = "npm"
    for script in ["lint", "typecheck", "test"]:
        configured = script in scripts
        gates.append(_command_gate(
            f"npm_{script}",
            "javascript_typescript",
            [package_manager, "run", script],
            configured=configured,
            required=configured and script in {"lint", "typecheck"},
            run_checks=run_checks,
            proof=f"configured npm {script} script passed",
            non_claim="browser behavior, production build, release readiness, or unrelated scripts",
        ))
    return gates


def _gate_blocker(gate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = gate.get("status")
    if status not in QUALITY_GATE_REQUIRED_STATUSES:
        return None
    return {
        "id": f"quality_gate_{gate['id']}_{status}",
        "family": gate.get("family"),
        "evidence": gate.get("command"),
        "valid_next_action": (
            "Install/configure the required tool or run the selected quality gate "
            "and preserve its receipt before claiming the cleanup slice is proven."
        ),
    }


def scan_quality_gates(run_checks: bool = False) -> Dict[str, Any]:
    """Assess configured project-native lint, parse, type, and test gates."""
    tracked = get_all_tracked_files()
    python_paths = _tracked_by_suffix(tracked, {PYTHON_SUFFIX})
    shell_paths = _tracked_by_suffix(tracked, SHELL_SUFFIXES)
    ts_js_paths = _tracked_by_suffix(tracked, TS_JS_SUFFIXES)
    scripts = _load_package_scripts()

    gates: List[Dict[str, Any]] = []
    gates.extend(_python_gates(python_paths, run_checks=run_checks))
    gates.extend(_shell_gates(shell_paths, run_checks=run_checks))
    if scripts or ts_js_paths:
        gates.extend(_node_gates(scripts, run_checks=run_checks))

    blockers = [
        blocker for blocker in (_gate_blocker(gate) for gate in gates)
        if blocker is not None
    ]
    required = [gate for gate in gates if gate.get("required")]
    failed = [gate for gate in gates if gate.get("status") == "failed"]
    missing = [gate for gate in gates if gate.get("status") == "missing_required_tool"]
    not_established = [gate for gate in gates if gate.get("status") == "not_established"]

    return {
        "schema": QUALITY_GATE_SCHEMA,
        "generated_at": datetime.now().isoformat(),
        "status": "blocked" if blockers else "passed",
        "mutation": "not_authorized",
        "run_checks": run_checks,
        "tracked_counts": {
            "python": len(python_paths),
            "shell": len(shell_paths),
            "javascript_typescript": len(ts_js_paths),
        },
        "gates": gates,
        "counts": {
            "total": len(gates),
            "required": len(required),
            "failed": len(failed),
            "missing_required_tool": len(missing),
            "not_established": len(not_established),
            "blockers": len(blockers),
        },
        "blockers": blockers,
        "closure_criteria": [
            "Run `--quality-gate` for the selected cleanup slice.",
            "Configured required gates pass or are explicitly marked not applicable with rationale.",
            "Missing tools are installed or the repository removes/updates the corresponding required configuration.",
            "Receipt states what was exercised and what remains unverified.",
        ],
        "non_claims": [
            "Does not replace full CI, release qualification, or project acceptance tests.",
            "Does not prove runtime behavior unless the configured project-native command does so.",
            "Does not mutate source files, format files, install tools, or change package configuration.",
        ],
    }


def append_quality_gate_markdown(plan: List[str], quality: Dict[str, Any]) -> None:
    """Append quality-gate details to a cleanup markdown report."""
    plan.append("## Quality Gate Cleanup")
    plan.append("")
    plan.append(
        "This lane reports project-native parse, lint, format-check, typecheck, "
        "and test evidence. It is scoped by cleanup slice and does not replace "
        "full CI or release qualification."
    )
    plan.append("")
    plan.append(f"- Status: `{quality.get('status', 'unknown')}`")
    plan.append(f"- Run checks: `{quality.get('run_checks', False)}`")
    counts = quality.get("counts", {})
    plan.append(f"- Required gates: `{counts.get('required', 0)}`")
    plan.append(f"- Blockers: `{counts.get('blockers', 0)}`")
    plan.append("")
    gates = quality.get("gates", [])
    if gates:
        plan.append("| Gate | Family | Status | Required | Command |")
        plan.append("| --- | --- | --- | --- | --- |")
        for gate in gates:
            command = gate.get("command")
            if isinstance(command, list):
                command = " ".join(str(part) for part in command)
            plan.append(
                f"| `{gate['id']}` | `{gate.get('family')}` | `{gate.get('status')}` | "
                f"`{gate.get('required', False)}` | `{command}` |"
            )
        plan.append("")
    if quality.get("blockers"):
        plan.append("Quality blockers:")
        plan.append("")
        for blocker in quality["blockers"]:
            plan.append(f"- `{blocker['id']}` — {blocker['valid_next_action']}")
        plan.append("")
