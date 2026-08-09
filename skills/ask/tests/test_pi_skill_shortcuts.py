"""Pi /skill:ask browser-handler shortcut regressions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ASK_DIR = Path(__file__).resolve().parents[1]


def test_webgpt_shortcut_compiles_to_tau_single_call(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            str(ASK_DIR / "run.sh"),
            "webgpt",
            "--compile-only",
            "--run-output-root",
            str(tmp_path),
            "What",
            "is",
            "2",
            "+",
            "2?",
        ],
        cwd=ASK_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    start = result.stdout.find("{")
    assert start >= 0, result.stdout
    payload = json.loads(result.stdout[start:])
    assert payload["ok"] is True
    assert payload["status"] == "READY"
    assert payload["live"] is False

    run_dir = Path(payload["bundle"]["run_dir"])
    dag = json.loads((run_dir / "dag.json").read_text())
    assert dag["context"]["handlers"] == ["webgpt"]
    assert dag["context"].get("dag_template") == "single-call"
    assert dag["goal"]["immutable_goal"] == "Answer the user question via the 'webgpt' Tau browser handler with a non-empty response."
    assert dag["context"]["request"] == "What is 2 + 2?"


def test_webgpt_shortcut_still_rejects_empty_question() -> None:
    result = subprocess.run(
        [str(ASK_DIR / "run.sh"), "webgpt"],
        cwd=ASK_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 2
    assert "Usage: ./run.sh webgpt <question>" in result.stderr
