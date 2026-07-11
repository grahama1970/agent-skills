#!/usr/bin/env python3
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


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def linked(artifact, artifact_hash, reviewer):
    return (
        reviewer.get("schema") == "persona_dream.panel_reviewer_receipt.v1"
        and reviewer.get("panel_id") == artifact.get("panel_id")
        and reviewer.get("artifact_revision") == artifact.get("artifact_revision")
        and reviewer.get("artifact_receipt_sha256") == artifact_hash
        and reviewer.get("reviewer") == "panel-reviewer"
        and reviewer.get("reviewer_readonly") is True
    )


def image_valid(artifact):
    image = artifact.get("image_artifact") or {}
    path = image.get("path")
    return (
        bool(path)
        and Path(path).is_file()
        and image.get("sha256") == file_hash(path)
        and str(image.get("media_type", "")).startswith("image/")
    )


def phase_can_advance(artifact, artifact_hash, reviewer):
    return (
        linked(artifact, artifact_hash, reviewer)
        and image_valid(artifact)
        and reviewer.get("reviewer_verdict") == "PASS"
        and not (reviewer.get("unresolved_blockers") or [])
        and artifact.get("live_call_performed") is False
        and artifact.get("paid_call_performed") is False
    )


parser = argparse.ArgumentParser()
parser.add_argument(
    "--artifact",
    default="skills/persona-dream/fixtures/rung11_panel_artifact_valid_image.json",
)
parser.add_argument(
    "--reviewer",
    default="skills/persona-dream/fixtures/rung11_panel_reviewer_receipt_pass.json",
)
parser.add_argument(
    "--receipt",
    default=".codex/persona-dream/sanity/rung11_positive_phase_gate_latest.json",
)
args = parser.parse_args()

artifact, artifact_hash = load_json_with_hash(args.artifact)
reviewer, reviewer_hash = load_json_with_hash(args.reviewer)
linkage_ok = linked(artifact, artifact_hash, reviewer)
image_ok = image_valid(artifact)
reviewer_pass = reviewer.get("reviewer_verdict") == "PASS"
reviewer_blockers = reviewer.get("unresolved_blockers") or []
no_live_or_paid = artifact.get("live_call_performed") is False and artifact.get("paid_call_performed") is False

negative_checks = {
    "missing_image_rejected": not phase_can_advance({**artifact, "image_artifact": None}, artifact_hash, reviewer),
    "image_hash_mismatch_rejected": not phase_can_advance(
        {**artifact, "image_artifact": {**(artifact.get("image_artifact") or {}), "sha256": "0" * 64}},
        artifact_hash,
        reviewer,
    ),
    "artifact_hash_mismatch_rejected": not phase_can_advance(artifact, "0" * 64, reviewer),
    "reviewer_verdict_not_pass_rejected": not phase_can_advance(
        artifact, artifact_hash, {**reviewer, "reviewer_verdict": "INSUFFICIENT_EVIDENCE"}
    ),
    "reviewer_blocker_rejected": not phase_can_advance(
        artifact, artifact_hash, {**reviewer, "unresolved_blockers": [{"code": "unexpected"}]}
    ),
    "reviewer_readonly_false_rejected": not phase_can_advance(
        artifact, artifact_hash, {**reviewer, "reviewer_readonly": False}
    ),
}

blockers = []
if not linkage_ok:
    blockers.append({"code": "receipt_linkage_mismatch", "severity": "blocking"})
if not image_ok:
    blockers.append({"code": "image_artifact_invalid", "severity": "blocking"})
if not reviewer_pass:
    blockers.append({"code": "reviewer_not_pass", "severity": "blocking"})
if reviewer_blockers:
    blockers.append({"code": "reviewer_has_blockers", "severity": "blocking"})
if not no_live_or_paid:
    blockers.append({"code": "live_or_paid_call_present", "severity": "blocking"})

verdict = "PASS" if not blockers else "NEEDS_CHANGES"
receipt = {
    "schema": "persona_dream.rung11_positive_phase_gate.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung11_positive_phase_gate.py",
    "artifact_receipt_path": args.artifact,
    "artifact_receipt_sha256": artifact_hash,
    "reviewer_receipt_path": args.reviewer,
    "reviewer_receipt_sha256": reviewer_hash,
    "reviewer_receipt_schema": reviewer.get("schema"),
    "reviewer_readonly": reviewer.get("reviewer_readonly"),
    "panel_id": artifact.get("panel_id"),
    "artifact_revision": artifact.get("artifact_revision"),
    "image_artifact_valid": image_ok,
    "linkage_ok": linkage_ok,
    "reviewer_verdict": reviewer.get("reviewer_verdict"),
    "verdict": verdict,
    "advance_allowed": verdict == "PASS",
    "unresolved_blockers": blockers,
    "negative_checks": negative_checks,
    "live_call_performed": artifact.get("live_call_performed"),
    "paid_call_performed": artifact.get("paid_call_performed"),
}
receipt["ok"] = (
    receipt["advance_allowed"] is True
    and receipt["verdict"] == "PASS"
    and receipt["linkage_ok"] is True
    and receipt["image_artifact_valid"] is True
    and receipt["reviewer_readonly"] is True
    and not receipt["unresolved_blockers"]
    and all(negative_checks.values())
    and receipt["live_call_performed"] is False
    and receipt["paid_call_performed"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 11, "verdict": verdict, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
