#!/usr/bin/env python3
"""rung13_yaml_stop_dry_run - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_yaml(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def run_spec(spec_path, receipt_path):
    return subprocess.run(
        [
            "python3",
            "skills/persona-dream/scripts/rung7_yaml_runner.py",
            str(spec_path),
            "--receipt",
            str(receipt_path),
        ],
        text=True,
        capture_output=True,
    )


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung13_yaml_stop_dry_run_latest.json")
args = parser.parse_args()

root = Path(".codex/persona-dream/sanity/rung13")
pass_spec = root / "pass_advances.yaml"
fail_spec = root / "fail_stops.yaml"
pass_receipt = root / "pass_advances_receipt.json"
fail_receipt = root / "fail_stops_receipt.json"

marker_cmd = ["python3", "-c", "import json; print(json.dumps({'marker':'ran'}))"]
write_yaml(
    pass_spec,
    {
        "steps": [
            {
                "id": "phase_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "valid_image_pass",
                    "--receipt",
                    str(root / "pass_gate.json"),
                ],
                "receipt": str(root / "pass_gate.json"),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.case_id": "valid_image_pass",
                    "cases.0.advance_allowed": True,
                },
            },
            {"id": "marker", "cmd": marker_cmd},
        ]
    },
)
write_yaml(
    fail_spec,
    {
        "steps": [
            {
                "id": "phase_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "missing_image_fail_closed",
                    "--receipt",
                    str(root / "fail_gate.json"),
                ],
                "receipt": str(root / "fail_gate.json"),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.case_id": "missing_image_fail_closed",
                    "cases.0.advance_allowed": True,
                },
            },
            {"id": "marker", "cmd": marker_cmd},
        ]
    },
)

pass_run = run_spec(pass_spec, pass_receipt)
fail_run = run_spec(fail_spec, fail_receipt)
pass_marker_ran = '"marker": "ran"' in pass_run.stdout or '"marker":"ran"' in pass_run.stdout
fail_marker_ran = '"marker": "ran"' in fail_run.stdout or '"marker":"ran"' in fail_run.stdout

receipt = {
    "schema": "persona_dream.rung13_yaml_stop_dry_run.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung13_yaml_stop_dry_run.py",
    "pass_spec": str(pass_spec),
    "pass_receipt": str(pass_receipt),
    "pass_returncode": pass_run.returncode,
    "pass_stdout": pass_run.stdout,
    "pass_marker_ran": pass_marker_ran,
    "fail_spec": str(fail_spec),
    "fail_receipt": str(fail_receipt),
    "fail_returncode": fail_run.returncode,
    "fail_stdout": fail_run.stdout,
    "fail_marker_ran": fail_marker_ran,
}
receipt["ok"] = (
    pass_run.returncode == 0
    and pass_marker_ran is True
    and fail_run.returncode != 0
    and fail_marker_ran is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 13, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
