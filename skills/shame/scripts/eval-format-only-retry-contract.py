#!/usr/bin/env python3
"""Format-only retry must accept only pi.agent_status.v1, never guard-internal schemas."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs"


def call(text: str) -> dict:
    env = {
        **os.environ,
        "LRSSS_FORCE_STATUS": "1",
        "LRSSS_FORMAT_ONLY_RETRY": "1",
    }
    run = subprocess.run(["node", str(CHECKER)], input=text, text=True, capture_output=True, timeout=20, env=env)
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fenced(obj: dict, *, prose: bool = False) -> str:
    body = "```json\n" + json.dumps(obj) + "\n```\n"
    return "extra prose\n" + body if prose else body


def main() -> None:
    wrong = call(fenced({
        "schema": "lazy_report_shame.rejection_notice.v1",
        "decision": "reject",
    }))
    assert wrong["decision"] == "reject" and wrong["reason_codes"] == ["format_retry_wrong_schema"], wrong

    with tempfile.TemporaryDirectory(prefix="shame-format-retry-") as raw:
        work = Path(raw)
        proof = work / "proof.txt"
        proof.write_text("format retry accepted proof\n")
        status = {
            "schema": "pi.agent_status.v1",
            "goal": "format-only retry contract",
            "state": "done",
            "changed": ["no change: retry-format fixture"],
            "verified": [{"command": f"read {proof}", "result": "format retry accepted proof"}],
            "proof": [str(proof)],
        }
        ok = call(fenced(status))
        assert ok["decision"] == "pass" and ok["reason_codes"] == ["valid_agent_status_json"], ok

        extra = call(fenced(status, prose=True))
        assert extra["decision"] == "reject" and extra["reason_codes"] == ["format_retry_extra_content"], extra

    print(json.dumps({
        "schema": "lazy_report_shame.format_only_retry_contract_eval.v1",
        "status": "PASS",
        "checked": [
            "format-only retry rejects lazy_report_shame.rejection_notice.v1 as assistant output",
            "format-only retry accepts exactly one pi.agent_status.v1 JSON block",
            "format-only retry rejects prose outside the status JSON block",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
