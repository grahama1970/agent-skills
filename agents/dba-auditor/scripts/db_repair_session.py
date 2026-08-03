#!/usr/bin/env python3
"""Dewey database commit/revert session — backup before change, revert on regression.

Git semantics for ArangoDB:
  begin   = baseline health + corpus counts + ops-arango dump (commit point)
  verify  = post health + counts; auto-revert if regression vs baseline
  revert  = arangorestore from this session's dump only
  repair  = begin + run repair command + verify

Session artifacts live under:
  /mnt/storage12tb/skills/review-db/outputs/dewey-sessions/<session_id>/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", "/home/graham/workspace/experiments/memory"))
OPS_ARANGO = Path(
    os.environ.get(
        "OPS_ARANGO_RUNSH",
        "/home/graham/workspace/experiments/agent-skills/skills/ops-arango/run.sh",
    )
)
SESSION_BASE = Path(
    os.environ.get(
        "DEWEY_SESSION_BASE",
        "/mnt/storage12tb/skills/review-db/outputs/dewey-sessions",
    )
)
BACKUP_BASE = Path(os.environ.get("DEWEY_ARANGO_BACKUP_BASE", "/mnt/storage12tb/backups/arangodb"))
CONTAINER = os.environ.get("CONTAINER", "embry-arangodb")
ARANGO_USER = os.environ.get("ARANGO_USER", "root")
ARANGO_PASS = os.environ.get("ARANGO_PASS", "openSesame")
ARANGO_DB = os.environ.get("ARANGO_DB", "memory")
MIN_CONTROLS = int(os.environ.get("DEWEY_MIN_SPARTA_CONTROLS", "1000"))

COUNT_KEYS = (
    "sparta_controls",
    "sparta_qra",
    "sparta_relationships",
)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, shell: bool = False) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
        shell=shell,
    )


def _run_streaming_with_heartbeats(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    artifact_dir: Path,
    output_stem: str,
    timeout_s: int | None,
) -> subprocess.CompletedProcess[str]:
    """Run a long subprocess with durable output and heartbeat JSONL."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_interval_s = int(os.environ.get("DEWEY_PROCESS_HEARTBEAT_S", "60"))
    stdout_path = artifact_dir / f"{output_stem}.stdout.txt"
    stderr_path = artifact_dir / f"{output_stem}.stderr.txt"
    heartbeat_path = artifact_dir / f"{output_stem}.heartbeats.jsonl"
    merged = os.environ.copy()
    if env:
        merged.update(env)
    started = time.time()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )

    def pump(stream, path: Path, sink: list[str]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            if stream is None:
                return
            for line in stream:
                sink.append(line)
                fh.write(line)
                fh.flush()

    threads = [
        threading.Thread(target=pump, args=(proc.stdout, stdout_path, stdout_lines), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, stderr_path, stderr_lines), daemon=True),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    heartbeat_count = 0
    with heartbeat_path.open("w", encoding="utf-8") as fh:
        next_heartbeat_at = started
        while True:
            exit_code = proc.poll()
            elapsed_s = time.time() - started
            if exit_code is not None:
                break
            if time.time() >= next_heartbeat_at:
                heartbeat_count += 1
                fh.write(json.dumps({
                    "cmd": cmd,
                    "elapsed_s": round(elapsed_s, 1),
                    "event": "process_heartbeat",
                    "pid": proc.pid,
                    "stderr_bytes": stderr_path.stat().st_size if stderr_path.exists() else 0,
                    "stdout_bytes": stdout_path.stat().st_size if stdout_path.exists() else 0,
                    "timeout_s": timeout_s,
                }, sort_keys=True) + "\n")
                fh.flush()
                next_heartbeat_at = time.time() + heartbeat_interval_s
            if timeout_s is not None and elapsed_s >= timeout_s:
                timed_out = True
                proc.kill()
                break
            time.sleep(min(1.0, max(0.1, next_heartbeat_at - time.time())))
        exit_code = proc.wait()
        fh.write(json.dumps({
            "cmd": cmd,
            "elapsed_s": round(time.time() - started, 1),
            "event": "process_finished",
            "exit_code": exit_code,
            "heartbeat_count": heartbeat_count,
            "pid": proc.pid,
            "timed_out": timed_out,
        }, sort_keys=True) + "\n")
    for thread in threads:
        thread.join(timeout=5)

    completed = subprocess.CompletedProcess(
        args=cmd,
        returncode=exit_code,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
    completed.heartbeat_path = str(heartbeat_path)  # type: ignore[attr-defined]
    completed.stdout_path = str(stdout_path)  # type: ignore[attr-defined]
    completed.stderr_path = str(stderr_path)  # type: ignore[attr-defined]
    completed.heartbeat_count = heartbeat_count  # type: ignore[attr-defined]
    completed.timed_out = timed_out  # type: ignore[attr-defined]
    return completed


def _now_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collection_count(collection: str) -> int:
    proc = _run(
        [
            "docker",
            "exec",
            CONTAINER,
            "arangosh",
            "--server.endpoint",
            "tcp://127.0.0.1:8529",
            "--server.username",
            ARANGO_USER,
            "--server.password",
            ARANGO_PASS,
            "--server.database",
            ARANGO_DB,
            "--javascript.execute-string",
            f"print(db._collection('{collection}') ? db._collection('{collection}').count() : -1)",
        ]
    )
    line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else "-1"
    try:
        return int(line)
    except ValueError:
        return -1


def capture_counts() -> dict[str, int]:
    return {key: _collection_count(key) for key in COUNT_KEYS}


def run_monitor_health(session_dir: Path, label: str) -> dict[str, Any]:
    out = session_dir / f"monitor_health_{label}.json"
    timeout_s = int(os.environ.get("DEWEY_MONITOR_HEALTH_TIMEOUT_S", "7200"))
    proc = _run_streaming_with_heartbeats(
        ["uv", "run", "python", "scripts/validation/monitor_sparta.py", "health", "--json"],
        cwd=MEMORY_ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        artifact_dir=session_dir,
        output_stem=f"monitor_health_{label}_process",
        timeout_s=timeout_s,
    )
    if proc.returncode not in (0, 1) and not (proc.stdout or "").strip():
        raise RuntimeError(f"monitor-sparta health failed: {(proc.stderr or '')[-2000:]}")
    data = json.loads(proc.stdout)
    _write_json(out, data)
    checks = data.get("checks") or []
    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "path": str(out),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "raw": data,
    }


def run_backup(session_dir: Path) -> dict[str, Any]:
    session_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = int(os.environ.get("DEWEY_ARANGO_BACKUP_TIMEOUT_S", "21600"))
    proc = _run_streaming_with_heartbeats(
        [str(OPS_ARANGO), "dump"],
        cwd=MEMORY_ROOT,
        env={"CONTAINER": CONTAINER, "ARANGO_PASS": ARANGO_PASS, "ARANGO_DB": ARANGO_DB},
        artifact_dir=session_dir,
        output_stem="arango_backup_process",
        timeout_s=timeout_s,
    )
    log = session_dir / "backup.log"
    log.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"ops-arango dump failed (exit {proc.returncode}); see {log}")

    latest = max(
        (p for p in BACKUP_BASE.iterdir() if p.is_dir() and p.name[:8].isdigit()),
        key=lambda p: p.stat().st_mtime,
        default=None,
    )
    if latest is None or not (latest / "dump.json").is_file():
        raise RuntimeError("no timestamped backup directory with dump.json found after dump")

    receipt = {
        "schema": "dewey_db_session_backup.v1",
        "completed_at": _now_id(),
        "backup_dir": str(latest),
        "dump_json": str(latest / "dump.json"),
        "sparta_controls_at_backup": _collection_count("sparta_controls"),
        "via": "ops-arango dump",
        "backup_process": {
            "cmd": list(proc.args) if isinstance(proc.args, list) else proc.args,
            "exit_code": proc.returncode,
            "timeout_s": timeout_s,
            "timed_out": bool(getattr(proc, "timed_out", False)),
            "heartbeat_count": int(getattr(proc, "heartbeat_count", 0)),
            "heartbeat_path": getattr(proc, "heartbeat_path", None),
            "stdout_path": getattr(proc, "stdout_path", None),
            "stderr_path": getattr(proc, "stderr_path", None),
        },
    }
    _write_json(session_dir / "backup_receipt.json", receipt)
    return receipt


def restore_session_backup(session_dir: Path) -> dict[str, Any]:
    session = _read_json(session_dir / "session.json")
    backup_dir = Path(session["backup_dir"])
    if not (backup_dir / "dump.json").is_file():
        raise RuntimeError(f"session backup missing dump.json: {backup_dir}")

    restore_in_container = f"/tmp/dewey-restore-{session['session_id']}"
    _run(["docker", "exec", CONTAINER, "sh", "-lc", f"rm -rf '{restore_in_container}' && mkdir -p '{restore_in_container}'"])
    cp = _run(["docker", "cp", f"{backup_dir}/.", f"{CONTAINER}:{restore_in_container}/"])
    if cp.returncode != 0:
        raise RuntimeError(f"docker cp to container failed: {cp.stderr}")

    proc = _run(
        [
            "docker",
            "exec",
            CONTAINER,
            "arangorestore",
            "--server.endpoint",
            "tcp://127.0.0.1:8529",
            "--server.database",
            ARANGO_DB,
            "--server.username",
            ARANGO_USER,
            "--server.password",
            ARANGO_PASS,
            "--input-directory",
            restore_in_container,
            "--overwrite",
            "true",
            "--progress",
            "true",
        ]
    )
    _run(["docker", "exec", CONTAINER, "rm", "-rf", restore_in_container])
    revert_log = session_dir / "revert.log"
    revert_log.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"arangorestore failed (exit {proc.returncode}); see {revert_log}")

    compose = MEMORY_ROOT / "scripts" / "compose.sh"
    if compose.is_file():
        _run([str(compose), "up", "-d", "--no-deps", "memory"])
    else:
        _run(["docker", "restart", "embry-memory"])

    counts = capture_counts()
    receipt = {
        "schema": "dewey_db_session_revert.v1",
        "reverted_at": _now_id(),
        "backup_dir": str(backup_dir),
        "counts_after_revert": counts,
        "status": "reverted",
    }
    _write_json(session_dir / "revert_receipt.json", receipt)
    session["status"] = "reverted"
    session["reverted_at"] = receipt["reverted_at"]
    _write_json(session_dir / "session.json", session)
    return receipt


def health_passed(health: dict[str, Any]) -> int:
    return int(health.get("passed") or 0)


def detect_regression(baseline: dict[str, Any], post: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    b_counts = baseline.get("counts") or {}
    p_counts = post.get("counts") or {}
    for key in COUNT_KEYS:
        b = int(b_counts.get(key, -1))
        p = int(p_counts.get(key, -1))
        if b >= 0 and p >= 0 and p < b:
            reasons.append(f"{key} decreased {b} -> {p}")
    if int(b_counts.get("sparta_controls", 0)) >= MIN_CONTROLS and int(
        p_counts.get("sparta_controls", -1)
    ) < MIN_CONTROLS:
        reasons.append(f"sparta_controls below minimum {MIN_CONTROLS}")

    b_pass = health_passed(baseline.get("health") or {})
    p_pass = health_passed(post.get("health") or {})
    if p_pass < b_pass:
        reasons.append(f"monitor health pass count decreased {b_pass} -> {p_pass}")

    def _dim_ok(health: dict[str, Any], dim: str) -> bool:
        for check in (health.get("checks") or []):
            if check.get("dimension") == dim:
                return bool(check.get("ok"))
        return False

    for critical in ("corpus_completeness",):
        if _dim_ok(baseline.get("health") or {}, critical) and not _dim_ok(
            post.get("health") or {}, critical
        ):
            reasons.append(f"{critical} regressed from pass to fail")

    return reasons


def live_memory_health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8601/health", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def cmd_begin(args: argparse.Namespace) -> int:
    session_id = args.session_id or _now_id()
    session_dir = SESSION_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    health = run_monitor_health(session_dir, "baseline")
    counts = capture_counts()
    if counts.get("sparta_controls", -1) < 0:
        print("ERROR: cannot read sparta_controls count", file=sys.stderr)
        return 1

    backup = run_backup(session_dir)
    session = {
        "schema": "dewey_db_session.v1",
        "session_id": session_id,
        "status": "committed",
        "started_at": _now_id(),
        "baseline": {"counts": counts, "health": health},
        "backup_dir": backup["backup_dir"],
        "backup_receipt": str(session_dir / "backup_receipt.json"),
        "container": CONTAINER,
        "arango_db": ARANGO_DB,
    }
    _write_json(session_dir / "session.json", session)
    _write_json(session_dir / "baseline_counts.json", counts)
    print(json.dumps({"session_id": session_id, "session_dir": str(session_dir), "backup_dir": backup["backup_dir"]}))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    session_dir = Path(args.session_dir)
    session = _read_json(session_dir / "session.json")
    baseline = session.get("baseline") or {}

    health = run_monitor_health(session_dir, "post")
    counts = capture_counts()
    post = {"counts": counts, "health": health}
    _write_json(session_dir / "post_counts.json", counts)

    reasons = detect_regression(baseline, post)
    memory_health = live_memory_health()
    if not memory_health.get("ok", False):
        reasons.append(f"memory /health not ok: {memory_health}")

    result = {
        "schema": "dewey_db_session_verify.v1",
        "verified_at": _now_id(),
        "regression": bool(reasons),
        "reasons": reasons,
        "post": post,
        "memory_health": memory_health,
    }
    _write_json(session_dir / "verify_result.json", result)

    if reasons and not args.no_revert:
        print("REGRESSION detected; reverting session backup...", file=sys.stderr)
        revert = restore_session_backup(session_dir)
        result["reverted"] = True
        result["revert_receipt"] = revert
        _write_json(session_dir / "verify_result.json", result)
        print(json.dumps(result, indent=2))
        return 2

    session["status"] = "verified" if not reasons else "failed"
    session["verified_at"] = result["verified_at"]
    session["post"] = post
    _write_json(session_dir / "session.json", session)
    print(json.dumps(result, indent=2))
    return 0 if not reasons else 1


def cmd_revert(args: argparse.Namespace) -> int:
    session_dir = Path(args.session_dir)
    receipt = restore_session_backup(session_dir)
    print(json.dumps(receipt, indent=2))
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    begin_args = argparse.Namespace(session_id=args.session_id)
    rc = cmd_begin(begin_args)
    if rc != 0:
        return rc
    if args.session_id:
        session_dir = SESSION_BASE / args.session_id
    else:
        session_dir = max(SESSION_BASE.iterdir(), key=lambda p: p.stat().st_mtime)

    if args.command:
        proc = _run(args.command, shell=True, cwd=MEMORY_ROOT)
        repair_log = session_dir / "repair.log"
        repair_log.write_text(
            f"$ {args.command}\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n",
            encoding="utf-8",
        )
        _write_json(
            session_dir / "repair_manifest.json",
            {
                "schema": "dewey_db_session_repair.v1",
                "command": args.command,
                "exit_code": proc.returncode,
            },
        )
        if proc.returncode != 0 and not args.allow_repair_failure:
            print(f"repair command failed (exit {proc.returncode}); see {repair_log}", file=sys.stderr)
            if not args.skip_verify:
                cmd_revert(argparse.Namespace(session_dir=str(session_dir)))
            return proc.returncode

    if args.skip_verify:
        return 0
    return cmd_verify(argparse.Namespace(session_dir=str(session_dir), no_revert=args.no_revert))


def cmd_classify(args: argparse.Namespace) -> int:
    path = Path(args.health_json)
    data = _read_json(path)
    checks = data.get("checks") or []
    mechanical = {
        "inline_embedding_policy",
        "sparta_relationship_integrity",
        "framework_name_normalization",
        "source_control_field_parity",
    }
    semantic = {
        "description_completeness",
        "qra_coverage_per_control",
        "qra_stub_grounding",
        "qra_evidence_coverage",
        "source_text_qra_coverage",
    }
    ux = {"sparta_explorer_page_purpose"}
    buckets: dict[str, list[dict[str, Any]]] = {
        "mechanical": [],
        "semantic_queue": [],
        "ux": [],
        "other": [],
    }
    for check in checks:
        if check.get("ok"):
            continue
        dim = str(check.get("dimension") or "")
        if dim in mechanical:
            buckets["mechanical"].append(check)
        elif dim in semantic:
            buckets["semantic_queue"].append(check)
        elif dim in ux:
            buckets["ux"].append(check)
        else:
            buckets["other"].append(check)
    out = {"schema": "dewey_health_classification.v1", "buckets": buckets}
    if args.out:
        _write_json(Path(args.out), out)
    print(json.dumps(out, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_begin = sub.add_parser("begin", help="baseline health + backup (commit point)")
    p_begin.add_argument("--session-id", help="optional fixed session id")

    p_verify = sub.add_parser("verify", help="post health; auto-revert on regression")
    p_verify.add_argument("session_dir", help="path to session directory")
    p_verify.add_argument("--no-revert", action="store_true", help="report regression without reverting")

    p_revert = sub.add_parser("revert", help="restore this session backup only")
    p_revert.add_argument("session_dir", help="path to session directory")

    p_repair = sub.add_parser("repair", help="begin + optional command + verify")
    p_repair.add_argument("--session-id", help="optional fixed session id")
    p_repair.add_argument("--command", help="shell repair command to run after backup")
    p_repair.add_argument("--allow-repair-failure", action="store_true")
    p_repair.add_argument("--skip-verify", action="store_true")
    p_repair.add_argument("--no-revert", action="store_true")

    p_classify = sub.add_parser("classify", help="bucket monitor health failures")
    p_classify.add_argument("health_json")
    p_classify.add_argument("--out", help="optional output path")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "begin": cmd_begin,
        "verify": cmd_verify,
        "revert": cmd_revert,
        "repair": cmd_repair,
        "classify": cmd_classify,
    }
    return handlers[args.subcommand](args)


if __name__ == "__main__":
    raise SystemExit(main())
