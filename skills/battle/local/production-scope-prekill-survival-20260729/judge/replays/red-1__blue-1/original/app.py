from pathlib import Path
from zipfile import ZipFile


def import_zip(zip_path: str, destination: str) -> list[str]:
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for name in archive.namelist():
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
            written.append(str(target))
    return written
