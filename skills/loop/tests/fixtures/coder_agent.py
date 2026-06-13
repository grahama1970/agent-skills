#!/usr/bin/env python3
"""Fixture write-capable coder for loop.py tests."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ALLOWED_LOOP_ENV = {"LOOP_ATTEMPT", "LOOP_FIXTURE_MODE", "LOOP_ROLE", "LOOP_REPO"}


def leaked_loop_env() -> list[str]:
    return sorted(key for key in os.environ if key.startswith("LOOP_") and key not in ALLOWED_LOOP_ENV)


def write_good(repo: Path) -> None:
    src = repo / "sample-target/src/time/parse_duration.py"
    tests = repo / "sample-target/tests/test_parse_duration.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    tests.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        '''"""Duration parsing helpers."""\n\nimport re\n\n\ndef parse_duration(value: str) -> int:\n    total = 0\n    for amount, unit in re.findall(r"(\\d+)\\s*([hms])", value.lower()):\n        n = int(amount)\n        if unit == "h":\n            total += n * 3600\n        elif unit == "m":\n            total += n * 60\n        elif unit == "s":\n            total += n\n    if total == 0:\n        raise ValueError("invalid duration")\n    return total\n''',
        encoding="utf-8",
    )
    tests.write_text(
        """import unittest\n\nfrom sample_target_import import parse_duration\n\n\nclass ParseDurationTests(unittest.TestCase):\n    def test_hours_and_minutes(self):\n        self.assertEqual(parse_duration('1h 30m'), 5400)\n\n    def test_seconds(self):\n        self.assertEqual(parse_duration('45s'), 45)\n\n    def test_invalid(self):\n        with self.assertRaises(ValueError):\n            parse_duration('bad input')\n\n\nif __name__ == '__main__':\n    unittest.main()\n""",
        encoding="utf-8",
    )
    (tests.parent / "sample_target_import.py").write_text(
        """import importlib.util\nfrom pathlib import Path\n\nmodule_path = Path(__file__).resolve().parents[1] / 'src/time/parse_duration.py'\nspec = importlib.util.spec_from_file_location('parse_duration_module', module_path)\nmodule = importlib.util.module_from_spec(spec)\nassert spec.loader is not None\nspec.loader.exec_module(module)\nparse_duration = module.parse_duration\n""",
        encoding="utf-8",
    )


def write_bad(repo: Path) -> None:
    src = repo / "sample-target/src/time/parse_duration.py"
    tests = repo / "sample-target/tests/test_parse_duration.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    tests.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def parse_duration(value: str) -> int:\n    return 0\n", encoding="utf-8")
    tests.write_text(
        """import unittest\n\nfrom sample_target_import import parse_duration\n\n\nclass ParseDurationTests(unittest.TestCase):\n    def test_hours_and_minutes(self):\n        self.assertEqual(parse_duration('1h 30m'), 5400)\n\n\nif __name__ == '__main__':\n    unittest.main()\n""",
        encoding="utf-8",
    )
    (tests.parent / "sample_target_import.py").write_text(
        """import importlib.util\nfrom pathlib import Path\n\nmodule_path = Path(__file__).resolve().parents[1] / 'src/time/parse_duration.py'\nspec = importlib.util.spec_from_file_location('parse_duration_module', module_path)\nmodule = importlib.util.module_from_spec(spec)\nassert spec.loader is not None\nspec.loader.exec_module(module)\nparse_duration = module.parse_duration\n""",
        encoding="utf-8",
    )


def main() -> int:
    _prompt = sys.stdin.read()
    repo = Path(os.environ["LOOP_REPO"])
    mode = os.environ.get("LOOP_FIXTURE_MODE", "pass")
    leaked = leaked_loop_env()
    if mode == "assert_no_artifact_access" and leaked:
        print(json.dumps({"changed_files_summary": "unexpected LOOP_* exposure", "mode": mode, "leaked": leaked}))
        return 9
    if mode == "disallowed":
        (repo / "outside.txt").write_text("not allowed\n", encoding="utf-8")
    elif mode == "disallowed_fail":
        (repo / "outside.txt").write_text("not allowed\n", encoding="utf-8")
        print(json.dumps({"changed_files_summary": "wrote disallowed file then failed", "mode": mode}))
        return 1
    elif mode == "disallowed_timeout":
        (repo / "outside.txt").write_text("not allowed\n", encoding="utf-8")
        time.sleep(10)
    elif mode in {"check_fail", "max_attempts"}:
        write_bad(repo)
    else:
        write_good(repo)
    print(json.dumps({"changed_files_summary": "fixture coder completed", "mode": mode}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
