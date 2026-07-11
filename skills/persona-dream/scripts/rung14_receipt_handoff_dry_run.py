#!/usr/bin/env python3
import argparse
import hashlib
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


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung14_receipt_handoff_dry_run_latest.json")
args = parser.parse_args()

root = Path(".codex/persona-dream/sanity/rung14")
pass_gate = root / "pass_gate.json"
pass_downstream = root / "pass_downstream_panel_reviewer.json"
pass_spec = root / "pass_handoff.yaml"
pass_parent = root / "pass_handoff_parent.json"
fail_gate = root / "fail_gate.json"
fail_downstream = root / "fail_downstream_panel_reviewer.json"
fail_spec = root / "fail_handoff.yaml"
fail_parent = root / "fail_handoff_parent.json"
for stale in [pass_gate, pass_downstream, pass_parent, fail_gate, fail_downstream, fail_parent]:
    stale.unlink(missing_ok=True)

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
                    str(pass_gate),
                ],
                "receipt": str(pass_gate),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.advance_allowed": True,
                },
            },
            {
                "id": "downstream_panel_reviewer",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung8_panel_reviewer_readonly.py",
                    "--upstream-receipt",
                    str(pass_gate),
                    "--receipt",
                    str(pass_downstream),
                ],
                "receipt": str(pass_downstream),
                "expect_receipt": {
                    "schema": "persona_dream.rung8_panel_reviewer.v1",
                    "ok": True,
                    "upstream_receipt.path": str(pass_gate),
                },
            },
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
                    str(fail_gate),
                ],
                "receipt": str(fail_gate),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.advance_allowed": True,
                },
            },
            {
                "id": "downstream_panel_reviewer",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung8_panel_reviewer_readonly.py",
                    "--upstream-receipt",
                    str(fail_gate),
                    "--receipt",
                    str(fail_downstream),
                ],
            },
        ]
    },
)

pass_run = run_spec(pass_spec, pass_parent)
fail_run = run_spec(fail_spec, fail_parent)
pass_gate_hash = sha256_file(pass_gate) if pass_gate.exists() else ""
pass_downstream_data = json.loads(pass_downstream.read_text()) if pass_downstream.exists() else {}
downstream_consumed_hash = (pass_downstream_data.get("upstream_receipt") or {}).get("sha256")

receipt = {
    "schema": "persona_dream.rung14_receipt_handoff_dry_run.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung14_receipt_handoff_dry_run.py",
    "pass_spec": str(pass_spec),
    "pass_returncode": pass_run.returncode,
    "pass_stdout": pass_run.stdout,
    "pass_gate_receipt": str(pass_gate),
    "pass_gate_sha256": pass_gate_hash,
    "pass_downstream_receipt": str(pass_downstream),
    "pass_downstream_created": pass_downstream.exists(),
    "pass_downstream_upstream_sha256": downstream_consumed_hash,
    "pass_downstream_consumed_exact_hash": bool(pass_gate_hash) and downstream_consumed_hash == pass_gate_hash,
    "fail_spec": str(fail_spec),
    "fail_returncode": fail_run.returncode,
    "fail_stdout": fail_run.stdout,
    "fail_gate_receipt": str(fail_gate),
    "fail_downstream_receipt": str(fail_downstream),
    "fail_downstream_created": fail_downstream.exists(),
}
receipt["ok"] = (
    pass_run.returncode == 0
    and receipt["pass_downstream_created"] is True
    and receipt["pass_downstream_consumed_exact_hash"] is True
    and fail_run.returncode != 0
    and receipt["fail_downstream_created"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 14, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
