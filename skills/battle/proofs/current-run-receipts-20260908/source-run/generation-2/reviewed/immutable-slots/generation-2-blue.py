from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile


def _safe_parts(name):
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("unsafe zip member")
    parts = posix_path.parts
    if not parts or any(part in ("..", "") for part in parts):
        raise ValueError("unsafe zip member")
    return parts


def import_zip(zip_path, destination):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            parts = _safe_parts(info.filename)
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                written.append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source:
                target.write_bytes(source.read())
            written.append(str(target))
    return written
