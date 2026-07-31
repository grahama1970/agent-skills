"""Docker-backed Battle swarm execution proof."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .packaged_deployment_smoke import _now_utc


def prove_unbounded_swarm_execution(
    *,
    out_dir: Path,
    worker_count: int = 12,
    docker_image: str = "python:3.12-slim",
    per_worker_timeout_s: int = 30,
    min_concurrent_observed: int = 4,
) -> dict[str, Any]:
    """Run a production-shaped dynamic swarm envelope in Docker.

    The receipt uses the historical "unbounded swarm" schema name, but the
    claim is bounded: it proves the orchestrator can drive a configurable
    worker-count swarm without a fixed 2-worker cap.
    """

    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")
    if min_concurrent_observed < 1:
        raise ValueError("min_concurrent_observed must be >= 1")
    if min_concurrent_observed > worker_count:
        raise ValueError("min_concurrent_observed must be <= worker_count")

    out_dir = out_dir.resolve()
    workers_dir = out_dir / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.perf_counter()
    max_workers = min(worker_count, max(min_concurrent_observed, os.cpu_count() or 1))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="battle-swarm") as executor:
        futures = [
            executor.submit(
                _run_worker,
                worker_index=index,
                worker_count=worker_count,
                docker_image=docker_image,
                per_worker_timeout_s=per_worker_timeout_s,
                workers_dir=workers_dir,
            )
            for index in range(worker_count)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: int(item["worker_index"]))
    max_concurrent = _max_concurrent(results)
    failed = [item for item in results if item["status"] != "PASS"]
    errors = [f"worker {item['worker_id']} failed: {item.get('error')}" for item in failed]
    if max_concurrent < min_concurrent_observed:
        errors.append(
            f"max_concurrent_observed {max_concurrent} < required {min_concurrent_observed}"
        )

    receipt = {
        "schema": "battle.unbounded_swarm_execution_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "local_docker_dynamic_swarm_execution",
        "worker_count": worker_count,
        "docker_image": docker_image,
        "network_mode": "none",
        "max_workers": max_workers,
        "max_concurrent_observed": max_concurrent,
        "min_concurrent_required": min_concurrent_observed,
        "completed_worker_count": sum(1 for item in results if item["status"] == "PASS"),
        "failed_worker_count": len(failed),
        "elapsed_seconds": round(time.perf_counter() - started_at, 6),
        "worker_receipts": [item["receipt_path"] for item in results],
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "Battle can schedule a configurable worker-count swarm beyond the prior fixed 2-worker proof.",
                "Each swarm worker executed inside Docker with network disabled.",
                "The swarm receipt records per-worker command, timing, stdout, stderr, exit code, and concurrency envelope.",
            ],
            "does_not_prove": [
                "Mathematically unbounded or infinite swarm execution.",
                "Live Tau provider generation for every worker.",
                "Exploit success, Blue kill, patch success, or Judge success.",
                "Production infrastructure, cluster scheduling, Kubernetes, or autoscaling behavior.",
                "Production-scale throughput under real target load.",
                "Battle or RelayForge is production ready.",
            ],
        },
        "created_at": _now_utc(),
    }
    (out_dir / "unbounded-swarm-execution-proof.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    return receipt


def _run_worker(
    *,
    worker_index: int,
    worker_count: int,
    docker_image: str,
    per_worker_timeout_s: int,
    workers_dir: Path,
) -> dict[str, Any]:
    role = "red" if worker_index % 2 == 0 else "blue"
    worker_id = f"{role}-{worker_index:03d}"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--name",
        f"battle-swarm-{os.getpid()}-{worker_index}",
        "-e",
        f"BATTLE_SWARM_WORKER_ID={worker_id}",
        "-e",
        f"BATTLE_SWARM_WORKER_COUNT={worker_count}",
        docker_image,
        "python",
        "-c",
        (
            "import os, time; "
            "wid=os.environ['BATTLE_SWARM_WORKER_ID']; "
            "count=os.environ['BATTLE_SWARM_WORKER_COUNT']; "
            "print(f'start {wid} of {count}', flush=True); "
            "time.sleep(0.35); "
            "print(f'end {wid}', flush=True)"
        ),
    ]
    started = time.perf_counter()
    error = ""
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=per_worker_timeout_s,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        error = f"timeout after {per_worker_timeout_s}s"
    ended = time.perf_counter()
    status = "PASS" if exit_code == 0 and f"start {worker_id}" in stdout and f"end {worker_id}" in stdout else "FAIL"
    if status != "PASS" and not error:
        error = "worker command did not produce expected start/end markers"
    receipt = {
        "schema": "battle.swarm_worker_receipt.v1",
        "status": status,
        "mocked": False,
        "live": "local_docker_worker",
        "worker_index": worker_index,
        "worker_id": worker_id,
        "role": role,
        "docker_image": docker_image,
        "network_mode": "none",
        "command": _redacted_command(command),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "started_monotonic": started,
        "ended_monotonic": ended,
        "duration_seconds": round(ended - started, 6),
        "error": error,
    }
    receipt_path = workers_dir / f"{worker_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(receipt_path)}


def _max_concurrent(results: list[dict[str, Any]]) -> int:
    points: list[tuple[float, int]] = []
    for item in results:
        points.append((float(item["started_monotonic"]), 1))
        points.append((float(item["ended_monotonic"]), -1))
    active = 0
    highest = 0
    for _, delta in sorted(points, key=lambda item: (item[0], -item[1])):
        active += delta
        highest = max(highest, active)
    return highest


def _redacted_command(command: list[str]) -> list[str]:
    redacted = list(command)
    if len(redacted) > 6:
        redacted[redacted.index("--name") + 1] = "<container-name>"
    return redacted
