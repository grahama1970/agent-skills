"""Doctor checks for ask runtime infrastructure."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from .chain_specs import load_chain_specs, validate_chain_spec
from .reviewer_specs import load_reviewer_specs
from .run_state import default_run_root
from .runtime_schema import validate_runtime_tree


app = typer.Typer(help="/ask doctor - Check runtime prerequisites")

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent
AGENT_SKILLS_DIR = SKILLS_DIR.parent / ".agent" / "skills"


def _skill_path(name: str) -> Path | None:
    for candidate in (SKILLS_DIR / name / "run.sh", AGENT_SKILLS_DIR / name / "run.sh"):
        if candidate.exists():
            return candidate
    return None


def _check(name: str, ok: bool, detail: str, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "ok": ok, "severity": severity, "detail": detail}


def _run_live_check(name: str, command: list[str], timeout: int = 10, severity: str = "warning") -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except subprocess.TimeoutExpired:
        return _check(name, False, f"timed out after {timeout}s", severity=severity)
    except OSError as exc:
        return _check(name, False, str(exc), severity=severity)
    detail = f"exit={result.returncode}"
    if result.stderr:
        detail += f" stderr={result.stderr.strip()[:160]}"
    return _check(name, result.returncode == 0, detail, severity=severity)


def run_doctor(live: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("python_version", sys.version_info >= (3, 11), sys.version.split()[0]))
    checks.append(_check("skill_root", SKILL_ROOT.exists(), str(SKILL_ROOT)))
    checks.append(_check("run_sh", os.access(SKILL_ROOT / "run.sh", os.X_OK), str(SKILL_ROOT / "run.sh")))
    checks.append(_check("uv", shutil.which("uv") is not None, shutil.which("uv") or "not found"))

    run_root = default_run_root()
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        probe = run_root / ".doctor-write"
        probe.write_text("ok\n")
        probe.unlink()
        writable = True
        detail = str(run_root)
    except OSError as exc:
        writable = False
        detail = f"{run_root}: {exc}"
    checks.append(_check("artifact-root", writable, detail))
    checks.append(_check("artifact_root_writable", writable, detail))
    schema_result = validate_runtime_tree(run_root)
    checks.append(
        _check(
            "runtime_artifact_schema",
            schema_result["ok"],
            f"checked={schema_result['runs_checked']} invalid={len(schema_result['invalid_runs'])}",
            severity="error",
        )
    )

    try:
        reviewer_specs = load_reviewer_specs()
        checks.append(_check("reviewer-specs", bool(reviewer_specs), f"loaded={len(reviewer_specs)}"))
    except Exception as exc:
        checks.append(_check("reviewer-specs", False, str(exc)))

    try:
        chain_specs = load_chain_specs()
        errors = {
            name: validation_errors
            for name, spec in chain_specs.items()
            if (validation_errors := validate_chain_spec(spec))
        }
        checks.append(_check("chain-specs", not errors, f"loaded={len(chain_specs)} invalid={len(errors)}"))
    except Exception as exc:
        checks.append(_check("chain-specs", False, str(exc)))

    for skill in ("memory", "dogpile", "scillm", "subagent-runner"):
        path = _skill_path(skill)
        checks.append(
            _check(
                f"skill:{skill}",
                path is not None and os.access(path, os.X_OK),
                str(path) if path else "not found",
                severity="warning" if skill in {"dogpile", "scillm", "subagent-runner"} else "error",
            )
        )

    checks.append(_check("ASK_RUN_OUTPUT_DIR", True, os.environ.get("ASK_RUN_OUTPUT_DIR", str(run_root)), "info"))
    checks.append(_check("ASK_ORACLE_BACKEND", True, os.environ.get("ASK_ORACLE_BACKEND", "auto"), "info"))
    checks.append(_check("ASK_ORACLE_MODEL", True, os.environ.get("ASK_ORACLE_MODEL", "gpt-5.5"), "info"))

    if live:
        memory = _skill_path("memory")
        dogpile = _skill_path("dogpile")
        scillm = _skill_path("scillm")
        runner = _skill_path("subagent-runner")
        if memory:
            checks.append(_run_live_check("live:memory", [str(memory), "recall", "--q", "ask doctor live", "--k", "1"], timeout=15, severity="error"))
        if dogpile:
            checks.append(_run_live_check("live:dogpile", [str(dogpile), "--help"], timeout=10))
        if scillm:
            checks.append(_run_live_check("live:scillm", [str(scillm), "warm-check", "--json"], timeout=15))
        if runner:
            checks.append(_run_live_check("live:subagent-runner", [str(runner), "--help"], timeout=10))

    error_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "error")
    warning_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "warning")
    return {
        "status": "pass" if error_count == 0 else "fail",
        "error_count": error_count,
        "warning_count": warning_count,
        "skill_root": str(SKILL_ROOT),
        "run_root": str(run_root),
        "runtime_schema": schema_result,
        "checks": checks,
    }


@app.command()
def main(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    live: bool = typer.Option(False, "--live", help="Run live subprocess/service checks"),
) -> None:
    result = run_doctor(live=live)
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        raise typer.Exit(0 if result["status"] == "pass" else 1)

    print(f"/ask doctor: {result['status']}")
    print(f"artifact root: {result['run_root']}")
    for check in result["checks"]:
        mark = "ok" if check["ok"] else check["severity"]
        print(f"  {mark:7} {check['name']}: {check['detail']}")
    raise typer.Exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    app()
