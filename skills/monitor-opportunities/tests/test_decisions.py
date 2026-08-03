from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_decision_idempotency_and_replay(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    args = [
        "decision",
        "--run",
        str(run_dir),
        "--item",
        "opp:a",
        "--action",
        "KEEP",
        "--idempotency-key",
        "same-key",
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    ledger_rows = (run_dir / "decision-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger_rows) == 1
    replay = runner.invoke(app, ["replay", "--run", str(run_dir)])
    assert replay.exit_code == 0, replay.output
    projection = json.loads((run_dir / "decision-projection.json").read_text(encoding="utf-8"))
    assert projection["items"]["opp:a"]["last_action"] == "KEEP"
    assert projection["external_effects"] is False
