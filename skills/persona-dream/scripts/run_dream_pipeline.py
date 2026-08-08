#!/usr/bin/env python3
"""Run the generate-dream spine deterministically, or refuse.

WHY THIS EXISTS
---------------
persona-dream had 284 scripts and a run.sh exposing 203 subcommands, with no
single entrypoint for "produce a dream and journal it". An agent handed that
does not follow a pipeline; it assembles one, differently every time. Observed
directly: an agent (me) spent a session calling scripts by path, wrote three new
ones, and never invoked run.sh once. Nothing objected, because nothing was
watching.

So the fix is not a better document. It is one door, and three refusals.

WHAT IT REFUSES
---------------
1. A dirty run directory. Stale artifacts must not masquerade as fresh output.
2. A step that exits 0 without producing its declared artifacts. Exit status is
   what a script CLAIMS; artifacts are what it DID. Only the second counts.
3. Continuing past a failed step. The legacy 42-step ledger sat at
   BLOCKED_FINAL_ACCEPTANCE while work continued around it; that is the exact
   behaviour this makes impossible.

It also REPORTS undeclared artifacts -- files in the run directory that no step
owns. That is the anti-bespoke check: gating invocation alone does not help when
the bypass is "write a new script", but an artifact nothing declared is visible
the moment anyone looks.

Steps are invoked through run.sh, never by path, so there is exactly one door
and it is the one this enforces.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "dream_spine.v1.yaml"
RUN_SH = ROOT / "run.sh"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_spine(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError(f"{path} is not a spine contract")
    return data


def assert_clean_run_dir(run_dir: Path) -> None:
    """A pipeline that tolerates leftovers cannot prove it produced anything."""
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(
            f"BLOCKED_RUN_DIR_NOT_EMPTY: {run_dir}\n"
            "  A stale artifact here would be indistinguishable from fresh output.\n"
            "  Use a new --run-dir, or delete this one deliberately."
        )
    run_dir.mkdir(parents=True, exist_ok=True)


def run_step(step: dict[str, Any], run_dir: Path, extra: list[str],
             dry_run: bool) -> dict[str, Any]:
    """Invoke one step through run.sh and verify it produced what it declared."""
    command = str(step["command"])
    produces = [str(p) for p in step.get("produces") or []]
    # Each step declares how it wants the run directory named, because they do
    # not agree: --run-root, --run-dir, --cycles-dir, or none at all.
    run_dir_arg = step.get("run_dir_arg", "--run-dir")
    cmd = [str(RUN_SH), command]
    if run_dir_arg:
        cmd += [str(run_dir_arg), str(run_dir)]
    cmd += extra

    record: dict[str, Any] = {
        "step_id": step["id"],
        "step_name": step["name"],
        "command": command,
        "argv": cmd,
        "declared_artifacts": produces,
        "proves": step.get("proves"),
        "does_not_prove": step.get("does_not_prove"),
        "started_at": _now(),
    }

    if dry_run:
        record["status"] = "DRY_RUN"
        return record

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        record["status"] = "BLOCKED_NO_SUCH_ENTRYPOINT"
        record["failed_gates"] = [f"run.sh not executable at {RUN_SH}"]
        return record
    except subprocess.TimeoutExpired:
        record["status"] = "BLOCKED_STEP_TIMEOUT"
        record["failed_gates"] = [f"{command} exceeded 1800s"]
        return record

    record["exit_code"] = proc.returncode
    record["stderr_tail"] = proc.stderr[-800:]

    # A step is not trusted on its exit code alone.
    missing = [name for name in produces if not (run_dir / name).is_file()]
    produced = {
        name: _sha256(run_dir / name)
        for name in produces
        if (run_dir / name).is_file()
    }
    record["produced"] = produced

    if proc.returncode != 0:
        record["status"] = "FAIL_STEP_EXIT"
        record["failed_gates"] = [f"{command} exited {proc.returncode}"]
    elif missing:
        record["status"] = "FAIL_ARTIFACTS_NOT_PRODUCED"
        record["failed_gates"] = [f"declared but absent: {name}" for name in missing]
        record["note"] = (
            "The step reported success and produced nothing. Exit status is a "
            "claim; artifacts are evidence."
        )
    else:
        record["status"] = "PASS"

    record["finished_at"] = _now()
    return record


def find_undeclared(run_dir: Path, spine: dict[str, Any]) -> list[str]:
    """Files nothing in the contract owns. The bespoke path, made visible."""
    owned: set[str] = set()
    for step in spine["steps"]:
        owned.update(str(p) for p in step.get("produces") or [])
    patterns = [str(p) for p in spine.get("permitted_unowned") or []]

    undeclared = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(run_dir))
        if rel in owned:
            continue
        if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat)
               for pat in patterns):
            continue
        undeclared.append(rel)
    return undeclared


def run_pipeline(*, run_dir: Path, contract: Path, extra: list[str],
                 dry_run: bool, allow_dirty: bool) -> dict[str, Any]:
    spine = load_spine(contract)
    if not allow_dirty and not dry_run:
        assert_clean_run_dir(run_dir)

    steps: list[dict[str, Any]] = []
    stopped_at: str | None = None

    for step in spine["steps"]:
        record = run_step(step, run_dir, extra, dry_run)
        steps.append(record)
        if record["status"] not in ("PASS", "DRY_RUN"):
            # Fail closed. Everything downstream is unreachable, and saying so
            # is more useful than attempting it.
            stopped_at = str(step["id"])
            for later in spine["steps"][len(steps):]:
                steps.append({
                    "step_id": later["id"],
                    "step_name": later["name"],
                    "command": later["command"],
                    "status": "NOT_REACHED",
                    "blocked_by": stopped_at,
                })
            break

    undeclared = find_undeclared(run_dir, spine) if run_dir.is_dir() else []
    passed = [s for s in steps if s["status"] == "PASS"]

    receipt: dict[str, Any] = {
        "schema": "persona_dream.dream_pipeline_receipt.v1",
        "created_at": _now(),
        "run_dir": str(run_dir),
        "contract": str(contract),
        "contract_sha256": _sha256(contract),
        "dry_run": dry_run,
        "mocked": False,
        "live": not dry_run,
        "steps": steps,
        "steps_passed": len(passed),
        "steps_total": len(spine["steps"]),
        "stopped_at": stopped_at,
        "terminates_at": spine.get("terminates_at"),
        "undeclared_artifacts": undeclared,
        "boundary": (
            "This receipt proves the declared steps ran in order and produced "
            "their declared artifacts. It proves nothing about whether the "
            "dream is any good, and nothing about the optional video lane."
        ),
    }

    if dry_run:
        receipt["status"] = "DRY_RUN"
    elif stopped_at:
        receipt["status"] = f"BLOCKED_AT_{stopped_at.upper()}"
    else:
        receipt["status"] = "PASS_SPINE_COMPLETE"

    if undeclared:
        receipt["undeclared_note"] = (
            "These files are in the run directory and no step declares them. "
            "Either a step's contract is incomplete, or something wrote here "
            "outside the pipeline. Both are worth knowing; neither is silent."
        )

    if not dry_run and run_dir.is_dir():
        (run_dir / "dream_pipeline_receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
        )
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the step plan without executing anything")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="reuse a non-empty run dir; recorded in the receipt")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("step_args", nargs="*",
                    help="extra args forwarded to every step")
    args = ap.parse_args()

    receipt = run_pipeline(
        run_dir=args.run_dir, contract=args.contract, extra=list(args.step_args),
        dry_run=args.dry_run, allow_dirty=args.allow_dirty,
    )

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']}  ({receipt['steps_passed']}/{receipt['steps_total']} steps)")
        for step in receipt["steps"]:
            mark = {"PASS": "✓", "DRY_RUN": "·", "NOT_REACHED": "–"}.get(step["status"], "✗")
            print(f"  {mark} {step['step_id']:16s} {step['status']}")
            for gate in step.get("failed_gates") or []:
                print(f"      {gate}")
        if receipt["undeclared_artifacts"]:
            print(f"  undeclared artifacts: {receipt['undeclared_artifacts']}")

    return 0 if receipt["status"] in ("PASS_SPINE_COMPLETE", "DRY_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
