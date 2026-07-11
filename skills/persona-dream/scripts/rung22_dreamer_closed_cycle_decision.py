#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import httpx


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def gate_case(gate):
    return (gate.get("cases") or [{}])[0]


def validate_story_gate_receipt(gate, expected_hash, current_hash):
    case = gate_case(gate)
    checks = {
        "schema_ok": gate.get("schema") == "persona_dream.rung12_shared_phase_gate.v1",
        "ok_true": gate.get("ok") is True,
        "case_id_ok": case.get("case_id") == "story_executor_pass",
        "advance_allowed_true": case.get("advance_allowed") is True,
        "executor_receipt_path_present": bool(case.get("executor_receipt_path")),
        "executor_receipt_sha256_present": bool(case.get("executor_receipt_sha256")),
        "hash_matches_expected": expected_hash == current_hash,
    }
    return {"ok": all(checks.values()), "checks": checks}


def validate_decision(parsed, parent_hash, persona_hash):
    if not isinstance(parsed, dict):
        return False
    files_read = parsed.get("files_read") or {}
    if not isinstance(files_read, dict):
        return False
    return (
        parsed.get("subagent") == "dreamer"
        and parsed.get("mode") == "read_only_closed_cycle_decision"
        and parsed.get("decision") == "NEXT_PHASE"
        and parsed.get("next_phase") == "voice"
        and parsed.get("consumed_story_gate_sha256") == parent_hash
        and parsed.get("persona_sha256") == persona_hash
        and parsed.get("direct_scheduler_implemented") is False
        and parsed.get("phase_execution_requested") is False
        and parsed.get("provider_call_requested") is False
        and parsed.get("active_artifact_mutation_requested") is False
        and parsed.get("edited_files") is False
        and files_read.get("agents/dreamer/persona.yaml") == persona_hash
        and files_read.get("input/story_gate_receipt.json") == parent_hash
    )


def negative_decision_checks(valid, parent_hash, persona_hash):
    return {
        "non_object_rejected": validate_decision([], parent_hash, persona_hash) is False,
        "wrong_decision_rejected": validate_decision({**valid, "decision": "STOP"}, parent_hash, persona_hash) is False,
        "wrong_next_phase_rejected": validate_decision({**valid, "next_phase": "panels"}, parent_hash, persona_hash) is False,
        "parent_hash_mismatch_rejected": validate_decision({**valid, "consumed_story_gate_sha256": "bad"}, parent_hash, persona_hash)
        is False,
        "persona_hash_mismatch_rejected": validate_decision({**valid, "persona_sha256": "bad"}, parent_hash, persona_hash)
        is False,
        "scheduler_enabled_rejected": validate_decision({**valid, "direct_scheduler_implemented": True}, parent_hash, persona_hash)
        is False,
        "phase_execution_rejected": validate_decision({**valid, "phase_execution_requested": True}, parent_hash, persona_hash)
        is False,
        "provider_requested_rejected": validate_decision({**valid, "provider_call_requested": True}, parent_hash, persona_hash)
        is False,
        "mutation_requested_rejected": validate_decision({**valid, "active_artifact_mutation_requested": True}, parent_hash, persona_hash)
        is False,
        "edited_files_rejected": validate_decision({**valid, "edited_files": True}, parent_hash, persona_hash) is False,
    }


def validate_successor_contract(contract, current_phase, next_phase):
    successors = contract.get("successors") or {}
    allowed = successors.get(current_phase) or []
    checks = {
        "schema_ok": contract.get("schema") == "persona_dream.phase_successors.v1",
        "current_phase_present": current_phase in successors,
        "next_phase_allowed": next_phase in allowed,
    }
    return {"ok": all(checks.values()), "checks": checks, "current_phase": current_phase, "next_phase": next_phase}


def run_dreamer_decision(endpoint, source_persona, gate_path, gate_hash):
    persona_hash = file_hash(source_persona)
    gate_data = load_json(gate_path)
    gate_validation = validate_story_gate_receipt(gate_data, gate_hash, file_hash(gate_path))
    result = {
        "story_gate_receipt": {"path": str(gate_path), "sha256": gate_hash},
        "story_gate_receipt_validation": gate_validation,
    }
    if not gate_validation["ok"]:
        result.update({"scillm_invoked": False, "ok": False})
        return result

    workspace_root = Path(".codex/persona-dream/workspaces").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory(prefix="rung22-dreamer-", dir=workspace_root)
    workspace = Path(temp_dir_obj.name)
    persona_target = workspace / "agents/dreamer/persona.yaml"
    gate_target = workspace / "input/story_gate_receipt.json"
    persona_target.parent.mkdir(parents=True, exist_ok=True)
    gate_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_persona, persona_target)
    shutil.copy2(gate_path, gate_target)
    (workspace / "readonly_sentinel.txt").write_text("do not edit\n", encoding="utf-8")
    manifest_before = tree_manifest(workspace)
    prompt = (
        "You are the Dreamer subagent in a read-only closed-cycle decision dry run. "
        "Read agents/dreamer/persona.yaml and input/story_gate_receipt.json. "
        "Compute the SHA-256 hash of each file. Do not edit files. "
        "Do not run phases, implement scheduling, call providers, or mutate artifacts. "
        "The story gate receipt has already been validated by the project agent. "
        "Choose only the next phase after story. Emit JSON only with these fields: "
        "subagent, mode, decision, next_phase, stop_reason, consumed_story_gate_sha256, "
        "persona_sha256, files_read, direct_scheduler_implemented, phase_execution_requested, "
        "provider_call_requested, active_artifact_mutation_requested, edited_files. "
        "files_read must be an object mapping each relative file path to its SHA-256 hash. "
        "Use subagent dreamer, mode read_only_closed_cycle_decision, decision NEXT_PHASE, "
        "next_phase voice, direct_scheduler_implemented false, phase_execution_requested false, "
        "provider_call_requested false, active_artifact_mutation_requested false, edited_files false."
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
    assistant_text = (
        str(raw_response.get("assistant_text") or raw_response.get("output") or raw_response)
        if raw_response_is_object
        else str(raw_response)
    )
    parsed = extract_json(assistant_text)
    parsed_is_object = isinstance(parsed, dict)
    if parsed_is_object and parsed.get("edited_files") == []:
        parsed["edited_files"] = False
    manifest_after = tree_manifest(workspace)
    readonly = manifest_before == manifest_after
    valid_decision = validate_decision(parsed, gate_hash, persona_hash)
    negative_checks = negative_decision_checks(parsed if parsed_is_object else {}, gate_hash, persona_hash)
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
            "isolated_workspace_manifest_before_count": len(manifest_before),
            "isolated_workspace_manifest_after_count": len(manifest_after),
            "workspace_manifest_unchanged": readonly,
            "readonly": readonly,
            "valid_decision": valid_decision,
            "negative_checks": negative_checks,
            "scillm_completed": scillm_completed,
            "scillm_run_id_present": scillm_run_id_present,
        }
    )
    result["ok"] = readonly and valid_decision and scillm_completed and scillm_run_id_present and all(negative_checks.values())
    temp_dir_obj.cleanup()
    return result


def preinvoke_rejection(name, source_gate, expected_hash, mutate, expect_hash_match=False):
    gate = deepcopy(source_gate)
    mutate(gate)
    actual_hash = hashlib.sha256(json.dumps(gate, sort_keys=True).encode("utf-8")).hexdigest()
    effective_expected_hash = actual_hash if expect_hash_match else expected_hash
    validation = validate_story_gate_receipt(gate, effective_expected_hash, actual_hash)
    return {
        "name": name,
        "expected_hash": effective_expected_hash,
        "actual_hash": actual_hash,
        "story_gate_receipt_validation": validation,
        "scillm_invoked": False,
        "ok": validation["ok"] is False,
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung22_dreamer_closed_cycle_decision_latest.json")
parser.add_argument("--story-chain-receipt", default=".codex/persona-dream/sanity/rung21_real_story_executor_chain_latest.json")
parser.add_argument("--phase-successors", default="skills/persona-dream/fixtures/rung22_phase_successors.json")
args = parser.parse_args()

source_persona = Path("agents/dreamer/persona.yaml")
endpoint = "http://localhost:4001/v1/scillm/opencode/runs"
story_chain = load_json(args.story_chain_receipt)
phase_successors_path = Path(args.phase_successors)
phase_successors = load_json(phase_successors_path)
story_gate_path = Path(story_chain["advance_handoff"]["gate_receipt_path"])
story_gate_hash = story_chain["advance_handoff"]["gate_receipt_sha256"]
story_gate = load_json(story_gate_path)
successor_validation = validate_successor_contract(phase_successors, "story", "voice")

receipt = {
    "schema": "persona_dream.rung22_dreamer_closed_cycle_decision.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung22_dreamer_closed_cycle_decision.py",
    "source_persona": {"path": str(source_persona), "sha256": file_hash(source_persona)},
    "story_chain_receipt": {"path": args.story_chain_receipt, "sha256": file_hash(args.story_chain_receipt)},
    "story_gate_source": {"path": str(story_gate_path), "sha256": story_gate_hash},
    "phase_successor_contract": {"path": str(phase_successors_path), "sha256": file_hash(phase_successors_path)},
    "successor_validation": successor_validation,
    "scillm_endpoint": endpoint,
}

try:
    valid_result = (
        run_dreamer_decision(endpoint, source_persona, story_gate_path, story_gate_hash)
        if successor_validation["ok"]
        else {"ok": False, "scillm_invoked": False, "reason": "phase_successor_contract_invalid"}
    )
    rejections = [
        preinvoke_rejection(
            "schema_mismatch",
            story_gate,
            story_gate_hash,
            lambda gate: gate.__setitem__("schema", "wrong"),
            expect_hash_match=True,
        ),
        preinvoke_rejection("hash_mismatch", story_gate, "0" * 64, lambda gate: None),
        preinvoke_rejection(
            "blocked_gate",
            story_gate,
            story_gate_hash,
            lambda gate: gate.__setitem__("ok", False),
            expect_hash_match=True,
        ),
        preinvoke_rejection(
            "advance_disallowed",
            story_gate,
            story_gate_hash,
            lambda gate: gate_case(gate).__setitem__("advance_allowed", False),
            expect_hash_match=True,
        ),
    ]
    receipt.update({"valid_result": valid_result, "preinvoke_rejections": rejections})
    receipt["ok"] = (
        successor_validation.get("ok") is True
        and valid_result.get("ok") is True
        and valid_result.get("parsed_decision", {}).get("decision") == "NEXT_PHASE"
        and valid_result.get("parsed_decision", {}).get("next_phase") == "voice"
        and valid_result.get("parsed_decision", {}).get("phase_execution_requested") is False
        and valid_result.get("parsed_decision", {}).get("direct_scheduler_implemented") is False
        and all(item.get("ok") is True and item.get("scillm_invoked") is False for item in rejections)
    )
except Exception as exc:
    receipt.update({"ok": False, "error": repr(exc)})

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 22, "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
