"""Regression tests for cleanup dependency evidence emission."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]


def test_scan_accepts_cleanup_evidence_flag_and_writes_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pkg" / "provider.py").write_text("VALUE = 1\n")
    (repo / "pkg" / "consumer.py").write_text("from pkg import provider\n")
    (repo / "tests" / "test_provider.py").write_text("def test_provider():\n    assert True\n")
    (repo / "loader.py").write_text("import importlib\nname = 'x'\nimportlib.import_module(name)\n")
    (repo / "ui.ts").write_text("export const value = 1;\n")

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_DIR / "ingest_code.py"),
            "scan",
            str(repo),
            "--treesitter",
            "--projection-mode",
            "emit",
            "--cleanup-evidence",
            "--local-artifacts-only",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "Cleanup evidence:" in result.stdout
    assert "--- Phase 1: skipped by --local-artifacts-only ---" in result.stdout
    assert "--- Phase 3: skipped by --local-artifacts-only ---" in result.stdout
    assert "--- Phase 4: skipped by --local-artifacts-only ---" in result.stdout
    assert "Code projection request:" not in result.stdout

    artifact = repo / ".cleanup-evidence.json"
    payload = json.loads(artifact.read_text())
    assert payload["contract"] == "cleanup.evidence.v1"
    assert payload["repository_path"] == str(repo.resolve())
    assert payload["analysis_complete"] is True

    files = payload["files"]
    assert sorted(files) == [
        "loader.py",
        "pkg/consumer.py",
        "pkg/provider.py",
        "tests/test_provider.py",
        "ui.ts",
    ]
    assert files["pkg/provider.py"]["inbound_references"][0]["from_path"] == "pkg/consumer.py"
    assert files["tests/test_provider.py"]["entry_kinds"] == ["pytest_test"]
    assert files["ui.ts"]["parse_status"] == "not_analyzed"
    assert files["loader.py"]["dynamic_reference_warnings"][0]["kind"] == "importlib"


def test_scan_no_cleanup_evidence_suppresses_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def app():\n    return 1\n")

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_DIR / "ingest_code.py"),
            "scan",
            str(repo),
            "--projection-mode",
            "emit",
            "--no-cleanup-evidence",
            "--local-artifacts-only",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert not (repo / ".cleanup-evidence.json").exists()
