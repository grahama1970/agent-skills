"""Evaluator lock verification for Battle campaign execution.

The lock is independent authority: campaign requests may point at executable
components, but they do not get to supply the expected digest for those files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .strict_json import finite_json_values, load_path

LOCK_SCHEMA = "battle.evaluator_lock.v1"
BATTLE_REL = Path("skills/battle/src/battle_skill/evaluator_lock.py")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_path(root: Path, rel: str) -> Path:
    path = Path(rel)
    return path if path.is_absolute() else root / path


def _manifest_digest(root: Path, files: list[str]) -> str:
    manifest = [[rel, _sha256_file(_bundle_path(root, rel))] for rel in files]
    manifest.sort()
    return "sha256:" + hashlib.sha256(json.dumps(manifest).encode()).hexdigest()


def _repo_root_from_this_file() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / BATTLE_REL).is_file():
            return parent
    raise ValueError("lock-verification-failed: cannot resolve Battle repo root")


def verify_evaluator_lock(lock_path: str | Path, request: dict[str, Any]) -> dict[str, Any]:
    """Verify executable evaluator files against an approved lock."""
    try:
        lock = load_path(lock_path)
        if not isinstance(lock, dict):
            raise ValueError("lock must be a JSON object")
        if lock.get("schema") != LOCK_SCHEMA:
            raise ValueError(f"lock schema must be {LOCK_SCHEMA}")
        if not finite_json_values(lock):
            raise ValueError("lock contains non-finite numeric value")
        files = lock.get("bundle_files")
        if not isinstance(files, list) or not files or any(not isinstance(item, str) or not item.strip() for item in files):
            raise ValueError("lock bundle_files must be a non-empty string list")
        if len(set(files)) != len(files):
            raise ValueError("lock bundle_files contains duplicates")
        expected = lock.get("bundle_manifest_sha256")
        if not isinstance(expected, str) or not expected.startswith("sha256:"):
            raise ValueError("lock bundle_manifest_sha256 is required")
        root = Path(lock.get("source_repo_path") or _repo_root_from_this_file()).resolve()
        missing = [rel for rel in files if not _bundle_path(root, rel).is_file()]
        if missing:
            raise ValueError(f"lock bundle files missing: {missing}")
        actual = _manifest_digest(root, files)
        if actual != expected:
            raise ValueError(f"lock bundle manifest mismatch: {actual} != {expected}")
        required = {
            "generator": request.get("generator"),
            "judge": request.get("judge"),
            "functional_judge": request.get("functional_judge"),
        }
        root_resolved = root.resolve()
        locked = {str(_bundle_path(root_resolved, rel).resolve()) for rel in files}
        for name, raw in required.items():
            resolved = str(Path(str(raw)).resolve())
            if resolved not in locked:
                raise ValueError(f"{name} not covered by evaluator lock: {resolved}")
        return {"schema": LOCK_SCHEMA + ".receipt", "status": "PASS", "lock_path": str(lock_path), "bundle_manifest_sha256": actual, "problems": []}
    except Exception as exc:
        return {"schema": LOCK_SCHEMA + ".receipt", "status": "BLOCKED", "lock_path": str(lock_path), "bundle_manifest_sha256": None, "problems": [f"lock-verification-failed:{exc}"]}
