#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", required=True)
parser.add_argument("--source", default="skills/persona-dream/PROJECT_KNOWLEDGE.md")
args = parser.parse_args()

source_path = Path(args.source)
receipt = {
    "schema": "persona_dream.rung20_story_executor_receipt.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung20_story_executor_readonly.py",
    "phase": "story",
    "executor": "story_executor_readonly_fixture",
    "executor_readonly": True,
    "source": {
        "path": str(source_path),
        "sha256": file_hash(source_path),
    },
    "output_contract": {
        "phase": "story",
        "status": "READY_FOR_SHARED_GATE",
        "artifact_type": "read_only_story_executor_fixture",
    },
    "unresolved_blockers": [],
    "active_artifact_mutation_performed": False,
    "provider_call_performed": False,
    "live_call_performed": False,
    "paid_call_performed": False,
}
receipt["ok"] = (
    receipt["executor_readonly"] is True
    and not receipt["unresolved_blockers"]
    and receipt["active_artifact_mutation_performed"] is False
    and receipt["provider_call_performed"] is False
    and receipt["live_call_performed"] is False
    and receipt["paid_call_performed"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 20, "executor": "story", "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
