"""Tests for Ask-backed code-question solution retrieval."""

from __future__ import annotations

import os
import asyncio
from pathlib import Path

import pytest

from live_evidence.config import AppSettings
from live_evidence.models import EvidenceSource, Freshness, RetrievalLane
from live_evidence.retrieval.ask import AskSolutionClient


def settings(tmp_path: Path, runner: Path | None) -> AppSettings:
    return AppSettings(
        skill_root=tmp_path,
        data_dir=tmp_path / "data",
        profile_path=tmp_path / "profile.yaml",
        repo_roots=[],
        memory_runner=None,
        ask_runner=runner,
        brave_runner=None,
        dogpile_runner=None,
        subprocess_timeout_s=2,
        ask_timeout_s=2,
    )


def write_runner(tmp_path: Path, run_dir: Path) -> Path:
    runner = tmp_path / "ask-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'mkdir -p "$1/node-artifacts/handler-fixture"',
                'printf "Ask says use target_symbol from src/live.py.\\n" > "$1/node-artifacts/handler-fixture/response.md"',
                'printf \'{"run_dir":"%s"}\\n\' "$1"',
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    wrapper = tmp_path / "ask-wrapper.sh"
    wrapper.write_text(
        f"#!/usr/bin/env bash\nexec {runner} {run_dir}\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def test_ask_solution_reads_response_from_run_receipt(tmp_path: Path) -> None:
    run_dir = tmp_path / "ask-run"
    client = AskSolutionClient(settings(tmp_path, write_runner(tmp_path, run_dir)))
    evidence = [
        EvidenceSource(
            lane=RetrievalLane.RIPGREP,
            label="repo/src/live.py",
            excerpt="def target_symbol(): return 'active'",
            score=0.9,
            freshness=Freshness.CURRENT,
            repository="repo",
            path=str(tmp_path / "repo" / "src" / "live.py"),
            line_start=1,
        )
    ]

    result = asyncio.run(client.solve("Where is target_symbol implemented?", evidence))

    assert result.ok is True
    assert result.sources[0].lane is RetrievalLane.ASK
    assert result.sources[0].path == str(run_dir.resolve())
    assert result.sources[0].metadata["seed_source_count"] == 1
    assert "target_symbol" in result.sources[0].excerpt


def test_ask_runner_is_explicit_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE_EVIDENCE_ASK_RUNNER", raising=False)
    monkeypatch.setenv("LIVE_EVIDENCE_PROFILE", str(tmp_path / "profile.yaml"))
    monkeypatch.setenv("LIVE_EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LIVE_EVIDENCE_REPOS", "")
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    loaded = AppSettings.from_env(skill_root=tmp_path)

    assert loaded.ask_runner is None
