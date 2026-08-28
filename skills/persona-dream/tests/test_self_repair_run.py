from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUN = SKILL_ROOT / "run.sh"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_self_repair_run_advances_after_passing_receipt(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    receipt = run_root / "step1.json"
    manifest = tmp_path / "manifest.json"
    _write_json(
        manifest,
        {
            "schema": "persona_dream.self_repair_manifest.v1",
            "run_id": "test-pass",
            "goal_project": "persona-dream",
            "steps": [
                {
                    "step_id": "fixture_pass",
                    "command": [
                        sys.executable,
                        "-c",
                        f"import json, pathlib; p=pathlib.Path({str(receipt)!r}); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({{'status':'PASS_FIXTURE_STEP','live':False,'mocked':True}}))",
                    ],
                    "receipt": str(receipt),
                    "pass_statuses": ["PASS_FIXTURE_STEP"],
                    "target": "skills/persona-dream/tests/test_self_repair_run.py",
                    "layer": "test",
                }
            ],
        },
    )
    out = run_root / "self_repair_run.json"
    proc = subprocess.run(
        [str(RUN), "self-repair-run", "--manifest", str(manifest), "--run-root", str(run_root), "--output", str(out), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "PASS_SELF_REPAIR_RUN"
    assert data["goal_preflight"]["status"] == "PASS_IMMUTABLE_GOAL_PREFLIGHT"
    assert data["goal_preflight"]["project"] == "persona-dream"
    assert data["steps"][0]["status"] == "PASS"
    assert not (run_root / "replay_ledger.jsonl").exists()


def test_self_repair_run_records_failure_and_blocks_next_step(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    failed_receipt = run_root / "failed.json"
    marker = run_root / "should_not_run.txt"
    manifest = tmp_path / "manifest.json"
    _write_json(
        manifest,
        {
            "schema": "persona_dream.self_repair_manifest.v1",
            "run_id": "test-fail",
            "goal_project": "persona-dream",
            "steps": [
                {
                    "step_id": "fixture_fail",
                    "command": [
                        sys.executable,
                        "-c",
                        f"import json, pathlib; p=pathlib.Path({str(failed_receipt)!r}); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({{'status':'BLOCKED_FIXTURE_STEP','live':False,'mocked':True,'reason':'forced failure'}}))",
                    ],
                    "receipt": str(failed_receipt),
                    "pass_statuses": ["PASS_FIXTURE_STEP"],
                    "target": "skills/persona-dream/tests/test_self_repair_run.py",
                    "layer": "test",
                    "checkpoint_id": "fixture-checkpoint",
                    "goal_context": "synthetic dreams add measurable value over direct memory and structured reflection",
                },
                {
                    "step_id": "must_not_advance",
                    "command": [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('advanced')"],
                    "target": "skills/persona-dream/tests/test_self_repair_run.py",
                    "layer": "test",
                },
            ],
        },
    )
    out = run_root / "self_repair_run.json"
    proc = subprocess.run(
        [
            str(RUN),
            "self-repair-run",
            "--manifest",
            str(manifest),
            "--run-root",
            str(run_root),
            "--output",
            str(out),
            "--skip-memory",
            "--skip-github",
            "--no-ticket",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "BLOCKED_REPAIR_RECORDED"
    assert data["goal_preflight"]["status"] == "PASS_IMMUTABLE_GOAL_PREFLIGHT"
    assert data["stop_reason"] == "step_failed_repair_branch_started"
    assert data["steps"][0]["status"] == "FAILED"
    assert len(data["steps"]) == 1
    assert not marker.exists()

    ledger = run_root / "replay_ledger.jsonl"
    assert ledger.exists()
    event = json.loads(ledger.read_text().splitlines()[0])
    assert event["step_id"] == "fixture_fail"
    assert event["goal_alignment"]["status"] == "PASS_COMPARED_TO_IMMUTABLE_GOAL"
    assert event["goal_alignment"]["project"] == "persona-dream"
    assert event["checkpoint_id"] == "fixture-checkpoint"
    assert event["blocking"] is True
