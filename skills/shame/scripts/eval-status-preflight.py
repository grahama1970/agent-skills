#!/usr/bin/env python3
"""Preflight must match the stop-boundary status checker."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "skills/shame/run.sh"
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def call(cmd: list[str], text: str) -> dict:
    env = {**os.environ, "LRSSS_FORCE_STATUS": "1"}
    run = subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=20, env=env)
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def preflight(text: str) -> dict:
    return call([str(RUN), "preflight", "-"], text)


def stop_check(text: str) -> dict:
    return call(["node", str(CHECKER)], text)


def rendered(status: dict) -> str:
    return "done\n```json\n" + json.dumps(status) + "\n```\n"


def compare(name: str, text: str) -> dict:
    a = preflight(text)
    b = stop_check(text)
    keys = ("decision", "reason_codes")
    assert {k: a.get(k) for k in keys} == {k: b.get(k) for k in keys}, (name, a, b)
    return a


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-preflight-") as raw:
        work = Path(raw)
        proof = work / "proof.md"
        proof.write_text("## proof\n")
        closure = work / "closure.json"
        closure.write_text(json.dumps({
            "schema": "ticket.closure_receipt.v1",
            "action": "close",
            "issue": "1622",
            "repo": "grahama1970/agent-skills",
            "reason": "completed",
            "state": "CLOSED",
            "proof_path": str(proof),
            "proof_sha256": sha(proof),
            "closed_at": "2026-09-07T00:00:00+00:00",
        }))
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "preflight parity",
            "state": "done",
            "changed": ["no change: parity fixture"],
            "verified": [{"command": "close grahama1970/agent-skills#1622", "result": "CLOSED"}],
            "proof": [str(closure)],
        }
        passed = compare("valid", rendered(status))
        assert passed["decision"] == "pass", passed

        missing = compare("missing", "done without status")
        assert missing["decision"] == "reject" and "missing_agent_status_json" in missing["reason_codes"], missing

        closure.write_text(json.dumps({
            "schema": "ticket.closure_receipt.v1",
            "action": "close",
            "issue": "1622",
            "repo": "grahama1970/agent-skills",
            "reason": "completed",
            "state": "OPEN",
            "proof_path": str(proof),
            "proof_sha256": sha(proof),
            "closed_at": "2026-09-07T00:00:00+00:00",
        }))
        changed = compare("changed-proof", rendered(status))
        assert changed["decision"] == "reject" and "ticket_closure_receipt_not_closed" in changed["reason_codes"], changed

    print(json.dumps({
        "schema": "lazy_report_shame.status_preflight_parity_eval.v1",
        "status": "PASS",
        "checked": [
            "preflight uses the stop-boundary checker",
            "missing status reason codes match",
            "valid ticket closure proof passes both paths",
            "mutated proof bytes reject before stop with matching reason codes",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
