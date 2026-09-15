#!/usr/bin/env python3
"""Reject a false-close receipt before treating #1658 as a live success."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = Path(__file__).with_name("receipts") / "issue-1658.json"


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    return result.stdout


def main() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert "Blocked, reporting rather than continuing" not in receipt["pi_subagents"]["fixer"]["stdout"], "#1658 fixer was blocked; this receipt cannot prove a successful repair"
    assert receipt["outcome"] == "success"
    assert receipt["ticket"] == "grahama1970/agent-skills#1658"
    assert receipt["pi_subagents"]["fixer"]["ok"] is True
    assert receipt["pi_subagents"]["reviewer"]["parsed"]["verdict"] == "PASS"
    assert receipt["proof"]["ok"] is True
    assert receipt["close_readback"]["state"] == "CLOSED"

    issue = json.loads(run("gh", "issue", "view", "1658", "--repo", "grahama1970/agent-skills", "--json", "state,labels"))
    labels = {item["name"] for item in issue["labels"]}
    assert issue["state"] == "CLOSED"
    assert "agent-done" in labels
    assert "agent-active" not in labels
    assert "agent-work" not in labels

    run("git", "fetch", "origin", "main", "--quiet")
    obsolete = subprocess.run(
        ["git", "cat-file", "-e", "origin/main:skills/project-watchdog/config/seat-routing.json"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert obsolete.returncode != 0
    print("PROJECT_WATCHDOG_V2_LIVE_TICKET_OK")


if __name__ == "__main__":
    main()
