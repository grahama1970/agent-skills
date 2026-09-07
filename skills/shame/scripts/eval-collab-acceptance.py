#!/usr/bin/env python3
"""Collaboration closure must include a peer acceptance receipt."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "skills/shame/scripts/collab_acceptance_schema.py"
STATUS_SCHEMA = ROOT / "skills/shame/scripts/agent_status_schema.py"
work = Path(tempfile.mkdtemp(prefix="shame-collab-", dir="/tmp"))


def run(*argv: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, input=input_text, text=True, capture_output=True, timeout=20)


def write(name: str, payload: dict) -> Path:
    path = work / name
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path

base = {
    "schema": "lazy_report_shame.collab_acceptance.v1",
    "implementer": "01a077ef",
    "acceptor": "01a0795e",
    "task_msg_id": "e509095f",
    "peer_rejection_msg_id": "f986f789-reply",
    "changed_action": "deterministic checker proof was rejected; live Pi question-turn eval was added before closure",
    "acceptance_msg_id": "c2d48911-reply",
    "verified_command": "intercom ask 01a0795e final acceptance",
    "verified_result": "ACCEPTED AS SOLVED; no next gap",
}
missing = dict(base)
missing.pop("acceptance_msg_id")
self_accept = dict(base, acceptor=base["implementer"])
good = dict(base)

missing_path = write("missing.json", missing)
self_path = write("self.json", self_accept)
good_path = write("good.json", good)

missing_result = run(sys.executable, str(SCHEMA), "validate", str(missing_path))
self_result = run(sys.executable, str(SCHEMA), "validate", str(self_path))
good_result = run(sys.executable, str(SCHEMA), "validate", str(good_path))
assert missing_result.returncode == 1 and "missing" in missing_result.stdout, missing_result.stdout
assert self_result.returncode == 1 and "collab_acceptor_must_differ" in self_result.stdout, self_result.stdout
assert good_result.returncode == 0, good_result.stdout + good_result.stderr

status = {
    "schema": "pi.agent_status.v1",
    "goal": "Close the Shame collaborator repair loop only after peer acceptance.",
    "answer": "Peer accepted the bidirectional Shame repair loop as solved.",
    "state": "done",
    "changed": ["recorded peer acceptance as a typed receipt"],
    "verified": [{"command": base["verified_command"], "result": base["verified_result"]}],
    "proof": [str(good_path)],
}
status_result = run(sys.executable, str(STATUS_SCHEMA), "validate", "-", input_text=json.dumps(status))
assert status_result.returncode == 0, status_result.stdout + status_result.stderr
report = {
    "schema": "lazy_report_shame.collab_acceptance.eval.v1",
    "status": "PASS_COLLAB_REQUIRES_PEER_ACCEPTANCE",
    "missing_acceptance_rejected": True,
    "self_acceptance_rejected": True,
    "status_proof_checked_known_receipt": True,
    "good_receipt": str(good_path),
}
print(json.dumps(report, indent=2))
