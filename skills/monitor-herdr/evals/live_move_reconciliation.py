#!/usr/bin/env python3
"""Live cross-skill proof that a moved agent keeps its monitor state.

Inputs: a running Herdr server, and the sibling ops-herdr skill for the move.
Outputs: a JSON report on stdout.
Failure modes: exits 1 when state does not survive the move, 2 when Herdr is
unreachable.

Monitor state is keyed by pane id and a cross-workspace move changes that id, so
this walks the whole real path -- launch a space, bind an agent, seed a cooldown,
move the pane through ops-herdr, then reconcile -- and asserts the cooldown and
strike count landed on the new id. Nothing here is stubbed: the receipt is the one
ops-herdr actually wrote for a move Herdr actually performed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVAL_DIR.parent
SKILLS_ROOT = SKILL_DIR.parent
OPS_HERDR = SKILLS_ROOT / "ops-herdr" / "run.sh"
LABEL = "monitor-herdr-recon-eval-disposable"
SEED_EPOCH = 1787000000
SEED_STRIKES = 2


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command with output captured, never raising on non-zero."""
    env = {**kwargs.pop("env", {})} or None
    return subprocess.run(argv, text=True, capture_output=True, env=env, **kwargs)


def herdr(args: list[str], herdr_bin: str) -> dict[str, Any] | None:
    """Call Herdr and return parsed JSON, or None when it produced none."""
    proc = run([herdr_bin, *args])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    """Run the live reconciliation proof and print a JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--herdr-bin", default="herdr")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        """Append one assertion outcome."""
        checks.append({"check": name, "ok": passed, "detail": detail})

    if run([args.herdr_bin, "status"]).returncode != 0:
        print(json.dumps({"status": "BLOCKED", "reason": "herdr_unreachable"}, indent=2))
        return 2
    if not OPS_HERDR.exists():
        print(json.dumps({"status": "BLOCKED", "reason": "ops_herdr_missing"}, indent=2))
        return 2

    workspaces: list[str] = []
    with tempfile.TemporaryDirectory(prefix="monitor-herdr-recon-") as tmp:
        tmpdir = Path(tmp)
        state_path = tmpdir / "state.json"
        try:
            launch = run([
                str(OPS_HERDR), "space", "launch", "--repo", str(SKILLS_ROOT),
                "--label", LABEL, "--grid", "1x2",
                "--run-root", str(tmpdir / "runs"), "--no-focus",
            ])
            manifest_data = json.loads(launch.stdout)
            workspaces.append(manifest_data["workspace_id"])
            manifest_path = Path(manifest_data["run_dir"]) / "workstation.json"
            old_pane = manifest_data["tabs"]["agents"]["panes"][0]
            record("space_launch", bool(old_pane), f"pane {old_pane}")

            # Bind an agent record to that pane so `agent move` has a target.
            manifest = json.loads(manifest_path.read_text())
            manifest["agents"]["recon-probe"] = {
                "role": "probe", "kind": "codex", "tab": "agents",
                "pane_id": old_pane, "previous_pane_ids": [],
            }
            manifest_path.write_text(json.dumps(manifest, indent=2))

            # Seed monitor state exactly as a real tick would key it.
            state_path.write_text(json.dumps({
                "schema": "agent_skills.monitor_herdr.state.v1",
                "prompts": {old_pane: {
                    "last_prompt_epoch": SEED_EPOCH,
                    "no_change_strikes": SEED_STRIKES,
                    "submit_confirmed": True,
                }},
            }))

            move = run([
                str(OPS_HERDR), "agent", "move", str(manifest_path),
                "--name", "recon-probe", "--new-space", f"{LABEL}-moved",
            ])
            receipt = json.loads(move.stdout)
            new_pane = receipt["after"]["pane_id"]
            if receipt.get("created_workspace_id"):
                workspaces.append(receipt["created_workspace_id"])
            record("pane_moved", new_pane != old_pane, f"{old_pane} -> {new_pane}")
            record("id_map_reported", receipt["id_map"] == {old_pane: new_pane}, json.dumps(receipt["id_map"]))

            receipts_dir = Path(manifest_data["run_dir"]) / "receipts"
            recon = SKILL_DIR / "run.sh"

            dry = run([str(recon), "reconcile-moves", "--receipts", str(receipts_dir), "--state", str(state_path)])
            after_dry = json.loads(state_path.read_text())["prompts"]
            record("dry_run_does_not_write", old_pane in after_dry and new_pane not in after_dry,
                   f"state keys still {sorted(after_dry)}")
            record("dry_run_reports_migration", '"migrated": 1' in dry.stdout, "reported 1 pending migration")

            applied = run([str(recon), "reconcile-moves", "--receipts", str(receipts_dir),
                           "--state", str(state_path), "--apply"])
            record("apply_exit", applied.returncode == 0, f"exit {applied.returncode}")
            final = json.loads(state_path.read_text())["prompts"]
            record("state_rekeyed", new_pane in final and old_pane not in final, f"state keys now {sorted(final)}")
            entry = final.get(new_pane, {})
            record("cooldown_preserved", entry.get("last_prompt_epoch") == SEED_EPOCH,
                   f"last_prompt_epoch={entry.get('last_prompt_epoch')}")
            record("strikes_preserved", entry.get("no_change_strikes") == SEED_STRIKES,
                   f"no_change_strikes={entry.get('no_change_strikes')}")
        except Exception as exc:  # noqa: BLE001 - the eval must always reach cleanup.
            record("unexpected_error", False, repr(exc))
        finally:
            for workspace_id in workspaces:
                run([args.herdr_bin, "workspace", "close", workspace_id])

    listing = herdr(["workspace", "list"], args.herdr_bin) or {}
    leftovers = [
        w.get("label") for w in (listing.get("result", {}) or {}).get("workspaces", [])
        if str(w.get("label", "")).startswith(LABEL)
    ]
    record("cleanup", not leftovers, f"leftover workspaces: {leftovers}" if leftovers else "none remain")

    failures = [c for c in checks if not c["ok"]]
    report = {"status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
