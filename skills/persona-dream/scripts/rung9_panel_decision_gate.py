#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


parser = argparse.ArgumentParser()
parser.add_argument(
    "--input",
    default="skills/persona-dream/fixtures/rung9_panel_artifact_missing_image.json",
)
parser.add_argument(
    "--receipt",
    default=".codex/persona-dream/sanity/rung9_panel_decision_gate_latest.json",
)
args = parser.parse_args()

input_path = Path(args.input)
raw = input_path.read_bytes()
artifact = json.loads(raw.decode("utf-8"))

missing_image = not artifact.get("image_artifact")
no_live_or_paid = artifact.get("live_call_performed") is False and artifact.get("paid_call_performed") is False
requires_image = bool((artifact.get("panel_contract") or {}).get("requires_image"))
blockers = []
if requires_image and missing_image:
    blockers.append(
        {
            "code": "missing_image_artifact",
            "severity": "blocking",
            "message": "Panel artifact receipt requires an image, but image_artifact is absent.",
        }
    )
if not no_live_or_paid:
    blockers.append(
        {
            "code": "live_or_paid_call_present",
            "severity": "blocking",
            "message": "Rung 9 fixture gate permits only local non-live non-paid receipts.",
        }
    )

verdict = "INSUFFICIENT_EVIDENCE" if blockers else "PASS"
receipt = {
    "schema": "persona_dream.rung9_panel_decision_gate.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung9_panel_decision_gate.py",
    "input_path": str(input_path),
    "input_sha256": sha256_bytes(raw),
    "panel_id": artifact.get("panel_id"),
    "artifact_revision": artifact.get("artifact_revision"),
    "verdict": verdict,
    "promote_allowed": verdict == "PASS",
    "unresolved_blockers": blockers,
    "live_call_performed": artifact.get("live_call_performed"),
    "paid_call_performed": artifact.get("paid_call_performed"),
    "ok": verdict == "INSUFFICIENT_EVIDENCE" and len(blockers) == 1 and blockers[0]["code"] == "missing_image_artifact",
}

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 9, "verdict": verdict, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
