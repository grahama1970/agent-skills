#!/usr/bin/env python3
"""rung7_yaml_runner - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


def validate_receipt(path, expected):
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    checks = []
    for key, expected_value in (expected or {}).items():
        actual = data
        for part in key.split("."):
            if isinstance(actual, list) and part.isdigit():
                index = int(part)
                if index >= len(actual):
                    checks.append({"key": key, "ok": False, "actual": None, "expected": expected_value})
                    break
                actual = actual[index]
                continue
            if not isinstance(actual, dict) or part not in actual:
                checks.append({"key": key, "ok": False, "actual": None, "expected": expected_value})
                break
            actual = actual[part]
        else:
            checks.append({"key": key, "ok": actual == expected_value, "actual": actual, "expected": expected_value})
    return {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


parser = argparse.ArgumentParser()
parser.add_argument("spec", nargs="?", default="skills/persona-dream/fixtures/rungs_0_6.yaml")
parser.add_argument("--receipt", default="")
args = parser.parse_args()

spec_path = Path(args.spec)
spec = yaml.safe_load(spec_path.read_text())
receipt = {
    "schema": "persona_dream.rung7_yaml_runner.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "spec": str(spec_path),
    "steps": [],
}

for step in spec["steps"]:
    t0 = time.monotonic()
    proc = subprocess.run(step["cmd"], text=True, capture_output=True)
    print(proc.stdout, end="")
    receipt_check = None
    if "receipt" in step:
        receipt_check = validate_receipt(step["receipt"], step.get("expect_receipt"))
    receipt["steps"].append(
        {
            "id": step["id"],
            "cmd": step["cmd"],
            "returncode": proc.returncode,
            "seconds": round(time.monotonic() - t0, 2),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "receipt_check": receipt_check,
        }
    )
    if proc.returncode != 0 or (receipt_check is not None and not receipt_check["ok"]):
        receipt["ok"] = False
        receipt["failed_step"] = step["id"]
        if args.receipt:
            Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
            Path(args.receipt).write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"rung": 7, "failed": step["id"], "seconds": round(time.monotonic() - t0, 2)}))
        raise SystemExit(proc.returncode or 1)

receipt["ok"] = True
if args.receipt:
    Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
    Path(args.receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"rung": 7, "yaml_steps": len(spec["steps"]), "receipt": args.receipt, "ok": True}))
