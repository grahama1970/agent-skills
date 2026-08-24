"""Non-mocked sanity checks for ops-calendly.

These checks exercise the production CLI with local fixture files and real
filesystem artifacts. They do not call the live Calendly API unless the caller
runs `doctor` separately with CALENDLY_PAT available.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

SKILL_DIR = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_DIR / "run.sh"
FIXTURES = SKILL_DIR / "fixtures"
FAILURES: list[str] = []


def _run(*args: str) -> tuple[int, dict[str, object], str]:
    proc = subprocess.run(
        [str(RUN_SH), *args],
        capture_output=True,
        text=True,
        timeout=90,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, payload, proc.stderr


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    with TemporaryDirectory(prefix="ops-calendly-sanity-") as tmp:
        out = Path(tmp) / "calendly.json"
        code, payload, _ = _run(
            "generate-site-metadata",
            "--fixture-me", str(FIXTURES / "sample_user_me.json"),
            "--fixture-event-types", str(FIXTURES / "sample_event_types.json"),
            "--out", str(out),
        )
        check(
            "fixture metadata writes validated public JSON",
            code == 0
            and payload.get("status") == "WROTE"
            and out.is_file()
            and json.loads(out.read_text(encoding="utf-8")).get("seam_validation", {}).get("status") == "PASS",
            f"status={payload.get('status')}",
        )

    code, payload, _ = _run(
        "capacity-holds", "plan",
        "--week", "current",
        "--today", "2026-08-24",
        "--target-ratio", "0.45",
    )
    check(
        "capacity hold plan is dry-run and caps at 45 percent",
        code == 0
        and payload.get("status") == "PLANNED"
        and payload.get("writesCalendar") is False
        and payload.get("targetRatio") == 0.45
        and payload.get("plannedHoldCount") == 15,
        f"status={payload.get('status')} holds={payload.get('plannedHoldCount')}",
    )

    code, payload, stderr = _run(
        "capacity-holds", "plan",
        "--week", "current",
        "--today", "2026-08-24",
        "--target-ratio", "0.46",
    )
    check(
        "capacity hold planner rejects ratios above 45 percent",
        code != 0 and "0.45" in stderr,
        f"code={code} status={payload.get('status')}",
    )

    code, payload, _ = _run("github-secret", "--repo", "grahama1970/agent-skills")
    check(
        "github-secret defaults to dry-run",
        code == 0 and payload.get("status") == "DRY_RUN" and payload.get("execute") is False,
        f"status={payload.get('status')}",
    )

    print()
    if FAILURES:
        print(f"ops-calendly sanity: FAIL ({', '.join(FAILURES)})")
        return 1
    print("ops-calendly sanity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
