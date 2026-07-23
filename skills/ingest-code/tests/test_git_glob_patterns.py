"""Regression tests for Git-backed collect_files glob semantics."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
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


def _write_tree(root: Path) -> None:
    (root / "src" / "nested").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "root.py").write_text("def root():\n    return 1\n")
    (root / "src" / "app.py").write_text("def app():\n    return 1\n")
    (root / "src" / "app.js").write_text("export function app() { return 1; }\n")
    (root / "src" / "nested" / "deep.py").write_text("def deep():\n    return 1\n")
    (root / "tests" / "test_app.py").write_text("def test_app():\n    pass\n")


def _relative_files(root: Path, files: list[Path]) -> set[str]:
    return {path.relative_to(root).as_posix() for path in files}


def test_git_scan_honors_repository_relative_recursive_glob(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_tree(repo)
    _git(repo, "init")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {
        "src/app.py",
        "src/nested/deep.py",
    }


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (
            "*.py",
            {
                "root.py",
                "src/app.py",
                "src/nested/deep.py",
                "tests/test_app.py",
            },
        ),
        ("src/*.py", {"src/app.py"}),
        ("./src/**/*.py", {"src/app.py", "src/nested/deep.py"}),
        ("src\\**\\*.py", {"src/app.py", "src/nested/deep.py"}),
        (
            "src/**/*.py",
            {
                "src/app.py",
                "src/nested/deep.py",
            },
        ),
        ("**/test_*.py", {"tests/test_app.py"}),
    ],
)
def test_git_and_non_git_glob_semantics_match(
    pattern: str,
    expected: set[str],
    tmp_path: Path,
) -> None:
    git_repo = tmp_path / "git-repo"
    non_git = tmp_path / "non-git"
    git_repo.mkdir()
    non_git.mkdir()
    _write_tree(git_repo)
    _write_tree(non_git)
    _git(git_repo, "init")

    assert _relative_files(git_repo, ingest_code.collect_files(git_repo, [pattern])) == expected
    assert _relative_files(non_git, ingest_code.collect_files(non_git, [pattern])) == expected


def test_git_custom_glob_still_respects_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "generated").mkdir(parents=True)
    (repo / "src" / "keep.py").write_text("def keep():\n    return 1\n")
    (repo / "src" / "generated" / "ignored.py").write_text("def ignored():\n    return 1\n")
    (repo / ".gitignore").write_text("src/generated/\n")
    _git(repo, "init")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"src/keep.py"}


@pytest.mark.parametrize("pattern", ["", "   ", "../*.py", "/tmp/*.py"])
def test_unsafe_git_globs_do_not_broaden_scan(pattern: str, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def app():\n    return 1\n")
    _git(repo, "init")

    assert ingest_code._git_glob_pathspec(pattern) is None
    assert ingest_code._git_ls_files(repo, [pattern]) == []


def test_non_git_parent_traversal_glob_cannot_escape_repository(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    repo = tmp_path / "repo"
    repo.mkdir()
    outside.write_text("def outside():\n    return 1\n")
    (repo / "app.py").write_text("def app():\n    return 1\n")

    files = ingest_code.collect_files(repo, ["../*.py"])

    assert outside not in files
    assert files == []


@pytest.mark.parametrize("pattern", ["", "   ", ".", "/tmp/*.py", "C:\\tmp\\*.py"])
def test_non_git_absolute_blank_and_dot_globs_fail_closed(pattern: str, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def app():\n    return 1\n")

    assert ingest_code._normalize_scan_glob(pattern) is None
    assert ingest_code.collect_files(repo, [pattern]) == []


def test_non_git_scoped_root_uses_repository_relative_glob(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "nested").mkdir(parents=True)
    (repo / "other").mkdir()
    (repo / ".monitor-codebase.json").write_text('{"include_dirs": ["src"]}\n')
    (repo / "src" / "app.py").write_text("def app():\n    return 1\n")
    (repo / "src" / "nested" / "deep.py").write_text("def deep():\n    return 1\n")
    (repo / "other" / "outside.py").write_text("def outside():\n    return 1\n")

    files = ingest_code.collect_files(repo, ["src/**/*.py"])

    assert _relative_files(repo, files) == {"src/app.py", "src/nested/deep.py"}


def test_non_git_glob_returns_files_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "nested").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("def app():\n    return 1\n")

    files = ingest_code.collect_files(repo, ["**/*"])

    assert _relative_files(repo, files) == {"src/app.py"}
    assert all(path.is_file() for path in files)


def test_git_glob_omits_deleted_index_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    deleted = repo / "deleted.py"
    deleted.write_text("def deleted():\n    return 1\n")
    _git(repo, "init")
    _git(repo, "add", "deleted.py")
    deleted.unlink()

    assert ingest_code._git_ls_files(repo, ["*.py"]) == []
