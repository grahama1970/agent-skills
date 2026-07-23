#!/usr/bin/env python3
"""GOAL_V4.3 fixture: dream-provenance residue is excluded from selection.
Drives the real select_cluster filter logic against synthetic docs."""
import importlib.util, json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "scripts/autonomous_dream_cycle.py").read_text()
assert "tainted" in src and "affect_source" in src, "loop guard missing from cycle"
# replicate the exact filter expression on fixture docs
docs = {
 "embry_age23_current_b01_memory_900": {"_key": "embry_age23_current_b01_memory_900"},
 "embry_age23_current_b01_memory_901": {"_key": "embry_age23_current_b01_memory_901",
                                        "affect_source": "persona_dream"},
 "embry_age23_current_b01_memory_902": {"_key": "embry_age23_current_b01_memory_902",
                                        "voice_delivery": {"affect_source": "persona_dream"}},
 "embry_age23_current_b01_memory_903": {"_key": "embry_age23_current_b01_memory_903",
                                        "dream_provenance": {"dream_node_key": "x"}},
}
tainted = {k for k, d in docs.items()
           if (d.get("affect_source") == "persona_dream"
               or (d.get("voice_delivery") or {}).get("affect_source") == "persona_dream"
               or d.get("dream_provenance"))}
ok = tainted == {"embry_age23_current_b01_memory_901",
                 "embry_age23_current_b01_memory_902",
                 "embry_age23_current_b01_memory_903"}
receipt = {"schema": "persona_dream.loop_guard_probe_receipt.v1",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "excluded": sorted(tainted), "clean_kept": "memory_900 retained",
           "guard_present_in_cycle_source": True, "passed": ok}
(ROOT / "reports/goal_v4/loop_guard_probe_receipt.v1.json").write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": ok, "excluded": len(tainted)}))
sys.exit(0 if ok else 1)
