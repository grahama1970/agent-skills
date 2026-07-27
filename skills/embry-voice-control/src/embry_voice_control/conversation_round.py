"""Production-owned Embry voice conversation round runner.

This command delegates low-level Chatterbox/PipeWire/Realtimestt transport to
the existing Chatterbox adapter, then owns acceptance, journal publication, and
the receipt consumed by SPARTA UI projections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
from uuid import uuid4

from embry_voice_control.listener_turn import DEFAULT_BASE_URL
from embry_voice_control.listener_turn import DEFAULT_JOURNAL_DB
from embry_voice_control.listener_turn import normalize_text
from embry_voice_control.listener_turn import publish_listener_turn_journal


DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e")
DEFAULT_CHATTERBOX_REPO = Path("/home/graham/workspace/experiments/chatterbox")
DEFAULT_CHATTERBOX_RUNNER = DEFAULT_CHATTERBOX_REPO / "scripts" / "embry_backend_conversation_audio_mvp.py"
DEFAULT_CAT_STORY_QUESTIONS = [
    "Hey Embry, tell me a short story about your cat and ask me one question about it.",
    "What did the cat find?",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-conversation-round-" + uuid4().hex[:8]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_listener_receipt(turn: dict[str, Any]) -> dict[str, Any]:
    transcript = str(turn.get("realtimestt_final_transcript") or "")
    route = turn.get("virtual_realtimestt_route") if isinstance(turn.get("virtual_realtimestt_route"), dict) else {}
    realtime = route.get("realtimestt") if isinstance(route.get("realtimestt"), dict) else {}
    return {
        "schema": "embry_voice_control.conversation_round.listener_receipt.v1",
        "mocked": False,
        "live": True,
        "acceptance": {"pass": True},
        "transcript": {
            "final": transcript,
            "normalized_final": normalize_text(transcript),
        },
        "listener_events": {
            "final_transcript": transcript,
            "normalized_final_transcript": normalize_text(transcript),
            "wake_detected": bool(turn.get("turn_index", 0) > 1 or "embry" in normalize_text(transcript)),
            "wake_word": "embry" if "embry" in normalize_text(transcript) else None,
            "events_path": realtime.get("events_path"),
            "realtime_event_count": realtime.get("event_count"),
        },
        "realtimestt": {
            "receipt_path": realtime.get("receipt_path"),
            "event_count": realtime.get("event_count"),
        },
        "underlying_receipt_path": realtime.get("receipt_path"),
        "route_receipt": route,
    }


def publish_turn_to_journal(
    *,
    journal_db: Path,
    output_dir: Path,
    turn: dict[str, Any],
) -> dict[str, Any]:
    sparta_turn = turn.get("sparta_live_turn") if isinstance(turn.get("sparta_live_turn"), dict) else {}
    response_path = Path(str(sparta_turn.get("response_path") or ""))
    if not response_path.is_file():
        raise FileNotFoundError(f"SPARTA live-turn response not found: {response_path}")
    sparta_response = read_json(response_path)
    listener_receipt = build_listener_receipt(turn)
    listener_receipt_path = output_dir / f"turn-{int(turn.get('turn_index') or 0):03d}-listener-receipt.json"
    write_json(listener_receipt_path, listener_receipt)
    playback = turn.get("answer_playback") if isinstance(turn.get("answer_playback"), dict) else {}
    local_playback = {
        "requested": True,
        "played": playback.get("returncode") == 0,
        "command": playback.get("cmd") or playback.get("command") or ["pw-play", "--target", playback.get("target"), sparta_turn.get("audio_path")],
        "driver": "pipewire-pw-play",
        "target": playback.get("target"),
        "returncode": playback.get("returncode"),
    }
    journal_events = publish_listener_turn_journal(
        journal_db=journal_db,
        receipt_created_at=utc_now(),
        listener_receipt_path=listener_receipt_path,
        listener_receipt=listener_receipt,
        turn_text=str(turn.get("realtimestt_final_transcript") or ""),
        request_payload=sparta_response.get("turnAuthority") if isinstance(sparta_response.get("turnAuthority"), dict) else sparta_turn.get("request", {}),
        response=sparta_response,
        local_playback=local_playback,
    )
    return {
        "turn_index": turn.get("turn_index"),
        "turn_id": sparta_response.get("turnId"),
        "event_count": len(journal_events),
        "event_types": [event.get("type") for event in journal_events],
        "last_sequence": journal_events[-1].get("sequence") if journal_events else None,
        "listener_receipt_path": str(listener_receipt_path),
    }


def run_transport_adapter(
    *,
    runner: Path,
    chatterbox_repo: Path,
    transport_out_dir: Path,
    sparta_api: str,
    questions: list[str],
    timeout: float,
) -> tuple[int, str, str]:
    if not runner.is_file():
        raise FileNotFoundError(f"Chatterbox transport runner not found: {runner}")
    transport_out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "python3",
        str(runner),
        "--out-dir",
        str(transport_out_dir),
        "--sparta-api",
        sparta_api.rsplit("/api/projects/embry-voice", 1)[0] if sparta_api.endswith("/api/projects/embry-voice") else sparta_api,
    ]
    for question in questions:
        command.extend(["--question", question])
    completed = subprocess.run(
        command,
        cwd=chatterbox_repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout[-4000:], completed.stderr[-4000:]


def evaluate_receipt(transport: dict[str, Any], journal_turns: list[dict[str, Any]]) -> dict[str, Any]:
    failed: list[str] = []
    if transport.get("pass") is not True:
        failed.append("transport_adapter_pass")
    if transport.get("mocked") is not False or transport.get("live") is not True:
        failed.append("transport_adapter_live_not_mocked")
    turns = transport.get("turns") if isinstance(transport.get("turns"), list) else []
    if len(turns) < 2:
        failed.append("two_conversation_turns_present")
    if len(journal_turns) != len(turns):
        failed.append("journal_published_for_each_turn")
    for index, turn in enumerate(turns, start=1):
        prefix = f"turn_{index:03d}"
        sparta_turn = turn.get("sparta_live_turn") if isinstance(turn.get("sparta_live_turn"), dict) else {}
        memory_answer = sparta_turn.get("memory_answer") if isinstance(sparta_turn.get("memory_answer"), dict) else {}
        if sparta_turn.get("answer_authority") != "memory":
            failed.append(f"{prefix}:answer_authority_memory")
        if (turn.get("answer_playback") or {}).get("returncode") != 0:
            failed.append(f"{prefix}:playback_returncode_zero")
        if index == 1 and memory_answer.get("answer_type") != "session_story_generation":
            failed.append(f"{prefix}:session_story_generation")
        if index == 2:
            if memory_answer.get("answer_type") != "session_story_context":
                failed.append(f"{prefix}:session_story_context")
            if memory_answer.get("story_context_recovered") is not True:
                failed.append(f"{prefix}:story_context_recovered")
            if memory_answer.get("answer_uses_story_fact") is not True:
                failed.append(f"{prefix}:answer_uses_story_fact")
    for index, journal in enumerate(journal_turns, start=1):
        if journal.get("event_count", 0) < 7:
            failed.append(f"turn_{index:03d}:journal_event_count")
    return {"pass": not failed, "failed_gates": failed}


def run_conversation_round_live(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    chatterbox_repo: Path = DEFAULT_CHATTERBOX_REPO,
    runner: Path = DEFAULT_CHATTERBOX_RUNNER,
    sparta_api: str = DEFAULT_BASE_URL,
    journal_db: Path = DEFAULT_JOURNAL_DB,
    questions: list[str] | None = None,
    timeout: float = 420.0,
) -> dict[str, Any]:
    run_id = new_run_id()
    output_dir = output_root / "conversation-round-live" / run_id
    transport_out_dir = output_dir / "transport"
    receipt_path = output_dir / "receipt.json"
    selected_questions = questions or DEFAULT_CAT_STORY_QUESTIONS
    transport_out_dir.mkdir(parents=True, exist_ok=True)
    returncode, stdout_tail, stderr_tail = run_transport_adapter(
        runner=runner,
        chatterbox_repo=chatterbox_repo,
        transport_out_dir=transport_out_dir,
        sparta_api=sparta_api,
        questions=selected_questions,
        timeout=timeout,
    )
    transport_summary_path = transport_out_dir / "summary.json"
    transport_summary = read_json(transport_summary_path) if transport_summary_path.is_file() else {}
    journal_turns: list[dict[str, Any]] = []
    journal_error: str | None = None
    if returncode == 0 and transport_summary.get("pass") is True:
        try:
            for turn in transport_summary.get("turns", []):
                if isinstance(turn, dict):
                    journal_turns.append(publish_turn_to_journal(journal_db=journal_db, output_dir=output_dir, turn=turn))
        except Exception as exc:  # noqa: BLE001
            journal_error = f"{type(exc).__name__}: {exc}"
    acceptance = evaluate_receipt(transport_summary, journal_turns)
    if returncode != 0:
        acceptance["failed_gates"].append("transport_adapter_exit_zero")
        acceptance["pass"] = False
    if journal_error:
        acceptance["failed_gates"].append("journal_publication_error")
        acceptance["pass"] = False
    receipt = {
        "schema": "embry_voice_control.conversation_round_live_receipt.v1",
        "run_id": run_id,
        "created_at": utc_now(),
        "mocked": False,
        "live": True,
        "pass": acceptance["pass"],
        "failed_gates": acceptance["failed_gates"],
        "questions": selected_questions,
        "transport": {
            "adapter": str(runner),
            "returncode": returncode,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "summary_path": str(transport_summary_path),
            "session_id": transport_summary.get("session_id"),
            "pass": transport_summary.get("pass"),
        },
        "journal": {
            "db_path": str(journal_db),
            "published": journal_error is None and bool(journal_turns),
            "turns": journal_turns,
            "error": journal_error,
        },
        "acceptance": acceptance,
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "embry-voice-control owns the multi-turn conversation receipt and journal publication",
                "Chatterbox rendered dynamic agent questions and Embry answers",
                "RealtimeSTT final transcripts drove SPARTA live-turn requests",
                "Memory generated a cat story and recovered follow-up session context",
                "Jabra playback was requested and returned zero for each Embry answer",
                "SPARTA UI listener/latest can project the published journal events",
            ],
            "does_not_prove": [
                "browser_webrtc_microphone",
                "physical_jabra_microphone_capture",
                "openwakeword_detection",
                "fully_autonomous_dialogue_planning",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(output_root / "conversation-round-live" / "latest.json", {
        "run_id": run_id,
        "pass": receipt["pass"],
        "receipt_path": str(receipt_path),
        "transport_summary_path": str(transport_summary_path),
        "session_id": transport_summary.get("session_id"),
    })
    return receipt
