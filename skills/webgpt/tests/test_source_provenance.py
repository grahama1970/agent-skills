from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "webgpt_cli.py"
SPEC = importlib.util.spec_from_file_location("webgpt_cli_provenance", MODULE_PATH)
assert SPEC and SPEC.loader
webgpt_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(webgpt_cli)


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _repo_with_upstream(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "init", "-b", "main", str(repo), cwd=tmp_path)
    _run("git", "config", "user.name", "WebGPT Test", cwd=repo)
    _run("git", "config", "user.email", "webgpt@example.invalid", cwd=repo)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("VALUE = 1\n")
    (repo / "notes.txt").write_text("tracked notes\n")
    _run("git", "add", "src/app.py", "notes.txt", cwd=repo)
    _run("git", "commit", "-m", "initial", cwd=repo)

    public_url = "https://example.invalid/project.git"
    _run("git", "remote", "add", "origin", public_url, cwd=repo)
    _run(
        "git",
        "config",
        f"url.file://{remote}.insteadOf",
        public_url,
        cwd=repo,
    )
    _run("git", "push", "-u", "origin", "main", cwd=repo)
    return repo, remote


def _error(repo: Path, paths: list[str]) -> webgpt_cli.SourceProvenanceError:
    with pytest.raises(webgpt_cli.SourceProvenanceError) as captured:
        webgpt_cli._source_provenance(str(repo), paths)
    return captured.value


def test_pushed_clean_relative_source_passes_with_unrelated_dirty_file(tmp_path: Path) -> None:
    repo, _ = _repo_with_upstream(tmp_path)
    (repo / "notes.txt").write_text("unrelated dirty change\n")

    result = webgpt_cli._source_provenance(str(repo), ["src/app.py"])

    assert result["repository_url"] == "https://example.invalid/project.git"
    assert result["source_paths"] == ["src/app.py"]
    assert len(result["commit_sha"]) == 40
    assert result["upstream"] == "origin/main"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/tmp/app.py", "SOURCE_PATH_ABSOLUTE"),
        ("../app.py", "SOURCE_PATH_OUTSIDE_REPO"),
        ("missing.py", "SOURCE_PATH_NOT_COMMITTED"),
    ],
)
def test_invalid_source_paths_fail_loudly(tmp_path: Path, path: str, code: str) -> None:
    repo, _ = _repo_with_upstream(tmp_path)
    assert _error(repo, [path]).code == code


def test_uncommitted_declared_source_fails_loudly(tmp_path: Path) -> None:
    repo, _ = _repo_with_upstream(tmp_path)
    (repo / "src" / "app.py").write_text("VALUE = 2\n")
    assert _error(repo, ["src/app.py"]).code == "SOURCE_PATH_UNCOMMITTED"


def test_missing_upstream_fails_loudly(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _run("git", "init", "-b", "main", str(repo), cwd=tmp_path)
    _run("git", "config", "user.name", "WebGPT Test", cwd=repo)
    _run("git", "config", "user.email", "webgpt@example.invalid", cwd=repo)
    (repo / "app.py").write_text("VALUE = 1\n")
    _run("git", "add", "app.py", cwd=repo)
    _run("git", "commit", "-m", "initial", cwd=repo)
    assert _error(repo, ["app.py"]).code == "SOURCE_UPSTREAM_MISSING"


def test_unpushed_head_fails_loudly(tmp_path: Path) -> None:
    repo, _ = _repo_with_upstream(tmp_path)
    (repo / "src" / "app.py").write_text("VALUE = 2\n")
    _run("git", "add", "src/app.py", cwd=repo)
    _run("git", "commit", "-m", "local only", cwd=repo)
    assert _error(repo, ["src/app.py"]).code == "SOURCE_COMMIT_UNPUSHED"


def test_local_only_remote_is_not_exposed_to_webgpt() -> None:
    with pytest.raises(webgpt_cli.SourceProvenanceError) as captured:
        webgpt_cli._cloneable_remote_url("file:///tmp/project.git")
    assert captured.value.code == "SOURCE_REMOTE_UNAVAILABLE"


def test_remote_credentials_are_removed() -> None:
    assert (
        webgpt_cli._cloneable_remote_url(
            "https://token@example.com/org/project.git?access_token=secret"
        )
        == "https://example.com/org/project.git"
    )
