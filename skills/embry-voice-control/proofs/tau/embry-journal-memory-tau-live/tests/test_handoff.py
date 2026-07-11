from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


LANE = Path(__file__).resolve().parents[1]
SCRIPT = LANE / "scripts" / "run_embry_journal_memory_tau_handoff.py"


def _write_json(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _start_handoff(tmp_path: Path) -> dict:
    receipt_locators = {}
    for name in ("source_event_claim", "speaker_resolution", "memory_intent", "memory_answer"):
        path = tmp_path / f"{name}.json"
        response = {}
        if name == "memory_intent":
            response = {"action": "QUERY"}
        elif name == "memory_answer":
            response = {"can_answer": False, "answer_type": "insufficient_memory_evidence"}
        digest = _write_json(path, {"schema": name, "ok": True, "request": {"q": "Hey Embry, what is the capital of France?"}, "response": response})
        receipt_locators[name] = {"path": str(path), "sha256": digest}

    packet = {
        "schema": "embry.voice.journal_memory_tau_input.v1",
        "lineage": {
            "source_event": {
                "event_id": "evt-final",
                "sequence": 7,
                "session_id": "session-1",
                "turn_id": "turn-1",
                "type": "listener.final_transcript",
                "receipt_hash": "sha256:event",
            },
            "journal": {"session_journal_sha256_at_claim": "sha256:journal"},
            "goal": {"goal_id": "goal", "goal_version": 1, "goal_hash": "sha256:goal"},
        },
        "turn_text": "What is the capital of France?",
        "receipts": receipt_locators,
    }
    claim_path = Path(receipt_locators["source_event_claim"]["path"])
    receipt_locators["source_event_claim"]["sha256"] = _write_json(
        claim_path,
        {"source_event": {"payload": {"text": "Hey Embry, what is the capital of France?"}}},
    )
    packet_path = tmp_path / "input-packet.json"
    packet_sha256 = _write_json(packet_path, packet)
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {"repo": "grahama1970/agent-skills", "target": "proof"},
        "goal": packet["lineage"]["goal"],
        "context": {
            "input_packet": {"path": str(packet_path), "sha256": packet_sha256},
            "persistent_subagent": {
                "schema": "tau.persistent_subagent.v1",
                "session_mode": "persistent",
                "tau_control": "bounded_receipt_gated_ticks",
                "unbounded_autonomy_allowed": False,
            },
        },
        "next_agent": {"name": "embry-memory-tau"},
    }


def _run(tmp_path: Path, handoff: dict) -> subprocess.CompletedProcess[str]:
    command_spec = json.loads((LANE / "command-specs/embry-memory-tau/tau-dispatch-command.json").read_text())
    return subprocess.run(
        command_spec["command"],
        input=json.dumps(handoff),
        text=True,
        capture_output=True,
        env={**os.environ, "TAU_HANDOFF_COMMAND_ARTIFACT_DIR": str(tmp_path / "artifacts"), "VIRTUAL_ENV": "/home/graham/workspace/experiments/tau/.venv"},
        check=False,
    )


def test_emits_one_bounded_persistent_handoff(tmp_path: Path) -> None:
    result = _run(tmp_path, _start_handoff(tmp_path))
    assert result.returncode == 0, result.stderr
    handoff = json.loads(result.stdout)
    assert handoff["schema"] == "tau.agent_handoff.v1"
    assert handoff["result"]["status"] == "COMPLETED"
    assert handoff["context"]["source_event"]["event_id"] == "evt-final"
    persistent = json.loads((tmp_path / "artifacts" / "persistent_subagent_receipt.json").read_text())
    plan = json.loads((tmp_path / "artifacts" / "tau-turn-plan.json").read_text())
    assert persistent["tick_index"] == 1
    assert persistent["tick_budget"] == 1
    assert persistent["unbounded_autonomy_allowed"] is False
    assert plan["display_text_sha256"] == hashlib.sha256(plan["display_text"].encode()).hexdigest()
    assert plan["tts_render_text_sha256"] == hashlib.sha256(plan["tts_render_text"].encode()).hexdigest()


def test_rejects_tampered_input_packet(tmp_path: Path) -> None:
    handoff = _start_handoff(tmp_path)
    Path(handoff["context"]["input_packet"]["path"]).write_text("{}\n", encoding="utf-8")
    result = _run(tmp_path, handoff)
    assert result.returncode != 0
    assert "input_packet_hash_mismatch" in result.stderr


def test_rejects_unbounded_persistent_contract(tmp_path: Path) -> None:
    handoff = _start_handoff(tmp_path)
    handoff["context"]["persistent_subagent"]["unbounded_autonomy_allowed"] = True
    result = _run(tmp_path, handoff)
    assert result.returncode != 0
    assert "persistent_subagent_contract_invalid" in result.stderr
