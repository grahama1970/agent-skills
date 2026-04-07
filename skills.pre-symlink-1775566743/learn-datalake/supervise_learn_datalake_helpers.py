"""supervise_learn_datalake helpers module.

Constants, regex patterns, JSON/JSONL helpers, utility functions,
memory integration, convergence state tracking, and task-monitor /
alert-hook wrappers.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from loguru import logger

# ─────────────────────────────────────────────────────────────────────────────
# Path constants
# ─────────────────────────────────────────────────────────────────────────────

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SKILL_DIR.parent
LEARN_DATALAKE_RUN = SKILL_DIR / "run.sh"
REVIEW_PDF_DIR = SKILLS_ROOT / "review-pdf"
DEBUG_PDF_DIR = SKILLS_ROOT / "debug-pdf"
DEBUG_TABLE_DIR = SKILLS_ROOT / "table-lab"
FIXTURE_TRICKY_DIR = SKILLS_ROOT / "fixture-tricky"
MEMORY_DIR = SKILLS_ROOT / "memory"
MEMORY_SOCK = Path("/run/user/1000/embry/memory.sock")
TASK_MONITOR_DIR = SKILLS_ROOT / "task-monitor"
TASK_MONITOR_RUN = TASK_MONITOR_DIR / "run.sh"
DEFAULT_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "extractor_corpus/nasa"
STATE_DIR = SKILL_DIR / "state"
WATCHDOG_DIR = STATE_DIR / "watchdogs"
RUN_DIR = STATE_DIR / "runs"
DIAG_DIR = WATCHDOG_DIR / "diagnostics"
TASK_MONITOR_STATE_DIR = STATE_DIR / "task_monitor"
MEMORY_RETRY_QUEUE = WATCHDOG_DIR / "memory_retry_queue.jsonl"
MEMORY_RETRY_DEAD_LETTER = WATCHDOG_DIR / "memory_retry_dead_letter.jsonl"
MEMORY_SERVICE_URL = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")
MEMORY_HTTP_TIMEOUT_SECONDS = 30
MEMORY_SUBPROCESS_TIMEOUT_SECONDS = 45
MEMORY_WRITE_TIMEOUT_SECONDS = 30

FAILED_PDF_BLACKLIST = STATE_DIR / "failed_pdf_blacklist.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns for log parsing
# ─────────────────────────────────────────────────────────────────────────────

EXTRACT_SUCCESS_RE = re.compile(r"extract_missing status=extracted new_count=[0-9]+")
EXTRACT_FAIL_RE = re.compile(r"extract_missing status=extract_failed")
EXTRACT_CACHED_PROFILE_RE = re.compile(r"extract_missing status=cached_profile")
EXTRACT_PREFLIGHT_FAIL_RE = re.compile(
    r"extract_missing status=preflight_failed"
    r"(?: .*?reason=(?P<reason>[^ ]+))?"
    r"(?: .*?detail=(?P<detail>[^ ]+))?"
    r"(?: .*?security=(?P<security>[^ ]+))?"
    r"(?: .*?pdf=(?P<pdf>.+))?$"
)
EXTRACT_EVENT_PDF_RE = re.compile(
    r"extract_missing status=(?P<status>[a-z_]+)(?: .*?)? pdf=(?P<pdf>.+)$"
)
EXTRACT_FAIL_DETAIL_RE = re.compile(
    r"extract_missing status=extract_failed(?: .*?)?timed_out=(?P<timed>[01])"
    r"(?: .*?missing_structural=(?P<missing_structural>[01]))?(?: .*?)? pdf=(?P<pdf>.+)$"
)
EXTRACT_TIMEOUT_HINT_RE = re.compile(
    r"extract_timeout seconds=(?P<seconds>[0-9]+)\s+"
    r"page_count=(?P<page_count>[0-9]+)\s+"
    r"step00_estimated=(?P<step00_estimated>[0-9]+)\s+"
    r"source=[^ ]+\s+pdf=(?P<pdf>.+)$"
)
TIMEOUT_MODEL_EVENT_RE = re.compile(
    r"review-pdf timeout_model "
    r"status=(?P<status>[a-z_]+)\s+"
    r"used=(?P<used>[01])\s+"
    r"risk=(?P<risk>[0-9.]+)\s+"
    r"baseline=(?P<baseline>[0-9]+)\s+"
    r"selected=(?P<selected>[0-9]+)\s+"
    r"pdf=(?P<pdf>.+)$"
)
ROLLING_QUALITY_RE = re.compile(
    r"rolling_quality\s+analyzed=(?P<analyzed>[0-9]+)\s+"
    r"avg_score=(?P<avg_score>[0-9.]+)\s+"
    r"fail_ratio=(?P<fail_ratio>[0-9.]+)\s+"
    r"critical_doc_ratio=(?P<critical_ratio>[0-9.]+)"
)
DOC_TOTAL_RE = re.compile(r"^documents_total=(?P<value>[0-9]+)$")
DOC_ANALYZED_RE = re.compile(r"^documents_analyzed=(?P<value>[0-9]+)$")
DOC_MISSING_RE = re.compile(r"^documents_missing=(?P<value>[0-9]+)$")
OVERALL_SCORE_RE = re.compile(r"^overall_average_score=(?P<value>[0-9.]+)$")
VERDICTS_RE = re.compile(
    r"^verdicts=PASS:(?P<pass>[0-9]+)\s+WARN:(?P<warn>[0-9]+)\s+FAIL:(?P<fail>[0-9]+)$"
)
LOOP_HEALTH_RE = re.compile(
    r"loop cycle=(?P<cycle>[0-9]+)\s+healthy=(?P<healthy>True|False)\s+"
    r"score=(?P<score>[0-9.]+)\s+fail_ratio=(?P<fail_ratio>[0-9.]+)"
)

# ─────────────────────────────────────────────────────────────────────────────
# JSON / JSONL helpers
# ─────────────────────────────────────────────────────────────────────────────


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))  # atomic on POSIX


def _failure_total(failure_buckets: dict[str, int]) -> int:
    return sum(int(v) for v in failure_buckets.values())


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _count_jsonl_records(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def _count_blacklist(path: Path | None = None) -> int:
    """Count entries in the blacklist JSONL file."""
    bl = path or FAILED_PDF_BLACKLIST
    if not bl.exists():
        return 0
    try:
        return sum(1 for line in bl.read_text().strip().split("\n") if line.strip())
    except Exception:
        return 0


def _count_deferred() -> int:
    """Count items deferred for human review (awaiting /interview)."""
    from config import DEFERRED_REVIEW_PATH
    if not DEFERRED_REVIEW_PATH.exists():
        return 0
    try:
        return sum(1 for line in DEFERRED_REVIEW_PATH.read_text().strip().split("\n") if line.strip())
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Memory integration
# ─────────────────────────────────────────────────────────────────────────────


def _memory_learn_http(
    *,
    problem: str,
    solution: str,
) -> None:
    """POST directly to the memory FastAPI service (no subprocess overhead)."""
    payload = json.dumps({
        "problem": problem,
        "solution": solution,
        "scope": "learn_datalake",
        "tags": ["learn-datalake"],
    }).encode()
    req = urllib.request.Request(
        f"{MEMORY_SERVICE_URL}/learn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=MEMORY_HTTP_TIMEOUT_SECONDS) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"memory service returned {resp.status}")


def _memory_learn(
    *,
    problem: str,
    solution: str,
    strict: bool,
) -> None:
    # Try HTTP first (fast, no subprocess overhead)
    try:
        _memory_learn_http(problem=problem, solution=solution)
        return
    except (urllib.error.URLError, OSError, RuntimeError) as exc:
        logger.debug(f"memory HTTP learn failed, falling back to subprocess: {exc}")

    # Fallback to httpx Unix socket
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(MEMORY_SUBPROCESS_TIMEOUT_SECONDS)) as client:
            resp = client.post("/learn", json={
                "problem": problem,
                "solution": solution,
                "scope": "datalake_convergence",
                "tags": ["learn-datalake"],
            })
            if resp.status_code != 200:
                msg = f"memory learn failed HTTP {resp.status_code} problem={problem[:80]}"
                if strict:
                    raise RuntimeError(msg)
                logger.warning(msg)
    except Exception as exc:
        msg = f"memory learn httpx failed: {exc}"
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)


def _drain_memory_retry_queue(
    *,
    max_items: int = 5,
    max_attempts: int = 3,
) -> dict[str, int]:
    if not MEMORY_RETRY_QUEUE.exists():
        return {
            "retried_count": 0,
            "succeeded_count": 0,
            "remaining_count": 0,
            "dead_lettered_count": _count_jsonl_records(MEMORY_RETRY_DEAD_LETTER),
            "queue_count_before": 0,
            "queue_count_after": 0,
        }

    raw_lines = [
        line for line in MEMORY_RETRY_QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    queue_count_before = len(raw_lines)
    items: list[dict[str, Any]] = []
    for line in raw_lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)

    retried_count = 0
    succeeded_count = 0
    dead_lettered_count = 0
    remaining: list[dict[str, Any]] = []
    for item in items:
        if retried_count >= max_items:
            remaining.append(item)
            continue
        problem = str(item.get("problem") or "").strip()
        solution = str(item.get("solution") or "").strip()
        if not problem or not solution:
            item["attempts"] = int(item.get("attempts", 0)) + 1
            if int(item["attempts"]) >= max_attempts:
                dead_lettered_count += 1
                _append_jsonl(
                    MEMORY_RETRY_DEAD_LETTER,
                    {
                        **item,
                        "dead_lettered_at": _now_utc_iso(),
                        "reason": "missing_problem_or_solution",
                    },
                )
            else:
                remaining.append(item)
            continue
        retried_count += 1
        try:
            _memory_learn(problem=problem, solution=solution, strict=False)
            succeeded_count += 1
        except Exception as exc:
            item["attempts"] = int(item.get("attempts", 0)) + 1
            item["last_error"] = str(exc)
            item["last_retry_at"] = _now_utc_iso()
            if int(item["attempts"]) >= max_attempts:
                dead_lettered_count += 1
                _append_jsonl(
                    MEMORY_RETRY_DEAD_LETTER,
                    {
                        **item,
                        "dead_lettered_at": _now_utc_iso(),
                        "reason": "retry_exhausted",
                    },
                )
            else:
                remaining.append(item)

    if remaining:
        tmp = MEMORY_RETRY_QUEUE.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(json.dumps(item, ensure_ascii=True) for item in remaining) + "\n",
            encoding="utf-8",
        )
        os.replace(str(tmp), str(MEMORY_RETRY_QUEUE))  # atomic on POSIX
    else:
        MEMORY_RETRY_QUEUE.unlink(missing_ok=True)

    return {
        "retried_count": retried_count,
        "succeeded_count": succeeded_count,
        "remaining_count": len(remaining),
        "dead_lettered_count": _count_jsonl_records(MEMORY_RETRY_DEAD_LETTER),
        "queue_count_before": queue_count_before,
        "queue_count_after": len(remaining),
    }


def _record_learning_event(
    *,
    events_path: Path,
    event_type: str,
    root: Path,
    label: str,
    run_id: str,
    summary: str,
    details: dict[str, Any],
    strict: bool,
) -> None:
    event = {
        "event_type": event_type,
        "timestamp": _now_utc_iso(),
        "root": str(root),
        "label": label,
        "run_id": run_id,
        "summary": summary,
        "details": details,
    }
    try:
        _append_jsonl(events_path, event)
    except Exception as exc:
        logger.warning(f"_record_learning_event disk write failed: {exc}")
        # Non-fatal -- continue to attempt memory write
    compact = {
        "event_type": event_type,
        "run_id": run_id,
        "summary": summary,
        "quality_gate_action": details.get("quality_gate_action"),
        "quality_gate_reason": details.get("quality_gate_reason"),
        "rolling_avg_score": details.get("rolling_avg_score"),
        "rolling_fail_ratio": details.get("rolling_fail_ratio"),
        "documents_missing_ratio": details.get("documents_missing_ratio"),
        "failure_signature": details.get("failure_signature"),
    }
    memory_problem = f"learn-datalake {event_type}: {summary}"
    memory_solution = json.dumps(compact, ensure_ascii=True)
    try:
        _memory_learn(
            problem=memory_problem,
            solution=memory_solution,
            strict=strict,
        )
    except Exception as exc:
        retry_payload = {
            "timestamp": _now_utc_iso(),
            "event_type": event_type,
            "root": str(root),
            "label": label,
            "run_id": run_id,
            "problem": memory_problem,
            "solution": memory_solution,
            "error": str(exc),
        }
        _append_jsonl(MEMORY_RETRY_QUEUE, retry_payload)
        logger.warning(
            "memory_write_queued "
            f"run_id={run_id} event_type={event_type} error={type(exc).__name__}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Task-monitor and alert-hook wrappers
# ─────────────────────────────────────────────────────────────────────────────


def _task_monitor_cmd(args: list[str], *, strict: bool, timeout: int = 120) -> bool:
    if not TASK_MONITOR_RUN.exists():
        msg = f"task-monitor missing at {TASK_MONITOR_RUN}"
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False

    proc = subprocess.run(
        [str(TASK_MONITOR_RUN), *args],
        cwd=str(TASK_MONITOR_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.splitlines()[-1] if proc.stderr else ""
        msg = (
            f"task-monitor command failed rc={proc.returncode} "
            f"args={' '.join(args)} stderr_tail={tail}"
        )
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    return True


def _run_alert_hook(
    *,
    command: str,
    env_extra: dict[str, str],
    strict: bool,
    timeout: int = 120,
) -> bool:
    if not command.strip():
        return True
    env = os.environ.copy()
    env.update(env_extra)
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=str(SKILL_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.splitlines()[-1] if proc.stderr else ""
        msg = f"alert hook failed rc={proc.returncode} cmd={command} stderr_tail={tail}"
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    return True


def _assert_required_paths(*, task_monitor_enabled: bool) -> None:
    required: list[Path] = [
        LEARN_DATALAKE_RUN,
        REVIEW_PDF_DIR / "run.sh",
        DEBUG_PDF_DIR / "run.sh",
        DEBUG_TABLE_DIR / "run.sh",
        FIXTURE_TRICKY_DIR / "run.sh",
        MEMORY_SOCK,
    ]
    if task_monitor_enabled:
        required.append(TASK_MONITOR_RUN)
    missing = [path for path in required if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise typer.BadParameter(f"missing required helper skill paths: {joined}")


def _register_supervisor_task(
    *,
    label: str,
    state_file: Path,
    project: str,
    enabled: bool,
    strict: bool,
) -> None:
    if not enabled:
        return
    _task_monitor_cmd(
        [
            "register",
            "--name",
            f"learn_datalake_supervisor_{label}",
            "--state",
            str(state_file),
            "--total",
            "1",
            "--desc",
            "Supervisor watchdog health for learn-datalake",
            "--project",
            project,
        ],
        strict=strict,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Process and log utilities
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_pdf_path(raw_value: str) -> str | None:
    candidate = raw_value.strip().strip('"').strip("'")
    if not candidate:
        return None
    if not candidate.lower().endswith(".pdf"):
        return None
    return candidate


def _parse_iso_to_epoch(value: str) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return None


def _tail_text(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[-max_lines:])


def _classify_failure(exit_code: int, log_tail: str, forced_reason: str = "") -> str:
    if forced_reason:
        return forced_reason
    lowered = log_tail.lower()
    if "watchdog failure" in lowered or "no output for" in lowered:
        return "watchdog_failure"
    if "hard_fail" in lowered:
        return "hard_fail"
    if "no_documents_analyzed" in lowered:
        return "no_documents_analyzed"
    if "traceback" in lowered:
        return "python_traceback"
    return f"exit_{exit_code}"


def _terminate_process(proc: subprocess.Popen[Any], wait_seconds: int = 20) -> None:
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None

    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=wait_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        return
    proc.wait(timeout=10)


def _run_shell_command(
    *,
    cmd: str,
    cwd: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
    }


def _aggregate_worker_states(state_dir: Path) -> dict[str, Any]:
    """Read all review_state_worker_*.json files and aggregate metrics."""
    worker_files = sorted(state_dir.glob("review_state_worker_*.json"))
    if not worker_files:
        return {}
    workers: list[dict[str, Any]] = []
    for wf in worker_files:
        payload = _safe_read_json(wf)
        if payload:
            workers.append(payload)
    if not workers:
        return {}
    agg: dict[str, Any] = {
        "worker_count": len(workers),
        "worker_files": [str(wf) for wf in worker_files],
    }
    for key in [
        "elapsed_seconds",
        "last_output_age_seconds",
    ]:
        values = [
            float(w.get("stats", {}).get(key, 0) or 0)
            for w in workers
        ]
        agg[f"max_{key}"] = round(max(values), 2) if values else 0
    return agg


def _build_child_command(
    *,
    root: Path,
    target_score: float,
    target_fail_ratio: float,
    poll_seconds: int,
    watchdog_seconds: int,
    watchdog_poll_seconds: int,
    task_monitor: bool,
    task_monitor_project: str,
    execute_jobs: bool,
    ingest_memory: bool,
    ingest_non_pdf: bool,
    workers: int = 1,
    inline_review: bool = False,
    extract_missing: bool = True,
) -> list[str]:
    cmd = [
        str(LEARN_DATALAKE_RUN),
        "start",
        str(root),
        "--target-score",
        str(target_score),
        "--target-fail-ratio",
        str(target_fail_ratio),
        "--poll-seconds",
        str(poll_seconds),
        "--watchdog-seconds",
        str(watchdog_seconds),
        "--watchdog-poll-seconds",
        str(watchdog_poll_seconds),
        "--task-monitor-project",
        task_monitor_project,
    ]
    if workers > 1:
        cmd.extend(["--workers", str(workers)])
    cmd.append("--task-monitor" if task_monitor else "--no-task-monitor")
    cmd.append("--execute-jobs" if execute_jobs else "--no-execute-jobs")
    cmd.append("--ingest-memory" if ingest_memory else "--no-ingest-memory")
    if inline_review:
        cmd.append("--inline-review")
    if not extract_missing:
        cmd.append("--no-extract-missing")
    return cmd
