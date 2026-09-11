#!/usr/bin/env python3
"""Seat-routing eval (capability-aware fallback, WebGPT design).

Validates the LIVE shipped config (skills/project-watchdog/config/seat-routing.json)
against the capability invariant and asserts the designed resolution: the
repair_creator has no fallback and parks when codex is out; reviewers and closure
auditors are non-codex-first and drop the codex route when it is out. Fault-injects
a config whose author seat falls back to a review-only route and proves it is
rejected fail-closed before any dispatch could use it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import seat_routing as sr  # noqa: E402


def main() -> int:
    checks: list[dict] = []

    def check(name, got, expected):
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    cfg = sr.load()  # live shipped config; raises if invariant violated
    check("live_config_loads", cfg.get("version"), "project_watchdog.seat_routing.v1")
    check("creator_routes_codex_first", sr.resolve("repair_creator", cfg)["routes"], ["codex_author"])
    alt = sr.resolve("repair_creator", cfg, codex_out=True)
    # Operator directive 2026-09-11: OpenCode is DECOMMISSIONED. The opencode_author
    # route was removed; with no eligible non-codex authoring transport the creator
    # parks quietly (no lease burn) rather than dispatching through a dead rail.
    check("creator_parks_when_codex_out_no_opencode", alt["action"], "park")
    check("reviewer_non_codex_first", sr.resolve("repair_reviewer", cfg)["routes"][0], "glm_review")
    check("reviewer_drops_codex_when_out",
          "codex_author" in sr.resolve("repair_reviewer", cfg, codex_out=True)["routes"], False)
    check("auditor_non_codex_only", sr.resolve("closure_auditor", cfg)["routes"], ["glm_review", "kimi_review"])

    # Fault injection: author fallback to a non-authoring route must be rejected.
    bad = {
        "version": "project_watchdog.seat_routing.v1",
        "routes": {
            "codex_author": {"executor": "codex_cli", "model": "codex",
                             "capabilities": ["repo_workspace_author", "review"]},
            "glm_review": {"executor": "scillm", "model": "zai-glm-high", "capabilities": ["review"]},
        },
        "seat_profiles": {
            "repair_creator": {"requires": ["repo_workspace_author"],
                               "routes": ["codex_author", "glm_review"],
                               "when_unavailable": "park_on_quota"},
        },
    }
    rejected = False
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.json"; p.write_text(json.dumps(bad))
        try:
            sr.load(p)
        except sr.SeatRoutingError:
            rejected = True
    check("capability_violating_fallback_rejected", rejected, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.seat_routing_eval.v1", "mocked": False, "live": True,
              "passed": passed, "checks": checks,
              "config": str(sr.default_config_path())}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-seat-routing.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
