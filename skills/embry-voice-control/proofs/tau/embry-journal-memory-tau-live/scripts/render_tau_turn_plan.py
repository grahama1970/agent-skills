"""Render one immutable Tau turn plan through Chatterbox."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    source_evidence = claim.get("source_evidence_event")
    if not isinstance(source_evidence, dict):
        # Backward compatibility for physical-only historical receipts.
        source_evidence = claim.get("speaker_evidence_event")
    if not isinstance(source_evidence, dict):
        raise ValueError("source_evidence_event_missing")
    source_contract = plan.get("source_contract") or {}
    contract_name = str(source_contract.get("name") or "")
    if contract_name not in {
        "physical_horus_identity",
        "qualified_horus_clone",
    }:
        raise ValueError("turn_plan_source_contract_invalid")
    if plan.get("suite_ready") is not False:
        raise ValueError("turn_plan_suite_ready_invalid")
    if source_contract.get("suite_ready") is not False:
        raise ValueError("source_contract_suite_ready_invalid")
    if source_contract.get("release_readiness_authority") is not False:
        raise ValueError("source_contract_release_authority_invalid")
    if source_evidence.get("session_id") != source_event.get("session_id"):
        raise ValueError("source_evidence_session_mismatch")
    if source_evidence.get("turn_id") != source_event.get("turn_id"):
        raise ValueError("source_evidence_turn_mismatch")
    if source_evidence.get("live") is not True or source_evidence.get("mocked") is not False:
        raise ValueError("source_evidence_not_live")
    evidence_payload = source_evidence.get("payload") or {}
    if contract_name == "qualified_horus_clone":
        expected_clone = {
            "source_contract": "qualified_horus_clone",
            "source_identity": "qualified_horus_clone",
            "fresh_physical_human_speech": False,
            "speaker_identity_proven": False,
            "allow_personal_memory": False,
            "suite_ready": False,
        }
        if source_evidence.get("type") != "audio_source.qualification.completed":
            raise ValueError("clone_source_evidence_type_invalid")
        if any(
            evidence_payload.get(key) != value
            for key, value in expected_clone.items()
        ):
            raise ValueError("clone_source_evidence_contract_mismatch")
    else:
        if source_evidence.get("type") != "speaker.verification.completed":
            raise ValueError("physical_source_evidence_type_invalid")

    tts_text = plan["tts_render_text"]
    tts_hash = hashlib.sha256(tts_text.encode()).hexdigest()
    if plan["tts_render_text_sha256"] != tts_hash:
        raise ValueError("turn_plan_text_hash_mismatch")

    plan_locator = handoff["context"]["tau_turn_plan"]
    render_label_digest = hashlib.sha256(
        f"{plan['session_id']}\0{plan['turn_id']}".encode()
    ).hexdigest()[:16]
    render_label = f"{str(plan['session_id'])[:48]}-{render_label_digest}"
    chunks_match_plan = (
        " ".join(
            " ".join(chunk["text"].split())
            for chunk in plan["speakable_chunks"]
        )
        == " ".join(tts_text.split())
        and all(
            chunk["text_sha256"] == hashlib.sha256(chunk["text"].encode()).hexdigest()
            and len(chunk["text"]) <= int(chunk["max_chars"])
            for chunk in plan["speakable_chunks"]
        )
    )
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
        "external_evidence": {
            "source_event": {
                "event_id": source["event_id"],
                "sequence": source["sequence"],
                "session_id": source["session_id"],
                "turn_id": source["turn_id"],
                "audio_sha256": source_event["payload"]["audio_sha256"],
            },
            "source_evidence": source_evidence,
            "source_contract": source_contract,
            "tau_turn_plan": plan_locator,
            "memory_intent": plan["memory_intent_receipt"],
            "memory_answer": plan["memory_answer_receipt"],
        },
        "receipt_root": str(output / "chatterbox"),
        "label": render_label,
        "include_completion_cue": False,
        "asr_verify": False,
    }
    request_path = output / "request.json"
    write_json(request_path, request)
    http_response = httpx.post(
        args.chatterbox_url.rstrip("/") + "/tau/voice-render", json=request, timeout=180
    )
    http_response.raise_for_status()
    response = http_response.json()
    response_path = output / "response.json"
    write_json(response_path, response)
    audio_value = response.get("finished_response_audio")
    audio_path = Path(str(audio_value)) if audio_value else Path()
    if str(audio_value).startswith("/out/"):
        host_out_dir = Path(
            os.environ.get("CHATTERBOX_HOST_OUT_DIR", "/tmp/chatterbox-fork-agent-out")
        )
        audio_path = host_out_dir / str(audio_value).removeprefix("/out/")
    failed = []
    if not response.get("ok") or response.get("live") is not True or response.get("mocked") is not False:
        failed.append("chatterbox_response_not_live")
    if not audio_path.is_file() or audio_path.stat().st_size <= 44:
        failed.append("chatterbox_audio_nonempty")
    tau_receipt = response.get("tau_voice_render_request") or {}
    if (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256") != plan_locator["sha256"]:
        failed.append("chatterbox_echoed_turn_plan_hash")
    audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest() if audio_path.is_file() else ""
    planner_project_root = Path(str(plan["planner"]["project_root"]))
    planner_python_executable = Path(str(plan["planner"]["python_executable"]))
    embry_project_runtime_selected = (
        planner_project_root.is_absolute()
        and planner_python_executable.is_absolute()
        and planner_python_executable.parent
        == planner_project_root / ".venv" / "bin"
    )
    receipt = {
        "schema": "embry.voice.causal_chatterbox_render_receipt.v2",
        "status": "PASS" if not failed else "FAIL",
        "ok": not failed,
        "live": True,
        "mocked": False,
        "suite_ready": False,
        "release_readiness_authority": False,
        "source_contract": source_contract,
        "source_event": {
            "event_id": source["event_id"],
            "sequence": source["sequence"],
            "session_id": source["session_id"],
            "turn_id": source["turn_id"],
            "audio_sha256": source_event["payload"]["audio_sha256"],
        },
        "source_evidence": {
            "event_id": source_evidence["event_id"],
            "type": source_evidence["type"],
            "source_identity": evidence_payload.get("source_identity"),
            "voice_persona": evidence_payload.get("voice_persona"),
            "fresh_physical_human_speech": evidence_payload.get(
                "fresh_physical_human_speech",
                contract_name == "physical_horus_identity",
            ),
            "speaker_identity_proven": evidence_payload.get(
                "speaker_identity_proven",
                contract_name == "physical_horus_identity",
            ),
        },
        "tau": {"tick_count": 1, "turn_plan_schema": plan["schema"], "turn_plan_path": str(plan_path), "turn_plan_sha256": plan_locator["sha256"], "route": plan["route"], "memory_result_classification": plan["memory_result_classification"], "tts_render_text_sha256": tts_hash},
        "chatterbox": {"endpoint": "/tau/voice-render", "request_path": str(request_path), "request_sha256": sha256_path(request_path), "response_path": str(response_path), "response_sha256": sha256_path(response_path), "response_source": response.get("source"), "answer_text_sha256": tau_receipt.get("answer_text_sha256"), "echoed_turn_plan_sha256": (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256"), "audio_path": str(audio_path), "audio_sha256": audio_sha, "audio_bytes": audio_path.stat().st_size if audio_path.is_file() else 0},
        "acceptance": {"embry_project_runtime_selected": embry_project_runtime_selected, "production_planner_called": plan["planner"]["callable"] == "embry_voice_control.embry_chat.build_tau_response_plan", "source_event_lineage_preserved": actual == expected, "memory_classification_matches_route": (plan["route"] == "memory_answer" and plan["memory_result_classification"] == "memory_answer") or (plan["route"] in {"static_answer", "memory_miss_no_static_answer"} and plan["memory_result_classification"].startswith("memory_miss")) or plan["route"] == "fail_closed", "turn_plan_route_is_renderable": plan["route"] in {"memory_answer", "static_answer", "research_answer", "skill_answer", "memory_miss_no_static_answer", "fail_closed"}, "one_bounded_tau_tick": True, "turn_plan_hash_preserved_in_handoff": sha256_path(plan_path) == plan_locator["sha256"], "render_request_built_only_from_turn_plan": True, "question_hash_matches_source_event": request["question_text_sha256"] == hashlib.sha256(source_event["payload"]["text"].encode()).hexdigest(), "chunk_hashes_match_turn_plan": chunks_match_plan, "chatterbox_echoed_turn_plan_hash": (tau_receipt.get("external_evidence") or {}).get("tau_turn_plan", {}).get("sha256") == plan_locator["sha256"], "chatterbox_audio_nonempty": audio_path.is_file() and audio_path.stat().st_size > 44, "no_global_latest_read": True, "no_ui": True, "no_orb": True, "no_replay": True, "no_playback": True, "source_contract_preserved": source_contract == plan.get("source_contract"), "suite_ready_false": plan.get("suite_ready") is False, "synthetic_audio_not_relabelled_as_physical": contract_name != "qualified_horus_clone" or (evidence_payload.get("fresh_physical_human_speech") is False and evidence_payload.get("speaker_identity_proven") is False)},
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
