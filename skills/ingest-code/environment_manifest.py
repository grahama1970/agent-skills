"""Emit reproducible environment manifests for ingest-code runs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ALLOWLISTED_ENV_NAMES = (
    "CODE_SYMBOLS_QDRANT_BATCH_SIZE",
    "CODE_SYMBOLS_SCAN_INCLUDE_DIRS",
    "INGEST_CODE_BUNDLE_PATH_MAP",
    "INGEST_CODE_RUN_ID",
    "INGEST_CODE_RUN_ROOT",
    "INGEST_WORKERS",
    "MEMORY_RUN_SH",
    "MEMORY_SOCKET_PATH",
    "PYTHONPYCACHEPREFIX",
    "TMPDIR",
    "UV_CACHE_DIR",
    "UV_PROJECT_ENVIRONMENT",
    "XDG_CACHE_HOME",
)

HASHED_SKILL_FILES = (
    "run.sh",
    "pyproject.toml",
    "uv.lock",
    "ingest_code.py",
    "code_memory_client.py",
    "code_graph_artifact.py",
    "code_symbol_record.py",
    "code_edge_record.py",
    "incremental_state.py",
    "environment_manifest.py",
)


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return _sha256_bytes(path.read_bytes())


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _distribution_rows(names: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in names:
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            rows.append({"name": name, "installed": False})
            continue
        rows.append(
            {
                "name": dist.metadata["Name"],
                "version": dist.version,
                "installed": True,
            }
        )
    return sorted(rows, key=lambda item: item["name"].lower())


def _source_identity(source_root: Path) -> dict[str, Any]:
    root = source_root.resolve()
    return {
        "root": str(root),
        "repo": root.name,
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "commit": _git(["rev-parse", "HEAD"], root),
        "dirty_state": "dirty" if _git(["status", "--porcelain"], root) else "clean",
    }


def build_environment_manifest(
    *,
    skill_root: Path,
    source_root: Path,
    projection_mode: str,
    argv: list[str],
    terminal_status: str,
) -> dict[str, Any]:
    """Build an ingest-code.environment_manifest.v1 without secret values."""
    skill_root = skill_root.resolve()
    stable = {
        "schema": "ingest-code.environment_manifest.v1",
        "skill": {
            "root": str(skill_root),
            "commit": _git(["rev-parse", "HEAD"], skill_root),
            "dirty_state": "dirty" if _git(["status", "--porcelain"], skill_root) else "clean",
            "file_hashes": {
                name: _sha256_file(skill_root / name)
                for name in HASHED_SKILL_FILES
            },
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "packages": _distribution_rows(("typer", "httpx", "loguru")),
        "lock_profile": {
            "pyproject_sha256": _sha256_file(skill_root / "pyproject.toml"),
            "uv_lock_sha256": _sha256_file(skill_root / "uv.lock"),
        },
        "command": {
            "argv": list(argv),
            "projection_mode": projection_mode,
        },
        "source": _source_identity(source_root),
        "environment": {
            name: {"present": name in os.environ}
            for name in ALLOWLISTED_ENV_NAMES
        },
        "mutable_paths": {
            "run_root": os.environ.get("INGEST_CODE_RUN_ROOT"),
            "uv_project_environment": os.environ.get("UV_PROJECT_ENVIRONMENT"),
            "uv_cache_dir": os.environ.get("UV_CACHE_DIR"),
            "python_pycache_prefix": os.environ.get("PYTHONPYCACHEPREFIX"),
            "tmpdir": os.environ.get("TMPDIR"),
        },
        "external_effect_policy": {
            "projection_mode": projection_mode,
            "memory_effect_allowed": projection_mode == "apply",
        },
        "terminal_status": terminal_status,
        "non_claims": [
            "locked_local_process_is_not_container_or_vm_sandbox",
            "environment_manifest_is_not_projection_activation",
            "environment_identity_is_separate_from_static_code_graph_identity",
        ],
    }
    digest = _sha256_bytes(json.dumps(stable, sort_keys=True).encode("utf-8"))
    return {
        **stable,
        "environment_manifest_digest": digest,
        "observed_at": datetime.now(UTC).isoformat(),
    }


def write_environment_manifest(
    path: Path,
    *,
    skill_root: Path,
    source_root: Path,
    projection_mode: str,
    argv: list[str],
    terminal_status: str = "complete",
) -> dict[str, Any]:
    """Write the environment manifest and return a compact artifact ref."""
    manifest = build_environment_manifest(
        skill_root=skill_root,
        source_root=source_root,
        projection_mode=projection_mode,
        argv=argv,
        terminal_status=terminal_status,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schema": "ingest-code.environment_manifest_artifact.v1",
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "environment_manifest_digest": manifest["environment_manifest_digest"],
        "admissible": True,
    }
