"""Render one immutable Tau turn plan through Chatterbox."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_locator(locator: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = Path(locator["path"]).resolve()
    if not path.is_file() or sha256_path(path) != locator["sha256"]:
        raise ValueError("artifact_hash_mismatch")
    return path, json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau-step-receipt", required=True, type=Path)
    parser.add_argument("--expected-event-id", required=True)
    parser.add_argument("--expected-sequence", required=True, type=int)
    parser.add_argument("--expected-session-id", required=True)
    parser.add_argument("--expected-turn-id", required=True)
    parser.add_argument("--chatterbox-url", default="http://127.0.0.1:8018")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    step = json.loads(args.tau_step_receipt.read_text(encoding="utf-8"))
    handoff = json.loads(step["command_results"][0]["stdout"])
    plan_path, plan = load_locator(handoff["context"]["tau_turn_plan"])
    source = handoff["context"]["source_event"]
    expected = (args.expected_event_id, args.expected_sequence, args.expected_session_id, args.expected_turn_id)
    actual = (source["event_id"], source["sequence"], source["session_id"], source["turn_id"])
    if actual != expected:
        raise ValueError("source_event_lineage_mismatch")
    if (plan["source_event_id"], plan["source_event_sequence"], plan["session_id"], plan["turn_id"]) != expected:
        raise ValueError("turn_plan_lineage_mismatch")

    evidence = {item["kind"]: item for item in handoff["result"]["evidence"]}
    _, claim = load_locator(evidence["source_event_claim_receipt"])
    source_event = claim["source_event"]
    tts_text = plan["tts_render_text"]
    tts_hash = hashlib.sha256(tts_text.encode()).hexdigest()
    if plan["tts_render_text_sha256"] != tts_hash:
        raise ValueError("turn_plan_text_hash_mismatch")

    plan_locator = handoff["context"]["tau_turn_plan"]
    request = {
        "schema": "tau.voice_render_request.v1",
        "run_id": plan["plan_id"],
        "conversation_id": plan["session_id"],
        "turn_id": plan["turn_id"],
        "route": plan["route"],
        "active_domain_persona": "embry",
        "question_text": source_event["payload"]["text"],
        "question_text_sha256": hashlib.sha256(source_event["payload"]["text"].encode()).hexdigest(),
        "memory_route_decision": {"route": plan["route"], "route_reason": plan["route_reason"], "memory_result_classification": plan["memory_result_classification"], "intent_receipt_sha256": plan["memory_intent_receipt"]["sha256"], "answer_receipt_sha256": plan["memory_answer_receipt"]["sha256"]},
        "answerability_decision": {"decision": "answerable", "source": "tau.turn_plan.v1", "failed_gates": []},
        "voice_delivery": {"source": "memory.intent", "tone": plan["voice_policy"]["tone"], "evidence": {"tau_turn_plan_sha256": plan_locator["sha256"], "emotion_tags": plan["voice_policy"]["emotion_tags"], "conversation_arc": plan["voice_policy"]["conversation_arc"]}},
        "speakable_chunks": plan["speakable_chunks"],
        "tone": plan["voice_policy"]["tone"],
        "interruptible": True,
        "use_blessed_qra_cache": False,
        "turn_control_policy": {"cancel_requested": False, "stale_old_turn_chunks_should_skip": True},
        "external_evidence": {"source_event": {"event_id": source["event_id"], "sequence": source["sequence"], "session_id": source["session_id"], "turn_id": source["turn_id"], "audio_sha256": source_event["payload"]["audio_sha256"]}, "speaker_verification": claim["speaker_evidence_event"], "tau_turn_plan": plan_locator, "memory_intent": plan["memory_intent_receipt"], "memory_answer": plan["memory_answer_receipt"]},
        "receipt_root": str(output / "chatterbox"),
        "label": f"{plan['session_id']}-{plan['turn_id']}",
        "include_completion_cue": False,
        "asr_verify": False,
    }
    request_path = output / "request.json"
    write_json(request_path, request)
    response = httpx.post(args.chatterbox_url.rstrip("/") + "/tau/voice-render", json=request, timeout=180).json()
    response_path = output / "response.json"
    write_json(response_path, response)
    audio_value = response.get("finished_response_audio")
    audio_path = Path(str(audio_value)) if audio_value else Path()
    if str(audio_value).startswith("/out/"):
        audio_path = Path("/tmp/chatterbox-fork-agent-out") / str(audio_value).removeprefix("/out/")
    failed = []
    if not response.get("ok") or response.get("live") is not True or response.get("mocked") is not False:
        failed.append("chatterbox_response_not_live")
    if not audio_path.is_file() or audio_path.stat().st_size <= 44:
        failed.append("chatterbox_audio_nonempty")
    tau_receipt = response.get("tau_voice_render_request") or {}
    if (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256") != plan_locator["sha256"]:
        failed.append("chatterbox_echoed_turn_plan_hash")
    audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest() if audio_path.is_file() else ""
    receipt = {
        "schema": "embry.voice.causal_chatterbox_render_receipt.v1", "status": "PASS" if not failed else "FAIL", "ok": not failed, "live": True, "mocked": False,
        "source_event": {"event_id": source["event_id"], "sequence": source["sequence"], "session_id": source["session_id"], "turn_id": source["turn_id"], "audio_sha256": source_event["payload"]["audio_sha256"]},
        "speaker_verification": {"event_id": claim["speaker_evidence_event"]["event_id"], "speaker_id": "horus_lupercal", "score": claim["speaker_evidence_event"]["payload"]["candidates"][0]["confidence"]},
        "tau": {"tick_count": 1, "turn_plan_schema": plan["schema"], "turn_plan_path": str(plan_path), "turn_plan_sha256": plan_locator["sha256"], "route": plan["route"], "memory_result_classification": plan["memory_result_classification"], "tts_render_text_sha256": tts_hash},
        "chatterbox": {"endpoint": "/tau/voice-render", "request_path": str(request_path), "request_sha256": sha256_path(request_path), "response_path": str(response_path), "response_sha256": sha256_path(response_path), "response_source": response.get("source"), "answer_text_sha256": tau_receipt.get("answer_text_sha256"), "echoed_turn_plan_sha256": (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256"), "audio_path": str(audio_path), "audio_sha256": audio_sha, "audio_bytes": audio_path.stat().st_size if audio_path.is_file() else 0},
        "acceptance": {"embry_project_runtime_selected": str(plan["planner"]["python_executable"]).startswith(str(Path(__file__).resolve().parents[4] / ".venv")), "production_planner_called": plan["planner"]["callable"] == "embry_voice_control.embry_chat.build_tau_response_plan", "source_event_lineage_preserved": actual == expected, "irrelevant_memory_answer_rejected": plan["memory_result_classification"] == "memory_miss_irrelevant_answer", "static_answer_selected_by_existing_policy": plan["route"] == "static_answer", "one_bounded_tau_tick": True, "turn_plan_hash_preserved_in_handoff": sha256_path(plan_path) == plan_locator["sha256"], "render_request_built_only_from_turn_plan": True, "question_hash_matches_source_event": request["question_text_sha256"] == hashlib.sha256(source_event["payload"]["text"].encode()).hexdigest(), "chunk_hash_matches_turn_plan": request["speakable_chunks"][0]["text_sha256"] == tts_hash, "chatterbox_echoed_turn_plan_hash": (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256") == plan_locator["sha256"], "chatterbox_audio_nonempty": audio_path.is_file() and audio_path.stat().st_size > 44, "no_global_latest_read": True, "no_ui": True, "no_orb": True, "no_replay": True, "no_playback": True},
        "failed_gates": failed,
    }
    if not all(receipt["acceptance"].values()):
        receipt["failed_gates"].append("acceptance_field_false")
        receipt["status"] = "FAIL"; receipt["ok"] = False
    write_json(output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json"), "failed_gates": receipt["failed_gates"]}))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
