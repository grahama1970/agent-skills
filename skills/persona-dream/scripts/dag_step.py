#!/usr/bin/env python3
"""Run one spine step for Tau, and tell Tau the truth about it.

Tau's generic DAG runner gates every downstream node on a schema-valid PASS
receipt, and fails closed on timeout, non-zero exit, a missing receipt, an
invalid receipt, or a BLOCKED verdict. That is the whole enforcement engine and
it already exists -- persona-dream does not need its own.

What Tau cannot know is which FILES a persona-dream step was supposed to leave
behind. So that is the only judgement this shim adds: it invokes the step
through run.sh, checks the artifacts the spine contract declared, and writes
`tau.generic_dag_node_receipt.v1`. A step that exits 0 having produced nothing
gets a BLOCKED verdict, because an exit code is what a script claims and an
artifact is what it did.

This never decides whether the dream is any good. It decides whether the step
did what it said it would.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_step_gate import validate_artifacts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / "run.sh"
NODE_RECEIPT_SCHEMA = "tau.generic_dag_node_receipt.v1"


class _PydanticGateBlocked(Exception):
    """Consumed-artifact pydantic gate failed; the step must not execute."""


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--command", required=True, help="run.sh subcommand for this step")
    ap.add_argument("--receipt", required=True, type=Path)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--artifact-dir", type=Path, default=None,
                    help="where declared artifacts actually land; defaults to "
                         "--run-dir. The dream cycle writes into its cycle "
                         "directory, not the DAG's bookkeeping directory.")
    ap.add_argument("--run-dir-arg", default="", help="empty when the step takes none")
    ap.add_argument("--produces", default="", help="comma-separated declared artifacts")
    ap.add_argument("--consumes", default="",
                    help="comma-separated input artifacts, pydantic-validated "
                         "BEFORE the step runs (first deterministic gate)")
    ap.add_argument("--proves", default="")
    ap.add_argument("--does-not-prove", default="")
    ap.add_argument("--goal-hash", default="",
                    help="binds this receipt to the DAG goal; Tau requires it")
    ap.add_argument("--step-arg", action="append", default=[],
                    help="extra argument forwarded to the step; repeatable")
    args = ap.parse_args()

    produces = [p for p in args.produces.split(",") if p]
    cmd = [str(RUN_SH), args.command]
    if args.run_dir_arg:
        cmd += [args.run_dir_arg, str(args.run_dir)]
    cmd += list(args.step_arg)

    errors: list[str] = []
    started = time.time()
    exit_code: int | None = None
    stderr_tail = ""

    # Pydantic FIRST gate: consumed artifacts must validate before the step runs.
    consume_dir = args.artifact_dir or args.run_dir
    consumed = [consume_dir / n for n in args.consumes.split(",") if n]
    pydantic_errors = [
        {"type": "artifact_missing", "loc": [str(path)], "msg": "file not found"}
        for path in consumed if not path.is_file()
    ]
    pydantic_errors += validate_artifacts([p for p in consumed if p.is_file()])
    if pydantic_errors:
        errors.extend(
            f"pydantic_gate_input {e['type']} at {e['loc']}: {e.get('msg', '')}"
            for e in pydantic_errors
        )

    try:
        if errors:
            raise _PydanticGateBlocked
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        exit_code = proc.returncode
        stderr_tail = proc.stderr[-8000:]
        if proc.returncode != 0:
            errors.append(f"{args.command} exited {proc.returncode}: {stderr_tail[-2500:]}")
    except subprocess.TimeoutExpired:
        errors.append(f"{args.command} exceeded 1800s")
    except _PydanticGateBlocked:
        pass  # consumed-artifact validation failed; step never ran
    except FileNotFoundError:
        errors.append(f"run.sh not executable at {RUN_SH}")

    # The artifact check. This is the part Tau cannot do for us.
    artifact_dir = args.artifact_dir or args.run_dir
    artifacts: list[dict[str, Any]] = []
    for name in produces:
        path = artifact_dir / name
        if path.is_file():
            artifacts.append({"path": str(path), "sha256": _sha256(path),
                              "bytes": path.stat().st_size})
        else:
            errors.append(f"declared artifact not produced: {artifact_dir / name}")
    # Pydantic gate on produced JSON artifacts (producer-side seam validation).
    produced_errors = validate_artifacts(
        [artifact_dir / n for n in produces if (artifact_dir / n).is_file()]
    )
    errors.extend(
        f"pydantic_gate_output {e['type']} at {e['loc']}: {e.get('msg', '')}"
        for e in produced_errors
    )
    pydantic_errors.extend(produced_errors)

    ok = not errors
    receipt = {
        "schema": NODE_RECEIPT_SCHEMA,
        "node_id": args.node_id,
        "goal_hash": args.goal_hash,
        "status": "PASS" if ok else "BLOCKED",
        "verdict": "PASS" if ok else "BLOCKED",
        "artifacts": artifacts,
        "commands_run": [{"argv": cmd, "exit_code": exit_code,
                          "elapsed_seconds": round(time.time() - started, 3)}],
        "errors": errors,
        "policy_exceptions": [],
        "handoff_summary": (
            f"{args.node_id}: produced {len(artifacts)}/{len(produces)} declared artifacts. "
            + (args.proves if ok else f"BLOCKED — {errors[0]}")
        ),
        "proves": args.proves,
        "does_not_prove": args.does_not_prove,
        "pydantic_errors": pydantic_errors,
        "mocked": False,
        "live": True,
        "stderr_tail": stderr_tail,
    }

    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")

    print(f"{receipt['status']} {args.node_id} "
          f"({len(artifacts)}/{len(produces)} artifacts)")
    for err in errors:
        print(f"  {err}")
    # Non-zero so Tau records the failure even before it reads the receipt.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
