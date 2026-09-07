#!/usr/bin/env python3
"""Shame checker: immutable-goal reports must lead with a decisive headline."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"
OUT = Path("/mnt/storage12tb/skills/shame/immutable-goal-headline")
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="headline-", dir=OUT))
proof = work / "proof.txt"
proof.write_text("command: read closure receipt\nresult: immutable_goal_state COMPLETE\n")


def status(answer: str) -> str:
    return "```json\n" + json.dumps({
        "schema": "pi.agent_status.v1",
        "goal": "Answer whether the immutable goal is met.",
        "answer": answer,
        "state": "done",
        "changed": ["no change: checker fixture"],
        "verified": [{"command": "read closure receipt", "result": "immutable_goal_state COMPLETE"}],
        "proof": [str(proof)],
    }) + "\n```\n"


def run(answer: str) -> dict:
    env = {**os.environ, "LRSSS_FORCE_STATUS": "1", "LRSSS_USER_TEXT": "has the immutable goal been met?"}
    proc = subprocess.run(
        ["node", str(CHECKER)],
        input=status(answer),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    try:
        parsed = json.loads(proc.stdout)
    except Exception as exc:
        raise AssertionError({"stdout": proc.stdout, "stderr": proc.stderr}) from exc
    return {"exit_code": proc.returncode, "stdout": parsed, "stderr": proc.stderr}

vague = run("Done; see proof below.")
complete = run("IMMUTABLE_GOAL: COMPLETE — receipt says immutable_goal_state COMPLETE.")
not_complete = run("IMMUTABLE_GOAL: NOT_COMPLETE — missing closure receipt.")
needs_human = run("IMMUTABLE_GOAL: NEEDS_HUMAN — acceptance requires a human decision.")

assert vague["exit_code"] == 1, vague
assert "missing_immutable_goal_headline" in vague["stdout"].get("reason_codes", []), vague
for item in (complete, not_complete, needs_human):
    assert item["exit_code"] == 0, item
    assert item["stdout"].get("decision") == "pass", item

report = {
    "schema": "shame.immutable_goal_headline_eval.v1",
    "status": "PASS_IMMUTABLE_GOAL_HEADLINE_ENFORCED",
    "vague_answer_rejected": True,
    "accepted_headlines": ["COMPLETE", "NOT_COMPLETE", "NEEDS_HUMAN"],
    "work_dir": str(work),
    "report": str(work / "report.json"),
}
(work / "report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
