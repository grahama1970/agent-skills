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


def test_named_root_mdx_documents_are_included(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.mdx").write_text("# readme\n")
    (repo / "CONTEXT.mdx").write_text("# context\n")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"README.mdx", "CONTEXT.mdx"}


def test_special_document_directories_include_mdx(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "local" / "docs").mkdir(parents=True)
    (repo / "docs" / "guide.mdx").write_text("# guide\n")
    (repo / "local" / "notes.mdx").write_text("# notes\n")
    (repo / "local" / "docs" / "architecture.mdx").write_text("# architecture\n")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {
        "docs/guide.mdx",
        "local/notes.mdx",
        "local/docs/architecture.mdx",
    }


@pytest.mark.parametrize("use_git", [False, True])
def test_explicit_mdx_is_included_in_git_and_non_git_repositories(
    tmp_path: Path,
    use_git: bool,
) -> None:
    repo = tmp_path / ("git-repo" if use_git else "plain-repo")
    repo.mkdir()
    (repo / "README.mdx").write_text("# readme\n")
    if use_git:
        _git(repo, "init")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"README.mdx"}


def test_gitignored_explicit_mdx_remains_included(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "guide.mdx").write_text("# guide\n")
    (repo / ".gitignore").write_text("docs/*.mdx\n")
    _git(repo, "init")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"docs/guide.mdx"}


def test_explicit_mdx_respects_since_threshold(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    old_doc = repo / "README.mdx"
    recent_doc = repo / "docs" / "recent.mdx"
    old_doc.write_text("# old\n")
    recent_doc.write_text("# recent\n")
    old = datetime.now() - timedelta(seconds=120)
    recent = datetime.now()
    threshold = datetime.now() - timedelta(seconds=10)
    os.utime(old_doc, (old.timestamp(), old.timestamp()))
    os.utime(recent_doc, (recent.timestamp(), recent.timestamp()))

    files = ingest_code.collect_files(repo, ["src/**/*.py"], mtime_after=threshold)

    assert _relative_files(repo, files) == {"docs/recent.mdx"}


def test_external_mdx_symlink_is_rejected(tmp_path: Path) -> None:
    external = tmp_path / "outside.mdx"
    repo = tmp_path / "repo"
    repo.mkdir()
    external.write_text("# outside\n")
    (repo / "README.mdx").symlink_to(external)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert external.resolve() not in files
    assert files == []


def test_in_repo_mdx_symlink_is_canonicalized_and_deduplicated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    guide = repo / "docs" / "guide.mdx"
    guide.write_text("# guide\n")
    (repo / "README.mdx").symlink_to(guide)

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert files.count(guide.resolve()) == 1
    assert files == [guide.resolve()]


def test_arbitrary_root_mdx_is_not_implicitly_included(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes.mdx").write_text("# notes\n")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert files == []


def test_source_glob_does_not_disable_special_mdx_inclusion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "src" / "app.py").write_text("def app():\n    return 1\n")
    (repo / "README.mdx").write_text("# readme\n")
    (repo / "docs" / "guide.mdx").write_text("# guide\n")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {
        "src/app.py",
        "README.mdx",
        "docs/guide.mdx",
    }
