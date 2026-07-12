"""Durable runner state for audio-first Embry e2e campaigns.

The runner deliberately records orchestration state only.  It does not accept
transcripts, fixture responses, or browser microphone substitutions; counted
inputs must arrive through the existing voice event journal.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from embry_voice_control.event_journal import append_event, session_snapshot
from .case_executor import CaseExecutor, ManagedListenerProcess


STAGES = ("compiled", "source_qualified", "turns_journaled", "completed")
PRODUCER = "embry-voice-control.audio-e2e"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def default_state_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(manifest_path.suffix + ".state.json")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != "embry.audio_e2e_campaign_manifest.v1":
        raise ValueError("campaign_manifest_schema_invalid")
    execution = manifest.get("execution", {})
    if execution.get("typed_transcript_allowed") is not False:
        raise ValueError("typed_transcript_not_allowed")
    if execution.get("fixture_substitution_allowed") is not False:
        raise ValueError("fixture_substitution_not_allowed")
    if execution.get("browser_microphone_allowed") is not False:
        raise ValueError("browser_microphone_not_allowed")
    for case in manifest.get("cases", []):
        if case.get("source_mode") not in {"physical_live_horus", "recorded_physical_horus", "qualified_horus_clone"}:
            raise ValueError("source_mode_not_countable")


def initial_state(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "embry.audio_e2e_stage_state.v1",
        "campaign_id": manifest["campaign_id"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_value(manifest),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "running",
        "cases": {
            case["case_id"]: {
                "session_id": case["session_id"],
                "attempt_id": case["attempt_id"],
                "stage": "compiled",
                "completed_turns": [],
                "failure_bundle": None,
            }
            for case in manifest["cases"]
        },
    }


def load_or_create_state(manifest_path: Path, state_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(manifest_path)
    validate_manifest(manifest)
    if state_path.exists():
        state = read_json(state_path)
        if state.get("manifest_sha256") != sha256_value(manifest):
            raise ValueError("state_manifest_hash_mismatch")
        return manifest, state
    state = initial_state(manifest_path, manifest)
    write_json(state_path, state)
    return manifest, state


def _event(*, event_type: str, case: dict[str, Any], campaign_id: str, payload: dict[str, Any], causation_id: str = "root") -> dict[str, Any]:
    seed = {"type": event_type, "session_id": case["session_id"], "payload": payload}
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_type + "." + hashlib.sha256(canonical(seed)).hexdigest()[:16],
        "session_id": case["session_id"],
        "turn_id": case["turn_script"][0]["turn_id"] if case.get("turn_script") else case["case_id"],
        "type": event_type,
        "created_at": utc_now(),
        "causation_id": causation_id,
        "correlation_id": campaign_id,
        "producer": PRODUCER,
        "mocked": False,
        "live": True,
        "artifact_hashes": {k: v for k, v in payload.items() if k.endswith("sha256")},
        "receipt_hash": sha256_value(seed),
        "payload": payload,
    }


def _advance_case(journal_db: Path, campaign_id: str, case: dict[str, Any], case_state: dict[str, Any]) -> None:
    if case_state["stage"] == "compiled":
        event = append_event(journal_db, _event(event_type="audio_e2e.case_started", case=case, campaign_id=campaign_id, payload={"case_id": case["case_id"], "contract_sha256": case["contract_sha256"], "source_mode": case["source_mode"]}))
        case_state["stage"] = "source_qualified"
        case_state["last_event_id"] = event["event_id"]
    if case_state["stage"] == "source_qualified":
        # Do not synthesize listener transcripts.  We only inspect the event spine
        # for live listener.final_transcript events for the scripted turns.
        snapshot = session_snapshot(journal_db, case["session_id"])
        final_by_turn = {
            event["turn_id"]: event for event in snapshot["events"]
            if event["type"] == "listener.final_transcript" and event["live"] and not event["mocked"] and event["payload"].get("text")
        }
        required = [turn["turn_id"] for turn in case.get("turn_script", [])]
        case_state["completed_turns"] = [turn_id for turn_id in required if turn_id in final_by_turn]
        if len(case_state["completed_turns"]) == len(required):
            event = append_event(journal_db, _event(event_type="audio_e2e.case_completed", case=case, campaign_id=campaign_id, payload={"case_id": case["case_id"], "journal_sha256": snapshot["sha256"], "turn_count": len(required)}, causation_id=case_state.get("last_event_id", "root")))
            case_state["stage"] = "completed"
            case_state["last_event_id"] = event["event_id"]


def run_campaign(*, manifest_path: Path, state_path: Path | None, journal_db: Path, live_config: dict[str, Any] | None = None) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    manifest, state = load_or_create_state(manifest_path, state_path)
    by_id = {case["case_id"]: case for case in manifest["cases"]}
    pending = [(case_id, case_state) for case_id, case_state in state["cases"].items() if case_state.get("stage") != "completed"]
    if live_config and pending:
        if len(pending) != 1:
            raise ValueError("physical_live_runner_requires_one_case")
        case_id, case_state = pending[0]
        case = by_id[case_id]
        config = {**live_config, "journal_db": str(journal_db)}
        with ManagedListenerProcess(config, len(case["turn_script"])) as listener:
            case_state["listener_turns"] = CaseExecutor(config, listener).execute_listener_turns(manifest["campaign_id"], case)
            case_state["stage"] = "listener_complete"
            case_state["failed_stage"] = "speaker_verification"
        state["status"] = "blocked_after_live_listener"
    else:
        for case_id, case_state in pending:
            _advance_case(journal_db, manifest["campaign_id"], by_id[case_id], case_state)
    state["updated_at"] = utc_now()
    if not live_config:
        state["status"] = "completed" if all(case["stage"] == "completed" for case in state["cases"].values()) else "waiting_for_audio"
    write_json(state_path, state)
    return state


def status(*, manifest_path: Path, state_path: Path | None) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    if not state_path.exists():
        manifest = read_json(manifest_path)
        validate_manifest(manifest)
        return {"schema": "embry.audio_e2e_status.v1", "campaign_id": manifest["campaign_id"], "status": "not_started", "state_path": str(state_path)}
    state = read_json(state_path)
    return {"schema": "embry.audio_e2e_status.v1", "campaign_id": state["campaign_id"], "status": state["status"], "state_path": str(state_path), "cases": state["cases"]}


def bundle_failure(*, manifest_path: Path, state_path: Path | None, output: Path, reason: str) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    manifest = read_json(manifest_path)
    state = read_json(state_path) if state_path.exists() else initial_state(manifest_path, manifest)
    bundle = {
        "schema": "embry.audio_e2e_fix_forward_failure_bundle.v1",
        "created_at": utc_now(),
        "reason": reason,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_value(manifest),
        "state_path": str(state_path),
        "state_sha256": sha256_value(state),
        "campaign_id": manifest.get("campaign_id"),
        "failed_cases": {case_id: case for case_id, case in state.get("cases", {}).items() if case.get("stage") != "completed"},
        "fix_forward": "resume with the same manifest, state file, and live journal after correcting the blocked audio/source condition",
    }
    write_json(output, bundle)
    return bundle
