#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
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


def manifest(paths):
    return {str(path): file_hash(path) for path in paths}


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


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", required=True)
parser.add_argument("--run-dir", required=True)
parser.add_argument("--idea", default="skills/persona-dream/fixtures/rung21_idea_contract.json")
parser.add_argument("--residue", default="skills/persona-dream/fixtures/rung21_residue_links.json")
args = parser.parse_args()

run_dir = Path(args.run_dir)
story_out = run_dir / "story_output"
story_script = Path("skills/persona-dream/pipeline/s03_story/story.py")
isolated_root = run_dir / "isolated_workspace"
isolated_story_script = isolated_root / story_script
isolated_idea = isolated_root / args.idea
isolated_residue = isolated_root / args.residue
for src, dst in [
    (story_script, isolated_story_script),
    (Path(args.idea), isolated_idea),
    (Path(args.residue), isolated_residue),
]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
source_paths = [
    story_script,
    Path(args.idea),
    Path(args.residue),
]
before = manifest(source_paths)
repo_before = git_content_manifest(run_dir)
cmd = [
    "python3",
    str(story_script),
    "--idea",
    args.idea,
    "--residue",
    args.residue,
    "--out",
    str(story_out.resolve()),
    "--persona-ids",
    "embry",
    "--model",
    "gpt-5.5",
    "--scillm-timeout",
    "120",
]
env = os.environ.copy()
env.setdefault("SCILLM_URL", "http://127.0.0.1:4001")
env.setdefault("SCILLM_KEY", "sk-dev-proxy-123")
env["PYTHONDONTWRITEBYTECODE"] = "1"
proc = subprocess.run(cmd, text=True, capture_output=True, env=env, cwd=isolated_root)
after = manifest(source_paths)
repo_after = git_content_manifest(run_dir)
repo_diff = diff_manifest(repo_before, repo_after)
story_contract = story_out / "story_contract.json"
story_data = load_json(story_contract) if story_contract.exists() else {}
story_hash = file_hash(story_contract) if story_contract.exists() else ""
blockers = []
if proc.returncode != 0:
    blockers.append({"code": "story_executor_returncode_nonzero", "severity": "blocking"})
if not story_contract.exists():
    blockers.append({"code": "story_contract_missing", "severity": "blocking"})
if story_data.get("schema") != "persona_dream.story_contract.v1":
    blockers.append({"code": "story_contract_schema_mismatch", "severity": "blocking"})
if before != after:
    blockers.append({"code": "source_manifest_changed", "severity": "blocking"})
receipt = {
    "schema": "persona_dream.rung21_story_executor_receipt.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung21_story_executor_real_dry_run.py",
    "phase": "story",
    "executor": "pipeline_s03_story_story_py_dry_run",
    "executor_readonly": True,
    "cmd": cmd,
    "returncode": proc.returncode,
    "stdout": proc.stdout,
    "stderr": proc.stderr,
    "input_hashes": {
        "idea": before[args.idea],
        "residue": before[args.residue],
        "story_script": before[str(story_script)],
    },
    "workspace_manifest_before": before,
    "workspace_manifest_after": after,
    "workspace_manifest_unchanged": before == after,
    "execution_isolated": True,
    "isolated_workspace": str(isolated_root),
    "isolated_source_hashes_match": {
        "story_script": file_hash(isolated_story_script) == before[str(story_script)],
        "idea": file_hash(isolated_idea) == before[args.idea],
        "residue": file_hash(isolated_residue) == before[args.residue],
    },
    "allowed_output_root": str(run_dir),
    "repo_manifest_scope": "git tracked plus non-ignored untracked files, excluding allowed_output_root",
    "repo_manifest_before_count": len(repo_before),
    "repo_manifest_after_count": len(repo_after),
    "repo_manifest_diff": repo_diff,
    "repo_manifest_unchanged_outside_allowed_output": repo_diff["changed_count"] == 0,
    "story_contract": {
        "path": str(story_contract),
        "sha256": story_hash,
        "schema": story_data.get("schema"),
        "artifact_id": story_data.get("artifact_id"),
        "story_chars": len(story_data.get("story", "")),
        "speaking_characters": story_data.get("speaking_characters"),
        "target_duration_s": story_data.get("target_duration_s"),
    },
    "output_contract": {
        "phase": "story",
        "status": "READY_FOR_SHARED_GATE",
        "artifact_type": "story_contract",
    },
    "unresolved_blockers": blockers,
    "active_artifact_mutation_performed": False,
    "provider_call_performed": False,
    "live_call_performed": False,
    "paid_call_performed": False,
}
receipt["ok"] = (
    proc.returncode == 0
    and story_contract.exists()
    and story_data.get("schema") == "persona_dream.story_contract.v1"
    and receipt["workspace_manifest_unchanged"] is True
    and receipt["execution_isolated"] is True
    and all(receipt["isolated_source_hashes_match"].values())
    and not blockers
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 21, "executor": "story", "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
