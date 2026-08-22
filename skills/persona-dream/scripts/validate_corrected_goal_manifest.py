#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    if manifest.get("schema") != "persona_dream.corrected_goal_manifest.v1":
        failures.append("bad_schema")
    if manifest.get("proof_id") != "PD-CORRECTED-GOAL-V1":
        failures.append("bad_proof_id")

    capsule = manifest.get("answer_capsule") or {}
    answer_body = capsule.get("answer_body")
    if not answer_body:
        failures.append("missing_answer_body")
    elif capsule.get("answer_body_sha256") != _sha_text(answer_body):
        failures.append("answer_body_sha256_mismatch")
    if not capsule.get("protected_tokens"):
        failures.append("missing_protected_tokens")

    conditions: dict[str, dict[str, Any]] = {
        item.get("condition_id"): item for item in manifest.get("conditions") or []
    }
    control = conditions.get("C0_STRUCTURED_REFLECTION") or {}
    treatment = conditions.get("C1_DREAM_JOURNAL") or {}
    if control.get("conflict_id") is not None:
        failures.append("control_conflict_not_null")
    if not treatment.get("conflict_id"):
        failures.append("treatment_conflict_missing")
    if set(treatment.get("required_journal_fields") or []) != {"conflict", "mood", "feelings"}:
        failures.append("treatment_journal_fields_incomplete")

    mapping = manifest.get("mood_to_chatterbox_mapping") or {}
    allowed_channels = set(mapping.get("allowed_channels") or [])
    if not {"intensity", "tempo", "native_tag"}.issubset(allowed_channels):
        failures.append("chatterbox_allowed_channels_incomplete")
    if "valence" not in set(mapping.get("forbidden_observed_channels") or []):
        failures.append("valence_not_forbidden_as_observed_channel")
    if "[sigh]" not in set(mapping.get("allowed_native_tags") or []):
        failures.append("native_tag_vocab_missing_sigh")
    if float(mapping.get("minimum_opening_duration_ratio") or 0) < 1.08:
        failures.append("opening_duration_ratio_too_weak")

    if args.strict:
        gates = set(manifest.get("fail_closed_gates") or [])
        required = {
            "live_true_mocked_false",
            "exact_answer_body_hash_across_aligned_embry_turns",
            "protected_tokens_recovered_by_asr",
            "treatment_emotion_lineage_complete",
            "control_conflict_null",
            "identity_core_digest_unchanged",
            "synthetic_provenance_preserved",
        }
        failures.extend(f"missing_gate:{gate}" for gate in sorted(required - gates))

    receipt = {
        "schema": "persona_dream.corrected_goal_manifest_validation.v1",
        "status": "PASS_CORRECTED_GOAL_MANIFEST" if not failures else "FAIL_CORRECTED_GOAL_MANIFEST",
        "manifest": str(manifest_path),
        "manifest_sha256": _sha_text(json.dumps(manifest, sort_keys=True, separators=(",", ":"))),
        "failures": failures,
        "mocked": False,
        "live": False,
        "proves": "the sealed PD-CORRECTED-GOAL-V1 fixture encodes the paired control/treatment gates",
        "does_not_prove": "that a live paired run has produced any artifact",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
