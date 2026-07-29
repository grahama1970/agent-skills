import json
import subprocess
from pathlib import Path

import pytest

from battle_skill.deployment_alignment_proof import prove_local_deployment_alignment


def test_local_deployment_alignment_cuts_and_activates_release(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    deployment_root = tmp_path / "deploy"
    (deployment_root / "releases").mkdir(parents=True)
    old = deployment_root / "releases" / "old"
    old.mkdir()
    (old / "stale.txt").write_text("old\n", encoding="utf-8")
    (deployment_root / "current").symlink_to(old)

    receipt = prove_local_deployment_alignment(
        out_dir=tmp_path / "out",
        repo_root=repo,
        deployment_root=deployment_root,
        activate=True,
        authorized_by="unit-test",
    )

    assert receipt["schema"] == "battle.local_deployment_alignment_proof.v1"
    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["activated"] is True
    assert Path(receipt["current_symlink_resolved_after"]) == Path(receipt["release_dir"])
    assert receipt["release_digest"] == receipt["expected_digest"] == receipt["current_digest"]
    assert (Path(receipt["release_dir"]) / "skills" / "battle" / "SKILL.md").exists()
    stored = json.loads((tmp_path / "out" / "local-deployment-alignment-proof.json").read_text(encoding="utf-8"))
    assert stored["status"] == "PASS"


def test_local_deployment_alignment_requires_authorization_to_activate(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    deployment_root = tmp_path / "deploy"
    (deployment_root / "releases").mkdir(parents=True)
    old = deployment_root / "releases" / "old"
    old.mkdir()
    (deployment_root / "current").symlink_to(old)

    with pytest.raises(RuntimeError, match="--activate requires --authorized-by"):
        prove_local_deployment_alignment(
            out_dir=tmp_path / "out",
            repo_root=repo,
            deployment_root=deployment_root,
            activate=True,
        )

    assert (deployment_root / "current").resolve() == old
    stored = json.loads((tmp_path / "out" / "local-deployment-alignment-proof.json").read_text(encoding="utf-8"))
    assert stored["status"] == "BLOCKED"


def _git_repo(path: Path) -> Path:
    path.mkdir()
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "battle-test@example.invalid"], path)
    _run(["git", "config", "user.name", "Battle Test"], path)
    (path / "skills" / "battle").mkdir(parents=True)
    (path / "skills" / "battle" / "SKILL.md").write_text("battle\n", encoding="utf-8")
    _run(["git", "add", "."], path)
    _run(["git", "commit", "-m", "seed"], path)
    commit = _run(["git", "rev-parse", "HEAD"], path).stdout.strip()
    _run(["git", "init", "--bare", str(path / "remote.git")], path)
    _run(["git", "remote", "add", "origin", str(path / "remote.git")], path)
    _run(["git", "push", "origin", f"{commit}:refs/heads/main"], path)
    _run(["git", "branch", "-M", "main"], path)
    return path


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
