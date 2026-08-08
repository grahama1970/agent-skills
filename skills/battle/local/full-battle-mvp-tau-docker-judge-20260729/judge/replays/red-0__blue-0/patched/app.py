"""app - patched.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile, ZipInfo


class UnsafeArchiveMember(ValueError):
    """Raised when a zip member would escape or subvert the destination."""


def _is_zip_symlink(info: ZipInfo) -> bool:
    # Unix file type bits are stored in the high 16 bits of external_attr.
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _safe_relative_parts(name: str) -> tuple[str, ...]:
    if not name or "\x00" in name:
        raise UnsafeArchiveMember("zip member has an empty or invalid name")

    # Zip paths are specified with forward slashes. Reject backslashes and
    # Windows drive/UNC forms so behavior is safe and consistent across OSes.
    if "" in name:
        raise UnsafeArchiveMember(f"unsafe zip member path: {name!r}")
    if PureWindowsPath(name).drive:
        raise UnsafeArchiveMember(f"unsafe zip member path: {name!r}")

    rel = PurePosixPath(name)
    if rel.is_absolute():
        raise UnsafeArchiveMember(f"absolute zip member path is not allowed: {name!r}")

    parts = rel.parts
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeArchiveMember(f"path traversal zip member is not allowed: {name!r}")

    return tuple(parts)


def _safe_target(dest_root: Path, parts: tuple[str, ...]) -> Path:
    target = (dest_root / Path(*parts)).resolve(strict=False)
    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise UnsafeArchiveMember("zip member resolves outside destination") from exc
    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination.

    Defenses:
    - rejects absolute paths, drive-qualified paths, backslashes, NUL bytes, and '..'
    - verifies resolved targets remain under the destination directory
    - rejects symlink entries to prevent link-based write redirection
    - validates the full archive before writing files, avoiding partial extraction
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve(strict=True)

    with ZipFile(zip_path) as archive:
        planned: list[tuple[ZipInfo, Path]] = []
        seen_targets: set[Path] = set()

        for info in archive.infolist():
            if _is_zip_symlink(info):
                raise UnsafeArchiveMember(f"symlink zip member is not allowed: {info.filename!r}")

            parts = _safe_relative_parts(info.filename.rstrip("/"))
            target = _safe_target(dest_root, parts)

            if target in seen_targets:
                raise UnsafeArchiveMember(f"duplicate zip member target is not allowed: {info.filename!r}")
            seen_targets.add(target)
            planned.append((info, target))

        written: list[str] = []
        for info, target in planned:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, open(target, "wb") as output:
                output.write(source.read())
            written.append(str(target))

    return written