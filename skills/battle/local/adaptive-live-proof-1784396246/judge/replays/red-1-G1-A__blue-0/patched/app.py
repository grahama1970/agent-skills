from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile, ZipInfo
import stat


def _is_zipinfo_symlink(info: ZipInfo) -> bool:
    """Return True when a ZipInfo entry represents a Unix symbolic link."""
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _safe_join(destination: Path, archive_name: str) -> Path:
    """Resolve an archive member path under destination or raise ValueError."""
    if not archive_name or archive_name.startswith(("/", "\\")):
        raise ValueError(f"unsafe archive path: {archive_name!r}")

    member_path = Path(archive_name)
    if member_path.is_absolute() or any(part in ("..", "") for part in member_path.parts):
        raise ValueError(f"unsafe archive path: {archive_name!r}")

    dest_root = destination.resolve()
    target = (dest_root / member_path).resolve()

    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise ValueError(f"unsafe archive path: {archive_name!r}") from exc

    return target


def import_zip(zip_path: str, destination: str) -> list[str]:
    """Safely extract a zip archive into destination.

    The original implementation wrote each archive member to ``dest / name`` directly,
    which allowed Zip Slip path traversal such as ``../../outside``. This replacement
    validates every member before writing, rejects absolute/traversal paths and symbolic
    link entries, creates directories as needed, and only writes regular files whose
    resolved target remains inside the destination directory.
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()
    written: list[str] = []

    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename

            if _is_zipinfo_symlink(info):
                raise ValueError(f"unsafe archive entry type: {name!r}")

            target = _safe_join(dest_root, name)

            if info.is_dir() or name.endswith(("/", "\\")):
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            written.append(str(target))

    return written
