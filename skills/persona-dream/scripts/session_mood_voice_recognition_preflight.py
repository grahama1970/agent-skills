#!/usr/bin/env python3
"""Fail-closed preflight for Persona Dream session-mood voice recognition."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE_RECEIPT = (
    ROOT / "reports" / "goal_v5" / "continuity" / "session_mood_chatterbox_live" / "RECEIPT.json"
)
DEFAULT_REFERENCE_AUDIO = Path(
    "/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs/"
    "embry_authorized_ref_30s_8s.wav"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": "sha256:" + sha256_file(path) if path.is_file() else None,
    }


def backend_status(engine: str) -> dict[str, Any]:
    if engine == "resemblyzer":
        required = ["resemblyzer", "numpy"]
    elif engine == "speechbrain_ecapa":
        required = ["speechbrain", "torch"]
    else:
        raise ValueError(f"unsupported_engine:{engine}")
    modules = {name: importlib.util.find_spec(name) is not None for name in required}
    return {
        "engine": engine,
        "required_modules": required,
        "modules": modules,
        "available": all(modules.values()),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_audio_snapshots(live_receipt_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    receipt = load_json(live_receipt_path)
    results = receipt.get("render_results")
    if not isinstance(results, list) or not results:
        return [], ["live_receipt_render_results_present"]
    snapshots: list[dict[str, Any]] = []
    for result in results:
        turn_id = str(result.get("turn_id") or "unknown")
        raw_snapshot = result.get("finished_response_audio_snapshot")
        if not isinstance(raw_snapshot, str) or not raw_snapshot:
            failures.append(f"{turn_id}_audio_snapshot_path_present")
            continue
        snapshot_path = Path(raw_snapshot)
        if not snapshot_path.is_absolute():
            snapshot_path = ROOT.parent.parent / snapshot_path
        row = {
            "turn_id": turn_id,
            "snapshot": artifact(snapshot_path),
            "reported_sha256": result.get("finished_response_audio_snapshot_sha256"),
            "asr_wer": (result.get("asr_gate") or {}).get("wer"),
        }
        if not snapshot_path.is_file():
            failures.append(f"{turn_id}_audio_snapshot_exists")
        elif row["reported_sha256"] != row["snapshot"]["sha256"]:
            failures.append(f"{turn_id}_audio_snapshot_sha256_matches")
        if (result.get("asr_gate") or {}).get("wer") != 0.0:
            failures.append(f"{turn_id}_asr_wer_zero")
        snapshots.append(row)
    return snapshots, failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    failed_gates: list[str] = []
    live_receipt = args.live_receipt.resolve()
    reference_audio = args.reference_audio.resolve()
    if not live_receipt.is_file():
        failed_gates.append("live_session_mood_receipt_exists")
        snapshots = []
    else:
        snapshots, snapshot_failures = validate_audio_snapshots(live_receipt)
        failed_gates.extend(snapshot_failures)
    reference = artifact(reference_audio)
    if not reference["exists"]:
        failed_gates.append("embry_reference_audio_exists")
    backends = [backend_status(engine) for engine in args.engine]
    if not any(item["available"] for item in backends):
        failed_gates.append("speaker_recognition_backend_available")
    receipt = {
        "schema": "persona_dream.session_mood_voice_recognition_preflight.v1",
        "created_at": utc_now(),
        "status": "PASS_SPEAKER_RECOGNITION_PREFLIGHT" if not failed_gates
        else "BLOCKED_SPEAKER_RECOGNITION_PREFLIGHT",
        "mocked": False,
        "live": False,
        "inputs": {
            "live_session_mood_receipt": str(live_receipt),
            "reference_audio": str(reference_audio),
            "engines_checked": args.engine,
        },
        "reference_audio": reference,
        "audio_snapshots": snapshots,
        "speaker_backend_candidates": backends,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "session_mood_audio_snapshots_are_durable",
                "speaker_recognition_backend_is_available",
            ] if not failed_gates else [],
            "does_not_prove": [
                "speaker similarity",
                "adversarial Embry recognition",
                "perceived target emotion",
                "naturalness",
                "production conversation-service binding",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-receipt", type=Path, default=DEFAULT_LIVE_RECEIPT)
    parser.add_argument("--reference-audio", type=Path, default=DEFAULT_REFERENCE_AUDIO)
    parser.add_argument("--engine", action="append", default=["resemblyzer", "speechbrain_ecapa"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    print(json.dumps({
        "status": receipt["status"],
        "failed_gates": receipt["failed_gates"],
        "backend_candidates": receipt["speaker_backend_candidates"],
        "audio_snapshot_count": len(receipt["audio_snapshots"]),
    }, indent=2))
    if receipt["failed_gates"] and not args.allow_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
