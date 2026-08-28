#!/usr/bin/env python3
"""Live diagnostic guard for monitor-opportunities terminal-error handoff."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _last_json_line(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        return json.loads(line)
    raise AssertionError("terminal error JSON line missing")


def _require(condition: bool, marker: str, detail: object | None = None) -> None:
    if condition:
        return
    suffix = f" {detail}" if detail is not None else ""
    raise AssertionError(marker + suffix)


def main() -> int:
    repo = _repo_root()
    out = Path("/tmp/monitor-opportunities-terminal-error-handoff-proof").resolve()
    if out.exists():
        shutil.rmtree(out)

    cmd = [
        str(repo / "skills" / "monitor-opportunities" / "run.sh"),
        "nightly",
        "--diagnostic",
        "--skip-buzz",
        "--out",
        str(out),
        "--expected-revision",
        "0000000000000000000000000000000000000000",
    ]
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False, timeout=180)
    _require(proc.returncode == 2, "TERMINAL_ERROR_EXIT_CODE_UNEXPECTED", proc.returncode)
    payload = _last_json_line(proc.stderr)
    _require(payload.get("code") == "NIGHTLY_REVISION_MISMATCH", "TERMINAL_ERROR_CODE_MISSING", payload)
    _require(
        payload.get("terminal_error_handoff_status") == "PASS",
        "TERMINAL_ERROR_HANDOFF_NOT_PASS",
        payload,
    )
    handoff_path = Path(str(payload.get("terminal_error_handoff") or ""))
    _require(handoff_path.is_file(), "TERMINAL_ERROR_HANDOFF_ARTIFACT_MISSING", handoff_path)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    _require(handoff.get("schema") == "monitor_opportunities.terminal_error_handoff.v1", "HANDOFF_SCHEMA")
    _require(handoff.get("status") == "PASS", "HANDOFF_STATUS", handoff)
    _require(handoff.get("mocked") is False, "HANDOFF_MOCKED", handoff)
    _require(handoff.get("live") is True, "HANDOFF_LIVE", handoff)
    _require(handoff.get("external_effects") is False, "HANDOFF_EXTERNAL_EFFECTS", handoff)
    _require((handoff.get("signal") or {}).get("code") == "NIGHTLY_REVISION_MISMATCH", "HANDOFF_SIGNAL_CODE")

    triage_receipt = Path(str(handoff.get("triage_receipt") or ""))
    _require(triage_receipt.is_file(), "TRIAGE_RECEIPT_MISSING", triage_receipt)
    triage = handoff.get("triage") or {}
    _require(
        triage.get("code") == "monitor_opportunities_nightly_revision_mismatch",
        "TRIAGE_CANONICAL_CODE",
        triage,
    )
    _require(triage.get("ambiguous") is False, "TRIAGE_AMBIGUOUS", triage)
    next_command = str(triage.get("next_command") or "")
    for marker in ("skills/monitor-opportunities/run.sh schedule --promoted-stage0", "route:ops_or_scheduler", "project-watchdog"):
        _require(marker in next_command, "TRIAGE_NEXT_COMMAND_MISSING", marker)

    ticket_handoff = handoff.get("ticket_handoff") or {}
    _require(ticket_handoff.get("mode") == "preview", "TICKET_MODE", ticket_handoff)
    _require(ticket_handoff.get("exit_code") == 0, "TICKET_EXIT_CODE", ticket_handoff)
    preview_labels = ticket_handoff.get("preview_labels") or []
    for marker in ("agent-work", "route:ops_or_scheduler", "lane:ops"):
        _require(marker in preview_labels, "TICKET_PREVIEW_LABEL_MISSING", marker)
    _require(ticket_handoff.get("preview_body_sha256"), "TICKET_PREVIEW_BODY_DIGEST", ticket_handoff)
    ticket_stdout = str(ticket_handoff.get("stdout_tail") or "")
    for marker in ("route:ops_or_scheduler", "Required proof", "project-watchdog"):
        _require(marker in ticket_stdout, "TICKET_PREVIEW_MISSING", marker)

    watchdog = handoff.get("project_watchdog") or {}
    _require(watchdog.get("dispatchable_by_project_watchdog") is True, "WATCHDOG_ROUTABLE", watchdog)
    _require(watchdog.get("route") == "ops_or_scheduler", "WATCHDOG_ROUTE", watchdog)
    _require("agent-work" in (watchdog.get("labels") or []), "WATCHDOG_LABELS", watchdog)
    _require("required_proof" in watchdog, "WATCHDOG_REQUIRED_PROOF", watchdog)

    print(
        "TERMINAL_ERROR_HANDOFF_OK "
        f"artifact={handoff_path} "
        f"triage={triage['code']} "
        f"ticket=preview watchdog=dispatchable"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
