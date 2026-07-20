from pathlib import Path
from zipfile import ZipFile, ZipInfo
import os


class UnsafeArchivePathError(ValueError):
    """Raised when a zip member would be written outside the destination."""


def _is_within_directory(base: Path, candidate: Path) -> bool:
    try:
        os.path.commonpath([str(base), str(candidate)]) == str(base)
        return os.path.commonpath([str(base), str(candidate)]) == str(base)
    except ValueError:
        return False


def _safe_target(base: Path, member_name: str) -> Path:
    # Zip names are specified as forward-slash paths, but reject backslashes too
    # so Windows-style traversal cannot bypass validation on any platform.
    if not member_name or "\x00" in member_name or "\\" in member_name:
        raise UnsafeArchivePathError(f"unsafe zip member path: {member_name!r}")

    member_path = Path(member_name)
    if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
        raise UnsafeArchivePathError(f"unsafe zip member path: {member_name!r}")

    target = (base / member_path).resolve(strict=False)
    if not _is_within_directory(base, target):
        raise UnsafeArchivePathError(f"unsafe zip member path: {member_name!r}")
    return target


def _is_symlink(info: ZipInfo) -> bool:
    # Unix file type bits are stored in the high 16 bits when present.
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def import_zip(zip_path: str, destination: str) -> list[str]:
    dest = Path(destination).resolve(strict=False)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            target = _safe_target(dest, name)

            if _is_symlink(info):
                raise UnsafeArchivePathError(f"refusing zip symlink member: {name!r}")

            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue

            parent = target.parent.resolve(strict=False)
            if not _is_within_directory(dest, parent):
                raise UnsafeArchivePathError(f"unsafe zip member parent: {name!r}")
            parent.mkdir(parents=True, exist_ok=True)

            # Refuse to overwrite an existing symlink inside the workspace, which
            # could otherwise redirect writes outside the destination.
            if target.exists() and target.is_symlink():
                raise UnsafeArchivePathError(f"refusing to overwrite symlink: {name!r}")

            target.write_bytes(archive.read(info))
            written.append(str(target))

    return written
