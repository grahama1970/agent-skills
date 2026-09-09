#!/usr/bin/env python3
"""Retained eval for Ask runs resume routing to Tau command-spec resume."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    skill_root = Path(__file__).resolve().parents[1]
    fixture = skill_root / "tests" / "fixtures" / "run_projection" / "roundtable_partial"
    with tempfile.TemporaryDirectory(prefix="ask-command-spec-resume-") as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        shutil.copytree(fixture, run_dir)
        (run_dir / "agents").mkdir()
        (run_dir / "command-specs").mkdir()
        (run_dir / "tau-receipts").mkdir()
        (run_dir / "tau-receipts" / "dag-run.sqlite3").write_text("sqlite marker", encoding="utf-8")
        tau_root = root / "tau"
        tau_root.mkdir()
        (tau_root / "pyproject.toml").write_text("[project]\nname='tau'\n", encoding="utf-8")
        env = dict(os.environ)
        env["ASK_TAU_PROJECT_ROOT"] = str(tau_root)
        completed = subprocess.run(
            [str(skill_root / "run.sh"), "runs", "resume", str(run_dir), "--json"],
            cwd=skill_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(completed.stdout)
        next_command = str(payload.get("next_command") or "")
        proof = {
            "schema": "ask.command_spec_resume_routing_proof.v1",
            "ok": completed.returncode == 0
            and payload.get("outcome") == "planned"
            and "dag-command-spec-resume" in next_command
            and "workflow-resume" not in next_command
            and "--preserve-node handler-webgpt" in next_command
            and "--rerun-node handler-webclaude" in next_command
            and "--rerun-dependent join" in next_command,
            "mocked": False,
            "live": True,
            "provider_live": False,
            "returncode": completed.returncode,
            "outcome": payload.get("outcome"),
            "next_command": next_command,
            "already_accepted": (payload.get("plan") or {}).get("already_accepted"),
            "would_rerun": (payload.get("plan") or {}).get("would_rerun"),
            "stderr": completed.stderr,
        }
    out.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
