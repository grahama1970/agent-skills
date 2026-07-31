from __future__ import annotations

import os
from pathlib import Path
from zipfile import ZipFile, ZipInfo


class UnsafeArchiveError(ValueError):
    """Raised when a zip archive contains an unsafe member path."""


def _is_zip_symlink(info: ZipInfo) -> bool:
    # On Unix-created zip files, the file type is stored in the upper 16 bits of
    # external_attr. 0o120000 is a symbolic link. Windows-created archives will
    # normally not set this, so this check is conservative and harmless there.
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _safe_target(destination: Path, member_name: str) -> Path:
    if not member_name or "\x00" in member_name:
        raise UnsafeArchiveError("zip member has an empty or invalid name")

    # Normalize zip separators before pathlib processing. Backslashes are path
    # separators on Windows and are commonly accepted by tooling, so treat them
    # as separators on every platform to avoid cross-platform traversal gaps.
    normalized_name = member_name.replace("\\", "/")
    member_path = Path(normalized_name)

    if member_path.is_absolute():
        raise UnsafeArchiveError(f"absolute zip member path rejected: {member_name!r}")

    if any(part in ("", ".", "..") for part in member_path.parts):
        raise UnsafeArchiveError(f"unsafe zip member path rejected: {member_name!r}")

    dest_root = destination.resolve()
    target = (dest_root / member_path).resolve()

    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise UnsafeArchiveError(f"zip member escapes destination: {member_name!r}") from exc

    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination and return written paths.

    Security properties:
    - rejects absolute paths and parent-directory traversal
    - treats both '/' and '\\' as separators
    - rejects symbolic-link entries
    - creates only directories/files inside the resolved destination root
    - skips directory entries in the returned written-file list
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()

    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            target = _safe_target(dest_root, name)

            if _is_zip_symlink(info):
                raise UnsafeArchiveError(f"symbolic link zip member rejected: {name!r}")

            if info.is_dir() or name.endswith(("/", "\\")):
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            written.append(str(target))

    return written
