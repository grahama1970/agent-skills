#!/usr/bin/env python3
"""Fixture read-only explorer for loop.py tests."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ALLOWED_LOOP_ENV = {"LOOP_FIXTURE_MODE", "LOOP_ROLE", "LOOP_REPO"}


def leaked_loop_env() -> list[str]:
    return sorted(key for key in os.environ if key.startswith("LOOP_") and key not in ALLOWED_LOOP_ENV)


def main() -> int:
    _prompt = sys.stdin.read()
    repo = Path(os.environ["LOOP_REPO"])
    mode = os.environ.get("LOOP_FIXTURE_MODE", "pass")
    leaked = leaked_loop_env()
    if mode == "assert_no_artifact_access" and leaked:
        print(json.dumps({"summary": "unexpected LOOP_* exposure", "leaked": leaked}))
        return 9
    if mode == "explorer_write_disallowed_fail":
        (repo / "outside.txt").write_text("explorer wrote outside scope\n", encoding="utf-8")
        print(json.dumps({"summary": "explorer wrote outside scope then failed"}))
        return 1
    if mode == "explorer_write_allowed_success":
        target = repo / "sample-target/src/time/parse_duration.py"
        target.write_text("def parse_duration(value: str) -> int:\n    return 0\n", encoding="utf-8")
    if mode == "explorer_timeout_disallowed":
        (repo / "outside.txt").write_text("explorer wrote outside scope then timed out\n", encoding="utf-8")
        time.sleep(10)
    print(
        json.dumps(
            {
                "summary": "parse_duration currently needs implementation",
                "target_files": ["sample-target/src/time/parse_duration.py"],
                "test_files": ["sample-target/tests/test_parse_duration.py"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
