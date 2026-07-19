from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_sh_read_prints_project_knowledge() -> None:
    result = subprocess.run(
        ["bash", "run.sh", "read"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "# Project Knowledge: persona-dream" in result.stdout
    assert "Current Understanding" in result.stdout
    assert "Unknown command" not in result.stderr


def test_run_sh_help_lists_read_command() -> None:
    result = subprocess.run(
        ["bash", "run.sh", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "read                 Print PROJECT_KNOWLEDGE.md before running pipeline phases" in result.stdout
    assert "./run.sh read" in result.stdout
