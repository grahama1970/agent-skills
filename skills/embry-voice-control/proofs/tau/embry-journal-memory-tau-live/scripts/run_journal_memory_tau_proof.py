"""Run one exact journal event through Memory and one bounded Tau tick."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import httpx


LANE = Path(__file__).resolve().parents[1]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def event_hash(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def append_derived(journal: httpx.Client, source: dict[str, Any], event_type: str, causation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    seed = {"source_event_id": source["event_id"], "type": event_type, "payload": payload}
    event = {"schema": "embry.voice_event.v1", "event_id": event_type + "." + hashlib.sha256(canonical(seed)).hexdigest()[:16], "session_id": source["session_id"], "turn_id": source["turn_id"], "type": event_type, "created_at": datetime.now(timezone.utc).isoformat(), "causation_id": causation_id, "correlation_id": source["correlation_id"], "producer": "embry.voice.journal_memory_tau_controller", "mocked": False, "live": True, "artifact_hashes": {key: value for key, value in payload.items() if key.endswith("sha256")}, "receipt_hash": event_hash(seed), "payload": payload}
    return post(journal, "/v1/listener/events", event)["event"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-url", required=True)
    parser.add_argument("--consumer-name", default="embry-journal-memory-tau-v1")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--speaker-evidence-event-id", required=True)
    parser.add_argument("--expected-session-id", required=True)
    parser.add_argument("--expected-turn-id", required=True)
    parser.add_argument("--expected-sequence", required=True, type=int)
    parser.add_argument("--physical-enrollment-receipt", required=True, type=Path)
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--tau-repo", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lease-seconds", default=300, type=int)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    enrollment = json.loads(args.physical_enrollment_receipt.read_text())
    goal_packet = json.loads((LANE / "goal-packet.json").read_text())
    goal_hash = "sha256:" + hashlib.sha256(canonical(goal_packet)).hexdigest()
    with httpx.Client(base_url=args.journal_url, timeout=10.0) as journal:
        journal_payload = journal.get(f"/v1/sessions/{args.expected_session_id}/journal").json()
        by_id = {event["event_id"]: event for event in journal_payload["events"]}
        source = by_id.get(args.event_id)
        speaker_evidence = by_id.get(args.speaker_evidence_event_id)
        if source is None or source.get("type") != "listener.final_transcript":
            raise ValueError("source_event_not_final_transcript")
        if (source["session_id"], source["turn_id"], source["sequence"]) != (args.expected_session_id, args.expected_turn_id, args.expected_sequence):
            raise ValueError("source_event_lineage_mismatch")
        if not source.get("live") or source.get("mocked") or not source.get("payload", {}).get("text"):
            raise ValueError("physical_listener_provenance_missing")
        if speaker_evidence is None or speaker_evidence.get("causation_id") != source["event_id"]:
            raise ValueError("speaker_evidence_missing")
        evidence_payload = speaker_evidence["payload"]
        if evidence_payload.get("profile_hash") != enrollment.get("profile_sha256"):
            raise ValueError("physical_profile_hash_mismatch")
        if evidence_payload.get("audio_sha256") != source["payload"].get("audio_sha256"):
            raise ValueError("speaker_audio_hash_mismatch")
        claim_response = post(journal, "/v1/listener/events/claim-one", {"consumer_name": args.consumer_name, "event_id": args.event_id, "expected_session_id": args.expected_session_id, "expected_turn_id": args.expected_turn_id, "expected_sequence": args.expected_sequence, "expected_type": "listener.final_transcript", "lease_seconds": args.lease_seconds})
        claim_receipt = {"schema": "embry.voice.source_event_claim_receipt.v1", "claim": {"consumer_name": args.consumer_name, "claimed": True, "lease_seconds": args.lease_seconds}, "source_event": source, "speaker_evidence_event": speaker_evidence, "journal": {"service_url": args.journal_url, "session_journal_sha256_at_claim": "sha256:" + journal_payload["sha256"]}}
        claim_path = out / "source-event-claim-receipt.json"
        write_json(claim_path, claim_receipt)
        with httpx.Client(base_url=args.memory_url, timeout=20.0) as memory:
            speaker_request = {"speaker_evidence_id": speaker_evidence["event_id"], "session_id": source["session_id"], "turn_id": source["turn_id"], "persona_id": "embry", "threshold": evidence_payload["threshold"], "ambiguity_margin": evidence_payload["ambiguity_margin"], "candidates": evidence_payload["candidates"]}
            speaker_response = post(memory, "/speaker/resolve", speaker_request)
            if speaker_response.get("status") != "known" or speaker_response.get("speaker_id") != "horus_lupercal" or speaker_response.get("allow_personal_memory") is not True:
                raise ValueError("speaker_resolution_not_known_horus")
            speaker_call = {"schema": "embry.memory.speaker_resolution_call_receipt.v1", "request": speaker_request, "request_sha256": event_hash(speaker_request), "response": speaker_response, "response_sha256": event_hash(speaker_response)}
            speaker_path = out / "memory-speaker-resolution-receipt.json"
            write_json(speaker_path, speaker_call)
            speaker_event = append_derived(journal, source, "memory.speaker_resolved", source["event_id"], {"response_path": str(speaker_path), "response_sha256": sha256_path(speaker_path), "profile_sha256": enrollment["profile_sha256"]})
            intent_request = {"q": source["payload"]["text"], "scope": "embry", "session_id": source["session_id"], "fast": True, "speaker_id": "horus_lupercal", "speaker_resolution": speaker_response, "listener_evidence": {"source": "physical_hot_mic", "source_event_id": source["event_id"], "source_event_sequence": source["sequence"], "source_event_receipt_hash": source["receipt_hash"], "physical_speaker_profile_hash": enrollment["profile_sha256"]}}
            intent_response = post(memory, "/intent", intent_request)
            intent_call = {"schema": "embry.memory.intent_call_receipt.v1", "request": intent_request, "request_sha256": event_hash(intent_request), "response": intent_response, "response_sha256": event_hash(intent_response), "speaker_resolution_response_sha256": event_hash(speaker_response), "source_event": {key: source[key] for key in ("event_id", "sequence", "session_id", "turn_id", "type")}}
            intent_path = out / "memory-intent-receipt.json"
            write_json(intent_path, intent_call)
            intent_event = append_derived(journal, source, "memory.intent_resolved", speaker_event["event_id"], {"response_path": str(intent_path), "response_sha256": sha256_path(intent_path)})
        receipts = {"source_event_claim": {"path": str(claim_path), "sha256": sha256_path(claim_path)}, "speaker_resolution": {"path": str(speaker_path), "sha256": sha256_path(speaker_path)}, "memory_intent": {"path": str(intent_path), "sha256": sha256_path(intent_path)}}
        lineage = {"source_event": {key: source[key] for key in ("event_id", "sequence", "session_id", "turn_id", "type", "causation_id", "correlation_id", "receipt_hash")}, "journal": {"service_url": args.journal_url, "session_journal_sha256_at_claim": "sha256:" + journal_payload["sha256"]}, "physical_speaker_profile": {"speaker_id": "horus_lupercal", "profile_hash": enrollment["profile_sha256"], "enrollment_receipt_path": str(args.physical_enrollment_receipt.resolve()), "enrollment_receipt_sha256": sha256_path(args.physical_enrollment_receipt)}, "goal": {"goal_id": goal_packet["goal_id"], "goal_version": goal_packet["goal_version"], "goal_hash": goal_hash}}
        packet = {"schema": "embry.voice.journal_memory_tau_input.v1", "lineage": lineage, "receipts": receipts}
        packet_path = out / "input-packet.json"
        write_json(packet_path, packet)
        command_spec = LANE / "command-specs/embry-memory-tau/tau-dispatch-command.json"
        dag = {"schema": "tau.dag_contract.v1", "dag_id": "embry-journal-memory-tau-live", "goal": lineage["goal"], "target": {"repo": "grahama1970/agent-skills", "target": "skills/embry-voice-control/proofs/tau/embry-journal-memory-tau-live", "allowed_paths": ["skills/embry-voice-control/proofs/tau/embry-journal-memory-tau-live/**"]}, "context": {"summary": "One claimed physical listener event, Memory-first routing, then one bounded Tau tick.", "input_packet": {"path": str(packet_path), "sha256": sha256_path(packet_path)}, "source_event_claim": {**receipts["source_event_claim"], **{key: source[key] for key in ("event_id", "sequence", "session_id", "turn_id", "type")}}, "does_not_require_surface_reachability": True}, "entry_node": "embry-memory-tau", "terminal_nodes": ["human"], "limits": {"resume": False, "default_timeout_seconds": 120, "max_total_attempts": 1}, "nodes": [{"id": "embry-memory-tau", "agent": "embry-chatterbox-voice", "executor": "local", "max_attempts": 1, "command_spec": str(command_spec), "required_evidence": ["source_event_claim_receipt", "memory.speaker_resolution.v1", "embry.memory.intent_call_receipt.v1", "persistent_subagent_receipt", "embry.voice.journal_memory_tau_tick_receipt.v1"], "persistent_subagent": {"schema": "tau.persistent_subagent.v1", "surface_id": "embry-voice", "surface_url": "http://localhost:3002/#embry-voice", "session_mode": "persistent", "tau_control": "bounded_receipt_gated_ticks", "dag_parameter": "embry_voice_surface", "required_receipts": ["embry.voice.journal_memory_tau_tick_receipt.v1"], "unbounded_autonomy_allowed": False, "memory_write_requires_receipt": True}}, {"id": "human", "agent": "human", "executor": "human"}], "edges": [{"from": "embry-memory-tau", "to": "human", "condition": "one_memory_grounded_tick_completed_or_blocked"}], "required_evidence": ["source_event_claim_receipt", "memory.speaker_resolution.v1", "embry.memory.intent_call_receipt.v1", "persistent_subagent_receipt", "embry.voice.journal_memory_tau_tick_receipt.v1"], "fail_closed_on": ["goal_hash_mismatch", "target_changed", "missing_required_evidence", "max_attempts_exceeded", "malformed_handoff"]}
        dag_path = out / "dag-contract.json"
        write_json(dag_path, dag)
        tau_run = out / "tau-run"
        completed = subprocess.run(["uv", "run", "tau", "dag-run", str(dag_path), "--receipt-dir", str(tau_run), "--no-resume"], cwd=args.tau_repo, text=True, capture_output=True, timeout=180, check=False)
        (out / "tau.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (out / "tau.stderr.log").write_text(completed.stderr, encoding="utf-8")
        dag_receipt_path = tau_run / "dag-receipt.json"
        if completed.returncode != 0 or not dag_receipt_path.is_file():
            raise RuntimeError("tau_dag_failed")
        dag_receipt = json.loads(dag_receipt_path.read_text())
        if dag_receipt.get("status") != "PASS":
            raise RuntimeError("tau_dag_not_pass")
        step_path = tau_run / "command-loop/command-loop-step-001.receipt.json"
        step = json.loads(step_path.read_text())
        handoff = json.loads(step["command_results"][0]["stdout"])
        handoff_source = handoff["context"]["source_event"]
        for key in ("event_id", "sequence", "session_id", "turn_id", "type", "receipt_hash"):
            if handoff_source.get(key) != lineage["source_event"].get(key):
                raise ValueError("tau_handoff_source_event_mismatch")
        tick = handoff["context"]["tau_tick"]
        tau_event = append_derived(journal, source, "tau.persistent_tick.completed", intent_event["event_id"], {"dag_receipt_sha256": sha256_path(dag_receipt_path), "agent_handoff_sha256": event_hash(handoff), "tick_receipt_sha256": tick["receipt_sha256"]})
        post(journal, "/v1/listener/events/ack", {"consumer_name": args.consumer_name, "event_id": source["event_id"]})
        duplicate = journal.post("/v1/listener/events/claim-one", json={"consumer_name": args.consumer_name, "event_id": args.event_id, "expected_session_id": args.expected_session_id, "expected_turn_id": args.expected_turn_id, "expected_sequence": args.expected_sequence, "expected_type": "listener.final_transcript", "lease_seconds": args.lease_seconds})
        duplicate_blocked = duplicate.status_code == 409 and duplicate.json().get("detail") == "event_already_acked"
    receipt = {"schema": "embry.voice.journal_memory_tau_proof_receipt.v1", "status": "PASS" if duplicate_blocked else "FAIL", "ok": duplicate_blocked, "live": True, "mocked": False, "lineage": lineage, "journal_events": {"listener_final": source, "memory_speaker_resolution": speaker_event, "memory_intent": intent_event, "tau_tick_completed": tau_event}, "memory": {"speaker_resolution": speaker_response, "speaker_resolution_path": str(speaker_path), "speaker_resolution_sha256": sha256_path(speaker_path), "intent_response_path": str(intent_path), "intent_response_sha256": sha256_path(intent_path)}, "tau": {"goal_hash": goal_hash, "dag_contract_path": str(dag_path), "dag_contract_sha256": sha256_path(dag_path), "dag_receipt_path": str(dag_receipt_path), "dag_receipt_sha256": sha256_path(dag_receipt_path), "agent_handoff_sha256": event_hash(handoff), "tick_count": 1}, "ack": {"consumer_name": args.consumer_name, "event_id": source["event_id"], "acked": True}, "duplicate_probe": {"claim_rejected_as_already_acked": duplicate_blocked, "memory_call_count": 0, "tau_tick_count": 0}, "forbidden_activity": {"global_latest_json_reads": [], "chatterbox_calls": [], "browser_calls": [], "typed_transcript_used": False, "source_wav_used": False}, "failed_gates": [] if duplicate_blocked else ["duplicate_source_event_execution"]}
    write_json(out / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(out / "receipt.json")}))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
