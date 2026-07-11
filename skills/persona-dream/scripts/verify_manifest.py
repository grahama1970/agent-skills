#!/usr/bin/env python3
"""Verify MANIFEST.json SHA-256 entries for this patch bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=Path("MANIFEST.json"))
    args = parser.parse_args(argv)

    manifest_path = args.manifest.resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        expected = entry["sha256"]
        actual_path = root / rel
        if not actual_path.exists():
            errors.append(f"missing: {rel}")
            continue
        actual = sha256_file(actual_path)
        if actual != expected:
            errors.append(f"sha256 mismatch: {rel}: expected {expected}, got {actual}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"manifest verification passed ({len(manifest.get('files', []))} files)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
