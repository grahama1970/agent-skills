from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from code_runner.tools import execute, safe_path
from code_runner.worktree import path_allowed
from ..helpers.patch_oracle import touched_paths_from_patch_or_hunk


@pytest.mark.parametrize(
    "raw_path",
    [
        "/tmp/escape.txt",
        "../escape.txt",
        "src/../../escape.txt",
        "src/../app.py",
        "./../escape.txt",
        "src/link.txt",
    ],
)
def test_denied_paths_never_mutate_external_sentinel(tmp_path: Path, raw_path: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("secret\n")
    (root / "src").mkdir()
    if raw_path == "src/link.txt":
        (root / "src" / "link.txt").symlink_to(sentinel)

    with pytest.raises(ValueError):
        safe_path(root, raw_path)

    assert sentinel.read_text() == "secret\n"


@pytest.mark.parametrize(
    "candidate,allowlist,expected",
    [
        ("src/app.py", ["src"], True),
        ("src/nested/app.py", ["src"], True),
        ("src_evil/app.py", ["src"], False),
        ("src-old/app.py", ["src"], False),
        ("src", ["src"], True),
        ("src2", ["src"], False),
    ],
)
def test_path_allowed_is_segment_property(candidate: str, allowlist: list[str], expected: bool) -> None:
    assert path_allowed(candidate, allowlist) is expected


@pytest.mark.parametrize(
    "raw_path",
    [
        "src/app.py",
        "src/file with spaces.py",
        "src/cafe-ß.py",
        unicodedata.normalize("NFD", "src/cafe\u0301.py"),
    ],
)
def test_accepted_write_paths_resolve_inside_worktree(tmp_path: Path, raw_path: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    resolved = safe_path(root, raw_path)

    assert resolved.relative_to(root.resolve())


def test_execute_write_denies_prefix_trick_without_mutating(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    result = execute("write_file", {"path": "src_evil/app.py", "content": "owned\n"}, root, ["src"], [])

    assert '"ok": false' in result
    assert not (root / "src_evil/app.py").exists()


def test_execute_write_denies_parent_traversal_without_mutating_external(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "escape.txt"
    result = execute("write_file", {"path": "../escape.txt", "content": "owned\n"}, root, ["../escape.txt"], [])

    assert '"ok": false' in result
    assert not external.exists()


@pytest.mark.parametrize(
    "diff_line,expected",
    [
        ('diff --git "a/src/file with spaces.py" "b/src/file with spaces.py"\n', {"src/file with spaces.py"}),
        ('diff --git "a/src/cafe-ß.py" "b/src/cafe-ß.py"\n', {"src/cafe-ß.py"}),
        ('diff --git "a/src/old name.py" "b/src/new name.py"\n', {"src/old name.py", "src/new name.py"}),
        ('diff --git a/src/app.py b/src/app.py\n', {"src/app.py"}),
    ],
)
def test_patch_oracle_handles_quoted_and_unquoted_git_paths(tmp_path: Path, diff_line: str, expected: set[str]) -> None:
    patch = tmp_path / "quoted.patch"
    patch.write_text(diff_line)

    assert touched_paths_from_patch_or_hunk(patch) == expected


def test_patch_oracle_is_independent_of_current_working_directory(tmp_path: Path, monkeypatch) -> None:
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    patch = patch_dir / "case.hunk.md"
    patch.write_text("# hunk\n```diff\ndiff --git a/src/app.py b/src/app.py\n```\n")
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    assert touched_paths_from_patch_or_hunk(patch) == {"src/app.py"}
