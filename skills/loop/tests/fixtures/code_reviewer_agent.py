#!/usr/bin/env python3
"""Fixture read-only reviewer for loop.py tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ALLOWED_LOOP_ENV = {"LOOP_ATTEMPT", "LOOP_FIXTURE_MODE", "LOOP_ROLE", "LOOP_REPO"}


def leaked_loop_env() -> list[str]:
    return sorted(key for key in os.environ if key.startswith("LOOP_") and key not in ALLOWED_LOOP_ENV)


def main() -> int:
    _prompt = sys.stdin.read()
    mode = os.environ.get("LOOP_FIXTURE_MODE", "pass")
    if mode == "assert_no_artifact_access":
        prompt = json.loads(_prompt)
        failures = []
        leaked = leaked_loop_env()
        if leaked:
            failures.append(f"unexpected LOOP_* exposure: {', '.join(leaked)}")
        if "diff_path" in prompt:
            failures.append("diff_path exposed")
        if "diff_text" not in prompt:
            failures.append("diff_text missing")
        if "check_results" not in prompt:
            failures.append("check_results missing")
        if failures:
            print(json.dumps({"verdict": "BLOCKED", "findings": failures}))
            return 0
        print(json.dumps({"verdict": "PASS", "findings": []}))
        return 0
    if mode == "invalid_review":
        print("not json")
        return 0
    if mode == "invalid_findings":
        print(json.dumps({"verdict": "PASS", "findings": "not a list"}))
        return 0
    if mode == "reviewer_edit":
        repo = Path(os.environ["LOOP_REPO"])
        (repo / "sample-target/src/time/reviewer_edit.py").write_text("# reviewer edited\n", encoding="utf-8")
    if mode == "reviewer_edit_disallowed":
        repo = Path(os.environ["LOOP_REPO"])
        (repo / "outside.txt").write_text("reviewer edited outside scope\n", encoding="utf-8")
    if mode in {"max_attempts"}:
        print(json.dumps({"verdict": "NEEDS_CHANGES", "findings": ["fixture asks for another attempt"]}))
        return 0
    print(json.dumps({"verdict": "PASS", "findings": []}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
