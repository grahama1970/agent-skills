"""app - blue.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import stat
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile, ZipInfo


class UnsafeArchivePath(ValueError):
    """Raised when a zip member would escape or otherwise endanger the import root."""


def _is_zip_symlink(info: ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _validate_member(info: ZipInfo, destination_root: Path) -> Path:
    name = info.filename

    if not name or "\x00" in name:
        raise UnsafeArchivePath(f"unsafe zip member name: {name!r}")

    # Zip member names are specified as POSIX-style paths. Reject backslashes so
    # Windows path separators cannot be smuggled through on any platform.
    if "\\" in name:
        raise UnsafeArchivePath(f"backslash path separators are not allowed: {name!r}")

    if _is_zip_symlink(info):
        raise UnsafeArchivePath(f"zip symlink entries are not allowed: {name!r}")

    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)

    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafeArchivePath(f"absolute or drive-qualified paths are not allowed: {name!r}")

    parts = posix_path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeArchivePath(f"relative traversal or ambiguous path component is not allowed: {name!r}")

    target = (destination_root / Path(*parts)).resolve(strict=False)
    try:
        target.relative_to(destination_root)
    except ValueError as exc:
        raise UnsafeArchivePath(f"zip member escapes destination: {name!r}") from exc

    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely import a zip archive into destination and return written file paths.

    The function preserves the original callable contract while preventing Zip
    Slip/path traversal. The whole archive is validated before any filesystem
    writes occur, so unsafe archives fail closed without partially importing
    earlier members.
    """

    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    destination_root = dest.resolve(strict=True)

    with ZipFile(zip_path) as archive:
        infos = archive.infolist()
        planned: list[tuple[ZipInfo, Path]] = [
            (info, _validate_member(info, destination_root)) for info in infos
        ]

        written: list[str] = []
        for info, target in planned:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            written.append(str(target))

    return written


try:
    from flask import Flask, jsonify, request
except Exception:  # pragma: no cover - core import_zip remains dependency-free.
    Flask = None
    app = None
else:
    app = Flask(__name__)

    @app.post("/api/import-zip")
    def import_zip_endpoint():
        upload = request.files.get("file") or request.files.get("zip") or request.files.get("archive")
        if upload is None:
            return jsonify({"error": "missing zip file upload"}), 400

        destination = request.form.get("destination") or request.form.get("dest")
        cleanup_destination = False
        if not destination:
            destination = tempfile.mkdtemp(prefix="import-workspace-")
            cleanup_destination = False

        with tempfile.NamedTemporaryFile(prefix="upload-", suffix=".zip", delete=False) as tmp:
            upload.save(tmp.name)
            tmp_path = tmp.name

        try:
            written = import_zip(tmp_path, destination)
        except UnsafeArchivePath as exc:
            return jsonify({"error": "unsafe archive path", "detail": str(exc)}), 400
        finally:
            try:
                Path(tmp_path).unlink()
            except FileNotFoundError:
                pass

        return jsonify({"written": written, "destination": destination, "cleanup_destination": cleanup_destination})
