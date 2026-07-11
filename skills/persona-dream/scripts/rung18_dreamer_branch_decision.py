#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def tree_manifest(root):
    root_path = Path(root)
    return {
        str(path.relative_to(root_path)): {"sha256": file_hash(path), "bytes": path.stat().st_size}
        for path in sorted(p for p in root_path.rglob("*") if p.is_file())
    }


def extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_json(path, payload):
    atomic_write(Path(path), payload)


def make_parent_receipt(invocation_id, branch):
    if branch == "advance":
        return {
            "schema": "persona_dream.rung18.parent_decision_input.v1",
            "invocation_id": invocation_id,
            "branch": "advance",
            "state": "ADVANCE_READY",
            "current_phase": "dream_substrate",
            "expected_decision": "NEXT_PHASE",
            "expected_next_phase": "story",
            "validated_phase_receipts": [
                {"phase": "idea", "receipt_sha256": "fixture-idea", "status": "PASS"},
                {"phase": "dream_substrate", "receipt_sha256": "fixture-substrate", "status": "PASS"},
            ],
            "unresolved_blockers": [],
            "ok": True,
            "read_only_parent": True,
            "provider_call_performed": False,
            "active_artifact_mutation_performed": False,
        }
    if branch == "blocked":
        return {
            "schema": "persona_dream.rung18.parent_decision_input.v1",
            "invocation_id": invocation_id,
            "branch": "blocked",
            "state": "BLOCKED",
            "current_phase": "dream_substrate",
            "expected_decision": "STOP",
            "expected_next_phase": "none",
            "validated_phase_receipts": [
                {"phase": "idea", "receipt_sha256": "fixture-idea", "status": "PASS"},
                {"phase": "dream_substrate", "receipt_sha256": "fixture-substrate", "status": "BLOCKED"},
            ],
            "unresolved_blockers": [{"code": "missing_memory_recall_proof", "severity": "blocking"}],
            "ok": False,
            "read_only_parent": True,
            "provider_call_performed": False,
            "active_artifact_mutation_performed": False,
        }
    return {
        "schema": "persona_dream.rung18.parent_decision_input.v1",
        "invocation_id": invocation_id,
        "branch": "invalid",
        "state": "ADVANCE_READY",
        "expected_decision": "NEXT_PHASE",
        "expected_next_phase": "story",
        "validated_phase_receipts": [],
        "unresolved_blockers": [],
        "ok": True,
        "read_only_parent": True,
        "provider_call_performed": True,
        "active_artifact_mutation_performed": False,
    }


def validate_parent(data, expected_branch):
    checks = {
        "schema_ok": data.get("schema") == "persona_dream.rung18.parent_decision_input.v1",
        "branch_ok": data.get("branch") == expected_branch,
        "read_only_parent_ok": data.get("read_only_parent") is True,
        "provider_call_performed_false": data.get("provider_call_performed") is False,
        "active_artifact_mutation_performed_false": data.get("active_artifact_mutation_performed") is False,
        "phase_receipts_present": bool(data.get("validated_phase_receipts")),
    }
    if expected_branch == "advance":
        checks.update(
            {
                "state_ok": data.get("state") == "ADVANCE_READY",
                "ok_true": data.get("ok") is True,
                "no_blockers": data.get("unresolved_blockers") == [],
                "expected_decision_ok": data.get("expected_decision") == "NEXT_PHASE",
                "expected_next_phase_ok": data.get("expected_next_phase") == "story",
            }
        )
    elif expected_branch == "blocked":
        checks.update(
            {
                "state_ok": data.get("state") == "BLOCKED",
                "ok_false": data.get("ok") is False,
                "has_blockers": bool(data.get("unresolved_blockers")),
                "expected_decision_ok": data.get("expected_decision") == "STOP",
                "expected_next_phase_ok": data.get("expected_next_phase") == "none",
            }
        )
    return {"ok": all(checks.values()), "checks": checks}


def validate_decision(parsed, expected, parent_hash, persona_hash):
    if not isinstance(parsed, dict):
        return False
    files_read = parsed.get("files_read") or {}
    if not isinstance(files_read, dict):
        return False
    return (
        parsed.get("subagent") == "dreamer"
        and parsed.get("mode") == "read_only_branch_decision"
        and parsed.get("decision") == expected["expected_decision"]
        and parsed.get("next_phase") == expected["expected_next_phase"]
        and parsed.get("consumed_parent_sha256") == parent_hash
        and parsed.get("persona_sha256") == persona_hash
        and parsed.get("direct_scheduler_implemented") is False
        and parsed.get("phase_execution_requested") is False
        and parsed.get("provider_call_requested") is False
        and parsed.get("active_artifact_mutation_requested") is False
        and parsed.get("edited_files") is False
        and files_read.get("agents/dreamer/persona.yaml") == persona_hash
        and files_read.get("input/parent_receipt.json") == parent_hash
    )


def negative_decision_checks(valid, expected, parent_hash, persona_hash):
    return {
        "non_object_rejected": validate_decision([], expected, parent_hash, persona_hash) is False,
        "wrong_decision_rejected": validate_decision({**valid, "decision": "STOP" if expected["expected_decision"] == "NEXT_PHASE" else "NEXT_PHASE"}, expected, parent_hash, persona_hash)
        is False,
        "wrong_next_phase_rejected": validate_decision({**valid, "next_phase": "panels"}, expected, parent_hash, persona_hash)
        is False,
        "parent_hash_mismatch_rejected": validate_decision({**valid, "consumed_parent_sha256": "bad"}, expected, parent_hash, persona_hash)
        is False,
        "persona_hash_mismatch_rejected": validate_decision({**valid, "persona_sha256": "bad"}, expected, parent_hash, persona_hash)
        is False,
        "scheduler_enabled_rejected": validate_decision({**valid, "direct_scheduler_implemented": True}, expected, parent_hash, persona_hash)
        is False,
        "phase_execution_rejected": validate_decision({**valid, "phase_execution_requested": True}, expected, parent_hash, persona_hash)
        is False,
        "provider_requested_rejected": validate_decision({**valid, "provider_call_requested": True}, expected, parent_hash, persona_hash)
        is False,
        "mutation_requested_rejected": validate_decision({**valid, "active_artifact_mutation_requested": True}, expected, parent_hash, persona_hash)
        is False,
        "edited_files_rejected": validate_decision({**valid, "edited_files": True}, expected, parent_hash, persona_hash) is False,
    }


def run_dreamer_branch(endpoint, source_persona, parent_path, expected):
    persona_hash = file_hash(source_persona)
    parent_hash = file_hash(parent_path)
    parent_data = json.loads(parent_path.read_text(encoding="utf-8"))
    parent_validation = validate_parent(parent_data, expected["branch"])
    result = {
        "branch": expected["branch"],
        "parent_receipt": {"path": str(parent_path), "sha256": parent_hash},
        "parent_receipt_validation": parent_validation,
    }
    if not parent_validation["ok"]:
        result.update({"scillm_invoked": False, "ok": False})
        return result

    workspace_root = Path(".codex/persona-dream/workspaces").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory(prefix=f"rung18-{expected['branch']}-", dir=workspace_root)
    workspace = Path(temp_dir_obj.name)
    persona_target = workspace / "agents/dreamer/persona.yaml"
    parent_target = workspace / "input/parent_receipt.json"
    persona_target.parent.mkdir(parents=True, exist_ok=True)
    parent_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_persona, persona_target)
    shutil.copy2(parent_path, parent_target)
    (workspace / "readonly_sentinel.txt").write_text("do not edit\n", encoding="utf-8")
    manifest_before = tree_manifest(workspace)
    prompt = (
        "You are the Dreamer subagent in a read-only branch-decision dry run. "
        "Read agents/dreamer/persona.yaml and input/parent_receipt.json. "
        "Compute the SHA-256 hash of each file. Do not edit files. "
        "Do not run phases, implement scheduling, call providers, or mutate artifacts. "
        "Use the parent receipt expected_decision and expected_next_phase fields to decide only. "
        "Emit JSON only with these fields: subagent, mode, decision, next_phase, stop_reason, "
        "consumed_parent_sha256, persona_sha256, files_read, direct_scheduler_implemented, "
        "phase_execution_requested, provider_call_requested, active_artifact_mutation_requested, edited_files. "
        "files_read must be an object mapping each relative file path to its SHA-256 hash. "
        "Use subagent dreamer, mode read_only_branch_decision, direct_scheduler_implemented false, "
        "phase_execution_requested false, provider_call_requested false, "
        "active_artifact_mutation_requested false, edited_files false."
    )
    request = {"agent": "build", "cwd": str(workspace), "skills": [], "timeout_s": 300, "prompt": prompt}
    response = httpx.post(
        endpoint,
        headers={"Authorization": "Bearer sk-dev-proxy-123", "X-Caller-Skill": "persona-dream"},
        json=request,
        timeout=360,
    )
    response.raise_for_status()
    raw_response = response.json()
    raw_response_is_object = isinstance(raw_response, dict)
    assistant_text = str(raw_response.get("assistant_text") or raw_response.get("output") or raw_response) if raw_response_is_object else str(raw_response)
    parsed = extract_json(assistant_text)
    parsed_is_object = isinstance(parsed, dict)
    if parsed_is_object and parsed.get("edited_files") == []:
        parsed["edited_files"] = False
    manifest_after = tree_manifest(workspace)
    readonly = manifest_before == manifest_after
    valid_decision = validate_decision(parsed, expected, parent_hash, persona_hash)
    negative_checks = negative_decision_checks(parsed if parsed_is_object else {}, expected, parent_hash, persona_hash)
    with tempfile.TemporaryDirectory(prefix="persona-dream-rung18-mutation-") as tmp_dir:
        tmp_file = Path(tmp_dir) / "sentinel.txt"
        tmp_file.write_text("before\n", encoding="utf-8")
        tmp_before = tree_manifest(tmp_dir)
        tmp_file.write_text("after\n", encoding="utf-8")
        tmp_after = tree_manifest(tmp_dir)
        negative_checks["workspace_mutation_rejected"] = tmp_before != tmp_after
    scillm_completed = raw_response_is_object and raw_response.get("status") == "completed"
    scillm_run_id_present = raw_response_is_object and bool(raw_response.get("run_id"))
    result.update(
        {
            "scillm_invoked": True,
            "http_status": response.status_code,
            "request": request,
            "scillm_run_id": raw_response.get("run_id") if raw_response_is_object else "",
            "scillm_status": raw_response.get("status") if raw_response_is_object else None,
            "scillm_artifacts": raw_response.get("artifacts") if raw_response_is_object else {},
            "raw_scillm_response": raw_response,
            "assistant_text": assistant_text,
            "parsed_decision": parsed,
            "parsed_decision_is_object": parsed_is_object,
            "isolated_workspace": {"path": str(workspace), "manifest_before": manifest_before},
            "isolated_workspace_manifest_after": manifest_after,
            "workspace_manifest_unchanged": readonly,
            "readonly": readonly,
            "valid_decision": valid_decision,
            "negative_checks": negative_checks,
            "scillm_completed": scillm_completed,
            "scillm_run_id_present": scillm_run_id_present,
        }
    )
    result["ok"] = (
        readonly
        and valid_decision
        and scillm_completed
        and scillm_run_id_present
        and all(negative_checks.values())
    )
    temp_dir_obj.cleanup()
    return result


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung18_dreamer_branch_decision_latest.json")
args = parser.parse_args()

invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
root = Path(".codex/persona-dream/sanity/rung18") / invocation_id
source_persona = Path("agents/dreamer/persona.yaml")
endpoint = "http://localhost:4001/v1/scillm/opencode/runs"

advance_parent = make_parent_receipt(invocation_id, "advance")
blocked_parent = make_parent_receipt(invocation_id, "blocked")
invalid_parent = make_parent_receipt(invocation_id, "invalid")
advance_path = root / "advance_parent_receipt.json"
blocked_path = root / "blocked_parent_receipt.json"
invalid_path = root / "invalid_parent_receipt.json"
write_json(advance_path, advance_parent)
write_json(blocked_path, blocked_parent)
write_json(invalid_path, invalid_parent)

receipt = {
    "schema": "persona_dream.rung18_dreamer_branch_decision.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung18_dreamer_branch_decision.py",
    "invocation_id": invocation_id,
    "run_directory": str(root),
    "source_persona": {"path": str(source_persona), "sha256": file_hash(source_persona)},
    "scillm_endpoint": endpoint,
    "parent_receipt_hashes": {
        "advance": json_hash(advance_parent),
        "blocked": json_hash(blocked_parent),
        "invalid": json_hash(invalid_parent),
    },
}

try:
    advance_result = run_dreamer_branch(
        endpoint,
        source_persona,
        advance_path,
        {"branch": "advance", "expected_decision": "NEXT_PHASE", "expected_next_phase": "story"},
    )
    blocked_result = run_dreamer_branch(
        endpoint,
        source_persona,
        blocked_path,
        {"branch": "blocked", "expected_decision": "STOP", "expected_next_phase": "none"},
    )
    invalid_data = json.loads(invalid_path.read_text(encoding="utf-8"))
    invalid_validation = validate_parent(invalid_data, "advance")
    invalid_result = {
        "branch": "invalid",
        "parent_receipt": {"path": str(invalid_path), "sha256": file_hash(invalid_path)},
        "parent_receipt_validation": invalid_validation,
        "scillm_invoked": False,
        "ok": invalid_validation["ok"] is False,
    }
    receipt.update(
        {
            "advance_result": advance_result,
            "blocked_result": blocked_result,
            "invalid_parent_result": invalid_result,
        }
    )
    receipt["ok"] = advance_result.get("ok") is True and blocked_result.get("ok") is True and invalid_result.get("ok") is True
except Exception as exc:
    receipt.update({"ok": False, "error": repr(exc)})

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 18, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
