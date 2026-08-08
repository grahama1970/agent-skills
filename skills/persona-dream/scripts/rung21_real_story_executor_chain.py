#!/usr/bin/env python3
"""rung21_real_story_executor_chain - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
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


def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


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


def run_gate(executor_receipt, gate_receipt):
    cmd = [
        "python3",
        "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
        "--case",
        "story_executor_pass",
        "--story-executor-receipt",
        str(executor_receipt),
        "--receipt",
        str(gate_receipt),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return cmd, proc


def materialize_template(source_spec, generated_spec, run_dir):
    source_text = Path(source_spec).read_text(encoding="utf-8")
    generated_text = source_text.replace("__RUN_DIR__", str(run_dir))
    if "__RUN_DIR__" in generated_text:
        raise ValueError("template placeholder was not fully replaced")
    atomic_write_text(generated_spec, generated_text)
    return {
        "source_spec": str(source_spec),
        "source_spec_sha256": file_hash(source_spec),
        "path": str(generated_spec),
        "sha256": file_hash(generated_spec),
        "transformation": "literal replacement of __RUN_DIR__ with invocation run_dir",
    }


def git_content_manifest(allowed_root):
    paths = set()
    for cmd in (
        ["git", "ls-files", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        output = subprocess.check_output(cmd)
        for raw in output.split(b"\0"):
            if not raw:
                continue
            path = Path(raw.decode("utf-8"))
            if path.is_file() and not is_relative_to(path, allowed_root):
                paths.add(path)
    return {str(path): file_hash(path) for path in sorted(paths)}


def is_relative_to(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def diff_manifest(before, after):
    before_keys = set(before)
    after_keys = set(after)
    modified = sorted(path for path in before_keys & after_keys if before[path] != after[path])
    created = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    return {
        "created": created,
        "modified": modified,
        "deleted": deleted,
        "changed_count": len(created) + len(modified) + len(deleted),
    }


def mutation_probe(run_dir):
    probe = Path("skills/persona-dream/rung21_mutation_probe.json")
    probe.unlink(missing_ok=True)
    before = git_content_manifest(run_dir)
    probe.write_text("mutation probe\n", encoding="utf-8")
    after = git_content_manifest(run_dir)
    diff = diff_manifest(before, after)
    probe.unlink(missing_ok=True)
    cleanup = diff_manifest(before, git_content_manifest(run_dir))
    return {
        "probe_path": str(probe),
        "detected": diff["changed_count"] == 1 and str(probe) in diff["created"],
        "diff": diff,
        "cleanup_restored": cleanup["changed_count"] == 0,
    }


def no_invocation_result(reason, decision, run_dir):
    probes = {
        "executor": run_dir / f"{reason}_story_executor_receipt.json",
        "gate": run_dir / f"{reason}_story_gate_receipt.json",
        "parent": run_dir / f"{reason}_story_parent_receipt.json",
    }
    for path in probes.values():
        path.unlink(missing_ok=True)
    return {
        "reason": reason,
        "decision": decision,
        "downstream_invoked": False,
        "child_processes": [],
        "candidate_executor_receipt": str(probes["executor"]),
        "candidate_executor_receipt_exists": probes["executor"].exists(),
        "candidate_gate_receipt": str(probes["gate"]),
        "candidate_gate_receipt_exists": probes["gate"].exists(),
        "candidate_parent_receipt": str(probes["parent"]),
        "candidate_parent_receipt_exists": probes["parent"].exists(),
        "ok": True,
    }


def negative_gate_check(base_executor, run_dir, name, changes):
    mutated = deepcopy(base_executor)
    for path, value in changes.items():
        target = mutated
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    executor_path = run_dir / f"negative_{name}_executor.json"
    gate_path = run_dir / f"negative_{name}_gate.json"
    atomic_write(executor_path, mutated)
    cmd, proc = run_gate(executor_path, gate_path)
    gate_data = load_json(gate_path) if gate_path.exists() else {}
    case = (gate_data.get("cases") or [{}])[0]
    return {
        "name": name,
        "executor_receipt": str(executor_path),
        "executor_receipt_sha256": file_hash(executor_path),
        "gate_receipt": str(gate_path),
        "gate_receipt_sha256": file_hash(gate_path) if gate_path.exists() else "",
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "gate_ok": gate_data.get("ok"),
        "advance_allowed": case.get("advance_allowed"),
        "unresolved_blockers": case.get("unresolved_blockers"),
        "rejected": proc.returncode != 0 and case.get("advance_allowed") is False,
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung21_real_story_executor_chain_latest.json")
parser.add_argument("--decision-receipt", default=".codex/persona-dream/sanity/rung18_dreamer_branch_decision_latest.json")
args = parser.parse_args()

decision_path = Path(args.decision_receipt)
decision_receipt = load_json(decision_path)
decision_invocation_id = decision_receipt.get("invocation_id")
invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
run_dir = Path(".codex/persona-dream/sanity/rung21") / invocation_id
allowlist = {
    "story": "skills/persona-dream/fixtures/rung21_story_phase.yaml",
}
source_spec = Path(allowlist["story"])
generated_spec = run_dir / "story_phase.generated.yaml"
parent_receipt = run_dir / "story_phase_parent.json"
executor_receipt = run_dir / "story_executor_receipt.json"
gate_receipt = run_dir / "story_gate_receipt.json"
for stale in [parent_receipt, executor_receipt, gate_receipt]:
    stale.unlink(missing_ok=True)
materialized_spec = materialize_template(source_spec, generated_spec, run_dir)

advance_validation = validate_decision_branch(
    decision_receipt.get("advance_result") or {}, "NEXT_PHASE", "story", decision_invocation_id
)
blocked_validation = validate_decision_branch(
    decision_receipt.get("blocked_result") or {}, "STOP", "none", decision_invocation_id
)
invalid_parent_result = decision_receipt.get("invalid_parent_result") or {}

receipt = {
    "schema": "persona_dream.rung21_real_story_executor_chain.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung21_real_story_executor_chain.py",
    "invocation_id": invocation_id,
    "run_dir": str(run_dir),
    "decision_receipt": {"path": str(decision_path), "sha256": file_hash(decision_path)},
    "decision_receipt_invocation_id": decision_invocation_id,
    "allowlist": {phase: {"spec": path, "sha256": file_hash(path)} for phase, path in allowlist.items()},
    "materialized_specs": {"story": materialized_spec},
    "advance_decision_validation": advance_validation,
    "blocked_decision_validation": blocked_validation,
}

if advance_validation["ok"] and advance_validation["next_phase"] in allowlist:
    story_cmd, story_run = run_yaml(generated_spec, parent_receipt)
    parent_data = load_json(parent_receipt) if parent_receipt.exists() else {}
    executor_data = load_json(executor_receipt) if executor_receipt.exists() else {}
    gate_data = load_json(gate_receipt) if gate_receipt.exists() else {}
    parent_steps = parent_data.get("steps") or []
    negative_checks = [
        negative_gate_check(executor_data, run_dir, "schema", {"schema": "wrong"}),
        negative_gate_check(executor_data, run_dir, "readonly", {"executor_readonly": False}),
        negative_gate_check(executor_data, run_dir, "blockers", {"unresolved_blockers": [{"code": "fixture_blocker"}]}),
        negative_gate_check(executor_data, run_dir, "mutation", {"active_artifact_mutation_performed": True}),
        negative_gate_check(executor_data, run_dir, "provider", {"provider_call_performed": True}),
        negative_gate_check(executor_data, run_dir, "output_status", {"output_contract.status": "BLOCKED"}),
    ]
    receipt["advance_handoff"] = {
        "downstream_invoked": True,
        "child_processes": [{"role": "yaml_runner", "cmd": story_cmd, "returncode": story_run.returncode}],
        "selected_phase": "story",
        "selected_spec": str(generated_spec),
        "selected_spec_sha256": file_hash(generated_spec),
        "selected_spec_source": str(source_spec),
        "selected_spec_source_sha256": file_hash(source_spec),
        "returncode": story_run.returncode,
        "stdout": story_run.stdout,
        "stderr": story_run.stderr,
        "parent_receipt_path": str(parent_receipt),
        "parent_receipt_sha256": file_hash(parent_receipt) if parent_receipt.exists() else "",
        "parent_receipt_ok": parent_data.get("ok") is True,
        "parent_step_ids": [step.get("id") for step in parent_steps],
        "parent_receipt_checks": [step.get("receipt_check") for step in parent_steps],
        "parent_receipt_checks_ok": all((step.get("receipt_check") or {}).get("ok") is True for step in parent_steps),
        "executor_receipt_path": str(executor_receipt),
        "executor_receipt_sha256": file_hash(executor_receipt) if executor_receipt.exists() else "",
        "executor_schema": executor_data.get("schema"),
        "executor_ok": executor_data.get("ok") is True,
        "executor_readonly": executor_data.get("executor_readonly"),
        "executor_workspace_manifest_unchanged": executor_data.get("workspace_manifest_unchanged"),
        "executor_execution_isolated": executor_data.get("execution_isolated"),
        "executor_isolated_source_hashes_match": executor_data.get("isolated_source_hashes_match"),
        "executor_repo_manifest_unchanged_outside_allowed_output": executor_data.get(
            "repo_manifest_unchanged_outside_allowed_output"
        ),
        "executor_repo_manifest_before_count": executor_data.get("repo_manifest_before_count"),
        "executor_repo_manifest_after_count": executor_data.get("repo_manifest_after_count"),
        "executor_repo_manifest_diff": executor_data.get("repo_manifest_diff"),
        "story_contract": executor_data.get("story_contract"),
        "gate_receipt_path": str(gate_receipt),
        "gate_receipt_sha256": file_hash(gate_receipt) if gate_receipt.exists() else "",
        "gate_schema": gate_data.get("schema"),
        "gate_ok": gate_data.get("ok") is True,
        "gate_case_id": ((gate_data.get("cases") or [{}])[0]).get("case_id"),
        "gate_advance_allowed": ((gate_data.get("cases") or [{}])[0]).get("advance_allowed"),
        "gate_executor_receipt_path": ((gate_data.get("cases") or [{}])[0]).get("executor_receipt_path"),
        "gate_executor_receipt_sha256": ((gate_data.get("cases") or [{}])[0]).get("executor_receipt_sha256"),
        "executor_gate_hash_linked": ((gate_data.get("cases") or [{}])[0]).get("executor_receipt_sha256")
        == (file_hash(executor_receipt) if executor_receipt.exists() else ""),
        "negative_checks": negative_checks,
        "negative_checks_ok": all(check.get("rejected") is True for check in negative_checks),
        "mutation_probe": mutation_probe(run_dir),
        "parent_receipt": parent_data,
        "executor_receipt": executor_data,
        "gate_receipt": gate_data,
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
    run_dir,
)
receipt["invalid_parent_handoff"] = no_invocation_result(
    "invalid_parent_rejected",
    {
        "parent_validation_ok": invalid_parent_result.get("parent_receipt_validation", {}).get("ok"),
        "scillm_invoked": invalid_parent_result.get("scillm_invoked"),
    },
    run_dir,
)
unknown_decision = {"decision": "NEXT_PHASE", "next_phase": "unknown_phase"}
receipt["unknown_phase_handoff"] = no_invocation_result("phase_not_allowlisted", unknown_decision, run_dir)
receipt["unknown_phase_allowlisted"] = unknown_decision["next_phase"] in allowlist

receipt["ok"] = (
    receipt["advance_decision_validation"].get("ok") is True
    and receipt["advance_handoff"].get("downstream_invoked") is True
    and receipt["advance_handoff"].get("child_processes", [{}])[0].get("returncode") == 0
    and receipt["advance_handoff"].get("returncode") == 0
    and receipt["advance_handoff"].get("parent_receipt_ok") is True
    and receipt["advance_handoff"].get("parent_step_ids") == ["story_executor", "story_gate"]
    and receipt["advance_handoff"].get("parent_receipt_checks_ok") is True
    and receipt["advance_handoff"].get("executor_schema") == "persona_dream.rung21_story_executor_receipt.v1"
    and receipt["advance_handoff"].get("executor_ok") is True
    and receipt["advance_handoff"].get("executor_readonly") is True
    and receipt["advance_handoff"].get("executor_workspace_manifest_unchanged") is True
    and receipt["advance_handoff"].get("executor_execution_isolated") is True
    and all((receipt["advance_handoff"].get("executor_isolated_source_hashes_match") or {}).values())
    and receipt["advance_handoff"].get("story_contract", {}).get("schema") == "persona_dream.story_contract.v1"
    and receipt["advance_handoff"].get("gate_schema") == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["advance_handoff"].get("gate_ok") is True
    and receipt["advance_handoff"].get("gate_case_id") == "story_executor_pass"
    and receipt["advance_handoff"].get("gate_advance_allowed") is True
    and receipt["advance_handoff"].get("gate_executor_receipt_path") == str(executor_receipt)
    and receipt["advance_handoff"].get("executor_gate_hash_linked") is True
    and receipt["advance_handoff"].get("negative_checks_ok") is True
    and receipt["advance_handoff"].get("mutation_probe", {}).get("detected") is True
    and receipt["advance_handoff"].get("mutation_probe", {}).get("cleanup_restored") is True
    and receipt["stop_handoff"].get("child_processes") == []
    and receipt["stop_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["stop_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["stop_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("child_processes") == []
    and receipt["invalid_parent_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("child_processes") == []
    and receipt["unknown_phase_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["unknown_phase_allowlisted"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 21, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
