#!/usr/bin/env python3
"""rungm_memory_recall - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import subprocess


q = "What prior lessons exist for Persona-Dream deterministic loops and Scillm batch calls?"
proc = subprocess.run(
    ["./run.sh", "recall", "--q", q, "--brief"],
    cwd="skills/memory",
    text=True,
    capture_output=True,
)
ok = proc.returncode == 0 and '"found": true' in proc.stdout
print(json.dumps({"rung": "memory", "recall": ok, "query": q}))
raise SystemExit(0 if ok else 1)
