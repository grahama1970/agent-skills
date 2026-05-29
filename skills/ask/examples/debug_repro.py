"""Repro script for examples/run-debugger-stuck.sh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_target import normalize_handoff_id  # noqa: E402

if __name__ == "__main__":
    print(normalize_handoff_id("bad..id"))
