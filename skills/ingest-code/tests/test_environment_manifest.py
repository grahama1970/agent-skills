"""Environment-manifest tests for ingest-code runner identity."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

spec = importlib.util.spec_from_file_location("environment_manifest", MODULE_DIR / "environment_manifest.py")
assert spec and spec.loader
environment_manifest = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = environment_manifest
spec.loader.exec_module(environment_manifest)


def _write_skill_root(root: Path, extra: str = "") -> None:
    for name in environment_manifest.HASHED_SKILL_FILES:
        (root / name).write_text(f"{name}\n{extra}", encoding="utf-8")


def test_environment_manifest_records_env_names_not_values(tmp_path: Path, monkeypatch) -> None:
    skill_root = tmp_path / "skill"
    source_root = tmp_path / "repo"
    skill_root.mkdir()
    source_root.mkdir()
    _write_skill_root(skill_root)
    monkeypatch.setenv("INGEST_WORKERS", "secret-canary-value")
    monkeypatch.setenv("UNDECLARED_CANARY", "must-not-appear")

    manifest = environment_manifest.build_environment_manifest(
        skill_root=skill_root,
        source_root=source_root,
        projection_mode="emit",
        argv=["scan", str(source_root)],
        terminal_status="complete",
    )
    encoded = json.dumps(manifest, sort_keys=True)

    assert manifest["environment"]["INGEST_WORKERS"]["present"] is True
    assert "secret-canary-value" not in encoded
    assert "UNDECLARED_CANARY" not in encoded
    assert "must-not-appear" not in encoded


def test_environment_manifest_digest_changes_when_locked_input_changes(tmp_path: Path) -> None:
    skill_root = tmp_path / "skill"
    source_root = tmp_path / "repo"
    skill_root.mkdir()
    source_root.mkdir()
    _write_skill_root(skill_root)

    first = environment_manifest.build_environment_manifest(
        skill_root=skill_root,
        source_root=source_root,
        projection_mode="emit",
        argv=["scan", str(source_root)],
        terminal_status="complete",
    )
    (skill_root / "uv.lock").write_text("changed-lock\n", encoding="utf-8")
    second = environment_manifest.build_environment_manifest(
        skill_root=skill_root,
        source_root=source_root,
        projection_mode="emit",
        argv=["scan", str(source_root)],
        terminal_status="complete",
    )

    assert first["environment_manifest_digest"] != second["environment_manifest_digest"]
