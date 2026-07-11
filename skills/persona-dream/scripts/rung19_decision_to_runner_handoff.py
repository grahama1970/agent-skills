#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_yaml(spec_path, receipt_path):
    cmd = [
        "python3",
        "skills/persona-dream/scripts/rung7_yaml_runner.py",
        str(spec_path),
        "--receipt",
        str(receipt_path),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return cmd, proc


def write_invocation_spec(path, gate_receipt):
    payload = {
        "steps": [
            {
                "id": "story_gate",
                "cmd": [
                    "python3",
                    "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
                    "--case",
                    "valid_image_pass",
                    "--receipt",
                    str(gate_receipt),
                ],
                "receipt": str(gate_receipt),
                "expect_receipt": {
                    "schema": "persona_dream.rung12_shared_phase_gate.v1",
                    "ok": True,
                    "cases.0.case_id": "valid_image_pass",
                    "cases.0.advance_allowed": True,
                },
            }
        ]
    }
    atomic_write(path, payload)


def validate_decision_branch(branch, expected_decision, expected_next_phase, expected_invocation_id):
    parsed = branch.get("parsed_decision") or {}
    parent_receipt = branch.get("parent_receipt") or {}
    parent_path = parent_receipt.get("path") or ""
    parent_path_bound = f"/rung18/{expected_invocation_id}/" in f"/{parent_path}" if expected_invocation_id else False
    return {
        "ok": (
            branch.get("ok") is True
            and branch.get("scillm_invoked") is True
            and branch.get("scillm_status") == "completed"
            and branch.get("parent_receipt_validation", {}).get("ok") is True
            and parent_path_bound is True
            and branch.get("workspace_manifest_unchanged") is True
            and branch.get("valid_decision") is True
            and parsed.get("decision") == expected_decision
            and parsed.get("next_phase") == expected_next_phase
            and parsed.get("direct_scheduler_implemented") is False
            and parsed.get("phase_execution_requested") is False
            and parsed.get("provider_call_requested") is False
            and parsed.get("active_artifact_mutation_requested") is False
            and parsed.get("edited_files") is False
        ),
        "decision": parsed.get("decision"),
        "next_phase": parsed.get("next_phase"),
        "scillm_run_id": branch.get("scillm_run_id"),
        "parent_receipt_path": parent_path,
        "parent_receipt_path_bound_to_invocation": parent_path_bound,
        "parent_receipt_sha256": parent_receipt.get("sha256"),
        "consumed_parent_sha256": parsed.get("consumed_parent_sha256"),
    }


def no_invocation_result(reason, decision, candidate_parent, candidate_gate):
    return {
        "reason": reason,
        "decision": decision,
        "downstream_invoked": False,
        "child_processes": [],
        "candidate_parent_receipt": str(candidate_parent),
        "candidate_parent_receipt_exists": candidate_parent.exists(),
        "candidate_gate_receipt": str(candidate_gate),
        "candidate_gate_receipt_exists": candidate_gate.exists(),
        "ok": True,
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung19_decision_to_runner_handoff_latest.json")
parser.add_argument("--decision-receipt", default=".codex/persona-dream/sanity/rung18_dreamer_branch_decision_latest.json")
args = parser.parse_args()

decision_path = Path(args.decision_receipt)
decision_receipt = load_json(decision_path)
invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
decision_invocation_id = decision_receipt.get("invocation_id")
run_dir = Path(".codex/persona-dream/sanity/rung19") / invocation_id
allowlist = {
    "story": "skills/persona-dream/fixtures/rung19_story_phase.yaml",
}
story_spec = Path(allowlist["story"])
story_invocation_spec = run_dir / "story_phase_spec.generated.yaml"
story_parent = run_dir / "story_phase_parent.json"
story_gate = run_dir / "story_phase_gate.json"
for stale in [story_parent, story_gate]:
    stale.unlink(missing_ok=True)
write_invocation_spec(story_invocation_spec, story_gate)

advance_validation = validate_decision_branch(
    decision_receipt.get("advance_result") or {}, "NEXT_PHASE", "story", decision_invocation_id
)
blocked_validation = validate_decision_branch(
    decision_receipt.get("blocked_result") or {}, "STOP", "none", decision_invocation_id
)
invalid_parent_result = decision_receipt.get("invalid_parent_result") or {}
refusal_probe_paths = {
    "stop": {
        "parent": run_dir / "refusal_stop_parent.json",
        "gate": run_dir / "refusal_stop_gate.json",
    },
    "invalid_parent": {
        "parent": run_dir / "refusal_invalid_parent.json",
        "gate": run_dir / "refusal_invalid_gate.json",
    },
    "unknown_phase": {
        "parent": run_dir / "refusal_unknown_parent.json",
        "gate": run_dir / "refusal_unknown_gate.json",
    },
}
for paths in refusal_probe_paths.values():
    for stale in paths.values():
        stale.unlink(missing_ok=True)

receipt = {
    "schema": "persona_dream.rung19_decision_to_runner_handoff.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung19_decision_to_runner_handoff.py",
    "invocation_id": invocation_id,
    "run_dir": str(run_dir),
    "decision_receipt": {"path": str(decision_path), "sha256": file_hash(decision_path)},
    "decision_receipt_invocation_id": decision_invocation_id,
    "allowlist": {phase: {"spec": path, "sha256": file_hash(path)} for phase, path in allowlist.items()},
    "materialized_specs": {
        "story": {
            "source_spec": str(story_spec),
            "source_spec_sha256": file_hash(story_spec),
            "path": str(story_invocation_spec),
            "sha256": file_hash(story_invocation_spec),
        }
    },
    "advance_decision_validation": advance_validation,
    "blocked_decision_validation": blocked_validation,
}

if advance_validation["ok"] and advance_validation["next_phase"] in allowlist:
    story_cmd, story_run = run_yaml(story_invocation_spec, story_parent)
    story_parent_data = load_json(story_parent) if story_parent.exists() else {}
    story_gate_data = load_json(story_gate) if story_gate.exists() else {}
    story_receipt_check = ((story_parent_data.get("steps") or [{}])[0].get("receipt_check") or {})
    receipt["advance_handoff"] = {
        "downstream_invoked": True,
        "child_processes": [
            {
                "role": "yaml_runner",
                "cmd": story_cmd,
                "returncode": story_run.returncode,
            }
        ],
        "selected_phase": "story",
        "selected_spec": str(story_invocation_spec),
        "selected_spec_sha256": file_hash(story_invocation_spec),
        "selected_spec_source": str(story_spec),
        "selected_spec_source_sha256": file_hash(story_spec),
        "returncode": story_run.returncode,
        "stdout": story_run.stdout,
        "stderr": story_run.stderr,
        "parent_receipt": str(story_parent),
        "parent_receipt_sha256": file_hash(story_parent) if story_parent.exists() else "",
        "parent_receipt_ok": story_parent_data.get("ok") is True,
        "parent_step_ids": [step.get("id") for step in story_parent_data.get("steps", [])],
        "gate_receipt": str(story_gate),
        "gate_receipt_sha256": file_hash(story_gate) if story_gate.exists() else "",
        "gate_schema": story_gate_data.get("schema"),
        "gate_ok": story_gate_data.get("ok") is True,
        "gate_case_id": ((story_gate_data.get("cases") or [{}])[0]).get("case_id"),
        "gate_advance_allowed": ((story_gate_data.get("cases") or [{}])[0]).get("advance_allowed"),
        "receipt_check_ok": story_receipt_check.get("ok") is True,
        "receipt_check": story_receipt_check,
        "parent_receipt": story_parent_data,
        "gate_receipt": story_gate_data,
    }
else:
    receipt["advance_handoff"] = {
        "downstream_invoked": False,
        "child_processes": [],
        "reason": "advance_decision_invalid_or_not_allowlisted",
    }

receipt["stop_handoff"] = no_invocation_result(
    "stop_decision",
    {"decision": blocked_validation["decision"], "next_phase": blocked_validation["next_phase"]},
    refusal_probe_paths["stop"]["parent"],
    refusal_probe_paths["stop"]["gate"],
)
receipt["invalid_parent_handoff"] = no_invocation_result(
    "invalid_parent_rejected",
    {
        "parent_validation_ok": invalid_parent_result.get("parent_receipt_validation", {}).get("ok"),
        "scillm_invoked": invalid_parent_result.get("scillm_invoked"),
    },
    refusal_probe_paths["invalid_parent"]["parent"],
    refusal_probe_paths["invalid_parent"]["gate"],
)
unknown_decision = {"decision": "NEXT_PHASE", "next_phase": "unknown_phase"}
receipt["unknown_phase_handoff"] = no_invocation_result(
    "phase_not_allowlisted",
    unknown_decision,
    refusal_probe_paths["unknown_phase"]["parent"],
    refusal_probe_paths["unknown_phase"]["gate"],
)
receipt["unknown_phase_allowlisted"] = unknown_decision["next_phase"] in allowlist

receipt["ok"] = (
    receipt["advance_handoff"].get("downstream_invoked") is True
    and len(receipt["advance_handoff"].get("child_processes", [])) == 1
    and receipt["advance_handoff"].get("returncode") == 0
    and receipt["advance_handoff"].get("parent_receipt_ok") is True
    and receipt["advance_handoff"].get("parent_step_ids") == ["story_gate"]
    and receipt["advance_handoff"].get("gate_schema") == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["advance_handoff"].get("gate_ok") is True
    and receipt["advance_handoff"].get("gate_case_id") == "valid_image_pass"
    and receipt["advance_handoff"].get("gate_advance_allowed") is True
    and receipt["advance_handoff"].get("receipt_check_ok") is True
    and receipt["stop_handoff"].get("downstream_invoked") is False
    and receipt["stop_handoff"].get("child_processes") == []
    and receipt["stop_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["stop_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("downstream_invoked") is False
    and receipt["invalid_parent_handoff"].get("child_processes") == []
    and receipt["invalid_parent_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["invalid_parent_handoff"]["decision"].get("parent_validation_ok") is False
    and receipt["invalid_parent_handoff"]["decision"].get("scillm_invoked") is False
    and receipt["unknown_phase_handoff"].get("downstream_invoked") is False
    and receipt["unknown_phase_handoff"].get("child_processes") == []
    and receipt["unknown_phase_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["unknown_phase_allowlisted"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 19, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
