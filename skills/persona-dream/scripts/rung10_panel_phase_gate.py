#!/usr/bin/env python3
"""rung10_panel_phase_gate - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_json_with_hash(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def linked(artifact, artifact_hash, reviewer):
    return (
        reviewer.get("panel_id") == artifact.get("panel_id")
        and reviewer.get("artifact_revision") == artifact.get("artifact_revision")
        and reviewer.get("artifact_receipt_sha256") == artifact_hash
        and reviewer.get("reviewer") == "panel-reviewer"
        and reviewer.get("reviewer_readonly") is True
    )


parser = argparse.ArgumentParser()
parser.add_argument(
    "--artifact",
    default="skills/persona-dream/fixtures/rung9_panel_artifact_missing_image.json",
)
parser.add_argument(
    "--reviewer",
    default="skills/persona-dream/fixtures/rung10_panel_reviewer_receipt_missing_image.json",
)
parser.add_argument(
    "--receipt",
    default=".codex/persona-dream/sanity/rung10_panel_phase_gate_latest.json",
)
args = parser.parse_args()

artifact, artifact_hash = load_json_with_hash(args.artifact)
reviewer, reviewer_hash = load_json_with_hash(args.reviewer)
linkage_ok = linked(artifact, artifact_hash, reviewer)
reviewer_blockers = reviewer.get("unresolved_blockers") or []
artifact_missing_image = not artifact.get("image_artifact")
reviewer_insufficient = reviewer.get("reviewer_verdict") == "INSUFFICIENT_EVIDENCE"

blockers = []
if not linkage_ok:
    blockers.append({"code": "receipt_linkage_mismatch", "severity": "blocking"})
if artifact_missing_image:
    blockers.append({"code": "missing_image_artifact", "severity": "blocking"})
if reviewer_insufficient:
    blockers.extend(reviewer_blockers)

unique_blockers = []
seen = set()
for blocker in blockers:
    code = blocker.get("code")
    if code in seen:
        continue
    seen.add(code)
    unique_blockers.append(blocker)

negative_checks = {
    "panel_id_mismatch_rejected": not linked({**artifact, "panel_id": "wrong-panel"}, artifact_hash, reviewer),
    "artifact_revision_mismatch_rejected": not linked({**artifact, "artifact_revision": "wrong-revision"}, artifact_hash, reviewer),
    "artifact_hash_mismatch_rejected": not linked(artifact, "0" * 64, reviewer),
    "reviewer_name_mismatch_rejected": not linked(artifact, artifact_hash, {**reviewer, "reviewer": "other-reviewer"}),
    "reviewer_readonly_false_rejected": not linked(artifact, artifact_hash, {**reviewer, "reviewer_readonly": False}),
    "reviewer_readonly_missing_rejected": not linked(
        artifact,
        artifact_hash,
        {key: value for key, value in reviewer.items() if key != "reviewer_readonly"},
    ),
}

verdict = "PASS" if linkage_ok and not unique_blockers else "INSUFFICIENT_EVIDENCE"
receipt = {
    "schema": "persona_dream.rung10_panel_phase_gate.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung10_panel_phase_gate.py",
    "artifact_receipt_path": args.artifact,
    "artifact_receipt_sha256": artifact_hash,
    "reviewer_receipt_path": args.reviewer,
    "reviewer_receipt_sha256": reviewer_hash,
    "reviewer_receipt_schema": reviewer.get("schema"),
    "reviewer_readonly": reviewer.get("reviewer_readonly"),
    "panel_id": artifact.get("panel_id"),
    "artifact_revision": artifact.get("artifact_revision"),
    "linkage_ok": linkage_ok,
    "reviewer_verdict": reviewer.get("reviewer_verdict"),
    "verdict": verdict,
    "advance_allowed": verdict == "PASS",
    "unresolved_blockers": unique_blockers,
    "negative_checks": negative_checks,
    "live_call_performed": artifact.get("live_call_performed"),
    "paid_call_performed": artifact.get("paid_call_performed"),
}
receipt["ok"] = (
    linkage_ok
    and receipt["advance_allowed"] is False
    and receipt["verdict"] == "INSUFFICIENT_EVIDENCE"
    and any(item.get("code") == "missing_image_artifact" for item in unique_blockers)
    and all(negative_checks.values())
    and receipt["live_call_performed"] is False
    and receipt["paid_call_performed"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 10, "verdict": verdict, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
