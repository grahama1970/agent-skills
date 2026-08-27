#!/usr/bin/env python3
"""ops-terraform: read-only Terraform posture detection (stdlib only).

Typed outcomes; failure_code on every non-PASS; no mutation anywhere.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _out(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, indent=1))
    sys.exit(code)


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)


def cmd_doctor() -> None:
    binary = shutil.which("terraform")
    if not binary:
        _out({"schema": "ops_terraform.doctor.v1", "status": "NOT_CONFIGURED",
              "failure_code": "terraform_binary_missing",
              "next_command": "install terraform or add it to PATH"}, 1)
    ver = _run(["terraform", "version", "-json"])
    version = None
    if ver.returncode == 0:
        try:
            version = json.loads(ver.stdout).get("terraform_version")
        except json.JSONDecodeError:
            version = (ver.stdout.splitlines() or [""])[0]
    _out({"schema": "ops_terraform.doctor.v1", "status": "PASS",
          "binary": binary, "version": version})


def cmd_check(module_dir: str) -> None:
    if not shutil.which("terraform"):
        _out({"schema": "ops_terraform.check.v1", "status": "NOT_CONFIGURED",
              "failure_code": "terraform_binary_missing",
              "next_command": "run doctor; install terraform first"}, 1)
    d = Path(module_dir)
    if not d.is_dir() or not list(d.glob("*.tf")):
        _out({"schema": "ops_terraform.check.v1", "status": "FAIL",
              "failure_code": "no_terraform_module",
              "module_dir": str(d),
              "next_command": "point at a directory containing *.tf files"}, 1)
    fmt = _run(["terraform", "fmt", "-check", "-recursive"], cwd=str(d))
    # validate needs providers; init locally without any backend or network
    # state migration. -backend=false keeps this read-only.
    init = _run(["terraform", "init", "-backend=false", "-input=false"], cwd=str(d))
    val = _run(["terraform", "validate", "-json"], cwd=str(d))
    valid = False
    diagnostics: list = []
    if val.returncode in (0, 1):
        try:
            vj = json.loads(val.stdout)
            valid = bool(vj.get("valid"))
            diagnostics = [
                {"severity": item.get("severity"),
                 "summary": item.get("summary")}
                for item in vj.get("diagnostics", [])[:5]
            ]
        except json.JSONDecodeError:
            pass
    status = "PASS" if valid and fmt.returncode == 0 else "FAIL"
    payload = {"schema": "ops_terraform.check.v1", "status": status,
               "module_dir": str(d), "fmt_clean": fmt.returncode == 0,
               "valid": valid, "diagnostics": diagnostics}
    if status != "PASS":
        payload["failure_code"] = (
            "terraform_invalid" if not valid else "terraform_fmt_dirty")
        payload["next_command"] = (
            f"terraform -chdir={d} validate" if not valid
            else f"terraform -chdir={d} fmt -recursive")
        if init.returncode != 0:
            payload["failure_code"] = "terraform_init_backendless_failed"
            payload["stderr_tail"] = init.stderr[-300:]
    _out(payload, 0 if status == "PASS" else 1)


def cmd_plan_summary(plan_json: str) -> None:
    p = Path(plan_json)
    if not p.is_file():
        _out({"schema": "ops_terraform.plan_summary.v1", "status": "FAIL",
              "failure_code": "plan_json_missing", "path": str(p),
              "next_command": "terraform show -json plan.tfplan > plan.json"}, 1)
    try:
        plan = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        _out({"schema": "ops_terraform.plan_summary.v1", "status": "FAIL",
              "failure_code": "plan_json_unparseable", "error": str(exc)[:120]}, 1)
    adds = changes = destroys = 0
    for rc in plan.get("resource_changes", []):
        actions = rc.get("change", {}).get("actions", [])
        adds += "create" in actions
        changes += "update" in actions
        destroys += "delete" in actions
    _out({"schema": "ops_terraform.plan_summary.v1", "status": "PASS",
          "adds": adds, "changes": changes, "destroys": destroys,
          "destructive": destroys > 0,
          "note": "summary of a SAVED plan; this skill never plans live state"})


def main() -> None:
    if len(sys.argv) < 2:
        _out({"schema": "ops_terraform.usage.v1", "status": "FAIL",
              "failure_code": "missing_subcommand",
              "usage": "doctor | check <module-dir> | plan-summary <plan.json>"}, 2)
    cmd = sys.argv[1]
    if cmd == "doctor":
        cmd_doctor()
    elif cmd == "check" and len(sys.argv) > 2:
        cmd_check(sys.argv[2])
    elif cmd == "plan-summary" and len(sys.argv) > 2:
        cmd_plan_summary(sys.argv[2])
    else:
        _out({"schema": "ops_terraform.usage.v1", "status": "FAIL",
              "failure_code": "unknown_subcommand", "got": sys.argv[1:]}, 2)


if __name__ == "__main__":
    main()
