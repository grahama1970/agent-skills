#!/usr/bin/env python3
"""Generate public Calendly metadata via the ops-calendly skill.

The site keeps only a thin wrapper so Calendly API behavior, token handling,
and public-metadata validation live in one operational skill. `CALENDLY_PAT`
remains a build-time/server-side credential; the emitted JSON contains only
public scheduling metadata.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
OUT = SITE / "calendly.json"
OPS_CALENDLY = REPO / "skills" / "ops-calendly" / "run.sh"


def _uv_environment() -> str:
    configured = os.environ.get("OPS_CALENDLY_UV_ENV") or os.environ.get("UV_PROJECT_ENVIRONMENT")
    if configured:
        return configured
    runner_tmp = os.environ.get("RUNNER_TEMP")
    base = Path(runner_tmp) if runner_tmp else Path(tempfile.gettempdir())
    return str(base / "ops-calendly-uv")


def main() -> int:
    if not OPS_CALENDLY.is_file():
        print(f"error: missing ops-calendly entrypoint at {OPS_CALENDLY}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = _uv_environment()
    proc = subprocess.run(
        [
            str(OPS_CALENDLY),
            "generate-site-metadata",
            "--out",
            str(OUT),
            "--no-json",
        ],
        cwd=str(OPS_CALENDLY.parent),
        env=env,
        check=False,
        timeout=120,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
