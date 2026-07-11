#!/usr/bin/env python3
import json
import subprocess
import sys
import time


STEPS = [
    ("rung0_httpx", [sys.executable, "skills/persona-dream/scripts/rung0_httpx.py"]),
    ("rung1_while_loop", [sys.executable, "skills/persona-dream/scripts/rung1_while_loop.py"]),
    ("rung2_chutes_as_completed", [sys.executable, "skills/persona-dream/scripts/rung2_chutes_as_completed.py"]),
]


for name, cmd in STEPS:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        print(
            json.dumps(
                {
                    "pipeline": "persona-dream-ladder",
                    "failed_step": name,
                    "seconds": round(time.monotonic() - t0, 2),
                    "stderr": proc.stderr,
                }
            )
        )
        raise SystemExit(proc.returncode)

print(json.dumps({"pipeline": "persona-dream-ladder", "steps": len(STEPS), "ok": True}))
