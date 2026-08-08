#!/usr/bin/env python3
"""Compile the dream spine into a Tau DAG spec.

The spine contract is the source of truth; this turns it into
`tau.generic_dag_spec.v1` so Tau executes it. That division matters:

    contracts/dream_spine.v1.yaml   WHAT the pipeline is
    this script                     compiles it
    tau dag-run                     EXECUTES and enforces it

Tau's runner already rejects cycles and unknown dependencies, runs nodes in
dependency order, gates each downstream node on a schema-valid PASS receipt,
resumes from valid receipts, and fails closed on timeout, non-zero exit, missing
receipt, invalid receipt, or a blocked verdict. Writing a second orchestrator
beside that would be the same mistake this whole effort exists to stop -- an
agent solving a problem that was already solved, in its own idiom.

Nodes are strictly sequential: each depends on the one before it, because the
journal cannot be written before the dream and the dream cannot be composed
before the residue. A step that fails leaves everything after it unreachable,
which is the behaviour the legacy 42-step ledger lacked when it sat at
BLOCKED_FINAL_ACCEPTANCE while work continued around it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "dream_spine.v1.yaml"
DAG_SPEC_SCHEMA = "tau.generic_dag_spec.v1"


def _goal_hash(goal: dict[str, Any]) -> str:
    """Canonical over the goal object, per the Tau convention."""
    canonical = json.dumps(goal, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_spec(*, contract: Path, run_dir: Path, run_id: str,
               step_args: list[str], timeout_seconds: int) -> dict[str, Any]:
    spine = yaml.safe_load(contract.read_text(encoding="utf-8"))
    if not isinstance(spine, dict) or not isinstance(spine.get("steps"), list):
        raise SystemExit(f"BLOCKED_BAD_CONTRACT: {contract} has no steps")

    receipts_dir = run_dir / "dag_receipts"
    shim = ROOT / "scripts" / "dag_step.py"

    nodes: list[dict[str, Any]] = []
    previous: str | None = None

    for step in spine["steps"]:
        node_id = str(step["id"])
        produces = ",".join(str(p) for p in step.get("produces") or [])
        run_dir_arg = step.get("run_dir_arg", "--run-dir")

        command = [
            "python3", str(shim),
            "--node-id", node_id,
            "--command", str(step["command"]),
            "--receipt", str(receipts_dir / f"{node_id}.json"),
            "--run-dir", str(run_dir),
            "--run-dir-arg", str(run_dir_arg or ""),
            "--produces", produces,
            "--proves", str(step.get("proves") or ""),
            "--does-not-prove", str(step.get("does_not_prove") or ""),
        ]
        for extra in step_args:
            command += ["--step-arg", extra]

        nodes.append({
            "node_id": node_id,
            "role": "backend",
            "command": command,
            # Strictly sequential: the journal cannot precede the dream.
            "depends_on": [previous] if previous else [],
            "accepted_context_from": [previous] if previous else [],
            "receipt_path": str(receipts_dir / f"{node_id}.json"),
            "timeout_seconds": timeout_seconds,
            "max_attempts": 1,
        })
        previous = node_id

    goal = {
        "goal_id": "persona-dream-spine",
        "goal_version": 1,
        "statement": (
            "Produce a dream from memory residue and journal it. Terminates at "
            "the spoken journal; the video lane is an optional branch and "
            "conversation is a downstream consumer, not a step."
        ),
        "contract": str(contract),
        "contract_sha256": "sha256:" + hashlib.sha256(
            contract.read_bytes()).hexdigest(),
    }

    return {
        "schema": DAG_SPEC_SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir / "dag_run"),
        "goal": {**goal, "goal_hash": _goal_hash(goal)},
        "nodes": nodes,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--step-arg", action="append", default=[])
    args = ap.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    run_id = args.run_id or f"dream-{run_dir.name}"
    spec = build_spec(contract=args.contract.resolve(), run_dir=run_dir,
                      run_id=run_id, step_args=list(args.step_arg),
                      timeout_seconds=args.timeout_seconds)

    out = args.out or (run_dir / "dag-spec.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
