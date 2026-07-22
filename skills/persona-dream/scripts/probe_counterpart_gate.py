#!/usr/bin/env python3
"""Committed negative fixture (round-1/round-2 requirement): a
Brandon-selected / Kai-target bundle MUST be flagged by the counterpart gate.
Drives the REAL gate function used by the autonomous cycle."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "adc", ROOT / "scripts/autonomous_dream_cycle.py")
adc = importlib.util.module_from_spec(spec)
sys.modules["adc"] = adc
spec.loader.exec_module(adc)

CASES = [
    ("kai_targets_under_brandon_selection", "brandon",
     [{"interpretation_id": "i1", "target": "kai"},
      {"interpretation_id": "i2", "target": "kai"}], ["i1", "i2"]),
    ("mixed_targets", "brandon",
     [{"interpretation_id": "i1", "target": "brandon"},
      {"interpretation_id": "i2", "target": "kai"}], ["i2"]),
    ("matching_targets_pass", "brandon",
     [{"interpretation_id": "i1", "target": "brandon"},
      {"interpretation_id": "i2", "target": "unknown_person"}], []),
    ("missing_target_blocks", "brandon",
     [{"interpretation_id": "i1"}], ["i1"]),
]
results, ok = {}, True
for name, cp, claims, expected in CASES:
    got = adc.counterpart_violations(claims, cp, "interpretation_id")
    results[name] = {"expected_violations": expected, "got": got,
                     "passed": got == expected}
    ok = ok and got == expected
receipt = {
    "schema": "persona_dream.counterpart_gate_probe_receipt.v1",
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "gate_source": "autonomous_dream_cycle.counterpart_violations (real gate)",
    "cases": results, "passed": ok,
}
out = ROOT / "reports/goal_v3/counterpart_gate_probe_receipt.v1.json"
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": ok, "cases": {k: v["passed"] for k, v in results.items()}}, indent=2))
sys.exit(0 if ok else 1)
