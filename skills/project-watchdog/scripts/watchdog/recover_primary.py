#!/usr/bin/env python3
"""Executable native lifecycle recovery; never launches a replacement worker."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import primary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = primary.reconcile(args.root) if args.apply else primary.pending(args.root)
    print(json.dumps(result or {"ok": True, "pending": False}, indent=2))
    return 1 if result and (result.get("operations") or result.get("invalid_operations")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
