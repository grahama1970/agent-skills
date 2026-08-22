#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CHAIN_KEYS = [
    "dream_residue_sha256",
    "dream_packet_sha256",
    "journal_sha256",
    "conflict_id",
    "session_mood_event_id",
    "horus_challenge_turn_id",
    "embry_emotional_frame_turn_id",
    "chatterbox_render_request_sha256",
    "audio_sha256",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--require-control-null-conflict", action="store_true")
    parser.add_argument("--require-treatment-complete-chain", action="store_true")
    parser.add_argument("--forbid-durable-identity-mutation", action="store_true")
    parser.add_argument("--live-artifacts", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    run_root = Path(args.run_root)
    failures: list[str] = []

    control_mood_path = run_root / "control" / "session_mood.json"
    treatment_mood_path = run_root / "treatment" / "session_mood.json"
    lineage_path = run_root / "treatment" / "emotion_lineage.json"

    if not control_mood_path.exists():
        failures.append("missing_control_session_mood")
        control = {}
    else:
        control = json.loads(control_mood_path.read_text(encoding="utf-8"))
    if not treatment_mood_path.exists():
        failures.append("missing_treatment_session_mood")
        treatment = {}
    else:
        treatment = json.loads(treatment_mood_path.read_text(encoding="utf-8"))
    if not lineage_path.exists():
        failures.append("missing_treatment_emotion_lineage")
        lineage = {}
    else:
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))

    if args.require_control_null_conflict and control.get("conflict_id") is not None:
        failures.append("control_conflict_not_null")
    if args.require_treatment_complete_chain:
        for key in CHAIN_KEYS:
            if not lineage.get(key):
                failures.append(f"lineage_missing:{key}")
        treatment_conflict = next(
            (item.get("conflict_id") for item in manifest.get("conditions", []) if item.get("condition_id") == "C1_DREAM_JOURNAL"),
            None,
        )
        if lineage.get("conflict_id") != treatment_conflict:
            failures.append("lineage_conflict_id_mismatch")
    if args.forbid_durable_identity_mutation:
        expected_identity = (manifest.get("identity") or {}).get("identity_core_digest")
        for side, mood in (("control", control), ("treatment", treatment)):
            observed = mood.get("identity_core_digest")
            if observed and observed != expected_identity:
                failures.append(f"{side}_identity_core_mutated")

    receipt = {
        "schema": "persona_dream.emotion_lineage_validation.v1",
        "status": "PASS_EMOTION_LINEAGE" if not failures else "FAIL_EMOTION_LINEAGE",
        "run_root": str(run_root),
        "failures": failures,
        "mocked": False,
        "live": bool(args.live_artifacts),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
