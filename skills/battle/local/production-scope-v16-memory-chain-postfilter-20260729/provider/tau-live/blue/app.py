"""Public bounded package-import contract for strategy qualification.

This replacement preserves the public import_zip(zip_path, destination) contract while
adding evidence-targeted boundary controls around archive member extraction.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from zipfile import ZipFile, ZipInfo


def _is_within_directory(root: Path, target: Path) -> bool:
    """Return True when target is contained by root after filesystem resolution."""
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _is_symlink(member: ZipInfo) -> bool:
    """Detect Unix-style symlink entries in a zip archive."""
    mode = (member.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _safe_member_path(root: Path, member_name: str) -> Path:
    """Map a zip member name to a safe destination path under root.

    Rejects absolute paths, drive-qualified paths, empty names, parent traversal,
    and paths that resolve outside the destination root.
    """
    normalized = member_name.replace("\\", "/")
    candidate = Path(normalized)

    if not normalized or normalized in {".", "./"}:
        raise ValueError(f"unsafe zip member path: {member_name!r}")
    if candidate.is_absolute() or os.path.isabs(normalized):
        raise ValueError(f"unsafe zip member path: {member_name!r}")
    if candidate.drive or candidate.root:
        raise ValueError(f"unsafe zip member path: {member_name!r}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError(f"unsafe zip member path: {member_name!r}")

    target = (root / candidate).resolve(strict=False)
    if not _is_within_directory(root, target):
        raise ValueError(f"unsafe zip member path: {member_name!r}")
    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Import regular files from zip_path into destination.

    The function keeps the original public behavior of creating destination,
    extracting non-directory files, and returning written file paths. It adds a
    bounded trust boundary: archive members must resolve inside destination and
    symlink entries are rejected rather than materialized.
    """
    root = Path(destination).resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if _is_symlink(member):
                raise ValueError(f"unsafe zip member type: {member.filename!r}")

            target = _safe_member_path(root, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            written.append(str(target))
    return written


BASELINE_STRATEGY = {
    "selected_methods": ["evidence-targeted-boundary-control"],
    "rejected_methods": ["global-service-quarantine"],
    "parameters": {"control_scope": "measured_trust_boundary", "preserve_functionality": True},
    "mutation_origin": "durable_memory",
    "expected_observation": "contain the evidenced trust boundary while preserving the public functionality contract",
}
