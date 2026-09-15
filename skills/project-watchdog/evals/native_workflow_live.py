#!/usr/bin/env python3
"""Exercise the production Pi fixer-reviewer workflow in an isolated repository."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "watchdog_v2.py"
SPEC = importlib.util.spec_from_file_location("watchdog_v2", SOURCE)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def run(*command: str, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="project-watchdog-native-") as root:
        repo = Path(root)
        run("git", "init", "-q", "-b", "main", cwd=repo)
        (repo / "marker.txt").write_text("BROKEN\n", encoding="utf-8")
        run("git", "add", "marker.txt", cwd=repo)
        run("git", "-c", "user.name=Watchdog Eval", "-c", "user.email=watchdog@example.invalid", "commit", "-qm", "Initial marker", cwd=repo)
        project = watchdog.Project(
            project_id="native-live", repo="example/native-live", cwd=str(repo),
            ready_label="agent-work", active_label="agent-active", done_label="agent-done",
            target_prefixes=(), target_excludes=(), default_state="active",
            proof_command=("bash", "-lc", 'test "$(cat marker.txt)" = FIXED'),
        )
        ticket = watchdog.Ticket(
            project=project, number=1, title="Repair marker.txt", url="", labels=(),
            body="Target: marker.txt. Change its only line from BROKEN to FIXED. Do not change any other file. Run a focused read-back.",
        )
        result = watchdog.PiSubagents().run(ticket)
        content = (repo / "marker.txt").read_text(encoding="utf-8")
        diff = subprocess.run(["git", "diff", "--", "marker.txt"], cwd=repo, capture_output=True, text=True, check=True).stdout
        receipt = {"result": result, "marker": content, "diff": diff}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        saved = json.loads(args.output.read_text(encoding="utf-8"))
        assert saved["result"]["ok"] is True, saved["result"]
        assert saved["marker"] == "FIXED\n", saved["marker"]
        assert saved["result"]["fixer"]["status"]["status"] == "COMPLETE"
        assert saved["result"]["reviewer"]["status"]["verdict"] == "PASS"
        assert "+FIXED" in saved["diff"]
        print("PROJECT_WATCHDOG_NATIVE_WORKFLOW_LIVE_OK")


if __name__ == "__main__":
    main()
