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


def tree_manifest(root):
    root_path = Path(root)
    manifest = {}
    for path in sorted(p for p in root_path.rglob("*") if p.is_file()):
        rel = str(path.relative_to(root_path))
        manifest[rel] = {"sha256": file_hash(path), "bytes": path.stat().st_size}
    return manifest


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


def validate_decision(parsed, parent_hash, persona_hash):
    if not isinstance(parsed, dict):
        return False
    files_read = parsed.get("files_read") or {}
    if not isinstance(files_read, dict):
        return False
    return (
        isinstance(parsed, dict)
        and parsed.get("subagent") == "dreamer"
        and parsed.get("mode") == "read_only_next_phase_decision"
        and parsed.get("decision") == "STOP_READ_ONLY_DRY_RUN"
        and parsed.get("next_phase") == "none"
        and parsed.get("consumed_parent_sha256") == parent_hash
        and parsed.get("persona_sha256") == persona_hash
        and parsed.get("direct_scheduler_implemented") is False
        and parsed.get("provider_call_requested") is False
        and parsed.get("active_artifact_mutation_requested") is False
        and parsed.get("edited_files") is False
        and files_read.get("agents/dreamer/persona.yaml") == persona_hash
        and files_read.get("input/rung16_parent_receipt.json") == parent_hash
    )


def validate_parent_receipt(data):
    required_flags = {
        "ok": True,
        "dreamer_contract_ok": True,
        "read_only_dry_run": True,
        "active_artifact_mutation_performed": False,
        "provider_call_performed": False,
        "live_call_performed": False,
        "paid_call_performed": False,
        "pass_consumed_only_validated_receipts": True,
        "fail_prevented_later_phase": True,
        "fail_later_phase_receipt_created": False,
    }
    checks = {
        "schema_ok": data.get("schema") == "persona_dream.rung16_dreamer_readonly_dry_run.v1",
    }
    for key, expected in required_flags.items():
        checks[key] = data.get(key) == expected
    checks["pass_phase_receipts_present"] = bool(data.get("pass_phase_receipts_consumed"))
    checks["pass_phase_receipts_validated"] = all(
        item.get("receipt_check_ok") is True and item.get("returncode") == 0
        for item in data.get("pass_phase_receipts_consumed") or []
    )
    checks["fail_parent_failed_step_ok"] = data.get("fail_parent_failed_step") == "dream_substrate_gate"
    return {"ok": all(checks.values()), "checks": checks}


def negative_decision_checks(valid, parent_hash, persona_hash):
    return {
        "non_object_rejected": validate_decision([], parent_hash, persona_hash) is False,
        "files_read_list_rejected": validate_decision({**valid, "files_read": list((valid.get("files_read") or {}).keys())}, parent_hash, persona_hash)
        is False,
        "parent_hash_mismatch_rejected": validate_decision({**valid, "consumed_parent_sha256": "bad"}, parent_hash, persona_hash)
        is False,
        "persona_hash_mismatch_rejected": validate_decision({**valid, "persona_sha256": "bad"}, parent_hash, persona_hash)
        is False,
        "scheduler_enabled_rejected": validate_decision({**valid, "direct_scheduler_implemented": True}, parent_hash, persona_hash)
        is False,
        "provider_requested_rejected": validate_decision({**valid, "provider_call_requested": True}, parent_hash, persona_hash)
        is False,
        "mutation_requested_rejected": validate_decision({**valid, "active_artifact_mutation_requested": True}, parent_hash, persona_hash)
        is False,
        "edited_files_rejected": validate_decision({**valid, "edited_files": True}, parent_hash, persona_hash) is False,
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung17_dreamer_scillm_readonly_decision_latest.json")
parser.add_argument("--parent-receipt", default=".codex/persona-dream/sanity/rung16_dreamer_readonly_dry_run_latest.json")
args = parser.parse_args()

source_persona = Path("agents/dreamer/persona.yaml")
source_parent = Path(args.parent_receipt)
persona_hash = file_hash(source_persona)
parent_hash = file_hash(source_parent)
parent_data = json.loads(source_parent.read_text(encoding="utf-8"))
parent_validation = validate_parent_receipt(parent_data)
receipt_path = Path(args.receipt)
endpoint = "http://localhost:4001/v1/scillm/opencode/runs"

receipt = {
    "schema": "persona_dream.rung17_dreamer_scillm_readonly_decision.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung17_dreamer_scillm_readonly_decision.py",
    "scillm_endpoint": endpoint,
    "source_persona": {"path": str(source_persona), "sha256": persona_hash},
    "parent_receipt": {"path": str(source_parent), "sha256": parent_hash},
    "parent_receipt_validation": parent_validation,
}

try:
    workspace_root = Path(".codex/persona-dream/workspaces").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory(prefix="rung17-dreamer-", dir=workspace_root)
    workspace = Path(temp_dir_obj.name)
    persona_target = workspace / "agents/dreamer/persona.yaml"
    parent_target = workspace / "input/rung16_parent_receipt.json"
    persona_target.parent.mkdir(parents=True, exist_ok=True)
    parent_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_persona, persona_target)
    shutil.copy2(source_parent, parent_target)
    (workspace / "readonly_sentinel.txt").write_text("do not edit\n", encoding="utf-8")
    manifest_before = tree_manifest(workspace)
    request = {
        "agent": "build",
        "cwd": str(workspace),
        "skills": [],
        "timeout_s": 300,
        "prompt": (
            "You are the Dreamer subagent in a read-only dry run. "
            "Read agents/dreamer/persona.yaml and input/rung16_parent_receipt.json. "
            "Compute the SHA-256 hash of each file and compare them to these expected values: "
            f"agents/dreamer/persona.yaml = {persona_hash}; "
            f"input/rung16_parent_receipt.json = {parent_hash}. "
            "Do not edit files. "
            "Do not run phases, implement scheduling, call providers, or mutate artifacts. "
            "Emit JSON only with these fields: subagent, mode, decision, next_phase, stop_reason, "
            "consumed_parent_sha256, persona_sha256, files_read, direct_scheduler_implemented, "
            "provider_call_requested, active_artifact_mutation_requested, edited_files. "
            "files_read must be an object mapping each relative file path to its SHA-256 hash; "
            "do not return files_read as a list. "
            "consumed_parent_sha256 must exactly equal the expected input/rung16_parent_receipt.json hash. "
            "persona_sha256 must exactly equal the expected agents/dreamer/persona.yaml hash. "
            "Use subagent dreamer, mode read_only_next_phase_decision, decision STOP_READ_ONLY_DRY_RUN, "
            "next_phase none, direct_scheduler_implemented false, provider_call_requested false, "
            "active_artifact_mutation_requested false, edited_files false."
        ),
    }
    receipt["request"] = request
    receipt["isolated_workspace"] = {
        "path": str(workspace),
        "manifest_before": manifest_before,
    }
    response = httpx.post(
        endpoint,
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "X-Caller-Skill": "persona-dream",
        },
        json=request,
        timeout=360,
    )
    receipt["http_status"] = response.status_code
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
    valid_decision = validate_decision(parsed, parent_hash, persona_hash)
    negative_checks = negative_decision_checks(parsed if parsed_is_object else {}, parent_hash, persona_hash)
    with tempfile.TemporaryDirectory(prefix="persona-dream-rung17-mutation-") as tmp_dir:
        tmp_file = Path(tmp_dir) / "sentinel.txt"
        tmp_file.write_text("before\n", encoding="utf-8")
        tmp_before = tree_manifest(tmp_dir)
        tmp_file.write_text("after\n", encoding="utf-8")
        tmp_after = tree_manifest(tmp_dir)
        negative_checks["workspace_mutation_rejected"] = tmp_before != tmp_after
    scillm_completed = raw_response_is_object and raw_response.get("status") == "completed"
    scillm_run_id_present = raw_response_is_object and bool(raw_response.get("run_id"))
    scillm_run_id = raw_response.get("run_id") if raw_response_is_object else ""
    scillm_status = raw_response.get("status") if raw_response_is_object else None
    receipt.update(
        {
            "raw_response_is_object": raw_response_is_object,
            "parsed_decision_is_object": parsed_is_object,
            "scillm_run_id": scillm_run_id,
            "scillm_status": scillm_status,
            "scillm_artifacts": raw_response.get("artifacts") if raw_response_is_object else {},
            "raw_scillm_response": raw_response,
            "assistant_text": assistant_text,
            "parsed_decision": parsed,
            "isolated_workspace_manifest_after": manifest_after,
            "workspace_manifest_unchanged": readonly,
            "readonly": readonly,
            "valid_decision": valid_decision,
            "negative_checks": negative_checks,
            "scillm_completed": scillm_completed,
            "scillm_run_id_present": scillm_run_id_present,
            "ok": parent_validation["ok"]
            and readonly
            and valid_decision
            and scillm_completed
            and scillm_run_id_present
            and all(negative_checks.values()),
        }
    )
    temp_dir_obj.cleanup()
except Exception as exc:
    receipt.update({"ok": False, "error": repr(exc)})
    try:
        temp_dir_obj.cleanup()
    except Exception:
        pass

atomic_write(receipt_path, receipt)
print(json.dumps({"rung": 17, "receipt": str(receipt_path), "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
