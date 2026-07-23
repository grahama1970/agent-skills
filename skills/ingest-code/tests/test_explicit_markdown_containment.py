"""Regression tests for explicit Markdown containment."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _relative_files(root: Path, files: list[Path]) -> set[str]:
    return {path.relative_to(root).as_posix() for path in files}


def test_explicit_root_markdown_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    external = tmp_path / "outside.md"
    repo = tmp_path / "repo"
    repo.mkdir()
    external.write_text("# outside\n")
    (repo / "README.md").symlink_to(external)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert external.resolve() not in files
    assert files == []


def test_explicit_docs_directory_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    external_docs = tmp_path / "external-docs"
    repo = tmp_path / "repo"
    external_docs.mkdir()
    repo.mkdir()
    outside = external_docs / "outside.md"
    outside.write_text("# outside\n")
    (repo / "docs").symlink_to(external_docs, target_is_directory=True)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert outside.resolve() not in files
    assert files == []


def test_explicit_local_markdown_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    external = tmp_path / "outside.md"
    repo = tmp_path / "repo"
    (repo / "local").mkdir(parents=True)
    external.write_text("# outside\n")
    (repo / "local" / "link.md").symlink_to(external)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert external.resolve() not in files
    assert files == []


def test_in_repo_markdown_symlink_is_allowed_and_deduplicated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    guide = repo / "docs" / "guide.md"
    guide.write_text("# guide\n")
    (repo / "README.md").symlink_to(guide)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert files.count(guide.resolve()) == 1
    assert files == [guide.resolve()]


def test_explicit_markdown_remains_included_despite_gitignore_and_source_glob(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("def app():\n    return 1\n")
    (repo / "README.md").write_text("# readme\n")
    (repo / ".gitignore").write_text("README.md\n")
    _git(repo, "init")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"src/app.py", "README.md"}


def test_explicit_markdown_respects_since_after_resolution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    guide = repo / "docs" / "guide.md"
    guide.write_text("# guide\n")
    (repo / "README.md").symlink_to(guide)
    old = datetime.now() - timedelta(seconds=120)
    threshold = datetime.now() - timedelta(seconds=10)
    os.utime(guide, (old.timestamp(), old.timestamp()))

    assert ingest_code.collect_files(repo, ["src/**/*.py"], mtime_after=threshold) == []

    fresh = datetime.now()
    os.utime(guide, (fresh.timestamp(), fresh.timestamp()))

    assert ingest_code.collect_files(repo, ["src/**/*.py"], mtime_after=threshold) == [guide.resolve()]


def test_non_markdown_symlink_with_markdown_alias_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    notes = repo / "NOTES.txt"
    notes.write_text("not markdown\n")
    (repo / "README.md").symlink_to(notes)

    assert ingest_code.collect_files(repo, ["src/**/*.py"]) == []
