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
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_step_gate import NodeReceipt, TriageError, validate_artifact, validate_artifacts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / "run.sh"
TRIAGE_RUN = ROOT.parent / "triage-error" / "run.sh"
NODE_RECEIPT_SCHEMA = "tau.generic_dag_node_receipt.v1"


class _PydanticGateBlocked(Exception):
    """Consumed-artifact pydantic gate failed; the step must not execute."""


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _triage(signal: str) -> dict[str, Any]:
    """Map a step failure to triage-error's typed code/cause/next_command JSON."""
    try:
        proc = subprocess.run(
            [str(TRIAGE_RUN), "classify", "--text", signal, "--layer", "persona-dream"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            result = json.loads(proc.stdout)
            if not isinstance(result, dict):
                raise ValueError("triage must return an object")
            result["next_command"] = result.get("next_command") or f"Inspect the named artifact and run {TRIAGE_RUN} classify --text <signal> --layer persona-dream"
            return TriageError.model_validate(result).model_dump(mode="json")
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass  # the explicit typed unavailable receipt below preserves the failure
    digest = hashlib.sha256(signal.encode("utf-8")).hexdigest()[:8]
    return {
        "code": f"persona_dream_unclassified_{digest}",
        "layer": "persona-dream",
        "cause": signal,
        "next_command": f"Run {TRIAGE_RUN} classify --text <signal> --layer persona-dream",
        "recoverable": None,
        "not_this": [],
        "ambiguous": True,
        "matched_tokens": [],
    }


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
    ap.add_argument("--input-receipt", type=Path, action="append", default=[],
                    help="upstream PASS receipt binding consumed artifact hashes; repeatable")
    ap.add_argument("--input-owner", action="append", default=[],
                    help="<artifact>=<node_id> producer ownership binding; repeatable")
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
    artifact_dir = args.artifact_dir or args.run_dir
    pydantic_errors: list[dict[str, Any]] = []
    unsafe = set()
    for name in [*args.consumes.split(","), *produces]:
        if not name:
            continue
        path = artifact_dir / name
        if Path(name).is_absolute() or ".." in Path(name).parts or not path.resolve().is_relative_to(artifact_dir.resolve()):
            unsafe.add(name)
            pydantic_errors.append({"type": "artifact_path_escape", "loc": [name], "msg": "artifact must stay within the cycle directory"})
    produces = [n for n in produces if n not in unsafe]
    consumed = [artifact_dir / n for n in args.consumes.split(",") if n and n not in unsafe]
    pydantic_errors.extend({"type": "artifact_missing", "loc": [str(p)], "msg": "file not found"}
                           for p in consumed if not p.is_file())
    # Hash BEFORE validation and re-hash after it: a consumed file swapped
    # between the two reads is a blocked race, not silently revalidated bytes.
    input_hashes = {}
    if not pydantic_errors:
        for path in consumed:
            try:
                input_hashes[str(path.resolve())] = _sha256(path)
            except OSError as exc:
                pydantic_errors.append({"type": "artifact_unreadable", "loc": [str(path)], "msg": str(exc)})
    pydantic_errors += validate_artifacts([p for p in consumed if p.is_file()], require_schema=True)
    if not pydantic_errors:
        for path in consumed:
            if _sha256(path) != input_hashes[str(path.resolve())]:
                pydantic_errors.append({"type": "artifact_changed_during_validation", "loc": [str(path)],
                                        "msg": "consumed bytes changed while being validated"})
    bindings: dict[str, str] = {}
    owners: dict[str, str] = {}
    for receipt_path in args.input_receipt:
        receipt_errors = validate_artifact(receipt_path, require_schema=True)
        pydantic_errors.extend(receipt_errors)
        if receipt_errors:
            continue
        upstream = json.loads(receipt_path.read_text(encoding="utf-8"))
        if upstream.get("schema") != NODE_RECEIPT_SCHEMA or upstream.get("status") != "PASS" or upstream.get("goal_hash") != args.goal_hash:
            pydantic_errors.append({"type": "upstream_receipt_rejected", "loc": [str(receipt_path)], "msg": "upstream PASS and matching goal hash required"})
        for artifact in upstream.get("artifacts", []):
            if isinstance(artifact, dict) and artifact.get("path"):
                claimed = Path(str(artifact["path"])).resolve()
                if not claimed.is_relative_to(artifact_dir.resolve()):
                    pydantic_errors.append({"type": "upstream_receipt_wrong_cycle", "loc": [str(receipt_path), str(claimed)],
                                            "msg": "upstream receipt claims artifacts outside this cycle directory"})
                    continue
                bindings[str(claimed)] = artifact.get("sha256", "")
                owners[str(claimed)] = str(upstream.get("node_id", ""))
    if args.input_receipt:
        for path, digest in input_hashes.items():
            if bindings.get(path) != digest:
                pydantic_errors.append({"type": "upstream_artifact_hash_mismatch", "loc": [path], "msg": "consumed bytes do not match upstream receipt"})
    for entry in args.input_owner:
        name, _, expected_node = entry.partition("=")
        if not name or not expected_node:
            pydantic_errors.append({"type": "input_owner_malformed", "loc": [entry], "msg": "expected <artifact>=<node_id>"})
            continue
        actual = owners.get(str((artifact_dir / name).resolve()))
        if actual != expected_node:
            pydantic_errors.append({"type": "upstream_receipt_wrong_producer", "loc": [name],
                                    "msg": f"artifact must be bound by producer {expected_node!r}, found {actual!r}"})
    if pydantic_errors:
        errors.extend(
            f"pydantic_gate_input {e['type']} at {e['loc']}: {e.get('msg', '')}"
            for e in pydantic_errors
        )

    prior_outputs = {}
    for name in produces:
        path = artifact_dir / name
        if path.is_file():
            stat = path.stat()
            prior_outputs[name] = (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    step_env = {**os.environ, "PERSONA_DREAM_STEP_EXECUTOR": "1"}
    try:
        if errors:
            raise _PydanticGateBlocked
        # Own process group: a timed-out producer must not leave descendant
        # writers mutating the cycle after the step is recorded as failed.
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=step_env, start_new_session=True) as proc:
            try:
                _, step_stderr = proc.communicate(timeout=1800)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
                proc.wait(timeout=30)
                raise
        exit_code = proc.returncode
        stderr_tail = (step_stderr or "")[-8000:]
        if exit_code != 0:
            errors.append(f"{args.command} exited {exit_code}: {stderr_tail[-2500:]}")
    except subprocess.TimeoutExpired:
        errors.append(f"{args.command} exceeded 1800s; process group killed")
    except _PydanticGateBlocked:
        pass  # consumed-artifact validation failed; step never ran
    except OSError as exc:
        errors.append(f"run.sh execution failed at {RUN_SH}: {exc}")

    # The artifact check. This is the part Tau cannot do for us.
    artifacts: list[dict[str, Any]] = []
    for name in produces:
        path = artifact_dir / name
        if path.is_file():
            stat = path.stat()
            if stat.st_size == 0:
                errors.append(f"declared artifact is empty: {path}")
            if exit_code == 0 and prior_outputs.get(name) == (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size):
                errors.append(f"declared artifact was not produced by this execution: {path}")
            artifacts.append({"path": str(path), "sha256": _sha256(path),
                              "bytes": stat.st_size})
        else:
            errors.append(f"declared artifact not produced: {artifact_dir / name}")
    # Pydantic gate on produced JSON artifacts (producer-side seam validation).
    produced_errors = validate_artifacts(
        [artifact_dir / n for n in produces if (artifact_dir / n).is_file()],
        require_schema=True,
    )
    errors.extend(
        f"pydantic_gate_output {e['type']} at {e['loc']}: {e.get('msg', '')}"
        for e in produced_errors
    )
    pydantic_errors.extend(produced_errors)

    for path, digest in input_hashes.items():
        try:
            unchanged = _sha256(Path(path)) == digest
        except OSError:
            unchanged = False
        if not unchanged:
            errors.append(f"consumed artifact changed during execution: {path}")
    triage_errors = [_triage(err) for err in errors]

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
        "triage_errors": triage_errors,
        "policy_exceptions": [],
        "handoff_summary": (
            f"{args.node_id}: produced {len(artifacts)}/{len(produces)} declared artifacts. "
            + (args.proves if ok else f"BLOCKED — {errors[0]}")
        ),
        "proves": args.proves,
        "does_not_prove": args.does_not_prove,
        "pydantic_errors": pydantic_errors,
        "mocked": False,
        "live": exit_code is not None,
        "stderr_tail": stderr_tail,
    }

    receipt = NodeReceipt.model_validate(receipt).model_dump(mode="json", by_alias=True)
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
