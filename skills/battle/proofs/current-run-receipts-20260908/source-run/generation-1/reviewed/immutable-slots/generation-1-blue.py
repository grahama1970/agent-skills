from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def import_zip(zip_path, destination):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            member = PurePosixPath(name)
            if member.is_absolute() or '..' in member.parts:
                raise ValueError('unsafe zip member path')
            if not name or name.endswith('/'):
                continue
            target = dest.joinpath(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source:
                target.write_bytes(source.read())
            written.append(str(target))
    return written
