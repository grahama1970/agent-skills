"""app - patched.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from pathlib import Path
from zipfile import ZipFile, BadZipFile
import os


class UnsafeArchivePathError(ValueError):
    """Raised when a zip member would escape the destination directory."""


def _safe_destination(base: Path, member_name: str) -> Path:
    """Return a safe extraction path for a zip member.

    Rejects absolute paths, drive-qualified paths, empty names, parent-directory
    traversal, and any normalized path that would resolve outside the intended
    extraction directory.
    """
    if not member_name or member_name.strip() == "":
        raise UnsafeArchivePathError("empty zip member name")

    normalized_name = member_name.replace("\\", "/")
    candidate = Path(normalized_name)

    if candidate.is_absolute() or candidate.drive:
        raise UnsafeArchivePathError(f"absolute zip member path rejected: {member_name!r}")

    if any(part in ("", ".", "..") for part in candidate.parts):
        raise UnsafeArchivePathError(f"unsafe zip member path rejected: {member_name!r}")

    target = (base / candidate).resolve()
    base_resolved = base.resolve()

    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafeArchivePathError(f"zip member escapes destination: {member_name!r}") from exc

    return target


def _is_symlink(info) -> bool:
    """Detect Unix symlink entries encoded in ZipInfo.external_attr."""
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination.

    This preserves the public behavior of importing files from a zip archive,
    while preventing Zip Slip path traversal and rejecting symlink entries that
    could redirect writes outside the workspace.
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest = dest.resolve()

    written: list[str] = []

    try:
        with ZipFile(zip_path) as archive:
            for info in archive.infolist():
                name = info.filename

                if _is_symlink(info):
                    raise UnsafeArchivePathError(f"symlink zip member rejected: {name!r}")

                target = _safe_destination(dest, name)

                if info.is_dir() or name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)

                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW

                fd = os.open(target, flags, 0o600)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(archive.read(info))
                except Exception:
                    os.close(fd)
                    raise

                written.append(str(target))
    except BadZipFile:
        raise

    return written
