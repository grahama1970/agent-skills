#!/usr/bin/env python3
"""Validate corrected-goal emotion lineage and byte-bound proof inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


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
SOURCE_MEMORY_FILES = {
    "residue_links_sha256": "residue_links.json",
    "day_context_sha256": "day_context.json",
}


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _resolve_inside(base: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    raw = Path(ref)
    path = raw if raw.is_absolute() else base / raw
    if not _is_relative_to(path, base):
        return None
    return path


def _identity(mood: dict[str, Any]) -> dict[str, Any]:
    embedded = mood.get("identity")
    if isinstance(embedded, dict):
        return embedded
    return {
        "artifact_path": mood.get("identity_artifact_path"),
        "artifact_sha256": mood.get("identity_artifact_sha256"),
        "identity_core_digest": mood.get("identity_core_digest"),
    }


def _validate_source_memory(run_root: Path, control: dict[str, Any], treatment: dict[str, Any], failures: list[str]) -> None:
    expected: dict[str, str] = {}
    for key, name in SOURCE_MEMORY_FILES.items():
        path = run_root / "source_memory" / name
        if not path.is_file():
            failures.append(f"source_memory_artifact_missing:{name}")
        else:
            expected[key] = _sha_file(path)
    for side, mood in (("control", control), ("treatment", treatment)):
        binding = mood.get("source_memory") if isinstance(mood.get("source_memory"), dict) else {}
        for key, digest in expected.items():
            observed = binding.get(key)
            if not observed:
                failures.append(f"{side}:source_memory_digest_missing:{key}")
            elif observed != digest:
                failures.append(f"{side}:source_memory_digest_mismatch:{key}")
    c_binding = control.get("source_memory") if isinstance(control.get("source_memory"), dict) else {}
    t_binding = treatment.get("source_memory") if isinstance(treatment.get("source_memory"), dict) else {}
    for key in SOURCE_MEMORY_FILES:
        if c_binding.get(key) and t_binding.get(key) and c_binding.get(key) != t_binding.get(key):
            failures.append(f"source_memory_digest_unequal:{key}")


def _resolve_identity_path(run_root: Path, side_dir: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    raw = Path(ref)
    candidates = [raw] if raw.is_absolute() else [side_dir / raw, run_root / raw]
    for path in candidates:
        if _is_relative_to(path, run_root):
            return path
    return None


def _validate_identity(manifest: dict[str, Any], run_root: Path, control: dict[str, Any], treatment: dict[str, Any], failures: list[str]) -> None:
    manifest_identity = (manifest.get("identity") or {}).get("identity_core_digest")
    if not manifest_identity:
        failures.append("manifest_identity_core_digest_missing")
    seen_artifact: list[str] = []
    seen_core: list[str] = []
    for side, mood in (("control", control), ("treatment", treatment)):
        side_dir = run_root / side
        identity = _identity(mood)
        artifact_path = identity.get("artifact_path")
        artifact_sha = identity.get("artifact_sha256")
        core = identity.get("identity_core_digest")
        if not artifact_path:
            failures.append(f"{side}:identity_artifact_path_missing")
        if not artifact_sha:
            failures.append(f"{side}:identity_artifact_digest_missing")
        if not core:
            failures.append(f"{side}:identity_core_digest_missing")
        if not (artifact_path and artifact_sha and core):
            continue
        path = _resolve_identity_path(run_root, side_dir, artifact_path)
        if path is None or not path.is_file():
            failures.append(f"{side}:identity_artifact_missing")
            continue
        actual = _sha_file(path)
        if artifact_sha != actual:
            failures.append(f"{side}:identity_artifact_digest_mismatch")
        if core != actual:
            failures.append(f"{side}:identity_core_digest_unverified")
        if manifest_identity and manifest_identity != actual:
            failures.append(f"{side}:manifest_identity_core_digest_mismatch")
        seen_artifact.append(str(artifact_sha))
        seen_core.append(str(core))
    if len(seen_artifact) == 2 and seen_artifact[0] != seen_artifact[1]:
        failures.append("identity_artifact_sha256_unequal")
    if len(seen_core) == 2 and seen_core[0] != seen_core[1]:
        failures.append("identity_core_digest_unequal")


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
        control = _load(control_mood_path)
    if not treatment_mood_path.exists():
        failures.append("missing_treatment_session_mood")
        treatment = {}
    else:
        treatment = _load(treatment_mood_path)
    if not lineage_path.exists():
        failures.append("missing_treatment_emotion_lineage")
        lineage = {}
    else:
        lineage = _load(lineage_path)

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
        _validate_identity(manifest, run_root, control, treatment, failures)
    _validate_source_memory(run_root, control, treatment, failures)

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
