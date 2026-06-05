from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_status.py"


def load_module():
    spec = importlib.util.spec_from_file_location("update_status", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_writes_status_html_and_manifest(tmp_path: Path) -> None:
    module = load_module()
    status_dir = tmp_path / "status"
    module.main([
        "init",
        "--campaign",
        "demo",
        "--goal",
        "Make agent work visible",
        "--status-dir",
        str(status_dir),
    ])

    assert (status_dir / "status.json").exists()
    assert (status_dir / "events.jsonl").exists()
    assert (status_dir / "proof_manifest.json").exists()
    assert (status_dir / "STATUS.html").exists()

    status = json.loads((status_dir / "status.json").read_text())
    assert status["schema"] == "agent_status.v1"
    assert status["campaign_id"] == "demo"
    assert status["state"] == "not_started"


def test_gate_passed_preserves_not_proven_and_proof(tmp_path: Path) -> None:
    module = load_module()
    status_dir = tmp_path / "status"
    module.main([
        "init",
        "--campaign",
        "demo",
        "--goal",
        "Make agent work visible",
        "--status-dir",
        str(status_dir),
    ])
    module.main([
        "gate-passed",
        "--campaign",
        "demo",
        "--status-dir",
        str(status_dir),
        "--label",
        "A01-A18 hardened gate",
        "--verdict",
        "PASS_SPEC",
        "--proof",
        ".plan-iterate/demo/proof.json",
        "--next-action",
        "Start reviewer packet phase",
        "--not-proven",
        "Full harness completion",
    ])

    status = json.loads((status_dir / "status.json").read_text())
    assert status["state"] == "passed_scoped_gate"
    assert status["last_completed"]["verdict"] == "PASS_SPEC"
    assert status["proofs"][0]["path"] == ".plan-iterate/demo/proof.json"
    assert status["not_proven"] == ["Full harness completion"]


def test_done_requires_final_proof_and_empty_not_proven() -> None:
    module = load_module()
    status = {
        "schema": "agent_status.v1",
        "campaign_id": "demo",
        "updated_at": "2026-06-05T00:00:00Z",
        "state": "done",
        "goal": "Finish thing",
        "current_step": {"id": "", "label": "", "status": ""},
        "last_completed": {"label": "", "verdict": "", "proof_path": ""},
        "next_action": {"owner": "none", "label": "", "why": ""},
        "human_decision_required": False,
        "blockers": [],
        "not_proven": ["Something unproven"],
        "proofs": [],
        "do_not_do_next": [],
    }
    errors = module.validate_status(status)
    assert any("not_proven" in item for item in errors)
    assert any("proof_path" in item for item in errors)


def test_needs_human_records_decisions(tmp_path: Path) -> None:
    module = load_module()
    status_dir = tmp_path / "status"
    module.main([
        "init",
        "--campaign",
        "demo",
        "--goal",
        "Make agent work visible",
        "--status-dir",
        str(status_dir),
    ])
    module.main([
        "needs-human",
        "--campaign",
        "demo",
        "--status-dir",
        str(status_dir),
        "--question",
        "Pick next campaign",
        "--option",
        "A=Continue harness: reviewer packet fan-in",
        "--option",
        "B=Transport UI: start B1",
    ])

    status = json.loads((status_dir / "status.json").read_text())
    assert status["state"] == "needs_attention"
    assert status["human_decision_required"] is True
    assert status["human_decisions"][0]["id"] == "A"


def test_artifact_add_registers_visual_artifact(tmp_path: Path) -> None:
    module = load_module()
    status_dir = tmp_path / "status"
    proof = tmp_path / "proof.json"
    proof.write_text('{"ok": true}', encoding="utf-8")
    module.main([
        "init",
        "--campaign",
        "demo",
        "--goal",
        "Make agent work visible",
        "--status-dir",
        str(status_dir),
    ])
    module.main([
        "artifact-add",
        "--campaign",
        "demo",
        "--status-dir",
        str(status_dir),
        "--path",
        str(proof),
        "--kind",
        "proof",
        "--label",
        "Gate proof",
        "--caption",
        "Positive-control fixture",
    ])
    status = json.loads((status_dir / "status.json").read_text())
    assert len(status["artifacts"]) == 1
    assert status["artifacts"][0]["kind"] == "proof"
