"""Public bounded package-import contract for strategy qualification."""
from pathlib import Path
from zipfile import ZipFile

def import_zip(zip_path: str, destination: str) -> list[str]:
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = root / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            written.append(str(target))
    return written

BASELINE_STRATEGY = {'selected_methods': ['global-service-quarantine'], 'parameters': {'control_scope': 'global', 'preserve_functionality': False}}
