"""Local deployment release-cut and alignment proof for Battle."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from tarfile import TarInfo
from typing import Any

from .packaged_deployment_smoke import _now_utc


DEFAULT_DEPLOYMENT_ROOT = Path("/mnt/storage12tb/deployments/agent-skills")


def prove_local_deployment_alignment(
    *,
    out_dir: Path,
    repo_root: Path,
    deployment_root: Path = DEFAULT_DEPLOYMENT_ROOT,
    commit: str = "HEAD",
    activate: bool = False,
    authorized_by: str | None = None,
) -> dict[str, Any]:
    """Cut a local release and optionally point deployment_root/current at it.

    This receipt proves only local filesystem release alignment. It is
    intentionally not accepted as production infrastructure evidence.
    """

    out_dir = out_dir.resolve()
    repo_root = repo_root.resolve()
    deployment_root = deployment_root.resolve()
    releases_root = deployment_root / "releases"
    current_link = deployment_root / "current"
    out_dir.mkdir(parents=True, exist_ok=True)
    releases_root.mkdir(parents=True, exist_ok=True)

    branch = _git(["branch", "--show-current"], cwd=repo_root).strip()
    resolved_commit = _git(["rev-parse", commit], cwd=repo_root).strip()
    origin_main = _git(["ls-remote", "origin", "refs/heads/main"], cwd=repo_root).split()[0]
    errors: list[str] = []
    if branch != "main":
        errors.append(f"branch is {branch!r}, expected 'main'")
    if resolved_commit != origin_main:
        errors.append("resolved commit does not match origin/main readback")
    if activate and not authorized_by:
        errors.append("--activate requires --authorized-by")

    release_dir = releases_root / resolved_commit[:12]
    previous_raw = os.readlink(current_link) if current_link.is_symlink() else None
    previous_resolved = current_link.resolve() if current_link.exists() or current_link.is_symlink() else None

    expected_dir: Path | None = None
    release_digest: str | None = None
    expected_digest: str | None = None
    current_resolved: Path | None = None
    current_digest: str | None = None
    activated = False

    try:
        if not errors:
            _ensure_release_from_git_archive(
                repo_root=repo_root,
                commit=resolved_commit,
                release_dir=release_dir,
                out_dir=out_dir,
            )
            expected_dir = out_dir / "expected-tree"
            if expected_dir.exists():
                shutil.rmtree(expected_dir)
            expected_dir.mkdir(parents=True)
            _extract_git_archive(repo_root=repo_root, commit=resolved_commit, dest=expected_dir)

            release_digest = _tree_digest(release_dir)
            expected_digest = _tree_digest(expected_dir)
            if release_digest != expected_digest:
                errors.append("release tree digest does not match git archive tree digest")

        if not errors and activate:
            _activate_symlink(current_link=current_link, release_dir=release_dir)
            activated = True

        if current_link.exists() or current_link.is_symlink():
            current_resolved = current_link.resolve()
            if current_resolved.exists() and current_resolved.is_dir():
                current_digest = _tree_digest(current_resolved)
            else:
                errors.append("current symlink target is missing or not a directory")
        else:
            errors.append("current symlink is missing")

        if current_resolved != release_dir:
            errors.append("current symlink does not resolve to the cut release")
        if current_digest is not None and expected_digest is not None and current_digest != expected_digest:
            errors.append("current release tree digest does not match git archive tree digest")
    finally:
        if expected_dir is not None and expected_dir.exists():
            shutil.rmtree(expected_dir)

    receipt = {
        "schema": "battle.local_deployment_alignment_proof.v1",
        "status": "PASS" if not errors else "BLOCKED",
        "mocked": False,
        "live": "local_filesystem_release_cut_and_symlink_readback",
        "repo_root": str(repo_root),
        "deployment_root": str(deployment_root),
        "branch": branch,
        "commit": resolved_commit,
        "origin_main": origin_main,
        "release_dir": str(release_dir),
        "release_digest": release_digest,
        "expected_digest": expected_digest,
        "current_symlink": str(current_link),
        "current_symlink_raw_before": previous_raw,
        "current_symlink_resolved_before": str(previous_resolved) if previous_resolved else None,
        "current_symlink_resolved_after": str(current_resolved) if current_resolved else None,
        "current_digest": current_digest,
        "activated": activated,
        "authorized_by": authorized_by if activated else None,
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "A local filesystem release was cut from the origin/main commit.",
                "The deployment-root current symlink resolves to that local release.",
                "The active local release tree digest matches a fresh git archive extraction of the same commit.",
            ]
            if not errors
            else [
                "A local deployment alignment attempt was executed and failed closed with recorded errors."
            ],
            "does_not_prove": [
                "Cloud, Kubernetes, DNS, certificate, ingress, or secret-management behavior.",
                "Production TLS/certificate-backed WebSocket deployment or production-scale fanout capacity.",
                "Mathematically infinite swarm execution or production cluster autoscaling.",
                "Battle or RelayForge is production ready.",
            ],
        },
        "created_at": _now_utc(),
    }
    (out_dir / "local-deployment-alignment-proof.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _ensure_release_from_git_archive(
    *,
    repo_root: Path,
    commit: str,
    release_dir: Path,
    out_dir: Path,
) -> None:
    if release_dir.exists():
        if not release_dir.is_dir():
            raise RuntimeError(f"release path exists and is not a directory: {release_dir}")
        return
    tmp_parent = release_dir.parent
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{release_dir.name}.", dir=tmp_parent))
    try:
        _extract_git_archive(repo_root=repo_root, commit=commit, dest=tmp_dir)
        os.replace(tmp_dir, release_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    (out_dir / "release-cut.json").write_text(
        json.dumps(
            {
                "schema": "battle.local_release_cut.v1",
                "status": "PASS",
                "mocked": False,
                "live": "git_archive_to_local_release_directory",
                "commit": commit,
                "release_dir": str(release_dir),
                "created_at": _now_utc(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _extract_git_archive(*, repo_root: Path, commit: str, dest: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tar_path = dest / ".archive.tar"
    tar_path.write_bytes(archive.stdout)
    with tarfile.open(tar_path, "r") as tar:
        tar.extractall(dest, filter=_git_archive_filter)
    tar_path.unlink()


def _git_archive_filter(member: TarInfo, dest_path: str) -> TarInfo | None:
    # The archive was produced by local `git archive`; keep Git-tracked symlinks
    # while rejecting paths that would escape the release root.
    del dest_path
    path = Path(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise tarfile.FilterError(f"unsafe archive path: {member.name}")
    return member


def _activate_symlink(*, current_link: Path, release_dir: Path) -> None:
    current_link.parent.mkdir(parents=True, exist_ok=True)
    tmp_link = current_link.parent / f".{current_link.name}.tmp-{os.getpid()}"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(str(release_dir), tmp_link)
    os.replace(tmp_link, current_link)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file() or path.is_symlink())
    for path in files:
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".deployment/"):
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            digest.update(b"file\0")
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _git(args: list[str], *, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
