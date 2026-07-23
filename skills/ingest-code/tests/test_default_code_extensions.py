"""Regression tests for default code extension discovery."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _write_react_tree(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "widget.tsx").write_text("export function Widget() {\n  return null;\n}\n")
    (root / "src" / "widget.jsx").write_text("export class Panel {}\n")
    (root / "src" / "plain.ts").write_text("export const value = 1;\n")
    (root / "src" / "plain.js").write_text("export function plain() { return 1; }\n")


def _relative_files(root: Path, files: list[Path]) -> set[str]:
    return {path.relative_to(root).as_posix() for path in files}


def test_default_patterns_include_existing_tsx_jsx_handlers() -> None:
    assert "*.tsx" in ingest_code.DEFAULT_GLOB_PATTERNS
    assert "*.jsx" in ingest_code.DEFAULT_GLOB_PATTERNS
    assert len(ingest_code.DEFAULT_GLOB_PATTERNS) == len(set(ingest_code.DEFAULT_GLOB_PATTERNS))


@pytest.mark.parametrize("git_repo", [False, True])
def test_default_discovery_finds_tsx_and_jsx_in_git_and_non_git_repositories(
    git_repo: bool,
    tmp_path: Path,
) -> None:
    repo = tmp_path / ("git-repo" if git_repo else "plain-repo")
    repo.mkdir()
    _write_react_tree(repo)
    if git_repo:
        _git(repo, "init")

    files = ingest_code.collect_files(repo, ingest_code.DEFAULT_GLOB_PATTERNS)

    assert _relative_files(repo, files) == {
        "src/widget.tsx",
        "src/widget.jsx",
        "src/plain.ts",
        "src/plain.js",
    }


def test_default_tsx_jsx_files_produce_generic_export_knowledge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_react_tree(repo)

    tsx_items = ingest_code.extract_knowledge(repo / "src" / "widget.tsx")
    jsx_items = ingest_code.extract_knowledge(repo / "src" / "widget.jsx")

    assert any("Widget" in item["problem"] for item in tsx_items)
    assert any("Panel" in item["problem"] for item in jsx_items)


def test_treesitter_command_includes_tsx_and_jsx_defaults(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    captured_commands = []

    def fake_run(cmd, **kwargs):
        captured_commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)

    assert ingest_code._store_treesitter_symbols_for_directory(
        repo / "src",
        repo,
        "code",
        allowed_files=frozenset(),
    ) == 0

    command = captured_commands[0]
    assert ["--include", "**/*.tsx"] == command[command.index("**/*.tsx") - 1: command.index("**/*.tsx") + 1]
    assert ["--include", "**/*.jsx"] == command[command.index("**/*.jsx") - 1: command.index("**/*.jsx") + 1]


def test_scan_default_manifest_contains_tsx_and_jsx(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_react_tree(repo)
    captured_manifests = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    def fake_store(*args, allowed_files, **kwargs):
        captured_manifests.append(allowed_files)
        return 0

    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fake_store)

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=True,
        code_index=True,
        dry_run=False,
        scope="code",
        batch_size=50,
    )

    manifest = captured_manifests[0]
    assert repo.resolve() / "src" / "widget.tsx" in manifest
    assert repo.resolve() / "src" / "widget.jsx" in manifest


def test_skill_docs_list_default_tsx_and_jsx_patterns() -> None:
    text = SKILL_PATH.read_text()

    assert "*.tsx" in text
    assert "*.jsx" in text
