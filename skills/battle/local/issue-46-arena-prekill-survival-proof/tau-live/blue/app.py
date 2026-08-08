"""app - blue.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from pathlib import Path
from zipfile import ZipFile, BadZipFile
import os
import shutil
import tempfile

try:
    from flask import Flask, jsonify, request
except Exception:  # Flask may not be present in direct unit-test environments.
    Flask = None
    jsonify = None
    request = None


class UnsafeArchiveEntry(ValueError):
    pass


def _is_zip_symlink(info) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _safe_target(base: Path, member_name: str) -> Path:
    if not member_name or "\x00" in member_name:
        raise UnsafeArchiveEntry("empty or invalid archive member name")

    normalized = member_name.replace("\\", "/")
    candidate = Path(normalized)

    if candidate.is_absolute() or os.path.isabs(normalized):
        raise UnsafeArchiveEntry(f"absolute archive path rejected: {member_name!r}")

    if any(part in ("", ".", "..") for part in candidate.parts):
        raise UnsafeArchiveEntry(f"unsafe archive path rejected: {member_name!r}")

    target = (base / candidate).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise UnsafeArchiveEntry(f"archive path escapes destination: {member_name!r}") from exc
    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    dest = Path(destination).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    try:
        with ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if _is_zip_symlink(info):
                    raise UnsafeArchiveEntry(f"symlink archive entry rejected: {info.filename!r}")

                target = _safe_target(dest, info.filename)

                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src, open(target, "xb") as out:
                    shutil.copyfileobj(src, out)
                written.append(str(target))
    except FileExistsError as exc:
        raise UnsafeArchiveEntry("refusing to overwrite existing destination file") from exc
    except BadZipFile:
        raise

    return written


if Flask is not None:
    app = Flask(__name__)

    @app.post("/api/import-zip")
    def import_zip_endpoint():
        uploaded = request.files.get("file") or request.files.get("zip") or request.files.get("archive")
        if uploaded is None:
            return jsonify({"error": "missing zip archive upload"}), 400

        destination = request.form.get("destination") or request.form.get("dest") or tempfile.mkdtemp(prefix="import-workspace-")

        with tempfile.NamedTemporaryFile(prefix="upload-", suffix=".zip", delete=True) as tmp:
            uploaded.save(tmp.name)
            try:
                files = import_zip(tmp.name, destination)
            except (UnsafeArchiveEntry, BadZipFile) as exc:
                return jsonify({"error": str(exc)}), 400

        return jsonify({"written": files})
else:
    app = None
