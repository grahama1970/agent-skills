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
    """Reproduce Tau's canonical_sha256 exactly, over the goal minus its hash.

    Tau recomputes this and refuses the spec on mismatch, so the encoding is not
    ours to choose: sort_keys, tight separators, and ensure_ascii=False. The
    default ensure_ascii=True silently diverges the moment a goal summary
    contains a non-ASCII character.
    """
    payload = {k: v for k, v in goal.items() if k != "goal_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_spec(*, contract: Path, run_dir: Path, run_id: str,
               persona: str, cycle_id: str, timeout_seconds: int) -> dict[str, Any]:
    spine = yaml.safe_load(contract.read_text(encoding="utf-8"))
    if not isinstance(spine, dict) or not isinstance(spine.get("steps"), list):
        raise SystemExit(f"BLOCKED_BAD_CONTRACT: {contract} has no steps")

    receipts_dir = run_dir / "dag_receipts"
    shim = ROOT / "scripts" / "dag_step.py"

    goal = {
        "goal_id": "persona-dream-spine",
        "goal_version": 1,
        "summary": (
            "Produce a dream from memory residue and journal it. Terminates at "
            "the spoken journal; the video lane is an optional branch and "
            "conversation is a downstream consumer, not a step."
        ),
        "completion_criteria": [
            "every spine node returns a schema-valid PASS node receipt",
            "each node produced the artifacts its step declared in the contract",
            f"the terminal node {spine.get('terminates_at')!r} produced its artifact",
        ],
    }
    goal_hash = _goal_hash(goal)

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
            "--produces", produces,
            "--proves", str(step.get("proves") or ""),
            "--does-not-prove", str(step.get("does_not_prove") or ""),
            "--goal-hash", goal_hash,
        ]
        # Omitted entirely when the step takes no run directory: Tau requires
        # every argv item to be a non-empty string, so an empty flag value is
        # not a way to say "none".
        # `=` form: the VALUE starts with a dash (--run-root), and argparse
        # would otherwise read it as the next flag.
        if run_dir_arg:
            command += [f"--run-dir-arg={run_dir_arg}"]
        subs = {"persona": persona, "cycle_id": cycle_id, "run_dir": str(run_dir)}
        for raw in step.get("args") or []:
            command += [f"--step-arg={str(raw).format(**subs)}"]

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

    return {
        "schema": DAG_SPEC_SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir / "dag_run"),
        "goal": {**goal, "goal_hash": goal_hash},
        "nodes": nodes,
        "extensions": {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "contract": str(contract),
            "contract_sha256": "sha256:" + hashlib.sha256(
                contract.read_bytes()).hexdigest(),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--persona", default="embry")
    ap.add_argument("--cycle-id", default="", help="cycle id; generated when omitted")
    args = ap.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    cycle_id = args.cycle_id or f"cycle_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    run_id = args.run_id or f"dream-{cycle_id}"
    spec = build_spec(contract=args.contract.resolve(), run_dir=run_dir,
                      run_id=run_id, persona=args.persona, cycle_id=cycle_id,
                      timeout_seconds=args.timeout_seconds)

    out = args.out or (run_dir / "dag-spec.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
