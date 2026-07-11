#!/usr/bin/env python3
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


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def step_ids(parent_receipt):
    return [step.get("id") for step in parent_receipt.get("steps", [])]


def receipt_checks_ok(parent_receipt):
    checks = []
    for step in parent_receipt.get("steps", []):
        receipt_check = step.get("receipt_check")
        if receipt_check is not None:
            checks.append(receipt_check.get("ok") is True)
    return bool(checks) and all(checks)


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
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung15_two_phase_chain_dry_run_latest.json")
args = parser.parse_args()

invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
root = Path(".codex/persona-dream/sanity/rung15") / invocation_id
pass_phase_a = root / "pass_phase_a_gate.json"
pass_phase_b = root / "pass_phase_b_gate.json"
pass_spec = root / "pass_two_phase.yaml"
pass_parent = root / "pass_two_phase_parent.json"
fail_phase_a = root / "fail_phase_a_gate.json"
fail_phase_b = root / "fail_phase_b_gate.json"
fail_spec = root / "fail_two_phase.yaml"
fail_parent = root / "fail_two_phase_parent.json"

write_yaml(
    pass_spec,
    {
        "steps": [
            {
                "id": "phase_a_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "valid_image_pass",
                    "--receipt",
                    str(pass_phase_a),
                ],
                "receipt": str(pass_phase_a),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.case_id": "valid_image_pass",
                    "cases.0.advance_allowed": True,
                },
            },
            {
                "id": "phase_b_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "valid_image_pass",
                    "--receipt",
                    str(pass_phase_b),
                ],
                "receipt": str(pass_phase_b),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.case_id": "valid_image_pass",
                    "cases.0.advance_allowed": True,
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
                "id": "phase_a_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "missing_image_fail_closed",
                    "--receipt",
                    str(fail_phase_a),
                ],
                "receipt": str(fail_phase_a),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.advance_allowed": True,
                },
            },
            {
                "id": "phase_b_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "valid_image_pass",
                    "--receipt",
                    str(fail_phase_b),
                ],
            },
        ]
    },
)

pass_run = run_spec(pass_spec, pass_parent)
fail_run = run_spec(fail_spec, fail_parent)
pass_phase_a_data = load_json(pass_phase_a) if pass_phase_a.exists() else {}
pass_phase_b_data = load_json(pass_phase_b) if pass_phase_b.exists() else {}
fail_phase_a_data = load_json(fail_phase_a) if fail_phase_a.exists() else {}
pass_parent_data = load_json(pass_parent) if pass_parent.exists() else {}
fail_parent_data = load_json(fail_parent) if fail_parent.exists() else {}

receipt = {
    "schema": "persona_dream.rung15_two_phase_chain_dry_run.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung15_two_phase_chain_dry_run.py",
    "invocation_id": invocation_id,
    "run_directory": str(root),
    "freshness": {
        "per_run_directory": str(root),
        "per_run_directory_existed_before": False,
        "receipt_paths_are_invocation_scoped": all(
            invocation_id in str(path)
            for path in [
                pass_phase_a,
                pass_phase_b,
                pass_parent,
                fail_phase_a,
                fail_phase_b,
                fail_parent,
            ]
        ),
    },
    "pass_spec": str(pass_spec),
    "pass_returncode": pass_run.returncode,
    "pass_stdout": pass_run.stdout,
    "pass_stderr": pass_run.stderr,
    "pass_parent_receipt": str(pass_parent),
    "pass_parent_step_ids": step_ids(pass_parent_data),
    "pass_parent_receipt_checks_ok": receipt_checks_ok(pass_parent_data),
    "pass_phase_a_receipt": str(pass_phase_a),
    "pass_phase_a_created": pass_phase_a.exists(),
    "pass_phase_a_advance_allowed": bool((pass_phase_a_data.get("cases") or [{}])[0].get("advance_allowed")),
    "pass_phase_a_schema": pass_phase_a_data.get("schema"),
    "pass_phase_b_receipt": str(pass_phase_b),
    "pass_phase_b_created": pass_phase_b.exists(),
    "pass_phase_b_advance_allowed": bool((pass_phase_b_data.get("cases") or [{}])[0].get("advance_allowed")),
    "pass_phase_b_schema": pass_phase_b_data.get("schema"),
    "fail_spec": str(fail_spec),
    "fail_returncode": fail_run.returncode,
    "fail_stdout": fail_run.stdout,
    "fail_stderr": fail_run.stderr,
    "fail_parent_receipt": str(fail_parent),
    "fail_parent_failed_step": fail_parent_data.get("failed_step"),
    "fail_parent_step_ids": step_ids(fail_parent_data),
    "fail_parent_phase_b_absent_from_steps": "phase_b_gate" not in step_ids(fail_parent_data),
    "fail_phase_a_receipt": str(fail_phase_a),
    "fail_phase_a_created": fail_phase_a.exists(),
    "fail_phase_a_advance_allowed": bool((fail_phase_a_data.get("cases") or [{}])[0].get("advance_allowed")),
    "fail_phase_a_schema": fail_phase_a_data.get("schema"),
    "fail_phase_b_receipt": str(fail_phase_b),
    "fail_phase_b_created": fail_phase_b.exists(),
}
receipt["ok"] = (
    receipt["freshness"]["receipt_paths_are_invocation_scoped"] is True
    and receipt["pass_returncode"] == 0
    and receipt["pass_parent_receipt_checks_ok"] is True
    and receipt["pass_parent_step_ids"] == ["phase_a_gate", "phase_b_gate"]
    and receipt["pass_phase_a_created"] is True
    and receipt["pass_phase_a_advance_allowed"] is True
    and receipt["pass_phase_a_schema"] == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["pass_phase_b_created"] is True
    and receipt["pass_phase_b_advance_allowed"] is True
    and receipt["pass_phase_b_schema"] == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["fail_returncode"] != 0
    and receipt["fail_parent_failed_step"] == "phase_a_gate"
    and receipt["fail_parent_step_ids"] == ["phase_a_gate"]
    and receipt["fail_parent_phase_b_absent_from_steps"] is True
    and receipt["fail_phase_a_created"] is True
    and receipt["fail_phase_a_advance_allowed"] is False
    and receipt["fail_phase_a_schema"] == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["fail_phase_b_created"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 15, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
