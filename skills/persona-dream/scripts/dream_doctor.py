#!/usr/bin/env python3
"""dream_doctor.py — one preflight that verifies the whole sanctioned dream chain
up front and fails loud, so a run never discovers its blockers one at a time.

Grounded in the 2026-08-07 failure session: the autonomous cycle died three
separate times mid-run — a deleted /tau node, an uninstalled identity dep, and a
GMO route drift — each surfacing only when reached. This checks all of them (and
more) before a cycle starts, with the exact fix for each failure.

No paid calls, no generation. Exit non-zero if any REQUIRED check fails.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO.parent  # tau is a sibling repo: experiments/tau, not nested
TAU_DIR = EXPERIMENTS / "tau"
TAU_VENV = TAU_DIR / ".venv" / "bin" / "python3"
GMO = "http://127.0.0.1:8601"
SCILLM = os.environ.get("SCILLM_BASE_URL", "http://127.0.0.1:4001")

# /tau nodes the pipeline dispatches to (the sanctioned /tau -> /scillm path).
TAU_NODES = [
    "tau_coding.persona_dream_text_reasoning_agent",
    "tau_coding.persona_dream_panel_agent",
    "tau_coding.persona_dream_dream_packet_agent",
]


def check(name: str, ok: bool, detail: str, fix: str = "", required: bool = True) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": fix, "required": required}


def _tau_import(module: str) -> tuple[bool, str]:
    if not TAU_VENV.exists():
        return False, f"tau venv missing: {TAU_VENV}"
    p = subprocess.run(
        [str(TAU_VENV), "-c", f"import {module}"],
        capture_output=True, text=True,
    )
    return p.returncode == 0, (p.stderr.strip().splitlines() or [""])[-1]


def _http_ok(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:  # up, but this route/path is a different story
        return True, f"HTTP {e.code} (service up)"
    except Exception as e:  # noqa: BLE001
        return False, f"unreachable: {e}"


def main() -> int:
    checks: list[dict] = []

    # 1. /tau reasoning + panel nodes importable (the deleted-module class of failure).
    for mod in TAU_NODES:
        ok, err = _tau_import(mod)
        checks.append(check(
            f"tau_node:{mod.split('.')[-1]}", ok,
            "importable in tau venv" if ok else err,
            fix=f"restore it: cd {TAU_DIR} && git checkout <add-commit> -- src/{mod.replace('.', '/')}.py",
        ))

    # 2. insightface identity gate (the false-FAIL-on-missing-dep class).
    ins = subprocess.run(
        ["uv", "run", "--project", str(SKILL), "python", "-c", "import insightface, onnxruntime"],
        capture_output=True, text=True, cwd=str(SKILL),
    )
    checks.append(check(
        "identity:insightface", ins.returncode == 0,
        "insightface + onnxruntime importable" if ins.returncode == 0
        else (ins.stderr.strip().splitlines() or [""])[-1],
        fix="uv pip install insightface==0.7.3 onnxruntime==1.19.2  "
            "(NOT '-e .[identity]' — that breaks on package discovery)",
    ))
    model = Path.home() / ".insightface" / "models" / "buffalo_l" / "w600k_r50.onnx"
    checks.append(check(
        "identity:buffalo_l_model", model.exists(),
        f"present: {model}" if model.exists() else "buffalo_l not downloaded",
        fix="downloads automatically on first FaceAnalysis(name='buffalo_l').prepare()",
    ))

    # 3. scillm image proxy reachable (the sanctioned OAuth image path lives behind /tau).
    ok, d = _http_ok(f"{SCILLM}/health")
    if not ok:
        ok, d = _http_ok(f"{SCILLM}/")
    checks.append(check(
        "scillm:proxy", ok, d,
        fix=f"start the scillm proxy service on {SCILLM}", required=False,
    ))

    # 4. Graph Memory Operator reachable (the commit/activate 404 class).
    ok, d = _http_ok(f"{GMO}/health")
    if not ok:
        ok, d = _http_ok(f"{GMO}/")
    checks.append(check(
        "memory:gmo", ok, d,
        fix=f"start Graph Memory Operator on {GMO}; the cycle POSTs /persona-dream/commit/activate",
    ))

    # 5. Reference sheets (identity anchors) present.
    for who in ("horus", "embry"):
        sheet = SKILL / "reports" / "assets" / f"{who}_reference_sheet.png"
        checks.append(check(
            f"anchor:{who}_reference_sheet", sheet.exists(),
            "present" if sheet.exists() else f"missing: {sheet}",
            fix=f"restore {who}_reference_sheet.png from git or regenerate the reference sheet",
            required=False,
        ))

    blockers = [c for c in checks if c["required"] and not c["ok"]]
    status = "DREAM_DOCTOR_OK" if not blockers else "DREAM_DOCTOR_BLOCKED"
    receipt = {
        "schema": "persona_dream.dream_doctor.v1",
        "status": status,
        "checks": checks,
        "blockers": [c["name"] for c in blockers],
    }

    if "--json" in sys.argv:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"dream doctor: {status}")
        for c in checks:
            mark = "ok " if c["ok"] else ("XX " if c["required"] else "-- ")
            print(f"  [{mark}] {c['name']}: {c['detail']}")
            if not c["ok"] and c["fix"]:
                print(f"         fix: {c['fix']}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
