"""assertions - helpers.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .git_repo import git


CONTRACT_RUNTIME_ARTIFACT_SUFFIXES = [
    "request.json",
    "status.json",
    "events.jsonl",
    "rounds.jsonl",
    "response.txt",
    "result.json",
    "hunk.md",
    "verifier.log",
]

MINIMUM_PREFLIGHT_ARTIFACT_SUFFIXES = [
    "request.json",
    "status.json",
    "result.json",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def result_path(output_dir: Path, task_id: str) -> Path:
    return output_dir / f"{task_id}.result.json"


def hunk_path(output_dir: Path, task_id: str) -> Path:
    return output_dir / f"{task_id}.hunk.md"


def patch_path(output_dir: Path, task_id: str) -> Path:
    return output_dir / f"{task_id}.patch"


def assert_minimum_preflight_artifacts(output_dir: Path, task_id: str) -> None:
    for suffix in MINIMUM_PREFLIGHT_ARTIFACT_SUFFIXES:
        path = output_dir / f"{task_id}.{suffix}"
        assert path.exists(), f"missing minimum preflight artifact: {path}"


def assert_runtime_artifacts(output_dir: Path, task_id: str) -> None:
    for suffix in CONTRACT_RUNTIME_ARTIFACT_SUFFIXES:
        path = output_dir / f"{task_id}.{suffix}"
        assert path.exists(), f"missing runtime artifact: {path}"


def assert_result_failed(result: dict) -> None:
    assert result["status"] != "pass"
    assert result["dod_passed"] is False


def assert_result_passed(result: dict) -> None:
    assert result["status"] == "pass"
    assert result["dod_passed"] is True


def assert_no_residual_code_runner_worktree(repo: Path, task_id: str) -> None:
    listing = git(repo, "worktree", "list", "--porcelain").stdout
    lines = listing.splitlines()
    leaked = [
        line
        for line in lines
        if line.startswith("worktree ")
        and str(repo) not in line
        and (task_id in line or "code-runner" in line)
    ]
    assert not leaked, f"residual code-runner worktree metadata: {leaked}\n{listing}"


def assert_patch_applies_to_clean_review_worktree(source_repo: Path, patch_file: Path, tmp_path: Path) -> None:
    review = tmp_path / f"review-worktree-{patch_file.stem}"
    git(source_repo, "worktree", "add", "--detach", str(review), "HEAD")
    try:
        if patch_file.exists() and patch_file.read_text(errors="replace").strip():
            check = subprocess.run(
                ["git", "apply", "--check", str(patch_file)],
                cwd=review,
                text=True,
                capture_output=True,
            )
            assert check.returncode == 0, check.stderr

            apply = subprocess.run(
                ["git", "apply", str(patch_file)],
                cwd=review,
                text=True,
                capture_output=True,
            )
            assert apply.returncode == 0, apply.stderr
    finally:
        git(source_repo, "worktree", "remove", "--force", str(review), check=False)


def committed_paths(repo: Path, commit: str = "HEAD") -> set[str]:
    proc = git(repo, "show", "--name-only", "--pretty=", commit)
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}
