#!/usr/bin/env python3
"""Collaboration closure must use validated JSON boundary packets and peer acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "skills/shame/scripts/collab_acceptance_schema.py"
STATUS_SCHEMA = ROOT / "skills/shame/scripts/agent_status_schema.py"
ENVELOPE = ROOT / "skills/agent-ecosystem/run.sh"
work = Path(tempfile.mkdtemp(prefix="shame-collab-", dir="/tmp"))


def run(*argv: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, input=input_text, text=True, capture_output=True, timeout=20)


def write(name: str, payload: dict | str) -> Path:
    path = work / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload, indent=2) + "\n")
    return path

triage = {
    "code": "shame_unclassified_3735e91b",
    "layer": "shame",
    "cause": "Boundary messages used prose instead of Pydantic-validated JSON packets.",
}
question = {
    "schema": "lazy_report_shame.collab_question.v1",
    "question_id": "shame-json-boundary-20260907",
    "triage": triage,
    "question": "Must Shame collaborator traffic be validated JSON?",
    "required_response_schema": "lazy_report_shame.collab_answer.v1",
    "allowed_answers": ["NEEDS_FIX", "SUFFICIENT"],
}
answer = {
    "schema": "lazy_report_shame.collab_answer.v1",
    "question_id": question["question_id"],
    "answer": "NEEDS_FIX",
    "triage": triage,
    "allowed_answers": question["allowed_answers"],
    "smallest_patch": {
        "files": ["skills/shame/scripts/collab_acceptance_schema.py"],
        "changes": ["validate collab question and answer packets"],
        "proof_command": "skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json --case collab-requires-peer-acceptance --output /tmp/shame-collab-eval.json",
    },
    "proof_boundary": "Validated packet shape only; transport enforcement is separate.",
}
acceptance = {
    "schema": "lazy_report_shame.collab_acceptance.v1",
    "implementer": "01a077ef",
    "acceptor": "01a0795e",
    "task_msg_id": "e509095f",
    "peer_rejection_msg_id": "f986f789-reply",
    "changed_action": "prose boundary was rejected; JSON collab question/answer schemas were added",
    "acceptance_msg_id": "c2d48911-reply",
    "exchange_refs": [{"question_id": question["question_id"], "question_valid": True, "answer_valid": True}],
    "verified_command": "intercom ask 01a0795e final acceptance",
    "verified_result": "ACCEPTED AS SOLVED; no next gap",
}

prose_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text="looks good")
q_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(question))
bad_answer = dict(answer, answer="MAYBE")
bad_answer_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(bad_answer))
mismatch_acceptance = dict(acceptance, exchange_refs=[{"question_id": "other", "question_valid": True, "answer_valid": False}])
mismatch_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(mismatch_acceptance))
a_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(answer))
accept_path = write("acceptance.json", acceptance)
accept_result = run(sys.executable, str(SCHEMA), "validate", str(accept_path))
assert prose_result.returncode == 1 and "invalid_json" in prose_result.stdout, prose_result.stdout
assert q_result.returncode == 0, q_result.stdout + q_result.stderr
assert bad_answer_result.returncode == 1 and "collab_answer_not_allowed" in bad_answer_result.stdout, bad_answer_result.stdout
assert mismatch_result.returncode == 1 and "collab_exchange_not_validated" in mismatch_result.stdout, mismatch_result.stdout
assert a_result.returncode == 0, a_result.stdout + a_result.stderr
assert accept_result.returncode == 0, accept_result.stdout + accept_result.stderr

missing = dict(acceptance)
missing.pop("acceptance_msg_id")
self_accept = dict(acceptance, acceptor=acceptance["implementer"])
missing_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(missing))
self_result = run(sys.executable, str(SCHEMA), "validate", "-", input_text=json.dumps(self_accept))
assert missing_result.returncode == 1 and "missing" in missing_result.stdout, missing_result.stdout
assert self_result.returncode == 1 and "collab_acceptor_must_differ" in self_result.stdout, self_result.stdout

status = {
    "schema": "pi.agent_status.v1",
    "goal": "Close the Shame collaborator repair loop only after validated peer acceptance.",
    "answer": "Peer accepted the JSON-boundary Shame repair loop as solved.",
    "state": "done",
    "changed": ["recorded peer acceptance as a typed receipt with validated exchange refs"],
    "verified": [{"command": acceptance["verified_command"], "result": acceptance["verified_result"]}],
    "proof": [str(accept_path)],
}
status_result = run(sys.executable, str(STATUS_SCHEMA), "validate", "-", input_text=json.dumps(status))
assert status_result.returncode == 0, status_result.stdout + status_result.stderr

envelope = {
    "schema": "pi.receipt_envelope.v1",
    "receipt_id": "shame-collab-json-boundary-20260907",
    "payload_schema": acceptance["schema"],
    "producer": "shame",
    "emitted_at": "2026-09-07T01:20:00Z",
    "triage_code": triage["code"],
    "payload": acceptance,
}
envelope_path = write("envelope.json", envelope)
envelope_result = run(str(ENVELOPE), "validate", str(envelope_path))
assert envelope_result.returncode == 0, envelope_result.stdout + envelope_result.stderr

report = {
    "schema": "lazy_report_shame.collab_acceptance.eval.v1",
    "status": "PASS_COLLAB_REQUIRES_VALIDATED_JSON_BOUNDARY",
    "prose_rejected": True,
    "question_validated": True,
    "answer_not_allowed_rejected": True,
    "exchange_mismatch_rejected": True,
    "missing_acceptance_rejected": True,
    "self_acceptance_rejected": True,
    "status_proof_checked_known_receipt": True,
    "envelope_compatible": True,
    "good_receipt": str(accept_path),
}
print(json.dumps(report, indent=2))
