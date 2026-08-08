"""git_repo - helpers.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(cmd)}\n"
            f"cwd={cwd}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )
    return proc


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=repo, check=check)


def init_git_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init")
    git(repo, "config", "user.email", "code-runner-tests@example.invalid")
    git(repo, "config", "user.name", "code-runner tests")
    return repo


def write(repo: Path, rel: str, content: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def make_minimal_python_repo(tmp_path: Path) -> Path:
    repo = init_git_repo(tmp_path / "source-repo")

    write(
        repo,
        "src/app.py",
        "def add_one(x):\n"
        "    return x\n",
    )
    write(
        repo,
        "README.md",
        "# Fixture repo\n\nFix add_one so add_one(1) == 2.\n",
    )
    write(
        repo,
        ".gitignore",
        ".venv/\n"
        "*.pyc\n"
        ".env.local\n",
    )

    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial fixture")
    return repo


def create_ignored_file(repo: Path, rel: str = ".env.local", content: str = "ignored secret\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def all_non_git_files(repo: Path) -> list[Path]:
    paths: list[Path] = []
    for root, dirs, names in os.walk(repo):
        root_path = Path(root)
        if ".git" in dirs:
            dirs.remove(".git")
        for name in names:
            paths.append(root_path / name)
    return sorted(paths)
