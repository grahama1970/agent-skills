#!/usr/bin/env python3
"""GOAL_V4 boundary checker — re-drives all evidence live.
V4.1 composer fixture probe rerun; V4.2 live matrix gate receipt with all
case gates true (probe itself hits live /intent + /tau/voice-render, so the
checker validates its fresh receipt rather than re-rendering); V4.3 loop
guard probe rerun + guard present in cycle source."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
SKILL = Path(__file__).resolve().parents[1]
G4 = SKILL / "reports/goal_v4"

def rerun(script):
    return subprocess.run([sys.executable, str(SKILL / "scripts" / script)],
                          capture_output=True, text=True, timeout=600)

def main() -> int:
    if "--json" not in sys.argv:
        pass  # flag accepted for the documented proof command
    r1 = rerun("probe_affect_composer.py")
    c1 = json.loads((G4 / "composer_probe_receipt.v1.json").read_text())
    v41 = r1.returncode == 0 and c1.get("passed") and len(c1.get("cases", {})) >= 7

    r2 = rerun("run_affect_matrix_probe.py")
    c2 = json.loads((G4 / "affect_matrix_probe_receipt.v1.json").read_text())
    v42 = (r2.returncode == 0 and c2.get("passed") and c2.get("live")
           and len(c2.get("cases", [])) == 4
           and all(x.get("gate") for x in c2["cases"])
           and all((x.get("render") or {}).get("audio_on_disk")
                   for x in c2["cases"]))

    r3 = rerun("probe_loop_guard.py")
    c3 = json.loads((G4 / "loop_guard_probe_receipt.v1.json").read_text())
    v43 = r3.returncode == 0 and c3.get("passed") \
        and "tainted" in (SKILL / "scripts/autonomous_dream_cycle.py").read_text()

    passed = v41 and v42 and v43
    print(json.dumps({
        "schema": "persona_dream.goal_v4_boundary_check.v1",
        "status": "PASS_GOAL_V4_BOUNDARY" if passed else "BLOCKED_GOAL_V4_BOUNDARY",
        "re_driven": True,
        "criteria": {
            "v4_1_composer": "PASS" if v41 else "FAIL",
            "v4_2_live_matrix_gate": "PASS" if v42 else "FAIL",
            "v4_3_loop_guard": "PASS" if v43 else "FAIL"},
        "matrix_summary": [{k: x.get(k) for k in
                            ("id", "intent_tone", "dream_tone", "gate")}
                           for x in c2.get("cases", [])],
    }, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
