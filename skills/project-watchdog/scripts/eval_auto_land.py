#!/usr/bin/env python3
"""Guard: alpha projects auto-land a reviewer-passed repair on main.

Operator rule: while a project is alpha/pre-stable, main is the single
directly-pushable branch. A reviewer-passed repair should land on main, not sit
as a branch awaiting a human. This guard checks the config gate and that the
landing step is wired into the repair path and fails closed on git errors.
"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from watchdog import config as c, handlers as h  # noqa: E402

def main() -> int:
    f = []
    if c.auto_land_main({"auto_land_main": True}) is not True:
        f.append("FLAG_TRUE_NOT_HONORED")
    if c.auto_land_main({"auto_land_main": False}) is not False:
        f.append("FLAG_FALSE_NOT_HONORED")
    if c.auto_land_main({}) is not False:
        f.append("DEFAULT_NOT_OFF: auto-land must default off for unset projects")
    src = inspect.getsource(h.handle_ticket_repair)
    if "auto_land_main" not in src or "_land_repair_to_main" not in src:
        f.append("AUTO_LAND_NOT_WIRED: repair path does not call the landing step")
    lsrc = inspect.getsource(h._land_repair_to_main)
    if "abort" not in lsrc:
        f.append("NO_FAIL_CLOSED: landing must abort a rebase conflict, not force main")
    if f:
        for x in f: print(x, file=sys.stderr)
        return 1
    print("AUTO_LAND_OK: alpha projects land reviewer-passed repairs on main; fails closed on conflict")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
