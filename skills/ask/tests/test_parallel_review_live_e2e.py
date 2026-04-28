"""Opt-in live /scillm E2E checks for /ask parallel-review."""

import json
import os

import pytest
from typer.testing import CliRunner

import ask.ask as ask_module
from ask.run_state import read_status


@pytest.mark.skipif(
    os.environ.get("ASK_LIVE_SCILLM_E2E") != "1",
    reason="set ASK_LIVE_SCILLM_E2E=1 to run the real /scillm parallel-review smoke test",
)
def test_live_parallel_review_scillm_composition(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n", encoding="utf-8")

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "this",
            "tiny",
            "target",
            "for",
            "correctness,",
            "tests,",
            "and",
            "maintainability",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--parallel-reviewers",
            "3",
            "--parallel-review-runner",
            "scillm",
            "--review-dag",
            "hybrid",
            "--oracle-model",
            "text",
            "--oracle-timeout",
            "120",
            "--ask-id",
            "live-parallel-review",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--json",
        ],
    )

    assert result.exit_code in {0, 2}
    payload = json.loads(result.stdout)
    status = read_status("live-parallel-review", tail_events=20, output_root=tmp_path / "runs")
    review_dir = tmp_path / "runs" / "live-parallel-review" / "parallel_review"
    verifier = json.loads((review_dir / "verdict.json").read_text(encoding="utf-8"))["verifier"]

    assert (review_dir / "target_bundle.md").exists()
    assert len(list((review_dir / "reviewer_outputs").glob("*.json"))) == 3
    assert (review_dir / "judge.json").exists()
    if result.exit_code == 0:
        assert payload["parallel_review"]["verifier_status"] == "PASS"
        assert status["state"] == "answered"
        assert verifier["status"] == "PASS"
    else:
        assert payload["needs_attention"]["reason"] == "parallel_review_verifier_failed"
        assert status["state"] == "needs_attention"
        assert verifier["status"] == "FAIL"
