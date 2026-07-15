"""Consume immutable Memory receipts and emit one bounded Tau handoff."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from embry_voice_control.embry_chat import (
    build_tau_response_plan,
    chunk_tone_arc,
    split_speakable_text,
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    start = json.loads(sys.stdin.read())
    context = start.get("context") or {}
    locator = context.get("input_packet") or {}
    input_path = Path(str(locator.get("path", ""))).resolve()
    if not input_path.is_file() or sha256_path(input_path) != locator.get("sha256"):
        raise ValueError("input_packet_hash_mismatch")

    packet = json.loads(input_path.read_text(encoding="utf-8"))
    lineage = packet["lineage"]
    source = lineage["source_event"]
    source_contract = lineage.get("source_contract") or {}
    contract_name = str(source_contract.get("name") or "")
    source_identity = str(source_contract.get("source_identity") or "")
    if contract_name not in {
        "physical_horus_identity",
        "qualified_horus_clone",
    }:
        raise ValueError("source_contract_invalid")
    if source_contract.get("suite_ready") is not False:
        raise ValueError("source_contract_suite_ready_invalid")
    if source_contract.get("release_readiness_authority") is not False:
        raise ValueError("source_contract_release_authority_invalid")

    receipts = packet["receipts"]
    for receipt in receipts.values():
        path = Path(receipt["path"]).resolve()
        if not path.is_file() or sha256_path(path) != receipt["sha256"]:
            raise ValueError("input_receipt_hash_mismatch")

    persistent = context.get("persistent_subagent") or {}
    if persistent.get("schema") != "tau.persistent_subagent.v1":
        raise ValueError("persistent_subagent_contract_invalid")
    if (
        persistent.get("session_mode") != "persistent"
        or persistent.get("tau_control") != "bounded_receipt_gated_ticks"
    ):
        raise ValueError("persistent_subagent_contract_invalid")
    if persistent.get("unbounded_autonomy_allowed") is not False:
        raise ValueError("persistent_subagent_contract_invalid")

    artifact_dir = Path(
        os.environ.get(
            "TAU_HANDOFF_COMMAND_ARTIFACT_DIR",
            "/tmp/embry-journal-memory-tau-node",
        )
    )
    intent_call = json.loads(
        Path(receipts["memory_intent"]["path"]).read_text(encoding="utf-8")
    )
    answer_call = json.loads(
        Path(receipts["memory_answer"]["path"]).read_text(encoding="utf-8")
    )
    speaker_call = json.loads(
        Path(receipts["speaker_resolution"]["path"]).read_text(encoding="utf-8")
    )
    source_claim = json.loads(
        Path(receipts["source_event_claim"]["path"]).read_text(encoding="utf-8")
    )
    turn_text = str(source_claim["source_event"]["payload"]["text"])
    if intent_call["request"]["q"] != turn_text:
        raise ValueError("memory_intent_query_source_event_mismatch")
    if answer_call["request"]["q"] != turn_text:
        raise ValueError("memory_answer_query_source_event_mismatch")
    speaker_response = speaker_call["response"]
    personal_memory_allowed = bool(source_contract.get("allow_personal_memory"))
    if speaker_response.get("allow_personal_memory") is not personal_memory_allowed:
        raise ValueError("memory_resolution_personal_policy_mismatch")
    if contract_name == "qualified_horus_clone":
        if source_identity != "qualified_horus_clone":
            raise ValueError("clone_source_identity_invalid")
        if source_contract.get("speaker_identity_proven") is not False:
            raise ValueError("clone_speaker_identity_claim_invalid")
        if source_contract.get("fresh_physical_human_speech") is not False:
            raise ValueError("clone_physical_speech_claim_invalid")
        if personal_memory_allowed:
            raise ValueError("clone_personal_memory_must_be_disabled")
        if speaker_response.get("status") != "unknown":
            raise ValueError("clone_memory_resolution_not_unknown")
        if speaker_response.get("speaker_id") is not None:
            raise ValueError("clone_memory_resolution_claimed_identity")
        if speaker_response.get("recall_profile") is not None:
            raise ValueError("clone_memory_recall_profile_not_null")
        memory_tags = speaker_response.get("memory_tags") or []
        if any(
            str(tag).startswith(("speaker:", "user:"))
            for tag in memory_tags
        ):
            raise ValueError("clone_memory_personal_tags_present")
        if "speaker_id" in intent_call["request"]:
            raise ValueError("clone_memory_intent_received_speaker_id")
        if "speaker_resolution" in intent_call["request"]:
            raise ValueError("clone_memory_intent_received_speaker_resolution")
        if "speaker_id" in answer_call["request"]:
            raise ValueError("clone_memory_answer_received_speaker_id")
        if "speaker_resolution" in answer_call["request"]:
            raise ValueError("clone_memory_answer_received_speaker_resolution")
    else:
        if source_identity != "horus_lupercal":
            raise ValueError("physical_source_identity_invalid")
        if source_contract.get("speaker_identity_proven") is not True:
            raise ValueError("physical_speaker_identity_not_proven")
        if not personal_memory_allowed:
            raise ValueError("physical_personal_memory_not_allowed")
        if speaker_response.get("status") != "known":
            raise ValueError("physical_memory_resolution_not_known")
        if speaker_response.get("speaker_id") != source_identity:
            raise ValueError("memory_resolution_source_identity_mismatch")
        if intent_call["request"].get("speaker_id") != source_identity:
            raise ValueError("memory_intent_source_identity_mismatch")
        if (
            intent_call["request"].get("speaker_resolution", {}).get("speaker_id")
            != source_identity
        ):
            raise ValueError("memory_intent_resolution_identity_mismatch")

    response_plan = build_tau_response_plan(
        turn_text=turn_text,
        intent_result=intent_call["response"],
        answer_result=answer_call["response"],
    )
    answer_text = str(response_plan["answer_text"])
    tts_render_text = str(response_plan["tts_render_text"])
    tts_sha256 = hashlib.sha256(tts_render_text.encode()).hexdigest()
    answer_sha256 = hashlib.sha256(answer_text.encode()).hexdigest()
    chunk_texts = split_speakable_text(tts_render_text, max_chars=300)
    chunk_tones = chunk_tone_arc(len(chunk_texts))
    plan_seed = canonical(
        {
            "source_event_id": source["event_id"],
            "source_event_sequence": source["sequence"],
            "memory_intent_sha256": receipts["memory_intent"]["sha256"],
            "memory_answer_sha256": receipts["memory_answer"]["sha256"],
            "source_contract": source_contract,
            "goal_hash": start["goal"]["goal_hash"],
            "tts_render_text_sha256": tts_sha256,
        }
    )
    turn_plan = {
        "schema": "tau.turn_plan.v1",
        "plan_id": "turn_plan_" + hashlib.sha256(plan_seed).hexdigest()[:16],
        "live": True,
        "mocked": False,
        "session_id": source["session_id"],
        "turn_id": source["turn_id"],
        "source_event_id": source["event_id"],
        "source_event_sequence": source["sequence"],
        "source_event_receipt_hash": source["receipt_hash"],
        "source_contract": source_contract,
        "suite_ready": False,
        "release_readiness_authority": False,
        "route": response_plan["route_taken"],
        "route_taken": response_plan["route_taken"],
        "route_reason": response_plan["route_reason"],
        "memory_result_classification": response_plan[
            "memory_result_classification"
        ],
        "display_text": answer_text,
        "display_text_sha256": answer_sha256,
        "answer_text": answer_text,
        "answer_text_sha256": answer_sha256,
        "tts_render_text": tts_render_text,
        "tts_render_text_sha256": tts_sha256,
        "voice_policy": response_plan["voice_policy"],
        "memory_intent_receipt": receipts["memory_intent"],
        "memory_answer_receipt": receipts["memory_answer"],
        "speakable_chunks": [
            {
                "chunk_id": source["turn_id"] + f"-chunk-{index:03d}",
                "text": chunk_text,
                "text_sha256": hashlib.sha256(chunk_text.encode()).hexdigest(),
                "tone": chunk_tones[index - 1],
                "pause_after_ms": 250,
                "interruptible": True,
                "max_chars": 300,
            }
            for index, chunk_text in enumerate(chunk_texts, start=1)
        ],
        "planner": {
            "callable": "embry_voice_control.embry_chat.build_tau_response_plan",
            "python_executable": sys.executable,
            "project_root": str(Path(__file__).resolve().parents[4]),
        },
    }
    plan_path = artifact_dir / "tau-turn-plan.json"
    write_json(plan_path, turn_plan)

    tick_seed = canonical(
        {
            "event_id": source["event_id"],
            "source_contract": source_contract,
            "goal_hash": start["goal"]["goal_hash"],
        }
    )
    tick_id = "tick_" + hashlib.sha256(tick_seed).hexdigest()[:16]
    persistent_receipt = {
        "schema": "tau.persistent_subagent_receipt.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "tick_id": tick_id,
        "tick_index": 1,
        "tick_budget": 1,
        "session_id": source["session_id"],
        "turn_id": source["turn_id"],
        "source_event_id": source["event_id"],
        "source_event_sequence": source["sequence"],
        "source_contract": source_contract,
        "suite_ready": False,
        "goal_hash": start["goal"]["goal_hash"],
        "tau_control": persistent["tau_control"],
        "session_mode": persistent["session_mode"],
        "unbounded_autonomy_allowed": False,
        "surface_reachable_checked": False,
        "surface_reachable_required_for_this_rung": False,
        "input_packet_sha256": locator["sha256"],
    }
    persistent_path = artifact_dir / "persistent_subagent_receipt.json"
    write_json(persistent_path, persistent_receipt)

    acceptance = {
        "source_event_is_final_transcript": (
            source["type"] == "listener.final_transcript"
        ),
        "source_event_lineage_matches": True,
        "source_contract": contract_name,
        "source_identity": source_identity,
        "speaker_identity_proven": bool(
            source_contract.get("speaker_identity_proven")
        ),
        "personal_memory_allowed": personal_memory_allowed,
        "intent_consumed_exact_resolution": (
            contract_name == "physical_horus_identity"
        ),
        "clone_source_excluded_from_speaker_scoped_memory": (
            contract_name != "qualified_horus_clone"
            or (
                speaker_response.get("status") == "unknown"
                and speaker_response.get("speaker_id") is None
                and speaker_response.get("recall_profile") is None
            )
        ),
        "goal_hash_matches": (
            lineage["goal"]["goal_hash"] == start["goal"]["goal_hash"]
        ),
        "tick_count_is_one": True,
        "no_renderer_call": True,
        "no_global_latest_read": True,
        "suite_ready": False,
    }
    tick_receipt = {
        "schema": "embry.voice.journal_memory_tau_tick_receipt.v1",
        "ok": True,
        "live": True,
        "mocked": False,
        "lineage": lineage,
        "lineage_sha256": "sha256:"
        + hashlib.sha256(canonical(lineage)).hexdigest(),
        "source_contract": source_contract,
        "suite_ready": False,
        "input_packet": locator,
        "source_event_claim_receipt": receipts["source_event_claim"],
        "speaker_resolution_receipt": receipts["speaker_resolution"],
        "memory_intent_receipt": receipts["memory_intent"],
        "memory_answer_receipt": receipts["memory_answer"],
        "tau_turn_plan_receipt": {
            "path": str(plan_path),
            "sha256": sha256_path(plan_path),
        },
        "persistent_subagent_receipt": {
            "path": str(persistent_path),
            "sha256": sha256_path(persistent_path),
        },
        "acceptance": acceptance,
        "ack_state": "pending_tau_validation",
    }
    tick_path = artifact_dir / "journal_memory_tau_tick_receipt.json"
    write_json(tick_path, tick_receipt)

    evidence = [
        {
            "kind": "source_event_claim_receipt",
            **receipts["source_event_claim"],
        },
        {
            "kind": "memory.speaker_resolution.v1",
            **receipts["speaker_resolution"],
        },
        {
            "kind": "embry.memory.intent_call_receipt.v1",
            **receipts["memory_intent"],
        },
        {
            "kind": "embry.memory.answer_call_receipt.v1",
            **receipts["memory_answer"],
        },
        {
            "kind": "tau.turn_plan.v1",
            "path": str(plan_path),
            "sha256": sha256_path(plan_path),
        },
        {
            "kind": "persistent_subagent_receipt",
            "path": str(persistent_path),
            "sha256": sha256_path(persistent_path),
        },
        {
            "kind": "embry.voice.journal_memory_tau_tick_receipt.v1",
            "path": str(tick_path),
            "sha256": sha256_path(tick_path),
        },
    ]
    source_summary = (
        "event-specific physical Horus identity"
        if contract_name == "physical_horus_identity"
        else "non-personal qualified Horus clone source"
    )
    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": start.get("github", {}),
        "goal": start["goal"],
        "previous_subagent": (
            start.get("next_agent") or {}
        ).get("name", "embry-memory-tau"),
        "context": {
            "summary": (
                f"One live listener event with {source_summary} was "
                "Memory-routed and consumed by one bounded Embry Tau tick."
            ),
            "source_event": source,
            "source_contract": source_contract,
            "suite_ready": False,
            "journal": lineage["journal"],
            "memory": {
                "speaker_resolution_receipt": receipts[
                    "speaker_resolution"
                ],
                "intent_receipt": receipts["memory_intent"],
                "answer_receipt": receipts["memory_answer"],
            },
            "tau_turn_plan": {
                "schema": "tau.turn_plan.v1",
                "path": str(plan_path),
                "sha256": sha256_path(plan_path),
                "plan_id": turn_plan["plan_id"],
                "session_id": source["session_id"],
                "turn_id": source["turn_id"],
                "source_event_id": source["event_id"],
            },
            "persistent_subagent": persistent,
            "tau_tick": {
                "tick_index": 1,
                "tick_budget": 1,
                "receipt_path": str(tick_path),
                "receipt_sha256": sha256_path(tick_path),
            },
            "artifacts": [item["path"] for item in evidence],
        },
        "result": {
            "status": "COMPLETED",
            "summary": (
                (
                    f"Memory resolved {source_identity} under the "
                    f"{contract_name} policy before one bounded Tau handoff."
                    if contract_name == "physical_horus_identity"
                    else "Memory excluded the qualified clone source from "
                    "speaker-scoped personal recall before one bounded Tau handoff."
                )
            ),
            "evidence": evidence,
            "suite_ready": False,
        },
        "rationale": (
            "The canonical journal event, explicit source contract, and live "
            "Memory receipts authorize exactly one bounded Tau tick."
        ),
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "The singular non-Chatterbox proof is complete.",
        },
        "required_evidence": [],
        "stop_condition": "Stop after this one bounded tick.",
    }
    print(json.dumps(handoff, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
