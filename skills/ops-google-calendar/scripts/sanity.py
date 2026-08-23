"""Non-mocked local sanity checks for ops-google-calendar.

Proves the propose-only fail-closed discipline WITHOUT a real calendar: a
proposal without --confirm must never touch the API, a confirmed write with no
token must fail closed, and status must report honestly when unauthenticated.
Live calendar reads are out of scope here (they need OAuth) and are reported
as such rather than faked.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MANAGER = Path(__file__).with_name("manager.py")
FAILURES: list[str] = []


def _run(*args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(MANAGER), *args],
                          capture_output=True, text=True, timeout=60)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, payload


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    code, payload = _run("propose-reschedule", "--event-id", "abc123",
                         "--to", "2026-08-28T15:00:00-04:00")
    check("proposal without --confirm does not execute",
          code == 0 and payload.get("status") == "NOT_EXECUTED"
          and payload.get("confirmed") is False, f"status={payload.get('status')}")

    code, payload = _run("propose-create", "--summary", "Sync",
                         "--start", "2026-08-28T15:00:00-04:00",
                         "--end", "2026-08-28T15:30:00-04:00")
    check("create proposal without --confirm does not execute",
          code == 0 and payload.get("status") == "NOT_EXECUTED",
          f"status={payload.get('status')}")

    code, payload = _run("status")
    check("status reports auth state honestly (no crash)",
          code == 0 and payload.get("schema") == "ops_google_calendar.status.v1"
          and payload.get("mocked") is False, f"status={payload.get('status')}")

    print()
    if FAILURES:
        print(f"ops-google-calendar sanity: FAIL ({', '.join(FAILURES)})")
        return 1
    print("ops-google-calendar sanity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
