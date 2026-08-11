#!/usr/bin/env python3
"""Live probe for monitor-sparta checks 30/31 (framework alignment/congruence).

Runs the real health checks from the memory repo against the live corpus and
asserts the alignment invariants established by the 2026-08-11 audit. Used by
fixtures/agentic_eval.json; exits non-zero on violation so eval cases fail
closed.

Modes:
  alignment    check 30 must report zero unexpected orphan frameworks and
               zero case collisions (EMB3D is an expected orphan and must
               appear in expected_orphan_frameworks, not orphan_frameworks)
  congruence   check 31 must report zero mismatched labels and zero
               unlabelled edges
  sensitivity  check 31 must still be REPORTING drift, not vacuously green:
               the corpus deliberately retains surfaced dangling-endpoint
               findings (F36_*/TA refs). If dangling drops to zero without a
               recorded ingest/deprecation decision, the check may have been
               weakened -- this mode exits non-zero when dangling == 0 so a
               silent hollowing of the check surfaces as an eval failure.

Each mode prints one JSON line with the observed numbers for the eval log.
"""

import json
import subprocess
import sys

MEMORY_REPO = "/home/graham/workspace/experiments/memory"

SNIPPET = r"""
import sys, json
sys.path.insert(0, "scripts/validation")
from _health_checks import check_framework_label_alignment, check_framework_label_congruence
mode = sys.argv[1]
if mode == "alignment":
    r = check_framework_label_alignment()
    out = {
        "orphans": r.details.get("orphan_frameworks", []),
        "expected_orphans": r.details.get("expected_orphan_frameworks", []),
        "collisions": r.details.get("case_collisions", []),
    }
    ok = (not out["orphans"]) and (not out["collisions"]) and any(
        e.get("label") == "EMB3D" for e in out["expected_orphans"]
    )
elif mode == "congruence":
    r = check_framework_label_congruence()
    out = {
        "mismatched": r.details.get("mismatched_labels"),
        "unlabelled": r.details.get("unlabelled_edges"),
        "dangling": r.details.get("dangling_endpoints"),
    }
    ok = out["mismatched"] == 0 and out["unlabelled"] == 0
elif mode == "sensitivity":
    r = check_framework_label_congruence()
    out = {"dangling": r.details.get("dangling_endpoints")}
    ok = isinstance(out["dangling"], int) and out["dangling"] > 0
else:
    print(json.dumps({"error": f"unknown mode {mode}"})); sys.exit(2)
out["mode"] = mode
out["ok"] = ok
print(json.dumps(out))
sys.exit(0 if ok else 1)
"""


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("alignment", "congruence", "sensitivity"):
        print(json.dumps({"error": "usage: framework_alignment_probe.py alignment|congruence|sensitivity"}))
        return 2
    proc = subprocess.run(
        ["uv", "run", "python", "-c", SNIPPET, sys.argv[1]],
        cwd=MEMORY_REPO,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        sys.stderr.write(proc.stderr[-500:])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
