from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tiered_qualification.py"
SPEC = importlib.util.spec_from_file_location("battle_tiered_qualification_rungs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
tq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tq)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fast_sanity(source: dict[str, str]) -> dict:
    return {
        "schema": "battle.tiered_fast_sanity_gate.v1",
        "status": "PASS",
        "mocked": False,
        "live": False,
        "source": source,
        "command_result": {"exit_code": 0},
    }


def _same_run_live(source: dict[str, str]) -> dict:
    return {
        "schema": "battle.same_run_arena_pixi_qualification.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "run_id": "run-1",
        "source_commit": source["commit"],
        "source_tree": source["battle_tree"],
        "browser": {"status": "PASS", "cdp_command": {"exit_code": 0}},
        "published_fixture": {"fixture_key": "battle-proof-rung-separation", "fixture_sha256": "f" * 64},
    }


def test_live_gate_rejects_fast_sanity_as_arena_or_pixi_receipt(tmp_path: Path, monkeypatch) -> None:
    source = {"commit": "c" * 40, "battle_tree": "t" * 40}
    monkeypatch.setattr(tq, "current_source", lambda: source)
    fast = _write(tmp_path / "fast.json", _fast_sanity(source))
    out = tmp_path / "live-out.json"

    assert tq.validate_live(fast, fast, out) == 1
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["schema"] == "battle.tiered_live_qualification_gate.v1"
    assert "arena_receipt_fast_sanity_substitution_rejected" in receipt["errors"]
    assert "pixi_receipt_fast_sanity_substitution_rejected" in receipt["errors"]
    assert receipt["status"] == "FAIL"


def test_same_run_live_gate_rejects_fast_sanity_receipt(tmp_path: Path, monkeypatch) -> None:
    source = {"commit": "c" * 40, "battle_tree": "t" * 40}
    monkeypatch.setattr(tq, "current_source", lambda: source)
    fast = _write(tmp_path / "fast.json", _fast_sanity(source))
    out = tmp_path / "same-run-out.json"

    assert tq.validate_same_run(fast, out) == 1
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert "same_run_receipt_fast_sanity_substitution_rejected" in receipt["errors"]


def test_same_run_live_gate_accepts_live_qualification_receipt(tmp_path: Path, monkeypatch) -> None:
    source = {"commit": "c" * 40, "battle_tree": "t" * 40}
    monkeypatch.setattr(tq, "current_source", lambda: source)
    same_run = _write(tmp_path / "same-run.json", _same_run_live(source))
    out = tmp_path / "same-run-out.json"

    assert tq.validate_same_run(same_run, out) == 0
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["inputs"]["run_id"] == "run-1"
