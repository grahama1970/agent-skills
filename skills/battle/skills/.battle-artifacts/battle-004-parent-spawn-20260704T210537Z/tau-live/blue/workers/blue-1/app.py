from pathlib import Path
from zipfile import ZipFile


def import_zip(zip_path: str, destination: str) -> list[str]:
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with ZipFile(zip_path) as archive:
        # Resolve the destination path once to its absolute, canonical form
        absolute_dest_path = dest.resolve()

        for name in archive.namelist():
            # Construct the full path by joining the destination with the archive member name.
            # This path is still potentially malicious if 'name' contains '..'
            target_path = dest / name

            # Resolve the target path to its absolute, canonical form.
            # This will resolve any '..' components in 'name'.
            # Use strict=False because the path might not exist yet.
            try:
                absolute_target_path = target_path.resolve(strict=False)
            except RuntimeError:
                # Handle cases where path resolution itself fails (e.g., invalid characters)
                print(f"Skipping problematic path resolution for: {name}")
                continue

            # Crucial security check: Ensure the resolved target path is a sub-path
            # of the resolved destination path. If not, it's a path traversal attempt.
            if not absolute_target_path.is_relative_to(absolute_dest_path):
                print(f"Skipping potential path traversal attempt: {name} (resolved to {absolute_target_path})")
                continue

            # If the entry is a directory (ends with '/'), create it and continue.
            # This handles creating subdirectories within the safe path.
            if name.endswith('/'):
                absolute_target_path.mkdir(parents=True, exist_ok=True)
                continue

            # Ensure parent directories exist for the file itself.
            absolute_target_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file content to the now-verified safe path.
            absolute_target_path.write_bytes(archive.read(name))
            written.append(str(absolute_target_path))
    return written
