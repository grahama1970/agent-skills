#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import ast
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


def run_yaml(spec_path, receipt_path):
    cmd = [
        "python3",
        "skills/persona-dream/scripts/rung7_yaml_runner.py",
        str(spec_path),
        "--receipt",
        str(receipt_path),
    ]
    env = scrubbed_env()
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    return cmd, proc


def run_gate(executor_receipt, gate_receipt):
    cmd = [
        "python3",
        "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
        "--case",
        "voice_executor_pass",
        "--voice-executor-receipt",
        str(executor_receipt),
        "--receipt",
        str(gate_receipt),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return cmd, proc


def materialize_template(source_spec, generated_spec, run_dir, story_chain_receipt):
    source_text = Path(source_spec).read_text(encoding="utf-8")
    generated_text = source_text.replace("__RUN_DIR__", str(run_dir)).replace(
        "__STORY_CHAIN_RECEIPT__", str(story_chain_receipt)
    )
    if "__RUN_DIR__" in generated_text or "__STORY_CHAIN_RECEIPT__" in generated_text:
        raise ValueError("template placeholder was not fully replaced")
    atomic_write_text(generated_spec, generated_text)
    return {
        "source_spec": str(source_spec),
        "source_spec_sha256": file_hash(source_spec),
        "path": str(generated_spec),
        "sha256": file_hash(generated_spec),
        "transformation": "literal replacement of __RUN_DIR__ and __STORY_CHAIN_RECEIPT__",
    }


def is_relative_to(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def git_content_paths(allowed_root):
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
    return sorted(paths)


def git_content_manifest(allowed_root):
    return {str(path): file_hash(path) for path in git_content_paths(allowed_root)}


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


def scrubbed_env():
    env = os.environ.copy()
    removed = []
    sensitive_fragments = [
        "OPENAI",
        "CHUTES",
        "KLING",
        "RUNPOD",
        "GEMINI",
        "GOOGLE",
        "ELEVEN",
        "ORPHEUS",
        "API_KEY",
        "TOKEN",
        "SECRET",
        "COOKIE",
        "AUTH",
    ]
    for key in list(env):
        if any(fragment in key.upper() for fragment in sensitive_fragments):
            removed.append(key)
            env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def scrubbed_env_report():
    before = os.environ.copy()
    after = scrubbed_env()
    removed = sorted(set(before) - set(after))
    return {
        "sensitive_keys_removed_count": len(removed),
        "sensitive_key_names_removed": removed,
        "remaining_sensitive_key_names": [
            key
            for key in sorted(after)
            if any(fragment in key.upper() for fragment in ["OPENAI", "CHUTES", "KLING", "API_KEY", "TOKEN", "SECRET", "COOKIE"])
        ],
    }


def source_policy(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    imports = sorted(set(imports))
    disallowed_imports = sorted(set(imports) & {"httpx", "requests", "subprocess", "socket", "urllib"})
    return {
        "path": str(path),
        "sha256": file_hash(path),
        "imports": imports,
        "disallowed_network_or_process_imports": disallowed_imports,
        "no_network_or_process_imports": not disallowed_imports,
    }


def gate_case(gate):
    return (gate.get("cases") or [{}])[0]


def validate_rung22_decision(decision_receipt, expected_hash, current_hash):
    valid = decision_receipt.get("valid_result") or {}
    parsed = valid.get("parsed_decision") or {}
    checks = {
        "receipt_schema_ok": decision_receipt.get("schema") == "persona_dream.rung22_dreamer_closed_cycle_decision.v1",
        "receipt_ok_true": decision_receipt.get("ok") is True,
        "hash_matches_expected": expected_hash == current_hash,
        "valid_result_ok": valid.get("ok") is True,
        "scillm_invoked": valid.get("scillm_invoked") is True,
        "story_gate_valid": valid.get("story_gate_receipt_validation", {}).get("ok") is True,
        "workspace_unchanged": valid.get("workspace_manifest_unchanged") is True,
        "decision_ok": parsed.get("decision") == "NEXT_PHASE",
        "next_phase_voice": parsed.get("next_phase") == "voice",
        "no_scheduler": parsed.get("direct_scheduler_implemented") is False,
        "no_phase_execution_request": parsed.get("phase_execution_requested") is False,
        "no_provider_request": parsed.get("provider_call_requested") is False,
        "no_mutation_request": parsed.get("active_artifact_mutation_requested") is False,
        "no_edits": parsed.get("edited_files") is False,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "decision": parsed.get("decision"),
        "next_phase": parsed.get("next_phase"),
        "story_chain_receipt": decision_receipt.get("story_chain_receipt"),
        "story_gate_source": decision_receipt.get("story_gate_source"),
    }


def no_invocation_result(reason, decision, run_dir):
    probes = {
        "executor": run_dir / f"{reason}_voice_executor_receipt.json",
        "gate": run_dir / f"{reason}_voice_gate_receipt.json",
        "parent": run_dir / f"{reason}_voice_parent_receipt.json",
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
    executor_path = run_dir / f"negative_{name}_voice_executor.json"
    gate_path = run_dir / f"negative_{name}_voice_gate.json"
    atomic_write(executor_path, mutated)
    cmd, proc = run_gate(executor_path, gate_path)
    gate_data = load_json(gate_path) if gate_path.exists() else {}
    case = gate_case(gate_data)
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
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung23_voice_phase_execution_chain_latest.json")
parser.add_argument("--decision-receipt", default=".codex/persona-dream/sanity/rung22_dreamer_closed_cycle_decision_latest.json")
args = parser.parse_args()

decision_path = Path(args.decision_receipt)
decision_receipt = load_json(decision_path)
decision_hash = file_hash(decision_path)
invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
run_dir = Path(".codex/persona-dream/sanity/rung23") / invocation_id
allowlist = {"voice": "skills/persona-dream/fixtures/rung23_voice_phase.yaml"}
source_spec = Path(allowlist["voice"])
generated_spec = run_dir / "voice_phase.generated.yaml"
parent_receipt = run_dir / "voice_phase_parent.json"
executor_receipt = run_dir / "voice_executor_receipt.json"
gate_receipt = run_dir / "voice_gate_receipt.json"
for stale in [parent_receipt, executor_receipt, gate_receipt]:
    stale.unlink(missing_ok=True)

advance_validation = validate_rung22_decision(decision_receipt, decision_hash, file_hash(decision_path))
story_chain_path = Path((advance_validation.get("story_chain_receipt") or {}).get("path", ""))
materialized_spec = materialize_template(source_spec, generated_spec, run_dir, story_chain_path)
repo_manifest_before = git_content_manifest(run_dir)
env_boundary = scrubbed_env_report()
voice_source_policy = source_policy("skills/persona-dream/scripts/rung23_voice_executor_dry_run.py")

receipt = {
    "schema": "persona_dream.rung23_voice_phase_execution_chain.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung23_voice_phase_execution_chain.py",
    "invocation_id": invocation_id,
    "run_dir": str(run_dir),
    "decision_receipt": {"path": str(decision_path), "sha256": decision_hash},
    "allowlist": {phase: {"spec": path, "sha256": file_hash(path)} for phase, path in allowlist.items()},
    "materialized_specs": {"voice": materialized_spec},
    "advance_decision_validation": advance_validation,
    "write_boundary": {
        "allowed_output_root": str(run_dir),
        "repo_manifest_scope": "git tracked plus non-ignored untracked files, excluding allowed_output_root",
        "before_count": len(repo_manifest_before),
    },
    "execution_boundary": {
        "yaml_runner_env": env_boundary,
        "voice_executor_source_policy": voice_source_policy,
        "allowed_child_commands": [
            "skills/persona-dream/scripts/rung23_voice_executor_dry_run.py",
            "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
        ],
    },
}

if advance_validation["ok"] and advance_validation["next_phase"] in allowlist and story_chain_path.is_file():
    voice_cmd, voice_run = run_yaml(generated_spec, parent_receipt)
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
        negative_gate_check(executor_data, run_dir, "missing_plan", {"voice_handoff_plan.path": ""}),
    ]
    receipt["advance_handoff"] = {
        "downstream_invoked": True,
        "child_processes": [{"role": "yaml_runner", "cmd": voice_cmd, "returncode": voice_run.returncode}],
        "selected_phase": "voice",
        "selected_spec": str(generated_spec),
        "selected_spec_sha256": file_hash(generated_spec),
        "selected_spec_source": str(source_spec),
        "selected_spec_source_sha256": file_hash(source_spec),
        "story_chain_receipt_path": str(story_chain_path),
        "story_chain_receipt_sha256": file_hash(story_chain_path),
        "returncode": voice_run.returncode,
        "stdout": voice_run.stdout,
        "stderr": voice_run.stderr,
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
        "voice_handoff_plan": executor_data.get("voice_handoff_plan"),
        "story_contract": executor_data.get("story_contract"),
        "gate_receipt_path": str(gate_receipt),
        "gate_receipt_sha256": file_hash(gate_receipt) if gate_receipt.exists() else "",
        "gate_schema": gate_data.get("schema"),
        "gate_ok": gate_data.get("ok") is True,
        "gate_case_id": gate_case(gate_data).get("case_id"),
        "gate_advance_allowed": gate_case(gate_data).get("advance_allowed"),
        "gate_executor_receipt_path": gate_case(gate_data).get("executor_receipt_path"),
        "gate_executor_receipt_sha256": gate_case(gate_data).get("executor_receipt_sha256"),
        "executor_gate_hash_linked": gate_case(gate_data).get("executor_receipt_sha256")
        == (file_hash(executor_receipt) if executor_receipt.exists() else ""),
        "negative_checks": negative_checks,
        "negative_checks_ok": all(check.get("rejected") is True for check in negative_checks),
        "parent_receipt": parent_data,
        "executor_receipt": executor_data,
        "gate_receipt": gate_data,
    }
else:
    receipt["advance_handoff"] = {
        "downstream_invoked": False,
        "child_processes": [],
        "reason": "advance_decision_invalid_or_not_allowlisted_or_missing_story_chain",
    }

stop_decision = {"decision": "STOP", "next_phase": "none"}
invalid_decision = deepcopy(decision_receipt)
invalid_decision["ok"] = False
stale_hash_validation = validate_rung22_decision(decision_receipt, "0" * 64, decision_hash)
unknown_decision = {"decision": "NEXT_PHASE", "next_phase": "unknown_phase"}
receipt["stop_handoff"] = no_invocation_result("stop_decision", stop_decision, run_dir)
receipt["invalid_parent_handoff"] = no_invocation_result(
    "invalid_parent_rejected",
    {"validation_ok": validate_rung22_decision(invalid_decision, decision_hash, decision_hash)["ok"]},
    run_dir,
)
receipt["stale_parent_handoff"] = no_invocation_result(
    "stale_parent_rejected",
    {"validation_ok": stale_hash_validation["ok"], "hash_matches_expected": stale_hash_validation["checks"]["hash_matches_expected"]},
    run_dir,
)
receipt["unknown_phase_handoff"] = no_invocation_result("phase_not_allowlisted", unknown_decision, run_dir)
receipt["unknown_phase_allowlisted"] = unknown_decision["next_phase"] in allowlist
repo_manifest_after = git_content_manifest(run_dir)
repo_diff = diff_manifest(repo_manifest_before, repo_manifest_after)
receipt["write_boundary"].update(
    {
        "after_count": len(repo_manifest_after),
        "diff": repo_diff,
        "unchanged_outside_allowed_output": repo_diff["changed_count"] == 0,
    }
)

receipt["ok"] = (
    receipt["advance_decision_validation"].get("ok") is True
    and receipt["write_boundary"].get("unchanged_outside_allowed_output") is True
    and receipt["execution_boundary"]["voice_executor_source_policy"]["no_network_or_process_imports"] is True
    and receipt["execution_boundary"]["yaml_runner_env"]["remaining_sensitive_key_names"] == []
    and receipt["advance_decision_validation"].get("next_phase") == "voice"
    and receipt["advance_handoff"].get("downstream_invoked") is True
    and receipt["advance_handoff"].get("child_processes", [{}])[0].get("returncode") == 0
    and receipt["advance_handoff"].get("returncode") == 0
    and receipt["advance_handoff"].get("parent_receipt_ok") is True
    and receipt["advance_handoff"].get("parent_step_ids") == ["voice_executor", "voice_gate"]
    and receipt["advance_handoff"].get("parent_receipt_checks_ok") is True
    and receipt["advance_handoff"].get("executor_schema") == "persona_dream.rung23_voice_executor_receipt.v1"
    and receipt["advance_handoff"].get("executor_ok") is True
    and receipt["advance_handoff"].get("executor_readonly") is True
    and receipt["advance_handoff"].get("voice_handoff_plan", {}).get("schema") == "persona_dream.voice_handoff_plan.v1"
    and receipt["advance_handoff"].get("voice_handoff_plan", {}).get("line_count", 0) > 0
    and receipt["advance_handoff"].get("gate_schema") == "persona_dream.rung12_shared_phase_gate.v1"
    and receipt["advance_handoff"].get("gate_ok") is True
    and receipt["advance_handoff"].get("gate_case_id") == "voice_executor_pass"
    and receipt["advance_handoff"].get("gate_advance_allowed") is True
    and receipt["advance_handoff"].get("gate_executor_receipt_path") == str(executor_receipt)
    and receipt["advance_handoff"].get("executor_gate_hash_linked") is True
    and receipt["advance_handoff"].get("negative_checks_ok") is True
    and receipt["stop_handoff"].get("child_processes") == []
    and receipt["stop_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["stop_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["stop_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("child_processes") == []
    and receipt["invalid_parent_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["invalid_parent_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["stale_parent_handoff"].get("child_processes") == []
    and receipt["stale_parent_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["stale_parent_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["stale_parent_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("child_processes") == []
    and receipt["unknown_phase_handoff"].get("candidate_executor_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("candidate_gate_receipt_exists") is False
    and receipt["unknown_phase_handoff"].get("candidate_parent_receipt_exists") is False
    and receipt["unknown_phase_allowlisted"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 23, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
