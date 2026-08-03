#!/usr/bin/env python3
from __future__ import annotations
"""Dewey2 DBA auditor CLI.

Dewey is a thin control panel over repair primitives:

- monitor-sparta observes health and writes repair_queue.jsonl
- memory/create-qras primitives perform actual repair work
- Dewey claims one issue, calls one primitive, verifies receipt, updates one
  queue issue, and exits

This CLI intentionally refuses broad repair paths:

- monitor_sparta.py repair-cycle
- monitor_sparta.py health --fix
- loop-until-green repair loops
- cron promotion
- direct AQL from the Dewey agent
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

app = typer.Typer(help="Dewey2 DBA auditor: one issue, one lane, one receipt, exit.")
queue_app = typer.Typer(help="Monitor-sparta repair queue helpers.")
primitive_app = typer.Typer(help="Direct primitive proof commands.")
embedding_app = typer.Typer(help="Embedding repair primitive commands.")
source_workbook_app = typer.Typer(help="Source workbook parity primitive commands.")
qra_app = typer.Typer(help="QRA repair primitive commands.")

app.add_typer(queue_app, name="queue")
app.add_typer(primitive_app, name="primitive")
primitive_app.add_typer(embedding_app, name="embedding")
primitive_app.add_typer(source_workbook_app, name="source-workbook")
primitive_app.add_typer(qra_app, name="qra")

DEFAULT_MEMORY_ROOT = Path("/home/graham/workspace/experiments/memory")
DEFAULT_AGENT_SKILLS_ROOT = Path("/home/graham/workspace/experiments/agent-skills")
DEFAULT_MONITOR_STATE_DIR = Path("/mnt/storage12tb/media/agents/shared/monitor-sparta")
DEFAULT_QUEUE = DEFAULT_MONITOR_STATE_DIR / "repair_queue.jsonl"
DEFAULT_RUN_ROOT = Path("/mnt/storage12tb/skills/review-db/outputs/dewey-sessions")

EMBEDDING_OPERATION_ALIASES = {
    "inline-vectors": "inline-vectors",
    "inline_embedding_policy": "inline-vectors",
    "missing-qdrant": "missing-qdrant-embeddings",
    "missing-qdrant-embeddings": "missing-qdrant-embeddings",
    "missing_qdrant_embeddings": "missing-qdrant-embeddings",
    "qdrant-pointer-metadata": "qdrant-pointer-metadata",
    "qdrant_pointer_metadata": "qdrant-pointer-metadata",
}

FORBIDDEN_COMMAND_FRAGMENTS = (
    "repair-cycle",
    "health --fix",
    "loop-until-green",
)


def _json_print(value: dict[str, Any]) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


def _refuse_forbidden(cmd: list[str]) -> None:
    joined = shlex.join([str(part) for part in cmd])
    if any(fragment in joined for fragment in FORBIDDEN_COMMAND_FRAGMENTS):
        raise typer.BadParameter(f"Dewey CLI refuses forbidden command: {joined}")


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    env: dict[str, str] | None = None,
) -> int:
    _refuse_forbidden(cmd)
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})
    typer.echo("+ " + shlex.join([str(part) for part in cmd]), err=True)
    proc = subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd),
        env=merged_env,
        check=False,
        timeout=timeout_s,
    )
    return int(proc.returncode)


def _require_apply_env() -> None:
    if os.environ.get("SPARTA_MONITOR_MUTATION_ENABLED") != "1":
        raise typer.BadParameter(
            "Apply requires SPARTA_MONITOR_MUTATION_ENABLED=1. "
            "Run dry-run first and preserve proof artifacts."
        )


def _normalize_embedding_operation(operation: str) -> str:
    normalized = EMBEDDING_OPERATION_ALIASES.get(operation.strip())
    if not normalized:
        allowed = ", ".join(sorted(EMBEDDING_OPERATION_ALIASES))
        raise typer.BadParameter(f"Unknown embedding operation {operation!r}; expected one of: {allowed}")
    return normalized


@app.command("status")
def status(
    queue: Path = typer.Option(DEFAULT_QUEUE, help="Path to monitor-sparta repair_queue.jsonl."),
) -> None:
    """Show Dewey queue status."""
    from dewey_repair_queue import summarize

    _json_print(summarize(queue))


@app.command("run-one")
def run_one(
    run_id: str = typer.Option(..., help="Run id for this one-issue invocation."),
    run_root: Path = typer.Option(DEFAULT_RUN_ROOT, help="Directory for Dewey run artifacts."),
    queue: Path = typer.Option(DEFAULT_QUEUE, help="Path to monitor-sparta repair_queue.jsonl."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    agent_skills_root: Path = typer.Option(DEFAULT_AGENT_SKILLS_ROOT),
    apply: bool = typer.Option(False, help="Apply exactly one claimed issue."),
    timeout_s: int = typer.Option(7200),
    heartbeat_s: int = typer.Option(60),
    no_bootstrap: bool = typer.Option(True, help="Prefer explicit monitor-sparta queue."),
) -> None:
    """Claim exactly one READY issue, run one lane, write one receipt, exit."""
    from dewey_issue_worker import run_one_issue

    rc, receipt = run_one_issue(
        run_id=run_id,
        run_root=run_root,
        queue_path=queue,
        memory_root=memory_root,
        agent_skills_root=agent_skills_root,
        apply=apply,
        bootstrap=not no_bootstrap,
        bootstrap_limit=0,
        timeout_s=timeout_s,
        health_timeout_s=300,
        heartbeat_s=heartbeat_s,
    )
    _json_print(receipt)
    raise typer.Exit(rc)


@queue_app.command("build")
def queue_build(
    health_json: Path = typer.Argument(..., help="Read-only monitor-sparta health JSON input."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    limit: int = typer.Option(200, help="Bound for bounded non-embedding queue slices."),
    out: Path | None = typer.Option(None, help="Optional path to write queue build output JSON."),
) -> None:
    """Build repair issues from health JSON without mutating the queue."""
    script = memory_root / "scripts" / "validation" / "monitor_sparta_repair_queue.py"
    cmd = ["uv", "run", "python", str(script), "build", str(health_json), "--limit", str(limit)]
    if out is None:
        rc = _run(cmd, cwd=memory_root, timeout_s=300)
        raise typer.Exit(rc)

    _refuse_forbidden(cmd)
    typer.echo("+ " + shlex.join([str(part) for part in cmd]) + f" > {out}", err=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as stdout_fh:
        proc = subprocess.run([str(part) for part in cmd], cwd=str(memory_root), stdout=stdout_fh, check=False, timeout=300)
    raise typer.Exit(int(proc.returncode))


@queue_app.command("enqueue")
def queue_enqueue(
    health_json: Path = typer.Argument(..., help="Read-only monitor-sparta health JSON input."),
    queue: Path = typer.Option(DEFAULT_QUEUE, help="Path to append repair_queue.jsonl issues."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    limit: int = typer.Option(200, help="Bound for bounded non-embedding queue slices."),
    timeout_s: int = typer.Option(300),
) -> None:
    """Append monitor-owned issues from health JSON into repair_queue.jsonl."""
    script = memory_root / "scripts" / "validation" / "monitor_sparta_repair_queue.py"
    cmd = [
        "uv",
        "run",
        "python",
        str(script),
        "enqueue",
        str(health_json),
        "--queue",
        str(queue),
        "--limit",
        str(limit),
    ]
    rc = _run(cmd, cwd=memory_root, timeout_s=timeout_s)
    raise typer.Exit(rc)


@embedding_app.command("repair")
def embedding_repair(
    operation: str = typer.Argument(..., help="inline-vectors | missing-qdrant | qdrant-pointer-metadata"),
    collection: str = typer.Option(..., help="SPARTA collection to repair."),
    output: Path = typer.Option(..., help="Primitive receipt JSON path."),
    rollback_out: Path = typer.Option(..., help="Rollback JSONL path."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    apply: bool = typer.Option(False, help="Apply the full affected embedding class."),
    batch_size: int = typer.Option(500, help="Internal batch size only; scope remains full-class."),
    timeout_s: int = typer.Option(21600),
) -> None:
    """Run the memory-owned embedding primitive directly."""
    if apply:
        _require_apply_env()
    primitive_operation = _normalize_embedding_operation(operation)
    script = memory_root / "scripts" / "validation" / "dewey_embedding_repair.py"
    cmd = [
        "uv",
        "run",
        "python",
        str(script),
        primitive_operation,
        "--collection",
        collection,
        "--batch-size",
        str(batch_size),
        "--output",
        str(output),
        "--rollback-out",
        str(rollback_out),
        "--apply" if apply else "--dry-run",
    ]
    rc = _run(cmd, cwd=memory_root, timeout_s=timeout_s)
    raise typer.Exit(rc)


@source_workbook_app.command("parity")
def source_workbook_parity(
    output: Path = typer.Option(..., help="Primitive receipt JSON path."),
    rollback_out: Path | None = typer.Option(None, help="Rollback JSONL path; required for --apply."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    apply: bool = typer.Option(False, help="Apply exact source workbook parity repairs."),
    timeout_s: int = typer.Option(7200),
) -> None:
    """Run the source workbook -> sparta_controls parity primitive directly."""
    if apply:
        _require_apply_env()
        if rollback_out is None:
            raise typer.BadParameter("--apply requires --rollback-out")
    script = memory_root / "scripts" / "validation" / "dewey_sparta_corpus_parity.py"
    cmd = ["uv", "run", "python", str(script), "--output", str(output), "--apply" if apply else "--dry-run"]
    if rollback_out is not None:
        cmd.extend(["--rollback-out", str(rollback_out)])
    rc = _run(cmd, cwd=memory_root, timeout_s=timeout_s)
    raise typer.Exit(rc)


@qra_app.command("repair")
def qra_repair(
    manifest: Path = typer.Option(..., help="Reviewed create-qras manifest."),
    prompt_reviewer_receipt: Path = typer.Option(..., help="PASS prompt-reviewer receipt."),
    output: Path = typer.Option(..., help="QRA repair receipt JSON path."),
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    apply: bool = typer.Option(False, help="Apply one bounded, reviewed QRA repair slice."),
    limit: int = typer.Option(1, help="QRA repair is bounded/gated, unlike embedding repair."),
    timeout_s: int = typer.Option(7200),
) -> None:
    """Deflect QRA repair to qra-auditor.

    Dewey owns deterministic DBA repair. QRA generation and QRA quality repair
    belong to qra-auditor, which gates review-prompt, Scillm/Chutes preflight,
    and create-qras receipts before any bounded generation.
    """
    _json_print(
        {
            "schema": "dewey.qra_repair.deflected.v1",
            "ok": False,
            "reason": "qra repair is owned by qra-auditor, not Dewey",
            "owner": "qra-auditor",
            "expected_contract": "one QRA-owned queue issue -> review-prompt gate -> scillm/chutes preflight -> create-qras manifest workflow -> one receipt",
            "manifest": str(manifest),
            "prompt_reviewer_receipt": str(prompt_reviewer_receipt),
            "output": str(output),
            "limit": limit,
            "mutation_applied": False,
        }
    )
    raise typer.Exit(2)


@app.command("doctor")
def doctor(
    memory_root: Path = typer.Option(DEFAULT_MEMORY_ROOT),
    agent_skills_root: Path = typer.Option(DEFAULT_AGENT_SKILLS_ROOT),
) -> None:
    """Check required primitive scripts. This does not prove live DB repair."""
    required = {
        "memory_embedding_repair": memory_root / "scripts" / "validation" / "dewey_embedding_repair.py",
        "memory_source_workbook_parity": memory_root / "scripts" / "validation" / "dewey_sparta_corpus_parity.py",
        "monitor_queue_builder": memory_root / "scripts" / "validation" / "monitor_sparta_repair_queue.py",
        "dewey_issue_worker": SCRIPT_DIR / "dewey_issue_worker.py",
        "dewey_repair_queue": SCRIPT_DIR / "dewey_repair_queue.py",
        "create_qras": agent_skills_root / "skills" / "create-qras" / "run.sh",
    }
    checks = {name: {"path": str(path), "exists": path.exists()} for name, path in required.items()}
    _json_print(
        {
            "schema": "dewey.doctor.v1",
            "ok": all(check["exists"] for check in checks.values()),
            "checks": checks,
            "does_not_prove": [
                "live ArangoDB connectivity",
                "live Qdrant connectivity",
                "mutation safety",
                "worker queue behavior",
                "cron readiness",
            ],
        }
    )
    raise typer.Exit(0 if all(check["exists"] for check in checks.values()) else 2)


if __name__ == "__main__":
    app()
