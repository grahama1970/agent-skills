#!/usr/bin/env python3
"""Seat-matrix eval (#1652).

Validates the LIVE registry (every registered project's repair seat pair must be
contract-valid) and fault-injects each violation class (non-authoring/oc- creator,
same-provider reviewer, browser reviewer) to prove the validator rejects them
before any lease is burned.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import seat_matrix  # noqa: E402

REGISTRY = Path(__file__).resolve().parents[1] / "registry" / "projects.json"


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected) -> None:
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    # Live registry must be contract-valid.
    projects = json.loads(REGISTRY.read_text())["projects"]
    live_failures = seat_matrix.validate_registry(projects)
    check("live_registry_clean", live_failures, [])
    check("live_registry_nonempty", len(projects) > 0, True)

    # Positive control.
    check("valid_pair_ok", seat_matrix.validate_pair("gpt-5.5-high", "zai-glm-high"), None)

    # Each violation class is rejected (error string, not None).
    check("oc_creator_rejected",
          seat_matrix.validate_pair("opencode-go/deepseek-v4-flash", "zai-glm-high") is not None, True)
    check("same_provider_reviewer_rejected",
          seat_matrix.validate_pair("gpt-5.5-high", "gpt-5.5-low") is not None, True)
    check("browser_reviewer_rejected",
          seat_matrix.validate_pair("gpt-5.5-high", "webgpt") is not None, True)

    # A fault-injected registry names the offending project only.
    injected = list(projects) + [{"project_id": "INJECTED_BAD",
                                   "repair_creator": "opencode-go/deepseek-v4-flash",
                                   "repair_reviewer": "zai-glm-high"}]
    f = seat_matrix.validate_registry(injected)
    check("injected_bad_caught", [x["project_id"] for x in f], ["INJECTED_BAD"])

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.seat_matrix_eval.v1", "mocked": False, "live": True,
              "passed": passed, "checks": checks, "registry": str(REGISTRY)}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-seat-matrix.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
