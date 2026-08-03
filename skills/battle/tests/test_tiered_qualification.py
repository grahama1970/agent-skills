from __future__ import annotations

import json
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tiered_qualification.py"
SPEC = importlib.util.spec_from_file_location("battle_tiered_qualification", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
tq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tq)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_live_gate_accepts_current_same_run_non_fixture_receipts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tq, "current_source", lambda: {"commit": "c" * 40, "battle_tree": "t" * 40})
    arena = _write(
        tmp_path / "arena.json",
        {
            "status": "PASS",
            "mocked": False,
            "live": "brave_search_docker_arena_oracle_tau_harness",
            "run_id": "run-1",
            "source_commit": "c" * 40,
            "source_tree": "t" * 40,
        },
    )
    pixi = _write(
        tmp_path / "pixi.json",
        {
            "status": "PASS",
            "mocked": False,
            "live": True,
            "run_id": "run-1",
            "fixture_backed": False,
            "source_commit": "c" * 40,
            "source_tree": "t" * 40,
        },
    )
    out = tmp_path / "out.json"

    assert tq.validate_live(arena, pixi, out) == 0
    assert json.loads(out.read_text())["status"] == "PASS"


def test_live_gate_rejects_stale_source_and_fixture_backed_browser(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tq, "current_source", lambda: {"commit": "c" * 40, "battle_tree": "t" * 40})
    arena = _write(
        tmp_path / "arena.json",
        {
            "status": "PASS",
            "mocked": False,
            "live": "brave_search_docker_arena_oracle_tau_harness",
            "run_id": "run-1",
            "source_commit": "old",
            "source_tree": "old-tree",
        },
    )
    pixi = _write(
        tmp_path / "pixi.json",
        {
            "status": "PASS",
            "mocked": False,
            "live": True,
            "run_id": "run-1",
            "fixture_backed": True,
            "source_commit": "old",
            "source_tree": "old-tree",
        },
    )
    out = tmp_path / "out.json"

    assert tq.validate_live(arena, pixi, out) == 1
    receipt = json.loads(out.read_text())
    assert receipt["status"] == "FAIL"
    assert "browser_state_fixture_backed" in receipt["errors"]
    assert "arena_source_commit_stale_or_missing" in receipt["errors"]
    assert "pixi_source_tree_stale_or_missing" in receipt["errors"]


def test_same_run_live_gate_accepts_current_browser_proof(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tq, "current_source", lambda: {"commit": "c" * 40, "battle_tree": "t" * 40})
    same_run = _write(
        tmp_path / "same-run.json",
        {
            "schema": "battle.same_run_arena_pixi_qualification.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "run_id": "run-1",
            "source_commit": "c" * 40,
            "source_tree": "t" * 40,
            "browser": {
                "status": "PASS",
                "cdp_command": {"exit_code": 0},
                "cdp_meta": {
                    "read_json": "/proof/read.json",
                    "screenshot": "/proof/screenshot.png",
                },
            },
            "published_fixture": {
                "fixture_key": "battle-004-same-run-qualification",
                "fixture_sha256": "f" * 64,
            },
        },
    )
    out = tmp_path / "out.json"

    assert tq.validate_same_run(same_run, out) == 0
    receipt = json.loads(out.read_text())
    assert receipt["status"] == "PASS"
    assert receipt["inputs"]["run_id"] == "run-1"


def test_same_run_live_gate_rejects_stale_browser_and_fixture_backed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(tq, "current_source", lambda: {"commit": "c" * 40, "battle_tree": "t" * 40})
    same_run = _write(
        tmp_path / "same-run.json",
        {
            "schema": "battle.same_run_arena_pixi_qualification.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "run_id": "run-1",
            "source_commit": "old",
            "source_tree": "old-tree",
            "browser": {"status": "FAIL", "cdp_command": {"exit_code": 1}},
            "published_fixture": {
                "fixture_key": "battle-004-same-run-qualification",
                "fixture_sha256": "f" * 64,
                "fixture_backed": True,
            },
        },
    )
    out = tmp_path / "out.json"

    assert tq.validate_same_run(same_run, out) == 1
    receipt = json.loads(out.read_text())
    assert receipt["status"] == "FAIL"
    assert "same_run_source_commit_stale_or_missing" in receipt["errors"]
    assert "same_run_browser_status_not_pass" in receipt["errors"]
    assert "same_run_fixture_backed" in receipt["errors"]
