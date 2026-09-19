#!/usr/bin/env python3
"""Deterministic replay validates a real Jev-v2-shaped closed-set decision."""
import json
import subprocess
import tempfile
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[3]
OPS = ROOT / "skills/ops-excalidraw/run.sh"
CATALOG = ROOT / "skills/best-practices-diagram-design/fixtures/template-catalog.json"
BOARD = ROOT / "skills/ops-excalidraw/fixtures/interview-board.excalidraw"
ASSET_ID = "decision-flow-control"
path.insert(0, str(ROOT / "skills/best-practices-diagram-design/scripts"))
from template_selection import eligible_entries, jev_hash, load_catalog, selection_state


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(OPS), *args], cwd=ROOT, capture_output=True, text=True, timeout=300)


with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    packet = temp / "packet.json"
    packet.write_text(json.dumps({"intent": "choose decision flow", "view": "decision-flow", "data": {"outcomes": ["yes", "no"]}, "steps": ["ask", "decide"]}))
    questions = temp / "questions.json"
    questions.write_text(json.dumps({"template_choice": {"type": "choice", "instructions": "Choose only an eligible template or ABSTAIN.", "criteria": {ASSET_ID: "Existing local decision-flow asset.", "ABSTAIN": "No eligible asset fits."}}}))
    missing = run("render-board", str(BOARD), "--output", str(temp / "out.svg"), "--governed")
    assert missing.returncode != 0 and "requires --receipt" in missing.stderr, missing.stderr
    old_choice = run("select-template", "--requirements", str(packet), "--catalog", str(CATALOG), "--jev-decision", str(temp / "invented.json"), "--output", str(temp / "bad.json"))
    assert old_choice.returncode != 0 and "No such option" in old_choice.stderr, old_choice.stderr

    data = json.loads(packet.read_text()); catalog = load_catalog(CATALOG)
    from template_selection import RequirementsPacket
    state = selection_state(RequirementsPacket.model_validate(data), eligible_entries(RequirementsPacket.model_validate(data), catalog, ROOT))
    q = json.loads(questions.read_text())
    raw = {"schema_version": "jev.decision.v2", "request_id": "replay-check", "status": "accepted", "reason": "required_questions_accepted", "request_hash": jev_hash({"state": state, "model": "jev-latest", "questions": q}), "state_hash": jev_hash(state), "questions_hash": jev_hash(q), "policy_hash": "test", "requested_model": "jev-latest", "resolved_model": "jev-1.13.0", "answers": {"template_choice": {"type": "choice", "choice": ASSET_ID, "confidence": 1.0}}, "usage": {}, "elapsed_ms": 0, "validation_errors": [], "retry_after_ms": None}
    raw_path = temp / "jev-v2.json"; raw_path.write_text(json.dumps(raw))
    receipt = temp / "receipt.json"
    replay = run("replay-template-selection", "--requirements", str(packet), "--catalog", str(CATALOG), "--questions", str(questions), "--jev-receipt", str(raw_path), "--output", str(receipt))
    assert replay.returncode == 0 and '"mode": "replay"' in replay.stdout, replay.stderr
    forged = json.loads(raw_path.read_text()); forged["answers"]["template_choice"]["choice"] = "invented"
    raw_path.write_text(json.dumps(forged))
    rejected = run("replay-template-selection", "--requirements", str(packet), "--catalog", str(CATALOG), "--questions", str(questions), "--jev-receipt", str(raw_path), "--output", str(temp / "bad.json"))
    assert rejected.returncode != 0 and "eligible template ID" in rejected.stderr, rejected.stderr
    governed = run("render-board", str(BOARD), "--output", str(temp / "out.svg"), "--governed", "--receipt", str(receipt), "--requirements", str(packet), "--catalog", str(CATALOG))
    assert governed.returncode == 0, governed.stderr
print("GOVERNED_TEMPLATE_SELECTION_OK")
