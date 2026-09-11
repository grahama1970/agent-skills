#!/usr/bin/env python3
"""Stale debugger-attach recovery eval (#1653).

Deterministic (mocked=true): fault-injects the surf runtime so a js probe first
fails with "Another debugger is already attached to the tab", then succeeds on
retry. Asserts the ask browser-provider probe detects the stale attach, runs the
tab.maintenance rebind, retries, and reports the tab healthy (stale_attach_
recovered=True). A non-attach failure is NOT treated as recoverable. Does not
touch a live browser.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ASK_SCRIPTS = Path(__file__).resolve().parents[2] / "ask" / "scripts"
sys.path.insert(0, str(ASK_SCRIPTS))
import probe_browser_provider_availability as probe  # noqa: E402


def _cp(rc, out="", err=""):
    return subprocess.CompletedProcess(args=["surf"], returncode=rc, stdout=out, stderr=err)


def main() -> int:
    checks: list[dict] = []

    def check(name, got, expected):
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    healthy_js = json.dumps({"href": "https://chatgpt.com/", "title": "ChatGPT",
                             "scoped_text": "ready", "modal_text": "", "body_text": "ready",
                             "has_main": True})

    # 1) stale attach then clean retry -> recovered + healthy.
    calls = {"n": 0}
    def fake_run_recover(cmd, *, timeout):
        if cmd[1] == "tab.maintenance":
            return _cp(0, "rebound")
        calls["n"] += 1
        if calls["n"] == 1:
            return _cp(1, "", "Failed to attach debugger: Another debugger is already attached to the tab")
        return _cp(0, healthy_js)
    probe._run = fake_run_recover  # type: ignore[assignment]
    r = probe._check_tab(surf_run=Path("/surf/run.sh"), tab_id="123", pattern="usage limit")
    check("recovered_flag", r.get("stale_attach_recovered"), True)
    check("retry_returncode_zero", r.get("returncode"), 0)
    check("repair_was_run", r.get("stale_attach_repair_rc"), 0)

    # 2) stale attach that stays broken -> not recovered, degraded.
    def fake_run_persist(cmd, *, timeout):
        if cmd[1] == "tab.maintenance":
            return _cp(0, "rebound")
        return _cp(1, "", "Failed to attach debugger: Another debugger is already attached to the tab")
    probe._run = fake_run_persist  # type: ignore[assignment]
    r2 = probe._check_tab(surf_run=Path("/surf/run.sh"), tab_id="123", pattern="usage limit")
    check("persistent_not_recovered", r2.get("stale_attach_recovered"), False)
    check("persistent_returncode_nonzero", r2.get("returncode") != 0, True)

    # 3) a non-attach failure is not treated as a stale-attach (no repair path).
    def fake_run_other(cmd, *, timeout):
        return _cp(124, "", "")  # timeout, not an attach error
    probe._run = fake_run_other  # type: ignore[assignment]
    r3 = probe._check_tab(surf_run=Path("/surf/run.sh"), tab_id="123", pattern="usage limit")
    check("nonattach_no_recovery_key", "stale_attach_recovered" in r3, False)
    check("classifier_detects_attach",
          probe._is_stale_attach_error({"stderr": "Another debugger is already attached"}), True)
    check("classifier_ignores_timeout", probe._is_stale_attach_error({"stderr": ""}), False)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "surf.stale_attach_recovery_eval.v1", "mocked": True, "live": False,
              "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/surf-stale-attach.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
