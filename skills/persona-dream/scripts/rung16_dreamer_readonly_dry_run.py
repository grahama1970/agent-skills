#!/usr/bin/env python3
"""rung16_dreamer_readonly_dry_run - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

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


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_yaml(spec_path, receipt_path):
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


def phase_receipts(parent_receipt):
    receipts = []
    for step in parent_receipt.get("steps", []):
        receipt_check = step.get("receipt_check") or {}
        if receipt_check:
            receipts.append(
                {
                    "step_id": step.get("id"),
                    "receipt_path": receipt_check.get("path"),
                    "receipt_sha256": receipt_check.get("sha256"),
                    "receipt_check_ok": receipt_check.get("ok") is True,
                    "returncode": step.get("returncode"),
                }
            )
    return receipts


def step_ids(parent_receipt):
    return [step.get("id") for step in parent_receipt.get("steps", [])]


def validate_dreamer_contract(path):
    raw = Path(path).read_bytes()
    contract = yaml.safe_load(raw.decode("utf-8"))
    allowed = contract.get("tool_policy", {}).get("allowed", [])
    denied = contract.get("tool_policy", {}).get("denied", [])
    orchestration = contract.get("orchestration_contract", {})
    status_reporting = contract.get("status_reporting", {})
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "schema": contract.get("schema"),
        "id": contract.get("id"),
        "owns_outer_dag": orchestration.get("owns_outer_dag") is True,
        "has_sequential_execution_contract": "sequential_execution_contract" in orchestration,
        "has_phase_loop_rule": "phase_loop_rule" in orchestration,
        "allows_scillm": "scillm.one_shot" in allowed or "scillm.opencode_run" in allowed,
        "allows_loop": "loop.scillm_loop_node" in allowed,
        "denies_live_provider_call": "direct_live_provider_call" in denied,
        "denies_paid_provider_call": "direct_paid_provider_call" in denied,
        "denies_kling_submit": "direct_kling_submit" in denied,
        "status_reporting_required": status_reporting.get("required") is True,
        "status_reporting_recipient": status_reporting.get("recipient"),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung16_dreamer_readonly_dry_run_latest.json")
args = parser.parse_args()

invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
root = Path(".codex/persona-dream/sanity/rung16") / invocation_id
contract_path = Path("agents/dreamer/persona.yaml")
pass_spec = root / "dreamer_pass.yaml"
pass_parent = root / "dreamer_pass_parent.json"
pass_phase_a = root / "pass_phase_a_gate.json"
pass_phase_b = root / "pass_phase_b_gate.json"
fail_spec = root / "dreamer_fail.yaml"
fail_parent = root / "dreamer_fail_parent.json"
fail_phase_a = root / "fail_phase_a_gate.json"
fail_phase_b = root / "fail_phase_b_gate.json"

write_yaml(
    pass_spec,
    {
        "steps": [
            {
                "id": "dream_substrate_gate",
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
                    "cases.0.advance_allowed": True,
                },
            },
            {
                "id": "story_gate",
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
                "id": "dream_substrate_gate",
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
                "id": "story_gate",
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

pass_run = run_yaml(pass_spec, pass_parent)
fail_run = run_yaml(fail_spec, fail_parent)
pass_parent_data = load_json(pass_parent) if pass_parent.exists() else {}
fail_parent_data = load_json(fail_parent) if fail_parent.exists() else {}
contract = validate_dreamer_contract(contract_path)
contract_ok = (
    contract["schema"] == "oc_subagent.persona.v1"
    and contract["id"] == "dreamer"
    and contract["owns_outer_dag"] is True
    and contract["has_sequential_execution_contract"] is True
    and contract["has_phase_loop_rule"] is True
    and contract["allows_scillm"] is True
    and contract["allows_loop"] is True
    and contract["denies_live_provider_call"] is True
    and contract["denies_paid_provider_call"] is True
    and contract["denies_kling_submit"] is True
    and contract["status_reporting_required"] is True
    and contract["status_reporting_recipient"] == "project_agent"
)
pass_receipts = phase_receipts(pass_parent_data)

receipt = {
    "schema": "persona_dream.rung16_dreamer_readonly_dry_run.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung16_dreamer_readonly_dry_run.py",
    "invocation_id": invocation_id,
    "run_directory": str(root),
    "dreamer_contract": contract,
    "dreamer_contract_ok": contract_ok,
    "delegated_runner": "skills/persona-dream/scripts/rung7_yaml_runner.py",
    "direct_scheduler_implemented": False,
    "read_only_dry_run": True,
    "active_artifact_mutation_performed": False,
    "provider_call_performed": False,
    "live_call_performed": False,
    "paid_call_performed": False,
    "pass_spec": str(pass_spec),
    "pass_returncode": pass_run.returncode,
    "pass_stdout": pass_run.stdout,
    "pass_stderr": pass_run.stderr,
    "pass_parent_receipt": str(pass_parent),
    "pass_parent_sha256": sha256_file(pass_parent) if pass_parent.exists() else "",
    "pass_parent_step_ids": step_ids(pass_parent_data),
    "pass_phase_receipts_consumed": pass_receipts,
    "pass_consumed_only_validated_receipts": bool(pass_receipts)
    and all(item["receipt_check_ok"] and item["returncode"] == 0 for item in pass_receipts),
    "fail_spec": str(fail_spec),
    "fail_returncode": fail_run.returncode,
    "fail_stdout": fail_run.stdout,
    "fail_stderr": fail_run.stderr,
    "fail_parent_receipt": str(fail_parent),
    "fail_parent_sha256": sha256_file(fail_parent) if fail_parent.exists() else "",
    "fail_parent_failed_step": fail_parent_data.get("failed_step"),
    "fail_parent_step_ids": step_ids(fail_parent_data),
    "fail_prevented_later_phase": "story_gate" not in step_ids(fail_parent_data),
    "fail_later_phase_receipt_created": fail_phase_b.exists(),
}
receipt["ok"] = (
    contract_ok
    and receipt["pass_returncode"] == 0
    and receipt["pass_parent_step_ids"] == ["dream_substrate_gate", "story_gate"]
    and receipt["pass_consumed_only_validated_receipts"] is True
    and receipt["fail_returncode"] != 0
    and receipt["fail_parent_failed_step"] == "dream_substrate_gate"
    and receipt["fail_parent_step_ids"] == ["dream_substrate_gate"]
    and receipt["fail_prevented_later_phase"] is True
    and receipt["fail_later_phase_receipt_created"] is False
    and receipt["read_only_dry_run"] is True
    and receipt["active_artifact_mutation_performed"] is False
    and receipt["provider_call_performed"] is False
    and receipt["live_call_performed"] is False
    and receipt["paid_call_performed"] is False
    and receipt["direct_scheduler_implemented"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 16, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
