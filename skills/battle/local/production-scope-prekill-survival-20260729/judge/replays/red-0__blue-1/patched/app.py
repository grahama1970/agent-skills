from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile, ZipInfo


class UnsafeArchiveError(ValueError):
    """Raised when a zip member would escape or tamper with the destination."""


_MAX_MEMBERS = 10_000
_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _is_zip_symlink(info: ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _safe_relative_path(name: str) -> Path:
    if not name or "\x00" in name:
        raise UnsafeArchiveError("zip member has an empty or invalid name")

    # ZIP paths are specified with forward slashes, but reject Windows-style
    # absolute paths and drive-qualified paths too so behavior is safe across OSes.
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise UnsafeArchiveError(f"absolute zip member path rejected: {name!r}")

    if "\\" in name:
        raise UnsafeArchiveError(f"backslash path separator rejected: {name!r}")

    parts = posix.parts
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeArchiveError(f"unsafe zip member path rejected: {name!r}")

    return Path(*parts)


def _ensure_within_directory(root: Path, candidate: Path) -> None:
    try:
        common = os.path.commonpath([str(root), str(candidate)])
    except ValueError as exc:
        raise UnsafeArchiveError("zip member path is on a different drive") from exc
    if common != str(root):
        raise UnsafeArchiveError(f"zip member escapes destination: {candidate}")


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination.

    The implementation rejects Zip Slip traversal attempts, absolute paths,
    Windows drive paths, symlink entries, pre-existing symlink targets, and
    archive shapes that exceed conservative size/member limits. Returned paths
    are the filesystem paths that were created or updated inside destination.
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve(strict=True)

    written: list[str] = []
    total_uncompressed = 0

    with ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise UnsafeArchiveError("zip archive contains too many members")

        for info in infos:
            if _is_zip_symlink(info):
                raise UnsafeArchiveError(f"symlink zip member rejected: {info.filename!r}")

            total_uncompressed += max(0, info.file_size)
            if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                raise UnsafeArchiveError("zip archive uncompressed size limit exceeded")

            relative = _safe_relative_path(info.filename)
            target = root / relative
            _ensure_within_directory(root, target.resolve(strict=False))

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                _ensure_within_directory(root, target.resolve(strict=True))
                written.append(str(target))
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            parent_real = target.parent.resolve(strict=True)
            _ensure_within_directory(root, parent_real)

            if target.exists() or target.is_symlink():
                if target.is_symlink():
                    raise UnsafeArchiveError(f"refusing to overwrite symlink: {target}")
                _ensure_within_directory(root, target.resolve(strict=True))

            with archive.open(info, "r") as source, open(target, "wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

            _ensure_within_directory(root, target.resolve(strict=True))
            written.append(str(target))

    return written
