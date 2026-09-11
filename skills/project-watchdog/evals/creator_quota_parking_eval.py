#!/usr/bin/env python3
"""Creator-quota parking eval (#1651).

Deterministic (mocked=true): a quota/limit signal parks the repair lane with the
canonical code codex_handler_quota_exhausted, records a durable outage that
auto-resumes at the parsed reset time, and produces one stable dedup key; a
non-quota failure never parks. Recovery/native-close never consult the outage,
so they are unaffected. Isolated state root; no live provider.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import transport_health as th  # noqa: E402


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected) -> None:
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        th.config.state_root = lambda: root  # type: ignore[assignment]

        quota = "You've hit your usage limit. try again at Sep 14th, 2026 9:36 PM"
        r = th.park_on_quota("codex", quota)
        check("parked", r["parked"], True)
        check("canonical_code", r["code"], "codex_handler_quota_exhausted")
        check("stable_dedup_key", r["alert_dedup_key"], "codex:codex_handler_quota_exhausted")
        check("resume_at_in_future", r["resume_at"] > time.time(), True)
        check("outage_active", th.active_outage("codex") is not None, True)

        # classify surfaces the same canonical code (no *_unclassified churn).
        check("classify_quota", th.classify_transport_failure(quota), "codex_handler_quota_exhausted")
        check("classify_nonquota", th.classify_transport_failure("segfault at 0x0"), None)

        # A non-quota failure never parks and never records an outage.
        with tempfile.TemporaryDirectory() as td2:
            th.config.state_root = lambda: Path(td2)  # type: ignore[assignment]
            r2 = th.park_on_quota("codex", "connection reset by peer")
            check("nonquota_not_parked", r2["parked"], False)
            check("nonquota_no_outage", th.active_outage("codex") is None, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.creator_quota_parking_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-quota-park.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
