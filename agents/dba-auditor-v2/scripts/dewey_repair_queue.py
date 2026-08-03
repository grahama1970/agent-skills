#!/usr/bin/env python3
from __future__ import annotations
"""File-backed monitor-sparta repair queue for Dewey.

Dewey is intentionally not the monitor.  This module gives Dewey a tiny,
deterministic queue contract: read monitor-sparta repair issues, claim one READY
issue, append an immutable status snapshot, and exit after one lane slice.

The queue is append-only JSONL.  The latest line for an issue_id is the current
state; earlier lines remain as audit history.  This avoids hidden in-place state
mutation and makes cron crashes diagnosable.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCHEMA = "monitor_sparta.repair_issue.v1"
SUPPORTED_SCHEMA_VERSION = 1
DEFAULT_STATE_DIR = "/mnt/storage12tb/media/agents/shared/monitor-sparta"
DEFAULT_QUEUE_BASENAME = "repair_queue.jsonl"
READY_STATUSES = {"READY", "READY_RETRY"}
TERMINAL_STATUSES = {
    "DONE",
    "DRY_RUN_DONE",
    "OPERATOR_REQUIRED",
    "FAILED_NEEDS_REVIEW",
    "BLOCKED_PERMANENT",
    "SKIPPED_OUT_OF_SCOPE",
}
RUNNING_STATUSES = {"RUNNING"}

DEWEY_OWNED_LANES = {
    "inline_embedding_policy",
    "qdrant_pointer_metadata",
    "missing_qdrant_embeddings",
    "source_workbook_parity",
    "source_text_status_repair",
    "source_url_text_backfill",
    "source_text_qra_coverage",
    "qra_coverage_per_control",
}

# These lanes are full-class DBA repairs.  Dewey still claims one issue and runs
# one lane, but the embedding lane itself must repair all affected records for
# that class.  Internal batch_size is allowed; apply-time finite limit is not the
# default contract.
EMBEDDING_BULK_LANES = {
    "inline_embedding_policy",
    "qdrant_pointer_metadata",
    "missing_qdrant_embeddings",
}

LANE_PRIORITY = {
    "inline_embedding_policy": 10,
    "qdrant_pointer_metadata": 20,
    "missing_qdrant_embeddings": 30,
    "source_workbook_parity": 35,
    "source_text_status_repair": 36,
    "source_url_text_backfill": 37,
    "source_text_qra_coverage": 40,
    "qra_coverage_per_control": 50,
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def default_state_dir() -> Path:
    return Path(os.environ.get("MONITOR_SPARTA_STATE_DIR") or DEFAULT_STATE_DIR)


def default_queue_path() -> Path:
    return default_state_dir() / DEFAULT_QUEUE_BASENAME


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sanitize_id_part(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text)
    return text.strip("-") or "unknown"


@contextlib.contextmanager
def queue_lock(queue_path: Path) -> Iterator[None]:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL in {path}:{lineno}: {exc}") from exc
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def latest_issue_state(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        issue_id = row.get("issue_id")
        if not issue_id:
            continue
        latest[str(issue_id)] = dict(row)
    return latest


def load_latest(queue_path: Path) -> dict[str, dict[str, Any]]:
    return latest_issue_state(read_jsonl(queue_path))


def _limit_means_all(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "all", "full", "bulk", "entire", "none", "null", "unbounded"}
    try:
        return int(value) <= 0
    except (TypeError, ValueError):
        return False


def _normalize_embedding_slice(out: dict[str, Any]) -> None:
    lane = str(out.get("lane") or "")
    if lane not in EMBEDDING_BULK_LANES:
        return
    slice_value = out.get("slice")
    slice_obj = dict(slice_value) if isinstance(slice_value, Mapping) else {}
    raw_limit = slice_obj.get("limit", out.get("limit"))
    explicit_scope = slice_obj.get("scope", out.get("scope"))
    if explicit_scope is None and _limit_means_all(raw_limit):
        slice_obj["scope"] = "all"
    slice_obj.setdefault("success_condition", "all affected embedding records for this lane are repaired")
    out["slice"] = slice_obj
    out.setdefault("bulk_embedding_contract", "full_scope_one_lane")


def normalize_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    now = utc_now()
    out: dict[str, Any] = dict(issue)
    out.setdefault("schema", SCHEMA)
    out.setdefault("schema_version", SUPPORTED_SCHEMA_VERSION)
    out.setdefault("status", "READY")
    out.setdefault("created_at", now)
    out["updated_at"] = now
    out.setdefault("priority", LANE_PRIORITY.get(str(out.get("lane")), 999))
    out.setdefault("attempt", 0)
    out.setdefault("mutation_allowed", False)
    out.setdefault("requires_prompt_reviewer", out.get("lane") == "qra_coverage_per_control")
    _normalize_embedding_slice(out)
    out.setdefault("history_event", "issue_snapshot")
    out["issue_hash"] = stable_hash({k: v for k, v in out.items() if k not in {"issue_hash", "updated_at"}})
    return out


def validate_queue_issue(issue: Mapping[str, Any]) -> tuple[bool, str | None]:
    if issue.get("schema") not in {None, SCHEMA}:
        return False, f"unsupported schema: {issue.get('schema')}"
    if int(issue.get("schema_version") or SUPPORTED_SCHEMA_VERSION) != SUPPORTED_SCHEMA_VERSION:
        return False, f"unsupported schema_version: {issue.get('schema_version')}"
    if not issue.get("issue_id"):
        return False, "missing issue_id"
    lane = str(issue.get("lane") or "")
    if lane not in DEWEY_OWNED_LANES:
        return False, f"lane is not Dewey-owned: {lane}"
    return True, None


def enqueue_issue(queue_path: Path, issue: Mapping[str, Any], *, replace_equivalent_ready: bool = False) -> dict[str, Any]:
    normalized = normalize_issue(issue)
    with queue_lock(queue_path):
        latest = load_latest(queue_path)
        if replace_equivalent_ready:
            for existing in latest.values():
                if existing.get("status") in READY_STATUSES and _same_issue_kind(existing, normalized):
                    return existing
        append_jsonl(queue_path, normalized)
    return normalized


def enqueue_issues(queue_path: Path, issues: Sequence[Mapping[str, Any]], *, replace_equivalent_ready: bool = True) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    with queue_lock(queue_path):
        latest = load_latest(queue_path)
        for issue in issues:
            normalized = normalize_issue(issue)
            if replace_equivalent_ready:
                duplicate = next(
                    (
                        existing
                        for existing in latest.values()
                        if existing.get("status") in READY_STATUSES and _same_issue_kind(existing, normalized)
                    ),
                    None,
                )
                if duplicate:
                    written.append(duplicate)
                    continue
            append_jsonl(queue_path, normalized)
            latest[str(normalized["issue_id"])] = normalized
            written.append(normalized)
    return written


def _same_issue_kind(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return (
        a.get("lane") == b.get("lane")
        and a.get("dimension") == b.get("dimension")
        and a.get("collection") == b.get("collection")
        and _slice_kind(a.get("slice")) == _slice_kind(b.get("slice"))
    )


def _slice_kind(value: Any) -> tuple[Any, Any]:
    if not isinstance(value, Mapping):
        return (None, None)
    return (value.get("bucket"), value.get("manifest_path"))


def selectable(issue: Mapping[str, Any]) -> bool:
    ok, _reason = validate_queue_issue(issue)
    return ok and issue.get("status") in READY_STATUSES


def select_next(latest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    candidates = [dict(issue) for issue in latest.values() if selectable(issue)]
    candidates.sort(
        key=lambda issue: (
            int(issue.get("priority") or LANE_PRIORITY.get(str(issue.get("lane")), 999)),
            str(issue.get("created_at") or ""),
            str(issue.get("issue_id") or ""),
        )
    )
    return candidates[0] if candidates else None


def claim_one(queue_path: Path, *, run_id: str, claimed_by: str = "dba-auditor") -> dict[str, Any] | None:
    with queue_lock(queue_path):
        latest = load_latest(queue_path)
        issue = select_next(latest)
        if issue is None:
            return None
        claimed = dict(issue)
        claimed["status"] = "RUNNING"
        claimed["claimed_by"] = claimed_by
        claimed["claimed_at"] = utc_now()
        claimed["run_id"] = run_id
        claimed["attempt"] = int(claimed.get("attempt") or 0) + 1
        claimed["history_event"] = "claimed"
        claimed = normalize_issue(claimed)
        append_jsonl(queue_path, claimed)
        return claimed


def update_issue(queue_path: Path, issue: Mapping[str, Any], *, status: str, result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    updated = dict(issue)
    updated["status"] = status
    updated["result"] = dict(result or {})
    updated["finished_at"] = utc_now()
    updated["history_event"] = "status_update"
    updated = normalize_issue(updated)
    with queue_lock(queue_path):
        append_jsonl(queue_path, updated)
    return updated


def summarize(queue_path: Path) -> dict[str, Any]:
    latest = load_latest(queue_path)
    counts: dict[str, int] = {}
    for issue in latest.values():
        status = str(issue.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema": "monitor_sparta.repair_queue.summary.v1",
        "queue_path": str(queue_path),
        "issue_count": len(latest),
        "counts_by_status": counts,
        "ready_issue_ids": [issue["issue_id"] for issue in latest.values() if selectable(issue)],
        "updated_at": utc_now(),
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=default_queue_path())
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--json", action="store_true", default=True)

    p_claim = sub.add_parser("claim")
    p_claim.add_argument("--run-id", required=True)
    p_claim.add_argument("--claimed-by", default="dba-auditor")

    p_update = sub.add_parser("update")
    p_update.add_argument("issue_json", type=Path)
    p_update.add_argument("--status", required=True)
    p_update.add_argument("--result", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "summary":
        print(json.dumps(summarize(args.queue), indent=2, sort_keys=True))
        return 0
    if args.cmd == "claim":
        issue = claim_one(args.queue, run_id=args.run_id, claimed_by=args.claimed_by)
        print(json.dumps({"claimed": bool(issue), "issue": issue}, indent=2, sort_keys=True))
        return 0 if issue else 3
    if args.cmd == "update":
        issue = _load_json(args.issue_json)
        result = _load_json(args.result) if args.result else None
        updated = update_issue(args.queue, issue, status=args.status, result=result)
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
