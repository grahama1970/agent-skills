#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path):
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def content_manifest(paths):
    return {path: {"sha256": file_hash(path), "bytes": Path(path).stat().st_size} for path in paths}


def tree_manifest(root):
    root_path = Path(root)
    manifest = {}
    for path in sorted(p for p in root_path.rglob("*") if p.is_file()):
        rel = str(path.relative_to(root_path))
        manifest[rel] = {"sha256": file_hash(path), "bytes": path.stat().st_size}
    return manifest


def git_status_snapshot():
    out = subprocess.check_output(["git", "status", "--short"], text=True)
    return {"sha256": sha256_text(out), "line_count": len(out.splitlines())}


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


def returned_file_hash(files, expected_path):
    if files.get(expected_path):
        return files.get(expected_path)
    suffix = "/" + expected_path
    for path, digest in files.items():
        if str(path).endswith(suffix):
            return digest
    return None


def validate_panel_result(data):
    files = data.get("files_read") or {}
    return (
        isinstance(data, dict)
        and data.get("subagent") == "panel-reviewer"
        and data.get("verdict") == "INSUFFICIENT_EVIDENCE"
        and data.get("edited_files") is False
        and isinstance(files, dict)
        and returned_file_hash(files, "agents/panel-reviewer/AGENTS.md") == file_hash("agents/panel-reviewer/AGENTS.md")
        and returned_file_hash(files, "agents/panel-reviewer/persona.yaml") == file_hash("agents/panel-reviewer/persona.yaml")
    )


def manifests_equal(before, after):
    return before == after


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung8_panel_reviewer_latest.json")
parser.add_argument("--upstream-receipt", default="")
args = parser.parse_args()

receipt_path = Path(args.receipt)
source_paths = [
    "agents/panel-reviewer/AGENTS.md",
    "agents/panel-reviewer/persona.yaml",
]
before = git_status_snapshot()
request = {
    "agent": "build",
    "skills": [],
    "timeout_s": 300,
    "prompt": (
        "Read agents/panel-reviewer/AGENTS.md and agents/panel-reviewer/persona.yaml. "
        "Compute the SHA-256 hash of each file you read. "
        "Do not edit files. A review request has a panel contract but no image artifact. "
        "Using the panel-reviewer contract, reply with JSON only containing these fields: "
        "subagent, verdict, edited_files, files_read, rationale. "
        "files_read must be an object mapping each path to its SHA-256 hash. "
        "Use verdict INSUFFICIENT_EVIDENCE and edited_files false."
    ),
}
receipt = {
    "schema": "persona_dream.rung8_panel_reviewer.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung8_panel_reviewer_readonly.py",
    "scillm_endpoint": "http://localhost:4001/v1/scillm/opencode/runs",
    "source_files": content_manifest(source_paths),
    "git_status_before": before,
}
if args.upstream_receipt:
    upstream_path = Path(args.upstream_receipt)
    upstream_raw = upstream_path.read_bytes()
    receipt["upstream_receipt"] = {
        "path": str(upstream_path),
        "sha256": hashlib.sha256(upstream_raw).hexdigest(),
    }

try:
    workspace_root = Path(".codex/persona-dream/workspaces").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory(prefix="rung8-", dir=workspace_root)
    workspace = Path(temp_dir_obj.name)
    for source in source_paths:
        target = workspace / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (workspace / "unrelated_sentinel.txt").write_text("sentinel\n", encoding="utf-8")
    request["cwd"] = str(workspace)
    receipt["request"] = request
    receipt["isolated_workspace"] = {
        "path": str(workspace),
        "manifest_before": tree_manifest(workspace),
    }
    response = httpx.post(
        receipt["scillm_endpoint"],
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
    assistant_text = str(raw_response.get("assistant_text") or raw_response.get("output") or raw_response)
    parsed = extract_json(assistant_text)
    after = git_status_snapshot()
    workspace_after = tree_manifest(workspace)
    returned_hashes_match_sources = validate_panel_result(parsed)
    scillm_completed = raw_response.get("status") == "completed"
    scillm_run_id_present = bool(raw_response.get("run_id"))
    with tempfile.TemporaryDirectory(prefix="persona-dream-rung8-") as tmp_dir:
        tmp_file = Path(tmp_dir) / "mutation.txt"
        tmp_file.write_text("before\n", encoding="utf-8")
        tmp_before = content_manifest([str(tmp_file)])
        tmp_file.write_text("after\n", encoding="utf-8")
        tmp_after = content_manifest([str(tmp_file)])
        content_mutation_rejected = not manifests_equal(tmp_before, tmp_after)
    negative_checks = {
        "bad_verdict_rejected": not validate_panel_result({**parsed, "verdict": "PASS"}),
        "edited_files_rejected": not validate_panel_result({**parsed, "edited_files": True}),
        "missing_files_read_rejected": not validate_panel_result({**parsed, "files_read": {}}),
        "content_mutation_rejected": content_mutation_rejected,
    }
    readonly = manifests_equal(receipt["isolated_workspace"]["manifest_before"], workspace_after)
    ok = (
        returned_hashes_match_sources
        and readonly
        and scillm_completed
        and scillm_run_id_present
        and all(negative_checks.values())
    )
    receipt.update(
        {
            "git_status_after": after,
            "isolated_workspace_manifest_after": workspace_after,
            "workspace_manifest_unchanged": readonly,
            "content_manifest_unchanged": readonly,
            "readonly": readonly,
            "raw_scillm_response": raw_response,
            "assistant_text": assistant_text,
            "parsed_panel_reviewer_result": parsed,
            "returned_hashes_match_sources": returned_hashes_match_sources,
            "scillm_completed": scillm_completed,
            "scillm_run_id_present": scillm_run_id_present,
            "negative_checks": negative_checks,
            "ok": ok,
        }
    )
    temp_dir_obj.cleanup()
except Exception as exc:
    receipt.update({"ok": False, "error": repr(exc), "git_status_after": git_status_snapshot()})
    try:
        temp_dir_obj.cleanup()
    except Exception:
        pass

atomic_write(receipt_path, receipt)
summary = {
    "rung": 8,
    "subagent": "panel-reviewer",
    "receipt": str(receipt_path),
    "readonly": receipt.get("readonly", False),
    "verdict": (receipt.get("parsed_panel_reviewer_result") or {}).get("verdict"),
    "ok": receipt["ok"],
}
print(json.dumps(summary))
raise SystemExit(0 if receipt["ok"] else 1)
