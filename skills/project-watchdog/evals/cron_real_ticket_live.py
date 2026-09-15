#!/usr/bin/env python3
"""Exercise the cron-shaped Watchdog path against a controlled GitHub issue."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "skills" / "project-watchdog" / "run.sh"
REPO = "grahama1970/agent-skills"


def command(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, check=False, timeout=7_500)


def gh(*args: str) -> dict[str, object]:
    result = command(["gh", *args], cwd=ROOT)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = f"watchdog-cron-canary-{uuid.uuid4().hex[:12]}"

    with tempfile.TemporaryDirectory(prefix="watchdog-cron-live-") as temporary:
        work = Path(temporary)
        checkout = work / "checkout"
        state = work / "state"
        checkout.mkdir()
        (checkout / "marker.txt").write_text("BROKEN\n", encoding="utf-8")
        for argv in (["git", "init", "-q"], ["git", "config", "user.name", "Watchdog Canary"], ["git", "config", "user.email", "watchdog-canary@example.invalid"], ["git", "add", "marker.txt"], ["git", "commit", "-qm", "canary baseline"]):
            result = command(list(argv), cwd=checkout)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)

        registry = {
            "defaults": {"state": "active", "labels": {"ready": "agent-work", "active": "agent-active", "done": "agent-done"}},
            "projects": [{
                "project_id": "cron-canary",
                "repo": REPO,
                "worktree": str(checkout),
                "issue_target_prefixes": [token],
                "state_policy": {"default_state": "active"},
                "runner": {"cwd": str(checkout), "proof_command": ["bash", "-lc", "test \"$(cat marker.txt)\" = FIXED"]},
            }],
        }
        registry_path = work / "registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        state.mkdir()
        (state / "state.json").write_text(json.dumps({"schema": "agent_skills.project_watchdog.state.v2", "global": {"state": "active"}, "projects": {}, "rotation": {}}), encoding="utf-8")

        created = command([
            "gh", "issue", "create", "--repo", REPO, "--title", f"Project Watchdog cron canary {token}",
            "--label", "agent-work", "--body",
            f"Controlled Project Watchdog agentic-eval canary.\n\nTarget: {token}\n\nChange marker.txt from BROKEN to FIXED. Do not change any other file. The controller owns proof and issue closure.",
        ], cwd=ROOT)
        if created.returncode:
            raise RuntimeError(created.stderr or created.stdout)
        match = re.search(r"/issues/(\d+)", created.stdout)
        if not match:
            raise RuntimeError(f"could not parse created issue URL: {created.stdout!r}")
        issue_number = int(match.group(1))

        visible = False
        for _ in range(20):
            listed = gh("issue", "list", "--repo", REPO, "--state", "open", "--label", "agent-work", "--json", "number", "--limit", "100")
            if any(item.get("number") == issue_number for item in listed):
                visible = True
                break
            time.sleep(1)
        if not visible:
            raise RuntimeError(f"created issue {issue_number} was not visible to the production list query")

        env = os.environ.copy()
        env.update({
            "PROJECT_WATCHDOG_REGISTRY": str(registry_path),
            "PROJECT_WATCHDOG_STATE_ROOT": str(state),
            "PROJECT_WATCHDOG_LOCK": str(work / "watchdog.lock"),
            "PROJECT_WATCHDOG_LOG": str(state / "events.jsonl"),
        })
        tick = command(["flock", "-n", str(work / "watchdog.lock"), str(RUN), "tick", "--apply", "--project", "cron-canary", "--lock-held"], cwd=ROOT, env=env)
        try:
            tick_result = json.loads(tick.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"tick did not return JSON: {tick.stdout!r} {tick.stderr!r}") from exc

        issue = gh("issue", "view", str(issue_number), "--repo", REPO, "--json", "state,labels,title,url")
        labels = sorted(item["name"] for item in issue["labels"])
        receipt_path = Path(str(tick_result.get("receipt") or ""))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        marker = (checkout / "marker.txt").read_text(encoding="utf-8")
        diff = command(["git", "diff", "--", "marker.txt"], cwd=checkout).stdout
        summary = {
            "schema": "project_watchdog.cron_real_ticket_evidence.v1",
            "ok": tick.returncode == 0 and tick_result.get("outcome") == "success",
            "cron_argv": ["flock", "-n", "<isolated-lock>", str(RUN), "tick", "--apply", "--project", "cron-canary", "--lock-held"],
            "issue": {"number": issue_number, "state": issue["state"], "labels": labels, "url": issue["url"]},
            "tick": tick_result,
            "marker": marker,
            "diff": diff,
            "receipt": receipt,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        assert summary["ok"] is True
        assert marker == "FIXED\n" and "-BROKEN" in diff and "+FIXED" in diff
        assert issue["state"] == "CLOSED"
        assert "agent-done" in labels and "agent-active" not in labels and "agent-work" not in labels
        assert receipt.get("ticket") == f"{REPO}#{issue_number}"
        assert receipt.get("pi_subagents", {}).get("ok") is True
        assert receipt.get("proof", {}).get("ok") is True
        assert receipt.get("close_readback", {}).get("state") == "CLOSED"
        print(json.dumps({"ok": True, "issue": issue["url"], "receipt": str(receipt_path)}, sort_keys=True))
        print("PROJECT_WATCHDOG_CRON_REAL_TICKET_OK")


if __name__ == "__main__":
    main()
