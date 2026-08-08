"""app - blue.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from pathlib import Path
from zipfile import ZipFile


def import_zip(zip_path: str, destination: str) -> list[str]:
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with ZipFile(zip_path) as archive:
        for name in archive.namelist():
            # Construct the full path for the file within the destination
            target = dest / name

            # Resolve the path to handle '..' and other special components
            # This is crucial for preventing path traversal attacks (zip slip)
            resolved_target = target.resolve()

            # Ensure the resolved path is still within the intended destination directory.
            # If not, it indicates a path traversal attempt, and the file should be skipped.
            if not resolved_target.is_relative_to(dest):
                print(f"Skipping potentially malicious file: {name} (resolved to {resolved_target})")
                continue  # Skip this file to prevent writing outside the intended directory

            # Ensure the parent directory exists for the safe, resolved target
            resolved_target.parent.mkdir(parents=True, exist_ok=True)

            # Write the file to the safe, resolved target path
            resolved_target.write_bytes(archive.read(name))
            written.append(str(resolved_target))
    return written
