"""Preflight diagnostics for /ask."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import typer

from .chain_specs import load_chain_specs, validate_chain_spec
from .reviewer_specs import load_reviewer_specs
from .run_state import ASK_ROOT, artifact_root

app = typer.Typer(help="/ask doctor - Preflight /ask dependencies")


def _skill_path(name: str) -> Path:
    return ASK_ROOT.parent / name / "run.sh"


def _check_skill(name: str) -> dict[str, Any]:
    path = _skill_path(name)
    executable = path.exists() and os.access(path, os.X_OK)
    return {
        "name": f"skill:{name}",
        "status": "pass" if executable else "warn",
        "detail": str(path) if executable else f"missing or not executable: {path}",
    }


def _check_git() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ASK_ROOT), "status", "--short"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"name": "git-status", "status": "fail", "detail": str(exc)}
    return {
        "name": "git-status",
        "status": "pass" if result.returncode == 0 else "fail",
        "detail": f"returncode={result.returncode}",
    }


def _check_artifact_root(root: str | None = None) -> dict[str, Any]:
    try:
        base = artifact_root(root)
        base.mkdir(parents=True, exist_ok=True)
        marker = base / ".doctor_check"
        marker.write_text("ok\n", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return {"name": "artifact-root", "status": "pass", "detail": str(base)}
    except Exception as exc:
        return {"name": "artifact-root", "status": "fail", "detail": str(exc)}


def _check_reviewers() -> dict[str, Any]:
    try:
        specs = load_reviewer_specs()
    except Exception as exc:
        return {"name": "reviewer-specs", "status": "fail", "detail": str(exc)}
    required = {"evidence-auditor", "failure-mode", "test-proof", "complexity-minimizer"}
    missing = sorted(required - set(specs))
    if missing:
        return {"name": "reviewer-specs", "status": "fail", "detail": f"missing: {', '.join(missing)}"}
    return {"name": "reviewer-specs", "status": "pass", "detail": f"{len(specs)} specs loaded"}


def _check_chains() -> dict[str, Any]:
    try:
        chains = load_chain_specs()
    except Exception as exc:
        return {"name": "chain-specs", "status": "fail", "detail": str(exc)}
    errors = []
    for name, spec in chains.items():
        for error in validate_chain_spec(spec):
            errors.append(f"{name}: {error}")
    required = {"deep-review", "parallel-review"}
    missing = sorted(required - set(chains))
    if missing:
        errors.append(f"missing: {', '.join(missing)}")
    if errors:
        return {"name": "chain-specs", "status": "fail", "detail": "; ".join(errors)}
    return {"name": "chain-specs", "status": "pass", "detail": f"{len(chains)} chains loaded"}


def run_doctor(*, artifact_root_override: str | None = None) -> dict[str, Any]:
    checks = [
        _check_skill("memory"),
        _check_skill("dogpile"),
        _check_skill("scillm"),
        _check_skill("subagent-runner"),
        _check_skill("monitor-personas"),
        _check_artifact_root(artifact_root_override),
        _check_git(),
        _check_reviewers(),
        _check_chains(),
    ]
    status = "pass"
    if any(check["status"] == "fail" for check in checks):
        status = "fail"
    elif any(check["status"] == "warn" for check in checks):
        status = "warn"
    return {
        "status": status,
        "artifact_root": str(artifact_root(artifact_root_override)),
        "checks": checks,
    }


@app.command()
def main(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON"),
    artifact_root_override: str | None = typer.Option(None, "--artifact-root", help="Override artifact root"),
) -> None:
    report = run_doctor(artifact_root_override=artifact_root_override)
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        raise typer.Exit(code=0 if report["status"] != "fail" else 1)

    print(f"/ask doctor: {report['status']}")
    for check in report["checks"]:
        print(f"- {check['status'].upper():4} {check['name']}: {check['detail']}")
    raise typer.Exit(code=0 if report["status"] != "fail" else 1)


if __name__ == "__main__":
    app()
