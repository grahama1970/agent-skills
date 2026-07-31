"""app - blue.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from pathlib import Path
from zipfile import ZipFile, ZipInfo
import os
import stat


class UnsafeArchivePath(ValueError):
    """Raised when an archive member would write outside the destination."""


def _is_symlink(info: ZipInfo) -> bool:
    """Return True if a ZipInfo entry represents a Unix symbolic link."""
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _safe_target(destination: Path, member_name: str) -> Path:
    """Resolve a zip member path and ensure it remains inside destination."""
    if not member_name or member_name.startswith(("/", "\\")):
        raise UnsafeArchivePath(f"unsafe archive path: {member_name!r}")

    # Reject Windows drive paths and UNC-like names even when running on POSIX.
    normalized_name = member_name.replace("\\", "/")
    first_part = normalized_name.split("/", 1)[0]
    if first_part.endswith(":") or normalized_name.startswith("//"):
        raise UnsafeArchivePath(f"unsafe archive path: {member_name!r}")

    dest_resolved = destination.resolve()
    target = (dest_resolved / normalized_name).resolve()

    try:
        target.relative_to(dest_resolved)
    except ValueError as exc:
        raise UnsafeArchivePath(f"unsafe archive path: {member_name!r}") from exc

    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination.

    The function preserves the public behavior of importing archive contents into
    an import workspace, but blocks zip-slip path traversal, absolute paths,
    drive-qualified paths, UNC-style paths, and symlink entries.
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            target = _safe_target(dest_resolved, name)

            if _is_symlink(info):
                raise UnsafeArchivePath(f"refusing symlink archive entry: {name!r}")

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
