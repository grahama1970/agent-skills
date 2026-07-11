#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung5_tool_harness_latest.json")
args = parser.parse_args()

target = "skills/persona-dream/scripts/rung0_httpx.py"
expected_hash = sha256_file(target)
request = {
    "agent": "build",
    "cwd": os.getcwd(),
    "skills": [],
    "timeout_s": 300,
    "prompt": (
        f"Read {target}. Compute its SHA-256 hash. Do not edit files. "
        "Reply with JSON only containing saw_file, saw_httpx_post, file_hash, edited_files. "
        "Set saw_httpx_post true only if the file contains an httpx.post call."
    ),
}
receipt = {
    "schema": "persona_dream.rung5_tool_harness.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "target": target,
    "expected_hash": expected_hash,
    "request": request,
}

try:
    response = httpx.post(
        "http://localhost:4001/v1/scillm/opencode/runs",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "X-Caller-Skill": "persona-dream",
        },
        json=request,
        timeout=360,
    )
    receipt["http_status"] = response.status_code
    response.raise_for_status()
    data = response.json()
    assistant_text = str(data.get("assistant_text") or data)
    parsed = extract_json(assistant_text)
    if parsed.get("edited_files") == []:
        parsed["edited_files"] = False
    ok = (
        data.get("status") == "completed"
        and bool(data.get("run_id"))
        and parsed.get("saw_file") is True
        and parsed.get("saw_httpx_post") is True
        and parsed.get("file_hash") == expected_hash
        and parsed.get("edited_files") is False
    )
    receipt.update(
        {
            "raw_scillm_response": data,
            "assistant_text": assistant_text,
            "parsed_result": parsed,
            "scillm_completed": data.get("status") == "completed",
            "scillm_run_id_present": bool(data.get("run_id")),
            "file_hash_matches": parsed.get("file_hash") == expected_hash,
            "ok": ok,
        }
    )
except Exception as exc:
    receipt.update({"ok": False, "error": repr(exc)})

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 5, "tool_harness": "opencode", "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
