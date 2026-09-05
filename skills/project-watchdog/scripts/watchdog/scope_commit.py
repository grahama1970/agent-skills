#!/usr/bin/env python3
"""Create a path-scoped commit object on primary; no branch/ref/index mutation."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import primary, target_content as content
from watchdog.core import write_json
from watchdog.primary_models import Operation, TargetSnapshot, OwnedTargets, encoded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root, _ = primary.identity(args.root)
    operation = Operation.model_validate(json.loads(args.journal.read_text()))
    before = TargetSnapshot.model_validate(json.loads(args.before.read_text()))
    if (operation.root != str(root) or operation.targets != before.targets or
            operation.phase != "running" or not primary.writer_active(root)):
        raise RuntimeError("scope commit is not bound to a live primary operation")
    current = content.snapshot(root, before.targets, before.remote_sha)
    if current.index_entries != before.index_entries:
        raise RuntimeError("target shared index changed; preserve it")
    commit = content.scoped_commit(root, current, before.remote_sha, Path(operation.receipt_dir),
                                  f"Ticket #{operation.issue_number}\n\nWatchdog-Run: {operation.run_id}")
    payload = {"schema": "agent_skills.project_watchdog.authored_commit.v1",
               "run_id": operation.run_id, "commit": commit, "content": encoded(current)}
    write_json(args.output, payload)
    # Provenance is this exact helper-produced commit/snapshot under this run,
    # not an arbitrary pre-existing dirty file or a blanket approval map.
    owned = OwnedTargets(repo=operation.repo, issue_number=operation.issue_number,
        task_sha256=operation.task_sha256, run_id=operation.run_id, targets=operation.targets,
        files=current.files, provenance="authored_checkpoint")
    write_json(primary._area(root) / "owned" / f"{operation.issue_number}.json", encoded(owned))
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
