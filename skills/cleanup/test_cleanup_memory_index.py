"""Tests for cleanup's ingest-code memory-index lane."""

from pathlib import Path
from types import SimpleNamespace
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cleanup_memory_index  # noqa: E402


def test_memory_index_builds_ingest_code_treesitter_command(tmp_path):
    runner = tmp_path / "run.sh"
    repo = tmp_path / "repo"

    command = cleanup_memory_index.build_ingest_code_command(runner, repo, dry_run=True)

    assert command == ["bash", str(runner), "scan", str(repo), "--treesitter", "--dry-run"]


def test_memory_index_receipt_captures_local_artifacts(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = tmp_path / "run.sh"
    runner.write_text("#!/usr/bin/env bash\n")
    receipt = tmp_path / "receipt.json"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"ok": true}\n', stderr="")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(cleanup_memory_index, "find_ingest_code_runner", lambda: runner)
    monkeypatch.setattr(cleanup_memory_index.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cleanup_memory_index,
        "scan_ingest_code_evidence",
        lambda: {
            "status": "complete",
            "marker_path": ".ingest-code.json",
            "local_artifacts": {
                "code_symbols_jsonl": str(repo / "artifacts/ingest-code/code-symbols.jsonl"),
            },
        },
    )
    monkeypatch.setattr(
        cleanup_memory_index,
        "scan_cleanup_evidence_artifact",
        lambda: {"status": "complete", "artifact_path": ".cleanup-evidence.json"},
    )

    result = cleanup_memory_index.run_memory_indexing(dry_run=True, output=str(receipt))

    assert calls[0][-1] == "--dry-run"
    assert result["schema"] == "cleanup.memory_index.v1"
    assert result["status"] == "passed"
    assert result["local_artifacts"]["code_symbols_jsonl"].endswith("code-symbols.jsonl")
    assert json.loads(receipt.read_text())["dry_run"] is True
