#!/usr/bin/env python3
from __future__ import annotations
"""Run one Dewey DBA repair lane.

This module deliberately does not call monitor_sparta.py repair-cycle.  Dewey's
unit of work is one monitor-sparta queue issue, and this runner dispatches only
that issue's explicit DBA lane.
"""

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from dewey_repair_queue import DEWEY_OWNED_LANES, utc_now

DEFAULT_MEMORY_REPO_ROOT = "/home/graham/workspace/experiments/memory"
DEFAULT_AGENT_SKILLS_ROOT = "/home/graham/workspace/experiments/agent-skills"
DEFAULT_LIMIT = 200
DEFAULT_QRA_LIMIT = 1
DEFAULT_HEARTBEAT_S = 60

# Embedding repairs are bulk DBA lanes.  A Dewey invocation still claims exactly
# one queue issue and runs one lane, but these three lanes must repair the
# complete affected class in that invocation.  Internal batching is allowed;
# slicing the apply scope by --limit is not the default contract.
EMBEDDING_BULK_LANES = {
    "inline_embedding_policy",
    "qdrant_pointer_metadata",
    "missing_qdrant_embeddings",
}
DEFAULT_EMBED_SCAN_BATCH_SIZE = 500
DEFAULT_EMBED_BATCH_SIZE = 16
DEFAULT_LANE_TIMEOUTS = {
    "inline_embedding_policy": 7200,
    "qdrant_pointer_metadata": 7200,
    "missing_qdrant_embeddings": 21600,
    "source_workbook_parity": 7200,
    "source_text_status_repair": 7200,
    "source_url_text_backfill": 7200,
    "source_text_qra_coverage": 180,
    "qra_coverage_per_control": 1800,
}
DEFAULT_MAX_QRA_APPLY_LIMIT = 25
INLINE_VECTOR_FIELD_NAMES = {
    "embedding",
    "embeddings",
    "vector",
    "vectors",
    "dense_embedding",
    "dense_vector",
    "sparse_embedding",
    "sparse_vector",
    "qdrant_vector",
}


@dataclass(frozen=True)
class CommandResult:
    id: str
    cmd: list[str]
    cwd: str | None
    exit_code: int
    ok: bool
    dry_run: bool
    duration_s: float
    timed_out: bool
    stdout_path: str | None = None
    stderr_path: str | None = None
    heartbeat_path: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "ok": self.ok,
            "dry_run": self.dry_run,
            "command_preview_dry_run": self.dry_run,
            "primitive_dry_run": "--dry-run" in self.cmd,
            "primitive_apply": "--apply" in self.cmd,
            "duration_s": round(self.duration_s, 3),
            "timed_out": self.timed_out,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "heartbeat_path": self.heartbeat_path,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    assert_no_inline_vectors(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_inline_vectors(value: Any, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in INLINE_VECTOR_FIELD_NAMES:
                hits.append(child_path)
            hits.extend(find_inline_vectors(child, path=child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(find_inline_vectors(child, path=f"{path}[{idx}]"))
    return hits


def assert_no_inline_vectors(value: Mapping[str, Any]) -> None:
    hits = find_inline_vectors(value)
    if hits:
        raise ValueError("Dewey artifacts must not contain inline embedding/vector fields: " + ", ".join(hits))


def tail(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) > limit:
        data = data[-limit:]
    return data.decode("utf-8", errors="replace")


def contains_repair_cycle(cmd: Sequence[str]) -> bool:
    return any(part == "repair-cycle" or str(part).endswith("monitor_sparta.py repair-cycle") for part in cmd)


def run_command(
    *,
    command_id: str,
    cmd: Sequence[str],
    cwd: Path | None,
    artifact_dir: Path,
    timeout_s: int,
    dry_run: bool,
    env: Mapping[str, str] | None = None,
    heartbeat_s: int = DEFAULT_HEARTBEAT_S,
) -> CommandResult:
    cmd = [str(part) for part in cmd]
    if contains_repair_cycle(cmd):
        raise ValueError("Dewey lane runner is forbidden from invoking monitor_sparta.py repair-cycle")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / f"{command_id}.stdout.log"
    stderr_path = artifact_dir / f"{command_id}.stderr.log"
    heartbeat_path = artifact_dir / f"{command_id}.heartbeat.jsonl"
    if dry_run:
        stdout_path.write_text("DRY_RUN: " + shlex.join(cmd) + "\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        heartbeat_path.write_text(
            json.dumps({"event": "dry_run", "cmd": cmd, "cwd": str(cwd) if cwd else None, "at": utc_now()}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return CommandResult(
            id=command_id,
            cmd=cmd,
            cwd=str(cwd) if cwd else None,
            exit_code=0,
            ok=True,
            dry_run=True,
            duration_s=0.0,
            timed_out=False,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            heartbeat_path=str(heartbeat_path),
            stdout_tail=tail(stdout_path),
            stderr_tail="",
        )

    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    started = time.time()
    timed_out = False
    stdout_fh = stdout_path.open("wb")
    stderr_fh = stderr_path.open("wb")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=stdout_fh,
            stderr=stderr_fh,
            env=merged_env,
            start_new_session=True,
        )
        next_heartbeat = started
        with heartbeat_path.open("a", encoding="utf-8") as hb:
            hb.write(json.dumps({"event": "started", "cmd": cmd, "cwd": str(cwd) if cwd else None, "pid": proc.pid, "at": utc_now()}, sort_keys=True) + "\n")
            hb.flush()
            while True:
                rc = proc.poll()
                now = time.time()
                if rc is not None:
                    break
                if now - started > timeout_s:
                    timed_out = True
                    hb.write(json.dumps({"event": "timeout", "elapsed_s": round(now - started, 1), "pid": proc.pid, "at": utc_now()}, sort_keys=True) + "\n")
                    hb.flush()
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    time.sleep(5)
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    break
                if now >= next_heartbeat:
                    hb.write(json.dumps({"event": "heartbeat", "elapsed_s": round(now - started, 1), "pid": proc.pid, "at": utc_now()}, sort_keys=True) + "\n")
                    hb.flush()
                    next_heartbeat = now + max(1, heartbeat_s)
                time.sleep(0.5)
            exit_code = proc.wait()
            hb.write(json.dumps({"event": "finished", "exit_code": exit_code, "timed_out": timed_out, "elapsed_s": round(time.time() - started, 1), "at": utc_now()}, sort_keys=True) + "\n")
    finally:
        stdout_fh.close()
        stderr_fh.close()
    return CommandResult(
        id=command_id,
        cmd=cmd,
        cwd=str(cwd) if cwd else None,
        exit_code=int(exit_code),
        ok=(exit_code == 0 and not timed_out),
        dry_run=False,
        duration_s=time.time() - started,
        timed_out=timed_out,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        heartbeat_path=str(heartbeat_path),
        stdout_tail=tail(stdout_path),
        stderr_tail=tail(stderr_path),
    )


def issue_slice(issue: Mapping[str, Any]) -> Mapping[str, Any]:
    value = issue.get("slice")
    return value if isinstance(value, Mapping) else {}


def _raw_issue_limit(issue: Mapping[str, Any]) -> Any:
    slice_ = issue_slice(issue)
    if "limit" in slice_:
        return slice_.get("limit")
    return issue.get("limit")


def issue_limit(issue: Mapping[str, Any], *, default: int = DEFAULT_LIMIT) -> int:
    value = _raw_issue_limit(issue)
    if value in (None, ""):
        value = default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def is_embedding_bulk_lane(lane: str) -> bool:
    return lane in EMBEDDING_BULK_LANES


def _limit_means_all(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "all", "full", "bulk", "entire", "none", "null", "unbounded"}
    try:
        return int(value) <= 0
    except (TypeError, ValueError):
        return False


def issue_scope(issue: Mapping[str, Any], *, lane: str) -> str:
    slice_ = issue_slice(issue)
    value = slice_.get("scope", issue.get("scope"))
    if value is None and is_embedding_bulk_lane(lane) and _limit_means_all(_raw_issue_limit(issue)):
        value = "all"
    return str(value or "limited").strip().lower()


def issue_requests_full_scope(issue: Mapping[str, Any], *, lane: str) -> bool:
    if not is_embedding_bulk_lane(lane):
        return False
    scope = issue_scope(issue, lane=lane)
    if scope in {"all", "full", "bulk", "entire"}:
        return True
    return _limit_means_all(_raw_issue_limit(issue))


def issue_optional_limit(issue: Mapping[str, Any], *, lane: str, default: int = DEFAULT_LIMIT) -> int | None:
    value = _raw_issue_limit(issue)
    if is_embedding_bulk_lane(lane) and issue_requests_full_scope(issue, lane=lane):
        return None
    if value in (None, ""):
        value = default
    if _limit_means_all(value):
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def issue_batch_size(issue: Mapping[str, Any], *, lane: str, default: int = DEFAULT_EMBED_SCAN_BATCH_SIZE) -> int:
    slice_ = issue_slice(issue)
    value = slice_.get("batch_size") or issue.get("batch_size") or os.environ.get("DEWEY_EMBED_SCAN_BATCH_SIZE") or default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def append_limit_arg(cmd: list[str], limit: int | None) -> list[str]:
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    return cmd


def lane_execution_mode(*, lane: str, apply: bool, commands: Sequence[CommandResult]) -> str:
    if apply:
        return "live_apply"
    if commands and all(cmd.dry_run for cmd in commands):
        return "command_preview_dry_run"
    return "read_only_live"


def issue_collection(issue: Mapping[str, Any], *, default: str = "sparta_controls") -> str:
    collection = issue.get("collection") or issue_slice(issue).get("collection") or default
    return str(collection)


def _memory_python_cmd(memory_root: Path, script: Path, *args: str) -> list[str]:
    return ["uv", "run", "python", str(script), *[str(a) for a in args]]


def _plain_python_cmd(script: Path, *args: str) -> list[str]:
    return [sys.executable, str(script), *[str(a) for a in args]]


def _agent_skills_uv_cmd(script: Path, *args: str) -> list[str]:
    return ["uv", "run", "--project", str(script.parent), f"./{script.name}", *[str(a) for a in args]]


def _verify_prompt_receipt(issue: Mapping[str, Any], run_dir: Path) -> tuple[bool, dict[str, Any] | None, str | None]:
    if not bool(issue.get("requires_prompt_reviewer")):
        return True, None, None
    receipt_path = issue.get("prompt_reviewer_receipt") or issue_slice(issue).get("prompt_reviewer_receipt")
    if not receipt_path:
        return False, None, "qra lane requires prompt_reviewer_receipt in issue or slice"
    path = Path(str(receipt_path))
    if not path.exists():
        return False, None, f"prompt reviewer receipt not found: {path}"
    try:
        # Reuse the existing Dewey receipt validator when available.
        from prompt_reviewer_receipt import validate_receipt_file

        gate = validate_receipt_file(path)
        payload = gate.to_json() if hasattr(gate, "to_json") else {"ok": bool(gate)}
        write_json(run_dir / "prompt_reviewer_gate.json", payload)
        if not bool(payload.get("ok")):
            return False, payload, payload.get("reason") or "prompt reviewer gate failed"
        return True, payload, None
    except Exception as exc:  # noqa: BLE001 - error is a fail-closed gate reason
        return False, None, f"prompt reviewer receipt validation failed: {exc}"


def _classify_failure(result: CommandResult) -> str:
    if result.timed_out:
        return "BLOCKED_TIMEOUT"
    text = (result.stdout_tail + "\n" + result.stderr_tail).lower()
    if any(marker in text for marker in ("429", "503", "504", "bad gateway", "service unavailable", "connection reset", "connection refused", "failed to establish")):
        return "BLOCKED_TRANSIENT_SERVICE"
    return "FAILED_NEEDS_REVIEW"


def _terminal_from_commands(commands: Sequence[CommandResult], *, dry_run: bool, success_status: str = "DONE") -> tuple[str, bool]:
    if not commands:
        return "FAILED_NEEDS_REVIEW", False
    if all(cmd.ok for cmd in commands):
        return ("DRY_RUN_PASS" if dry_run else success_status), True
    if any(_classify_failure(cmd) == "BLOCKED_TIMEOUT" for cmd in commands):
        return "BLOCKED_TIMEOUT", False
    if any(_classify_failure(cmd) == "BLOCKED_TRANSIENT_SERVICE" for cmd in commands):
        return "BLOCKED_TRANSIENT_SERVICE", False
    return "FAILED_NEEDS_REVIEW", False


def effective_timeout(lane: str, timeout_s: int | None) -> int:
    if timeout_s and timeout_s > 0:
        return timeout_s
    return DEFAULT_LANE_TIMEOUTS.get(lane, 300)


def _issue_flag(issue: Mapping[str, Any], name: str) -> bool:
    slice_ = issue_slice(issue)
    return bool(slice_.get(name) or issue.get(name))


def apply_precondition_error(issue: Mapping[str, Any], *, lane: str) -> str | None:
    if not bool(issue.get("mutation_allowed")) and lane != "source_text_qra_coverage":
        return "issue does not allow mutation"
    if is_embedding_bulk_lane(lane):
        # Embedding apply must be full-scope.  Sampling/limits are acceptable for
        # read-only checks, but an apply with a finite limit would reintroduce the
        # years-long queue-drain failure mode this agent is meant to avoid.
        if not issue_requests_full_scope(issue, lane=lane) and not bool(os.environ.get("DEWEY_ALLOW_LIMITED_EMBED_APPLY")):
            return "embedding apply requires full scope: set slice.scope='all' or omit/clear slice.limit"
        # Rollback/count support is enforced by the memory-owned primitive before
        # Dewey claims apply success.  Do not require a manually-maintained
        # rollback_capable flag here; that flag created a second schema gate and
        # caused Dewey to spiral on queue metadata instead of running the concrete
        # memory-side proof primitive.
        return None
    if lane == "qra_coverage_per_control":
        limit = issue_limit(issue, default=DEFAULT_QRA_LIMIT)
        max_apply_limit = int(os.environ.get("DEWEY_MAX_QRA_APPLY_LIMIT", str(DEFAULT_MAX_QRA_APPLY_LIMIT)))
        if limit > max_apply_limit:
            return f"qra apply limit {limit} exceeds DEWEY_MAX_QRA_APPLY_LIMIT={max_apply_limit}"
        if not bool(issue.get("requires_prompt_reviewer")):
            return "qra_coverage_per_control apply requires prompt reviewer gate"
    return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _lane_observed_field(lane: str) -> str:
    if lane == "inline_embedding_policy":
        return "observed_inline_count"
    if lane == "missing_qdrant_embeddings":
        return "observed_missing_count"
    if lane == "qdrant_pointer_metadata":
        return "observed_missing_or_stale_pointer_count"
    if lane == "source_workbook_parity":
        return "observed_strict_field_mismatches"
    return "observed_count"


def expected_before_count(issue: Mapping[str, Any], *, lane: str) -> int | None:
    slice_ = issue_slice(issue)
    observed_field = _lane_observed_field(lane)
    return _first_int(
        slice_.get("expected_before_count"),
        issue.get("expected_before_count"),
        slice_.get(observed_field),
        issue.get(observed_field),
        slice_.get("observed_count"),
        slice_.get("observed_missing"),
        issue.get("observed_count"),
    )


def _source_workbook_count_from_payload(payload: Mapping[str, Any]) -> int | None:
    return _first_int(
        payload.get("before_count"),
        payload.get("strict_field_mismatches"),
        _json_get_path(payload, "gap_counts", "strict_field_mismatches"),
    )


def _source_workbook_preflight_from_output(*, output: Path, command: CommandResult) -> dict[str, Any]:
    payload = _load_optional_json(output) or {}
    before_count = _source_workbook_count_from_payload(payload)
    return {
        "schema": "dewey.source_workbook_parity_preflight.v1",
        "lane": "source_workbook_parity",
        "collection": "sparta_controls",
        "scope": "all",
        "live": bool(not command.dry_run),
        "source": "memory.scripts.validation.dewey_sparta_corpus_parity",
        "mutation_applied": False,
        "before_count": before_count,
        "count_artifact": str(output),
        "success_condition": {"after_strict_field_mismatches": 0},
        "command_ok": bool(command.ok),
        "created_at": utc_now(),
    }


def extract_source_workbook_proof(
    *,
    output_path: Path,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _load_optional_json(output_path)
    if payload is None:
        return {
            "schema": "dewey.source_workbook_parity_proof.v1",
            "lane": "source_workbook_parity",
            "proof_ok": False,
            "reason": f"repair output JSON missing or invalid: {output_path}",
            "output_path": str(output_path),
        }
    before_count = _first_int(payload.get("before_count"), preflight.get("before_count"))
    after_count = _first_int(payload.get("after_count"), _json_get_path(payload, "after_gap_counts", "strict_field_mismatches"))
    changed_count = _first_int(payload.get("changed_count"), payload.get("updated_document_count"))
    rollback_manifest = payload.get("rollback_manifest")
    rollback_records = _first_int(payload.get("rollback_records"))
    if rollback_manifest and rollback_records is None:
        rollback_records = _count_jsonl_records(Path(str(rollback_manifest)))

    reasons: list[str] = []
    if before_count is None:
        reasons.append("missing before_count")
    if after_count is None:
        reasons.append("missing after_count")
    elif after_count != 0:
        reasons.append(f"after_count is {after_count}, expected 0")
    if changed_count is None:
        reasons.append("missing changed_count")
    if rollback_manifest is None:
        reasons.append("missing rollback_manifest")
    elif not Path(str(rollback_manifest)).exists():
        reasons.append(f"rollback_manifest does not exist: {rollback_manifest}")
    if rollback_records is None:
        reasons.append("missing rollback_records")
    elif changed_count is not None and rollback_records != changed_count:
        reasons.append(f"rollback_records {rollback_records} does not equal changed_count {changed_count}")
    if before_count is not None and changed_count is not None and changed_count != before_count:
        reasons.append(f"changed_count {changed_count} does not equal before_count {before_count}")

    return {
        "schema": "dewey.source_workbook_parity_proof.v1",
        "lane": "source_workbook_parity",
        "proof_ok": not reasons,
        "reason": "; ".join(reasons) if reasons else "rollback-backed source workbook parity proof accepted",
        "before_count": before_count,
        "after_count": after_count,
        "changed_count": changed_count,
        "rollback_manifest": str(rollback_manifest) if rollback_manifest else None,
        "rollback_records": rollback_records,
        "output_path": str(output_path),
    }


def write_embedding_preflight(
    issue: Mapping[str, Any],
    *,
    lane: str,
    collection: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Write the read-only before-count artifact for an embedding lane.

    monitor_sparta_repair_queue.py owns health to queue conversion.  Dewey treats
    the queue issue's expected_before_count as the read-only monitor-derived
    full-scope count.  If the queue does not carry such a count, Dewey fails
    closed before apply because it cannot prove full-class convergence.
    """

    artifact_dir.mkdir(parents=True, exist_ok=True)
    before_count = expected_before_count(issue, lane=lane)
    count_path = artifact_dir / "before_counts.json"
    payload = {
        "schema": "dewey.embedding_preflight.v1",
        "lane": lane,
        "collection": collection,
        "scope": "all" if issue_requests_full_scope(issue, lane=lane) else issue_scope(issue, lane=lane),
        "live": True,
        "source": "monitor_sparta_repair_queue.expected_before_count",
        "mutation_applied": False,
        "before_count": before_count,
        "count_artifact": str(count_path),
        "success_condition": {"after_affected_count": 0},
        "created_at": utc_now(),
    }
    write_json(count_path, payload)
    return payload


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _json_get_path(payload: Mapping[str, Any], *path: str) -> Any:
    cur: Any = payload
    for part in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(part)
    return cur


def _find_existing_path(path_value: Any, *, base_dir: Path) -> str | None:
    if not path_value:
        return None
    p = Path(str(path_value))
    if not p.is_absolute():
        p = base_dir / p
    return str(p)


def _count_jsonl_records(path: Path) -> int | None:
    if not path.exists():
        return None
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def extract_embedding_proof(
    *,
    lane: str,
    output_path: Path,
    preflight: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Extract before/after/change/rollback proof from a memory primitive output.

    Dewey must not infer success from exit code alone.  The memory primitive must
    produce rollback-backed counters; otherwise this function returns proof_ok
    false and the lane is marked OPERATOR_REQUIRED.
    """

    payload = _load_optional_json(output_path)
    if payload is None:
        return {
            "schema": "dewey.embedding_proof.v1",
            "lane": lane,
            "proof_ok": False,
            "reason": f"repair output JSON missing or invalid: {output_path}",
            "output_path": str(output_path),
        }

    before_count = _first_int(
        payload.get("before_count"),
        payload.get("affected_before_count"),
        payload.get("initial_count"),
        payload.get(_lane_observed_field(lane)),
        _json_get_path(payload, "before", "affected_count"),
        preflight.get("before_count"),
    )
    after_count = _first_int(
        payload.get("after_count"),
        payload.get("affected_after_count"),
        payload.get("remaining_count"),
        _json_get_path(payload, "after", "affected_count"),
    )
    changed_count = _first_int(
        payload.get("changed_count"),
        payload.get("updated"),
        payload.get("processed"),
        payload.get("stripped"),
        payload.get("migrated"),
        _json_get_path(payload, "changes", "changed_count"),
    )
    rollback_manifest = _find_existing_path(
        payload.get("rollback_manifest") or payload.get("rollback_path") or payload.get("rollback_jsonl"),
        base_dir=artifact_dir,
    )
    rollback_records = _first_int(payload.get("rollback_records"), payload.get("rollback_count"))
    if rollback_manifest and rollback_records is None:
        rollback_records = _count_jsonl_records(Path(rollback_manifest))

    deterministic_explanation = payload.get("deterministic_explanation") or payload.get("skip_explanation")
    reasons: list[str] = []
    if before_count is None:
        reasons.append("missing before_count")
    if after_count is None:
        reasons.append("missing after_count")
    elif after_count != 0:
        reasons.append(f"after_count is {after_count}, expected 0")
    if changed_count is None:
        reasons.append("missing changed_count")
    if rollback_manifest is None:
        reasons.append("missing rollback_manifest")
    elif not Path(rollback_manifest).exists():
        reasons.append(f"rollback_manifest does not exist: {rollback_manifest}")
    if rollback_records is None:
        reasons.append("missing rollback_records")
    elif changed_count is not None and rollback_records < changed_count:
        reasons.append(f"rollback_records {rollback_records} is less than changed_count {changed_count}")
    if before_count is not None and changed_count is not None and changed_count != before_count and not deterministic_explanation:
        reasons.append(f"changed_count {changed_count} does not equal before_count {before_count}")

    proof_ok = not reasons
    return {
        "schema": "dewey.embedding_proof.v1",
        "lane": lane,
        "proof_ok": proof_ok,
        "reason": "; ".join(reasons) if reasons else "rollback-backed full-scope embedding proof accepted",
        "before_count": before_count,
        "after_count": after_count,
        "changed_count": changed_count,
        "rollback_manifest": rollback_manifest,
        "rollback_records": rollback_records,
        "deterministic_explanation": deterministic_explanation,
        "output_path": str(output_path),
    }


def _embedding_result_from_command(
    *,
    lane: str,
    collection: str,
    scope: str,
    limit: int | None,
    batch_size: int,
    command: CommandResult,
    preflight: Mapping[str, Any],
    output: Path,
    apply: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    terminal, ok = _terminal_from_commands([command], dry_run=not apply, success_status="DONE")
    proof: dict[str, Any] | None = None
    if command.ok and apply:
        proof = extract_embedding_proof(lane=lane, output_path=output, preflight=preflight, artifact_dir=output.parent)
        if not bool(proof.get("proof_ok")):
            terminal = "OPERATOR_REQUIRED"
            ok = False
    result: dict[str, Any] = {
        "schema": "dewey.lane_result.v1",
        "lane": lane,
        "terminal_status": terminal,
        "ok": ok,
        "collection": collection,
        "scope": scope,
        "limit": limit,
        "batch_size": batch_size,
        "bulk_embedding_contract": "full_scope_apply" if scope == "all" else "limited_dry_run_only",
        "execution_mode": lane_execution_mode(lane=lane, apply=apply, commands=[command]),
        "dry_run": not apply,
        "mutation_applied": bool(apply and ok and proof and proof.get("proof_ok")),
        "preflight": dict(preflight),
        "proof": dict(proof or {}),
        "before_count": proof.get("before_count") if proof else preflight.get("before_count"),
        "after_count": proof.get("after_count") if proof else None,
        "changed_count": proof.get("changed_count") if proof else None,
        "rollback_manifest": proof.get("rollback_manifest") if proof else None,
        "rollback_records": proof.get("rollback_records") if proof else None,
        "proof_ok": bool(proof and proof.get("proof_ok")) if apply else False,
        "commands": [command.to_json()],
        "artifacts": {"output": str(output), "before_counts": str(Path(str(preflight.get("count_artifact"))))},
    }
    if extra:
        result.update(dict(extra))
    return result


def _embedding_repair_subcommand(lane: str) -> str:
    if lane == "inline_embedding_policy":
        return "inline-vectors"
    if lane == "qdrant_pointer_metadata":
        return "qdrant-pointer-metadata"
    if lane == "missing_qdrant_embeddings":
        return "missing-qdrant-embeddings"
    raise ValueError(f"not an embedding repair lane: {lane}")


def _embedding_primitive_cmd(
    *,
    memory_root: Path,
    lane: str,
    collection: str,
    batch_size: int,
    output: Path,
    rollback_out: Path,
    apply: bool,
) -> list[str]:
    """Build the one concrete memory-owned embedding repair primitive command.

    This is the anti-spiral boundary: Dewey does not assemble AQL, does not call
    monitor_sparta.py repair-cycle, and does not fan out into legacy repair
    scripts.  It calls exactly one memory-side primitive that owns read-only
    counts, rollback manifest creation, mutation, and after-count proof.
    """

    script = memory_root / "scripts" / "validation" / "dewey_embedding_repair.py"
    cmd = _memory_python_cmd(
        memory_root,
        script,
        _embedding_repair_subcommand(lane),
        "--collection",
        collection,
        "--batch-size",
        str(batch_size),
        "--output",
        str(output),
        "--rollback-out",
        str(rollback_out),
    )
    cmd.append("--apply" if apply else "--dry-run")
    return cmd


def _preflight_from_output(*, lane: str, collection: str, output: Path, command: CommandResult) -> dict[str, Any]:
    payload = _load_optional_json(output) or {}
    before_count = _first_int(
        payload.get("before_count"),
        payload.get("affected_before_count"),
        payload.get("initial_count"),
        payload.get(_lane_observed_field(lane)),
        _json_get_path(payload, "before", "affected_count"),
    )
    return {
        "schema": "dewey.embedding_preflight.v1",
        "lane": lane,
        "collection": collection,
        "scope": "all",
        "live": bool(not command.dry_run),
        "source": "memory.scripts.validation.dewey_embedding_repair",
        "mutation_applied": False,
        "before_count": before_count,
        "count_artifact": str(output),
        "success_condition": {"after_affected_count": 0},
        "command_ok": bool(command.ok),
        "created_at": utc_now(),
    }


def run_embedding_bulk_lane(
    issue: Mapping[str, Any],
    *,
    lane: str,
    memory_root: Path,
    run_dir: Path,
    apply: bool,
    timeout_s: int,
    heartbeat_s: int,
) -> dict[str, Any]:
    collection = issue_collection(issue)
    limit = issue_optional_limit(issue, lane=lane)
    batch_size = issue_batch_size(issue, lane=lane)
    scope = "all" if limit is None else "limited"
    artifact_dir = run_dir / lane
    output = artifact_dir / f"{collection}_{lane}.json"
    preflight_output = artifact_dir / "before_counts.json"
    rollback_out = artifact_dir / "rollback.jsonl"

    if limit is not None:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "embedding lane apply/preflight must be full scope; finite limit is not accepted",
            "collection": collection,
            "scope": scope,
            "limit": limit,
            "mutation_applied": False,
            "commands": [],
        }

    preflight_cmd = run_command(
        command_id=f"{lane}_preflight",
        cmd=_embedding_primitive_cmd(
            memory_root=memory_root,
            lane=lane,
            collection=collection,
            batch_size=batch_size,
            output=preflight_output,
            rollback_out=rollback_out,
            apply=False,
        ),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env=None,
        heartbeat_s=heartbeat_s,
    )
    preflight = _preflight_from_output(lane=lane, collection=collection, output=preflight_output, command=preflight_cmd)
    if not preflight_cmd.ok:
        terminal, ok = _terminal_from_commands([preflight_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": terminal,
            "ok": ok,
            "reason": "embedding preflight failed; Dewey did not attempt mutation",
            "collection": collection,
            "scope": scope,
            "limit": limit,
            "batch_size": batch_size,
            "bulk_embedding_contract": "full_scope_apply",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    if preflight.get("before_count") is None:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "embedding preflight did not produce before_count; Dewey did not attempt mutation",
            "collection": collection,
            "scope": scope,
            "limit": limit,
            "batch_size": batch_size,
            "bulk_embedding_contract": "full_scope_apply",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    if not apply:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "collection": collection,
            "scope": scope,
            "limit": limit,
            "batch_size": batch_size,
            "bulk_embedding_contract": "full_scope_apply",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "after_count": None,
            "changed_count": None,
            "rollback_manifest": None,
            "rollback_records": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    apply_cmd = run_command(
        command_id=f"{lane}_apply",
        cmd=_embedding_primitive_cmd(
            memory_root=memory_root,
            lane=lane,
            collection=collection,
            batch_size=batch_size,
            output=output,
            rollback_out=rollback_out,
            apply=True,
        ),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env={"SPARTA_MONITOR_MUTATION_ENABLED": "1"},
        heartbeat_s=heartbeat_s,
    )
    if not apply_cmd.ok:
        terminal, ok = _terminal_from_commands([apply_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": terminal,
            "ok": ok,
            "reason": "memory-owned embedding primitive failed; no Dewey retry loop was attempted",
            "collection": collection,
            "scope": scope,
            "limit": limit,
            "batch_size": batch_size,
            "bulk_embedding_contract": "full_scope_apply",
            "execution_mode": "live_apply",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    result = _embedding_result_from_command(
        lane=lane,
        collection=collection,
        scope=scope,
        limit=limit,
        batch_size=batch_size,
        command=apply_cmd,
        preflight=preflight,
        output=output,
        apply=True,
    )
    result["commands"] = [preflight_cmd.to_json(), apply_cmd.to_json()]
    result["artifacts"] = {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)}
    return result


def run_inline_embedding_policy(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    return run_embedding_bulk_lane(issue, lane="inline_embedding_policy", memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)


def run_qdrant_pointer_metadata(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    return run_embedding_bulk_lane(issue, lane="qdrant_pointer_metadata", memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)


def run_missing_qdrant_embeddings(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    return run_embedding_bulk_lane(issue, lane="missing_qdrant_embeddings", memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)


def run_source_workbook_parity(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    collection = issue_collection(issue)
    if collection != "sparta_controls":
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_workbook_parity",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": f"source_workbook_parity only supports sparta_controls, got {collection}",
            "collection": collection,
            "mutation_applied": False,
            "commands": [],
        }
    artifact_dir = run_dir / "source_workbook_parity"
    script = memory_root / "scripts" / "validation" / "dewey_sparta_corpus_parity.py"
    preflight_output = artifact_dir / "before_counts.json"
    output = artifact_dir / "apply_receipt.json"
    rollback_out = artifact_dir / "rollback.jsonl"

    preflight_cmd = run_command(
        command_id="source_workbook_parity_preflight",
        cmd=_memory_python_cmd(memory_root, script, "--dry-run", "--output", str(preflight_output)),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env=None,
        heartbeat_s=heartbeat_s,
    )
    preflight = _source_workbook_preflight_from_output(output=preflight_output, command=preflight_cmd)
    if not preflight_cmd.ok:
        terminal, ok = _terminal_from_commands([preflight_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_workbook_parity",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "source workbook parity preflight failed; Dewey did not attempt mutation",
            "collection": collection,
            "scope": "all",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    if preflight.get("before_count") is None:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_workbook_parity",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "source workbook parity preflight did not produce before_count",
            "collection": collection,
            "scope": "all",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    if not apply:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_workbook_parity",
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "collection": collection,
            "scope": "all",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "after_count": None,
            "changed_count": None,
            "rollback_manifest": None,
            "rollback_records": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    apply_cmd = run_command(
        command_id="source_workbook_parity_apply",
        cmd=_memory_python_cmd(memory_root, script, "--apply", "--output", str(output), "--rollback-out", str(rollback_out)),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env={"SPARTA_MONITOR_MUTATION_ENABLED": "1"},
        heartbeat_s=heartbeat_s,
    )
    if not apply_cmd.ok:
        terminal, ok = _terminal_from_commands([apply_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_workbook_parity",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "memory-owned source workbook parity primitive failed; no Dewey retry loop was attempted",
            "collection": collection,
            "scope": "all",
            "execution_mode": "live_apply",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    proof = extract_source_workbook_proof(output_path=output, preflight=preflight)
    terminal = "DONE" if bool(proof.get("proof_ok")) else "OPERATOR_REQUIRED"
    ok = bool(proof.get("proof_ok"))
    return {
        "schema": "dewey.lane_result.v1",
        "lane": "source_workbook_parity",
        "terminal_status": terminal,
        "ok": ok,
        "collection": collection,
        "scope": "all",
        "execution_mode": "live_apply",
        "dry_run": False,
        "mutation_applied": bool(ok and int(proof.get("changed_count") or 0) > 0),
        "preflight": preflight,
        "proof": proof,
        "before_count": proof.get("before_count"),
        "after_count": proof.get("after_count"),
        "changed_count": proof.get("changed_count"),
        "rollback_manifest": proof.get("rollback_manifest"),
        "rollback_records": proof.get("rollback_records"),
        "proof_ok": ok,
        "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
        "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
    }


def _source_text_status_proof(output_path: Path) -> dict[str, Any]:
    payload = load_json(output_path)
    return {
        "schema": "dewey.source_text_status_repair_proof.v1",
        "lane": "source_text_status_repair",
        "operation": payload.get("operation"),
        "collection": payload.get("collection"),
        "source_evidence_manifest": payload.get("source_evidence_manifest"),
        "before_count": payload.get("before_count"),
        "after_count": payload.get("after_count"),
        "changed_count": payload.get("changed_count"),
        "rollback_manifest": payload.get("rollback_manifest"),
        "rollback_records": payload.get("rollback_records"),
        "mutation_applied": payload.get("mutation_applied"),
        "proof_ok": bool(payload.get("proof_ok")),
    }


def run_source_text_status_repair(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    slice_ = issue_slice(issue)
    next_action = slice_.get("next_action") if isinstance(slice_.get("next_action"), Mapping) else {}
    manifest_path = (
        slice_.get("source_evidence_manifest")
        or slice_.get("manifest_path")
        or next_action.get("source_evidence_manifest")
        or next_action.get("manifest_path")
        or issue.get("source_evidence_manifest")
    )
    if not manifest_path:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_text_status_repair",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "source_text_status_repair requires source_evidence_manifest",
            "mutation_applied": False,
            "commands": [],
        }
    manifest = Path(str(manifest_path))
    if not manifest.exists():
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_text_status_repair",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": f"source evidence manifest not found: {manifest}",
            "mutation_applied": False,
            "commands": [],
        }

    artifact_dir = run_dir / "source_text_status_repair"
    script = memory_root / "scripts" / "validation" / "dewey_source_text_status_repair.py"
    preflight_output = artifact_dir / "before_counts.json"
    output = artifact_dir / "apply_receipt.json"
    rollback_out = artifact_dir / "rollback.jsonl"
    preflight_cmd = run_command(
        command_id="source_text_status_preflight",
        cmd=_memory_python_cmd(memory_root, script, "--dry-run", "--source-evidence-manifest", str(manifest), "--output", str(preflight_output)),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env=None,
        heartbeat_s=heartbeat_s,
    )
    preflight = load_json(preflight_output) if preflight_output.exists() else {}
    if not preflight_cmd.ok:
        terminal, ok = _terminal_from_commands([preflight_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_text_status_repair",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "source text status preflight failed; Dewey did not attempt mutation",
            "collection": "sparta_controls",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    if not apply:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_text_status_repair",
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "collection": "sparta_controls",
            "scope": "source_evidence_manifest",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "after_count": None,
            "changed_count": None,
            "rollback_manifest": None,
            "rollback_records": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    apply_cmd = run_command(
        command_id="source_text_status_apply",
        cmd=_memory_python_cmd(
            memory_root,
            script,
            "--apply",
            "--source-evidence-manifest",
            str(manifest),
            "--output",
            str(output),
            "--rollback-out",
            str(rollback_out),
        ),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env={"SPARTA_MONITOR_MUTATION_ENABLED": "1"},
        heartbeat_s=heartbeat_s,
    )
    if not apply_cmd.ok:
        terminal, ok = _terminal_from_commands([apply_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_text_status_repair",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "memory-owned source text status primitive failed; no Dewey retry loop was attempted",
            "collection": "sparta_controls",
            "execution_mode": "live_apply",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }

    proof = _source_text_status_proof(output)
    terminal = "DONE" if bool(proof.get("proof_ok")) else "OPERATOR_REQUIRED"
    ok = bool(proof.get("proof_ok"))
    return {
        "schema": "dewey.lane_result.v1",
        "lane": "source_text_status_repair",
        "terminal_status": terminal,
        "ok": ok,
        "collection": "sparta_controls",
        "scope": "source_evidence_manifest",
        "execution_mode": "live_apply",
        "dry_run": False,
        "mutation_applied": bool(ok and int(proof.get("changed_count") or 0) > 0),
        "preflight": preflight,
        "proof": proof,
        "before_count": proof.get("before_count"),
        "after_count": proof.get("after_count"),
        "changed_count": proof.get("changed_count"),
        "rollback_manifest": proof.get("rollback_manifest"),
        "rollback_records": proof.get("rollback_records"),
        "proof_ok": ok,
        "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
        "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
    }


def run_source_url_text_backfill(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    slice_ = issue_slice(issue)
    next_action = slice_.get("next_action") if isinstance(slice_.get("next_action"), Mapping) else {}
    url_id = next_action.get("url_id") or slice_.get("url_id") or issue.get("url_id")
    fetcher_summary = next_action.get("fetcher_summary") or slice_.get("fetcher_summary") or issue.get("fetcher_summary")
    if not url_id or not fetcher_summary:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_url_text_backfill",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "source_url_text_backfill requires url_id and fetcher_summary",
            "mutation_applied": False,
            "commands": [],
        }
    artifact_dir = run_dir / "source_url_text_backfill"
    script = memory_root / "scripts" / "validation" / "dewey_url_text_backfill.py"
    preflight_output = artifact_dir / "before_counts.json"
    output = artifact_dir / "apply_receipt.json"
    rollback_out = artifact_dir / "rollback.jsonl"
    base_args = ["--url-id", str(url_id), "--fetcher-summary", str(fetcher_summary)]
    preflight_cmd = run_command(
        command_id="source_url_text_backfill_preflight",
        cmd=_memory_python_cmd(memory_root, script, "--dry-run", *base_args, "--output", str(preflight_output)),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env=None,
        heartbeat_s=heartbeat_s,
    )
    preflight = load_json(preflight_output) if preflight_output.exists() else {}
    if not preflight_cmd.ok:
        terminal, ok = _terminal_from_commands([preflight_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_url_text_backfill",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "source URL text backfill preflight failed; Dewey did not attempt mutation",
            "collection": "sparta_url_knowledge",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    if not apply:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_url_text_backfill",
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "collection": "sparta_url_knowledge",
            "scope": "one_url_fetcher_artifact",
            "execution_mode": "read_only_live",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "after_count": None,
            "changed_count": None,
            "rollback_manifest": None,
            "rollback_records": None,
            "proof_ok": False,
            "commands": [preflight_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    apply_cmd = run_command(
        command_id="source_url_text_backfill_apply",
        cmd=_memory_python_cmd(memory_root, script, "--apply", *base_args, "--output", str(output), "--rollback-out", str(rollback_out)),
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env={"SPARTA_MONITOR_MUTATION_ENABLED": "1"},
        heartbeat_s=heartbeat_s,
    )
    if not apply_cmd.ok:
        terminal, ok = _terminal_from_commands([apply_cmd], dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "source_url_text_backfill",
            "terminal_status": terminal,
            "ok": ok,
            "reason": "memory-owned URL text backfill primitive failed; no Dewey retry loop was attempted",
            "collection": "sparta_url_knowledge",
            "execution_mode": "live_apply",
            "dry_run": False,
            "mutation_applied": False,
            "preflight": preflight,
            "before_count": preflight.get("before_count"),
            "proof_ok": False,
            "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
            "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
        }
    proof = load_json(output)
    ok = bool(proof.get("proof_ok"))
    return {
        "schema": "dewey.lane_result.v1",
        "lane": "source_url_text_backfill",
        "terminal_status": "DONE" if ok else "OPERATOR_REQUIRED",
        "ok": ok,
        "collection": "sparta_url_knowledge",
        "scope": "one_url_fetcher_artifact",
        "execution_mode": "live_apply",
        "dry_run": False,
        "mutation_applied": bool(ok and proof.get("mutation_applied")),
        "preflight": preflight,
        "proof": proof,
        "before_count": proof.get("before_count"),
        "after_count": proof.get("after_count"),
        "changed_count": proof.get("changed_count"),
        "rollback_manifest": proof.get("rollback_manifest"),
        "rollback_records": proof.get("rollback_records"),
        "proof_ok": ok,
        "commands": [preflight_cmd.to_json(), apply_cmd.to_json()],
        "artifacts": {"before_counts": str(preflight_output), "output": str(output), "rollback_manifest": str(rollback_out)},
    }


def run_source_text_qra_coverage(issue: Mapping[str, Any], *, memory_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    limit = issue_limit(issue)
    artifact_dir = run_dir / "source_text_qra_coverage"
    script = memory_root / "scripts" / "validation" / "source_text_qra_coverage.py"
    cmd = _memory_python_cmd(
        memory_root,
        script,
        "--manifest-limit",
        str(limit),
        "--artifact-dir",
        str(artifact_dir),
    )
    result = run_command(
        command_id="source_text_qra_coverage_manifest",
        cmd=cmd,
        cwd=memory_root,
        artifact_dir=artifact_dir,
        timeout_s=timeout_s,
        dry_run=False,
        env=None,
        heartbeat_s=heartbeat_s,
    )
    terminal, ok = _terminal_from_commands([result], dry_run=False, success_status="DONE")
    return {
        "schema": "dewey.lane_result.v1",
        "lane": "source_text_qra_coverage",
        "terminal_status": terminal,
        "ok": ok,
        "limit": limit,
        "execution_mode": "read_only_live",
        "dry_run": False,
        "mutation_applied": False,
        "commands": [result.to_json()],
        "artifact_dir": str(artifact_dir),
    }


def run_qra_coverage_per_control(issue: Mapping[str, Any], *, memory_root: Path, agent_skills_root: Path, run_dir: Path, apply: bool, timeout_s: int, heartbeat_s: int) -> dict[str, Any]:
    gate_ok, gate_payload, gate_reason = _verify_prompt_receipt(issue, run_dir)
    if not gate_ok:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "qra_coverage_per_control",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": gate_reason,
            "prompt_reviewer_gate": gate_payload,
            "mutation_applied": False,
            "commands": [],
        }

    slice_ = issue_slice(issue)
    manifest_path = slice_.get("manifest_path") or issue.get("manifest_path")
    if not manifest_path:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "qra_coverage_per_control",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": "qra_coverage_per_control issue requires slice.manifest_path",
            "prompt_reviewer_gate": gate_payload,
            "mutation_applied": False,
            "commands": [],
        }
    manifest = Path(str(manifest_path))
    if not manifest.exists():
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "qra_coverage_per_control",
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": f"create-qras manifest not found: {manifest}",
            "prompt_reviewer_gate": gate_payload,
            "mutation_applied": False,
            "commands": [],
        }

    limit = issue_limit(issue, default=DEFAULT_QRA_LIMIT)
    artifact_dir = run_dir / "qra_coverage_per_control"
    create_qras = agent_skills_root / "skills" / "create-qras" / "run.sh"
    review_output = artifact_dir / "create_qras_review.json"
    review = run_command(
        command_id="create_qras_review",
        cmd=_agent_skills_uv_cmd(create_qras, "review", str(manifest), "--output", str(review_output)),
        cwd=create_qras.parent,
        artifact_dir=artifact_dir,
        timeout_s=int(os.environ.get("DEWEY_CREATE_QRAS_REVIEW_TIMEOUT_S", str(timeout_s))),
        dry_run=False,
        heartbeat_s=heartbeat_s,
    )
    dry = run_command(
        command_id="create_qras_manifest_dry_run",
        cmd=_agent_skills_uv_cmd(create_qras, "manifest", str(manifest), "--limit", str(limit), "--dry-run"),
        cwd=create_qras.parent,
        artifact_dir=artifact_dir,
        timeout_s=int(os.environ.get("DEWEY_CREATE_QRAS_DRY_RUN_TIMEOUT_S", str(timeout_s))),
        dry_run=False,
        heartbeat_s=heartbeat_s,
    )
    commands = [review, dry]
    if not (review.ok and dry.ok):
        terminal, ok = _terminal_from_commands(commands, dry_run=False)
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "qra_coverage_per_control",
            "terminal_status": terminal,
            "ok": ok,
            "limit": limit,
            "prompt_reviewer_gate": gate_payload,
            "manifest_path": str(manifest),
            "mutation_applied": False,
            "commands": [cmd.to_json() for cmd in commands],
            "artifacts": {"review_output": str(review_output)},
        }
    if not apply:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "qra_coverage_per_control",
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "limit": limit,
            "prompt_reviewer_gate": gate_payload,
            "manifest_path": str(manifest),
            "mutation_applied": False,
            "commands": [cmd.to_json() for cmd in commands],
            "artifacts": {"review_output": str(review_output)},
        }
    canary = run_command(
        command_id="create_qras_manifest_canary",
        cmd=_agent_skills_uv_cmd(create_qras, "manifest", str(manifest), "--limit", str(limit)),
        cwd=create_qras.parent,
        artifact_dir=artifact_dir,
        timeout_s=int(os.environ.get("DEWEY_CREATE_QRAS_CANARY_TIMEOUT_S", str(timeout_s))),
        dry_run=False,
        env={"SPARTA_MONITOR_MUTATION_ENABLED": "1"},
        heartbeat_s=heartbeat_s,
    )
    commands.append(canary)
    terminal, ok = _terminal_from_commands(commands, dry_run=False, success_status="DONE")
    return {
        "schema": "dewey.lane_result.v1",
        "lane": "qra_coverage_per_control",
        "terminal_status": terminal,
        "ok": ok,
        "limit": limit,
        "prompt_reviewer_gate": gate_payload,
        "manifest_path": str(manifest),
        "mutation_applied": bool(ok),
        "commands": [cmd.to_json() for cmd in commands],
        "artifacts": {"review_output": str(review_output)},
    }


def run_lane(
    issue: Mapping[str, Any],
    *,
    run_dir: Path,
    memory_root: Path,
    agent_skills_root: Path,
    apply: bool,
    timeout_s: int,
    heartbeat_s: int = DEFAULT_HEARTBEAT_S,
) -> dict[str, Any]:
    lane = str(issue.get("lane") or "")
    if lane not in DEWEY_OWNED_LANES:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": f"lane is not Dewey-owned: {lane}",
            "mutation_applied": False,
            "commands": [],
        }
    if apply:
        precondition_error = apply_precondition_error(issue, lane=lane)
    else:
        precondition_error = None
    if precondition_error:
        return {
            "schema": "dewey.lane_result.v1",
            "lane": lane,
            "terminal_status": "OPERATOR_REQUIRED",
            "ok": False,
            "reason": precondition_error,
            "mutation_applied": False,
            "commands": [],
        }
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "issue.json", dict(issue))
    timeout_s = effective_timeout(lane, timeout_s)

    if lane == "inline_embedding_policy":
        result = run_inline_embedding_policy(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "qdrant_pointer_metadata":
        result = run_qdrant_pointer_metadata(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "missing_qdrant_embeddings":
        result = run_missing_qdrant_embeddings(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "source_workbook_parity":
        result = run_source_workbook_parity(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "source_text_status_repair":
        result = run_source_text_status_repair(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "source_url_text_backfill":
        result = run_source_url_text_backfill(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "source_text_qra_coverage":
        result = run_source_text_qra_coverage(issue, memory_root=memory_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    elif lane == "qra_coverage_per_control":
        result = run_qra_coverage_per_control(issue, memory_root=memory_root, agent_skills_root=agent_skills_root, run_dir=run_dir, apply=apply, timeout_s=timeout_s, heartbeat_s=heartbeat_s)
    else:  # pragma: no cover - guarded above
        raise AssertionError(lane)

    assert_no_inline_vectors(result)
    write_json(run_dir / "lane_result.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_json", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--memory-repo-root", type=Path, default=Path(os.environ.get("MEMORY_ROOT") or DEFAULT_MEMORY_REPO_ROOT))
    parser.add_argument("--agent-skills-root", type=Path, default=Path(os.environ.get("AGENT_SKILLS_ROOT") or DEFAULT_AGENT_SKILLS_ROOT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--timeout-s", type=int, default=int(os.environ.get("DEWEY_LANE_TIMEOUT_S", "7200")))
    parser.add_argument("--heartbeat-s", type=int, default=int(os.environ.get("DEWEY_SUBPROCESS_HEARTBEAT_S", str(DEFAULT_HEARTBEAT_S))))
    args = parser.parse_args(argv)
    issue = load_json(args.issue_json)
    result = run_lane(
        issue,
        run_dir=args.run_dir,
        memory_root=args.memory_repo_root,
        agent_skills_root=args.agent_skills_root,
        apply=args.apply,
        timeout_s=args.timeout_s,
        heartbeat_s=args.heartbeat_s,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
