#!/usr/bin/env python3
"""Run the capability-gated debugger eval matrix (#1441).

The matrix maps the audit's suite families to concrete agentic-eval fixtures and
runs each through the /agentic-evals runner, gated by an explicit capability
model. A capability that is absent BLOCKS its suites -- it never passes them.

Capabilities:
  headless      always present (deterministic + local-process cases)
  vscode-live   an open, trusted VS Code workspace with the bridge extension
                (probed via DEBUGGER_VSCODE_WORKSPACE + a recent bridge status)
  remote-ssh    a VS Code Remote SSH workspace host (probed via VSCODE_IPC_HOOK_CLI
                + SSH_CONNECTION); absent on a local workstation
  human         a human present to confirm/correct paused state; asserted only
                via --with-human (never inferred)

Each suite emits a debugger.eval_receipt.v1 JSON receipt naming the suite,
capability, fixtures, per-case outcomes, and the derived readiness. Exit 0 when
every suite whose capability is PRESENT is READY; exit 1 otherwise. BLOCKED
capability-absent suites do not fail the matrix (they are reported, not passed).

Usage:
  run_eval_matrix.py [--out DIR] [--suite NAME ...] [--with-human]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FIXTURES = SKILL / "fixtures"
AGENTIC = SKILL.parent / "agentic-evals"

# The audit's suite families -> capability + fixtures. Fixture names are the
# canonical files in fixtures/; a family with no runnable fixture yet lists
# planned=... so the 72-case path stays visible instead of silently shrinking.
MATRIX: dict[str, dict] = {
    "integrity": {
        "capability": "headless",
        "fixtures": ["proof-security.json", "proof-correlation.json"],
    },
    "harness-generation": {
        "capability": "headless",
        "fixtures": ["agentic_eval.json"],
    },
    "headless-python": {
        "capability": "headless",
        "fixtures": ["variable-state-bug.json", "secret-redaction.json"],
    },
    "headless-typescript": {
        "capability": "headless",
        # node-shape hostile/genuine proofs are validated inside proof-correlation
        "fixtures": ["proof-correlation.json"],
        "cases": ["reject-node-borrowed-frame", "accept-node-genuine-frame"],
    },
    "headless-rust": {
        "capability": "headless",
        "fixtures": ["proof-correlation.json"],
        "cases": ["rust-transcript-without-stop-is-invalid"],
    },
    "proof-security": {
        "capability": "headless",
        "fixtures": ["proof-security.json"],
    },
    "failure-recovery": {
        "capability": "headless",
        "fixtures": ["runtime-containment.json"],
    },
    "vscode-session": {
        "capability": "vscode-live",
        "fixtures": ["vscode-session.json", "open-in-vscode.json"],
    },
    "vscode-races": {
        "capability": "vscode-live",
        "fixtures": ["vscode-races.json"],
    },
    "vscode-collaboration": {
        "capability": "vscode-live",
        "fixtures": ["walkthrough.json", "walkthrough-converse.json", "walkthrough-e2e.json",
                      "bounded-inspection.json"],
    },
    "voice-collaboration": {
        "capability": "vscode-live",
        "fixtures": ["walkthrough-voice.json", "voice-delivery.json", "answer-grounding.json"],
    },
    "remote-ssh-live": {
        "capability": "remote-ssh",
        "fixtures": [],
        # Runs the live authority gate instead of an agentic-eval fixture: it
        # requires this process to run INSIDE the Remote SSH context (ssh shell
        # with the remote window's VSCODE_IPC_HOOK_CLI). Proven passed
        # 2026-08-26 over an ssh-remote+localhost workspace host
        # (debugger.remote_ssh_bridge_proof.v1: proof_valid=true,
        # accepted_relocation=true, authority ssh-remote/workspace).
        "gate": ["bash", "sanity-bridge-remote-ssh.sh", "--allow-live"],
    },
    "human-collaboration-live": {
        "capability": "human",
        "fixtures": [],
        "planned": "human confirmation/correction bound to an exact stop sequence",
    },
}


def capability_present(name: str, with_human: bool) -> tuple[bool, str]:
    if name == "headless":
        return True, "always present"
    if name == "vscode-live":
        workspace = os.environ.get("DEBUGGER_VSCODE_WORKSPACE", "")
        if workspace and Path(workspace, ".vscode", "debugger-bridge").is_dir():
            return True, f"open workspace with bridge dir: {workspace}"
        return False, "no DEBUGGER_VSCODE_WORKSPACE with a bridge dir"
    if name == "remote-ssh":
        if os.environ.get("SSH_CONNECTION") and os.environ.get("VSCODE_IPC_HOOK_CLI"):
            return True, "SSH_CONNECTION + VSCODE_IPC_HOOK_CLI present"
        return False, "not a VS Code Remote SSH workspace host"
    if name == "human":
        return (True, "--with-human asserted") if with_human else (False, "no human asserted (--with-human)")
    return False, f"unknown capability {name}"


def run_fixture(fixture: str, out_dir: Path) -> dict:
    report_path = out_dir / f"report.{fixture.replace('/', '_')}"
    cmd = [
        "uv", "run", "--project", str(AGENTIC), "python", str(AGENTIC / "src" / "runner.py"),
        "run", fixture, "--report-only", "-o", str(report_path),
    ]
    result = subprocess.run(cmd, cwd=FIXTURES, capture_output=True, text=True, timeout=3600)
    try:
        report = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"fixture": fixture, "readiness": "ERROR",
                "error": (result.stdout + result.stderr).strip()[-300:]}
    return {
        "fixture": fixture,
        "readiness": report.get("readiness"),
        "cases": [
            {"name": c.get("name"),
             "outcomes": [t.get("outcome") for t in c.get("trials", [])]}
            for c in report.get("cases", [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "agent-skills-debugger" / "eval-matrix")
    parser.add_argument("--suite", action="append", default=None)
    parser.add_argument("--with-human", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    selected = args.suite or list(MATRIX)
    ran: dict[str, dict] = {}
    failures = 0
    fixture_cache: dict[str, dict] = {}
    for suite in selected:
        spec = MATRIX.get(suite)
        if spec is None:
            print(f"SUITE {suite}: unknown (valid: {', '.join(MATRIX)})", file=sys.stderr)
            return 2
        present, why = capability_present(spec["capability"], args.with_human)
        receipt: dict = {
            "schema": "debugger.eval_receipt.v1",
            "suite": suite,
            "capability": spec["capability"],
            "capabilityPresent": present,
            "capabilityEvidence": why,
            "fixtures": spec["fixtures"],
        }
        if spec.get("planned"):
            receipt["planned"] = spec["planned"]
        if present and spec.get("gate"):
            result = subprocess.run(spec["gate"], cwd=SKILL, capture_output=True, text=True, timeout=1800)
            receipt["gateExit"] = result.returncode
            receipt["gateTail"] = (result.stdout + result.stderr).strip()[-300:]
            receipt["readiness"] = "READY" if result.returncode == 0 else "NOT_READY"
            if result.returncode != 0:
                failures += 1
            print(f"SUITE {suite}: {receipt['readiness']} (gate exit {result.returncode})")
        elif not present or not spec["fixtures"]:
            receipt["readiness"] = "BLOCKED" if not present else "PLANNED"
            print(f"SUITE {suite}: {receipt['readiness']} ({why})")
        else:
            results = []
            for fixture in spec["fixtures"]:
                if fixture not in fixture_cache:
                    fixture_cache[fixture] = run_fixture(fixture, args.out)
                results.append(fixture_cache[fixture])
            wanted_cases = spec.get("cases")
            if wanted_cases:
                for result in results:
                    result = dict(result)
                    result["cases"] = [c for c in result.get("cases", []) if c["name"] in wanted_cases]
            receipt["results"] = results
            statuses = {r.get("readiness") for r in results}
            receipt["readiness"] = "READY" if statuses == {"READY"} else "NOT_READY"
            if receipt["readiness"] != "READY":
                failures += 1
            print(f"SUITE {suite}: {receipt['readiness']} "
                  f"({', '.join(f'{r['fixture']}={r.get('readiness')}' for r in results)})")
        (args.out / f"receipt.{suite}.json").write_text(json.dumps(receipt, indent=2) + "\n")
        ran[suite] = receipt

    summary = {
        "schema": "debugger.eval_matrix_summary.v1",
        "suites": {name: r.get("readiness") for name, r in ran.items()},
        "failures": failures,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"MATRIX {'READY' if failures == 0 else 'NOT_READY'} "
          f"({sum(1 for r in ran.values() if r.get('readiness') == 'READY')} ready, "
          f"{sum(1 for r in ran.values() if r.get('readiness') == 'BLOCKED')} blocked-by-capability, "
          f"{sum(1 for r in ran.values() if r.get('readiness') == 'PLANNED')} planned) "
          f"receipts: {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
