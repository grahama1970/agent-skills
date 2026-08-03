#!/usr/bin/env python3
"""
Structured Dewey R3 diagnostics helpers for monitor_sparta.py repair-cycle.

This module is intentionally small, dependency-free, and safe to import from the
large brownfield monitor_sparta.py. It does not mutate SPARTA data. It only
normalizes health/repair-cycle receipts so Dewey can see why a completed
repair-cycle did or did not move monitor-sparta health dimensions.

R3 contract choice: Option B.
- qra_coverage_per_control is operator/review-gated and remains unfixable by
  Dewey's nightly database repair loop.
- repair-cycle must not silently launch unbounded create-qras workers for that
  dimension by default.
- it should emit an explicit skipped/operator_lane step instead.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

UNFIXABLE_BY_DEWEY: Set[str] = {
    "sparta_explorer_page_purpose",
    "qra_coverage_per_control",
}

REPAIRABLE_BY_REPAIR_CYCLE: Set[str] = {
    "embedding_gaps",
    "description_completeness",
    "inline_embedding_policy",
}

QRA_OPERATOR_REQUIRED_DIMENSIONS: Set[str] = {
    "qra_coverage_per_control",
}

_KV_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_\-]*)=(?P<value>[^\s,;]+)")
_NUMERIC_SUFFIX_RE = re.compile(r"(?P<count>\d+)\s*(?:missing|failed|gaps?|records?|controls?|docs?)", re.I)


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return int(value)
    return None


def parse_kv_tail(text: str | None) -> Dict[str, Any]:
    """Parse simple key=value metrics from stdout/stderr tails.

    Example:
        processed=200 synced=200 dropped=200 resume_offset=200
    """
    metrics: Dict[str, Any] = {}
    if not text:
        return metrics
    for match in _KV_RE.finditer(text):
        key = match.group("key").replace("-", "_")
        raw = match.group("value").strip().strip('"\'')
        value = _as_int(raw)
        metrics[key] = raw if value is None else value
    return metrics


def failed_dimensions(health: Mapping[str, Any] | None) -> List[str]:
    """Extract failed dimension names from common monitor-sparta JSON shapes."""
    if not isinstance(health, Mapping):
        return []
    candidates: List[str] = []
    direct = health.get("failed_dimensions")
    if isinstance(direct, Sequence) and not isinstance(direct, (str, bytes)):
        candidates.extend(str(x) for x in direct if x)

    for key in ("dimensions", "checks", "health_dimensions", "results"):
        node = health.get(key)
        if isinstance(node, Mapping):
            for dim, value in node.items():
                if _dimension_failed(value):
                    candidates.append(str(dim))
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for item in node:
                if isinstance(item, Mapping):
                    name = item.get("dimension") or item.get("id") or item.get("name") or item.get("key")
                    if name and _dimension_failed(item):
                        candidates.append(str(name))
    # Preserve first-seen order while removing duplicates.
    out: List[str] = []
    seen: Set[str] = set()
    for dim in candidates:
        if dim not in seen:
            seen.add(dim)
            out.append(dim)
    return out


def _dimension_failed(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"fail", "failed", "failing", "missing", "incomplete", "error"}
    if isinstance(value, bool):
        return not value
    if isinstance(value, Mapping):
        for key in ("ok", "passed", "pass"):
            if key in value and isinstance(value[key], bool):
                return not value[key]
        status = str(value.get("status") or value.get("result") or "").lower()
        if status in {"fail", "failed", "failing", "missing", "incomplete", "error"}:
            return True
        if status in {"ok", "pass", "passed", "skipped", "not_applicable"}:
            return False
        for key in ("failed", "missing", "missing_count", "failed_count", "gap_count", "remaining", "count"):
            if key in value:
                val = _as_int(value.get(key))
                if val is not None and val > 0:
                    return True
    return False


def dimension_node(health: Mapping[str, Any] | None, dimension: str) -> Any:
    if not isinstance(health, Mapping):
        return None
    for key in ("dimensions", "checks", "health_dimensions", "results"):
        node = health.get(key)
        if isinstance(node, Mapping) and dimension in node:
            return node[dimension]
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for item in node:
                if isinstance(item, Mapping):
                    name = item.get("dimension") or item.get("id") or item.get("name") or item.get("key")
                    if name == dimension:
                        return item
    return None


def dimension_count(health: Mapping[str, Any] | None, dimension: str) -> Optional[int]:
    """Best-effort affected/eligible count extraction for a dimension."""
    node = dimension_node(health, dimension)
    if isinstance(node, Mapping):
        for key in (
            "eligible_count",
            "missing_count",
            "failed_count",
            "gap_count",
            "remaining",
            "affected_count",
            "count",
            "total_missing",
            "missing",
            "failed",
        ):
            val = _as_int(node.get(key))
            if val is not None:
                return val
        for key in ("message", "reason", "summary", "details"):
            text = node.get(key)
            if isinstance(text, str):
                found = _NUMERIC_SUFFIX_RE.search(text)
                if found:
                    return int(found.group("count"))
    elif isinstance(node, str):
        found = _NUMERIC_SUFFIX_RE.search(node)
        if found:
            return int(found.group("count"))

    # Some repair-cycle receipts only expose failed_dimensions. That proves the
    # dimension failed but not how many rows were affected.
    if dimension in failed_dimensions(health):
        return None
    return 0


def health_status(health: Mapping[str, Any] | None, dimension: str) -> str:
    return "failed" if dimension in failed_dimensions(health) else "passed"


def changed_count_from_embed_metrics(metrics: Mapping[str, Any]) -> Optional[int]:
    """Infer created/updated embeddings from migration script counters.

    Existing output uses processed/synced/dropped. When all processed documents
    are dropped as already present in Qdrant, the health needle did not move.
    """
    for key in ("changed", "changed_count", "created", "created_count", "inserted", "new_embeddings"):
        val = _as_int(metrics.get(key))
        if val is not None:
            return max(val, 0)
    synced = _as_int(metrics.get("synced"))
    dropped = _as_int(metrics.get("dropped"))
    if synced is not None and dropped is not None:
        return max(synced - dropped, 0)
    processed = _as_int(metrics.get("processed"))
    if processed is not None and dropped is not None:
        return max(processed - dropped, 0)
    return None


def build_embed_step_diagnostics(
    step: Mapping[str, Any] | None,
    baseline_health: Mapping[str, Any] | None,
    after_health: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a normalized diagnostics object for the embedding repair lane."""
    source = dict(step or {})
    tail = "\n".join(
        str(source.get(k) or "")
        for k in ("stdout_tail", "stderr_tail", "stdout", "stderr")
        if source.get(k)
    )
    metrics = parse_kv_tail(tail)
    eligible = source.get("eligible_count")
    if eligible is None:
        eligible = dimension_count(baseline_health, "embedding_gaps")
    changed = source.get("changed_count")
    if changed is None:
        changed = changed_count_from_embed_metrics(metrics)

    processed = _as_int(metrics.get("processed")) or 0
    dropped = _as_int(metrics.get("dropped")) or 0
    synced = _as_int(metrics.get("synced")) or 0
    skip_reason = source.get("skip_reason")
    mismatch = False
    debug_hint: Optional[str] = None

    if changed == 0 and processed > 0 and dropped >= processed:
        skip_reason = skip_reason or "all_processed_documents_already_present_in_qdrant"
        if health_status(after_health or baseline_health, "embedding_gaps") == "failed":
            mismatch = True
            debug_hint = (
                "embedding_gaps still fails even though the embed batch dropped every processed doc; "
                "compare health-check eligible IDs with migrate_arango_embeddings_to_qdrant candidate query."
            )
    elif processed == 0 and eligible not in (None, 0):
        skip_reason = skip_reason or "no_embed_candidates_returned_for_failed_health_dimension"
        mismatch = True
        debug_hint = (
            "health reports embedding gaps but embed migration found no candidates; check collection/filter mismatch."
        )
    elif changed in (None, 0):
        skip_reason = skip_reason or "no_embedding_records_changed"

    out = dict(source)
    out.update(
        {
            "id": source.get("id", "sparta_qdrant_embed_batch"),
            "eligible_count": eligible,
            "changed_count": changed,
            "skip_reason": skip_reason,
            "embed_metrics": metrics,
            "health_dimension": "embedding_gaps",
            "health_after_status": health_status(after_health or baseline_health, "embedding_gaps"),
            "health_embed_mismatch": mismatch,
        }
    )
    if debug_hint:
        out["debug_hint"] = debug_hint
    if synced or dropped or processed:
        out["processed_count"] = processed
        out["synced_count"] = synced
        out["dropped_count"] = dropped
    return out


def compare_dimension(before_health: Mapping[str, Any] | None, after_health: Mapping[str, Any] | None, dimension: str) -> Dict[str, Any]:
    before = health_status(before_health, dimension)
    after = health_status(after_health, dimension)
    before_count = dimension_count(before_health, dimension)
    after_count = dimension_count(after_health, dimension)
    if before == "failed" and after == "passed":
        result = "succeeded"
    elif before == "failed" and after == "failed":
        result = "stuck"
    elif before == "passed" and after == "failed":
        result = "regressed"
    elif before == "passed" and after == "passed":
        result = "unchanged_pass"
    else:
        result = "unknown"
    changed_count = None
    if before_count is not None and after_count is not None:
        changed_count = max(before_count - after_count, 0)
    return {
        "dimension": dimension,
        "before_status": before,
        "after_status": after,
        "result": result,
        "eligible_count": before_count,
        "affected_count_before": before_count,
        "affected_count_after": after_count,
        "changed_count": changed_count,
        "skip_reason": _skip_reason_for_dimension(dimension, result, before_count, after_count),
    }


def _skip_reason_for_dimension(dimension: str, result: str, before_count: Optional[int], after_count: Optional[int]) -> Optional[str]:
    if dimension in UNFIXABLE_BY_DEWEY:
        return "operator_review_required" if dimension == "qra_coverage_per_control" else "not_repairable_by_monitor_sparta"
    if result == "stuck" and before_count is None:
        return "dimension_still_failing_count_unreported"
    if result == "stuck" and before_count == after_count:
        return "no_records_changed"
    if result == "unchanged_pass":
        return "dimension_not_failing_before_fix"
    return None


def build_health_fix_diagnostics(
    before_health: Mapping[str, Any] | None,
    after_health: Mapping[str, Any] | None,
    attempted_dimensions: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Summarize health --fix impact dimension-by-dimension."""
    dims: List[str]
    if attempted_dimensions is None:
        dims = failed_dimensions(before_health)
    else:
        dims = list(dict.fromkeys(str(d) for d in attempted_dimensions))
    if not dims:
        dims = failed_dimensions(after_health)

    per_dim = [compare_dimension(before_health, after_health, dim) for dim in dims]
    succeeded = sum(1 for item in per_dim if item["result"] == "succeeded")
    stuck = [item["dimension"] for item in per_dim if item["result"] == "stuck"]
    skipped = [item["dimension"] for item in per_dim if item.get("skip_reason")]

    eligible_counts = [item.get("eligible_count") for item in per_dim if item.get("eligible_count") is not None]
    changed_counts = [item.get("changed_count") for item in per_dim if item.get("changed_count") is not None]

    if not per_dim:
        status = "skipped"
        skip_reason = "no_failed_dimensions_before_fix"
    elif succeeded:
        status = "succeeded" if succeeded == len(per_dim) else "partial"
        skip_reason = None
    elif stuck:
        status = "attempted_no_progress"
        skip_reason = "all_attempted_dimensions_still_failing"
    else:
        status = "skipped"
        skip_reason = "no_repairable_dimensions_attempted"

    return {
        "id": "monitor_health_fix",
        "status": status,
        "eligible_count": sum(eligible_counts) if eligible_counts else None,
        "changed_count": sum(changed_counts) if changed_counts else 0,
        "skip_reason": skip_reason,
        "per_dimension_results": per_dim,
        "stuck_dimensions": stuck,
        "skipped_dimensions": skipped,
    }


def should_skip_qra_repair_lane(failing_dimensions: Iterable[str] | None) -> bool:
    dims = set(failing_dimensions or [])
    return bool(dims & QRA_OPERATOR_REQUIRED_DIMENSIONS)


def qra_operator_lane_step(
    baseline_health: Mapping[str, Any] | None,
    *,
    reason: str = "operator_review_required",
    operator_queue_path: str | None = None,
) -> Dict[str, Any]:
    """Return the explicit skipped step replacing unbounded create-qras launch."""
    return {
        "id": "qra_coverage_operator_lane",
        "ok": True,
        "status": "skipped",
        "contract": "Option B: qra_coverage_per_control is operator/review-gated, not Dewey-repairable",
        "dimension": "qra_coverage_per_control",
        "eligible_count": dimension_count(baseline_health, "qra_coverage_per_control"),
        "changed_count": 0,
        "skip_reason": reason,
        "operator_queue_path": operator_queue_path,
        "debug_hint": (
            "Do not launch create_qras_backfill from Dewey repair-cycle by default. "
            "Queue/review QRA generation through the operator lane, then rerun health --json."
        ),
    }


def summarize_worker_wait(
    wait_result: Mapping[str, Any] | None,
    *,
    started_workers: Sequence[Mapping[str, Any]] | None = None,
    wait_started_at: float | None = None,
    wait_finished_at: float | None = None,
) -> Dict[str, Any]:
    """Normalize monitor worker wait receipts.

    This does not block. It reports whether workers were seen, completed, timed
    out, or remain running, and preserves diagnostic paths for follow-up.
    """
    wait = dict(wait_result or {})
    workers = list(started_workers or wait.get("workers") or [])
    now = time.time()
    started_at = wait_started_at or wait.get("wait_started_at") or now
    finished_at = wait_finished_at or wait.get("wait_finished_at") or now
    timed_out = bool(wait.get("timed_out"))
    still_running = bool(wait.get("create_qras_running") or wait.get("still_running"))
    completed = bool(wait.get("completed")) or (bool(workers) and not timed_out and not still_running and bool(wait.get("ok", True)))

    pid_files: List[str] = []
    log_paths: List[str] = []
    pids: List[int] = []
    for worker in workers:
        if not isinstance(worker, Mapping):
            continue
        for key in ("pid_file", "pid_path"):
            if worker.get(key):
                pid_files.append(str(worker[key]))
        for key in ("log_path", "stdout_path", "stderr_path"):
            if worker.get(key):
                log_paths.append(str(worker[key]))
        pid = _as_int(worker.get("pid"))
        if pid is not None:
            pids.append(pid)

    return {
        "ok": bool(wait.get("ok", not timed_out)),
        "worker_count": len(workers),
        "pids": pids,
        "pid_files": pid_files,
        "log_paths": log_paths,
        "waited_s": wait.get("waited_s", max(0, int(finished_at - started_at))),
        "timed_out": timed_out,
        "completed": completed,
        "still_running": still_running,
        "status": "timed_out" if timed_out else ("still_running" if still_running else ("completed" if completed else "no_workers")),
    }


def enrich_repair_cycle_receipt(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    """Add R3 diagnostics to an existing repair-cycle receipt.

    This is useful as a final normalization call at the end of monitor_sparta.py
    repair_cycle(), and for isolated tests against captured repair-cycle JSON.
    """
    out: Dict[str, Any] = deepcopy(dict(receipt))
    baseline = out.get("baseline") or out.get("baseline_health") or {}
    final = out.get("final") or out.get("final_health") or {}
    post_fix = out.get("post_fix") or out.get("after_fix") or out.get("health_after_fix") or None
    if post_fix is None:
        # Some current receipts place the post-health-fix health summary inside
        # the monitor_health_fix step. Use that when present; otherwise fall
        # back to final health for diagnostic enrichment.
        for step in out.get("steps", []) or []:
            if isinstance(step, Mapping) and step.get("id") == "monitor_health_fix" and isinstance(step.get("summary"), Mapping):
                post_fix = step.get("summary")
                break
    post_fix = post_fix or final

    enriched_steps: List[Dict[str, Any]] = []
    saw_qra_step = False
    for step in out.get("steps", []) or []:
        if not isinstance(step, Mapping):
            enriched_steps.append({"id": "unknown_step", "raw_step": step})
            continue
        sid = str(step.get("id") or "")
        if sid == "sparta_qdrant_embed_batch":
            enriched_steps.append(build_embed_step_diagnostics(step, baseline, post_fix))
        elif sid == "monitor_health_fix":
            diag = dict(step)
            fix_diag = build_health_fix_diagnostics(baseline, step.get("summary") if isinstance(step.get("summary"), Mapping) else post_fix)
            # Preserve original step fields while adding normalized R3 fields.
            for key, value in fix_diag.items():
                if key == "id":
                    continue
                diag[key] = value
            enriched_steps.append(diag)
        elif sid in {"create_qras_backfill", "qra_coverage_operator_lane"}:
            saw_qra_step = True
            if sid == "create_qras_backfill":
                diag = dict(step)
                diag.setdefault("dimension", "qra_coverage_per_control")
                diag.setdefault("eligible_count", dimension_count(baseline, "qra_coverage_per_control"))
                diag.setdefault("changed_count", 0)
                diag["contract_violation"] = True
                diag["skip_reason"] = "qra_coverage_per_control_should_use_operator_lane_not_default_worker"
                diag["debug_hint"] = (
                    "R3 chooses Option B. Replace this default create_qras_backfill launch with "
                    "qra_operator_lane_step unless an explicit human/operator QRA run is requested."
                )
                enriched_steps.append(diag)
            else:
                enriched_steps.append(dict(step))
        else:
            diag = dict(step)
            diag.setdefault("eligible_count", None)
            diag.setdefault("changed_count", None)
            diag.setdefault("skip_reason", None)
            enriched_steps.append(diag)

    if should_skip_qra_repair_lane(failed_dimensions(baseline)) and not saw_qra_step:
        enriched_steps.append(qra_operator_lane_step(baseline))
    out["steps"] = enriched_steps

    if out.get("worker_wait") is not None:
        out["worker_wait"] = summarize_worker_wait(out.get("worker_wait"), started_workers=out.get("started_workers") or [])

    before_failed = failed_dimensions(baseline)
    final_failed = failed_dimensions(final)
    out["r3_diagnostics"] = {
        "contract": "Option B: QRA coverage is operator/review-gated and remains unfixable by Dewey",
        "unfixable_by_dewey": sorted(UNFIXABLE_BY_DEWEY),
        "repairable_by_repair_cycle": sorted(REPAIRABLE_BY_REPAIR_CYCLE),
        "baseline_failed_dimensions": before_failed,
        "final_failed_dimensions": final_failed,
        "improved_dimensions": [d for d in before_failed if d not in final_failed],
        "stuck_dimensions": [d for d in before_failed if d in final_failed],
        "regressed_dimensions": [d for d in final_failed if d not in before_failed],
        "remaining_unfixable_dimensions": [d for d in final_failed if d in UNFIXABLE_BY_DEWEY],
    }
    return out


def write_operator_manifest_entry(
    path: str | os.PathLike[str],
    *,
    session_id: str,
    baseline_health: Mapping[str, Any] | None,
    reason: str = "qra_coverage_per_control requires operator/reviewer lane",
) -> Dict[str, Any]:
    """Append a JSONL operator-lane entry for review-gated QRA coverage.

    The caller owns deciding the session directory. This helper creates parent
    directories and returns the entry it wrote.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "type": "operator_lane",
        "session_id": session_id,
        "dimension": "qra_coverage_per_control",
        "reason": reason,
        "eligible_count": dimension_count(baseline_health, "qra_coverage_per_control"),
        "created_at_epoch_s": int(time.time()),
        "contract": "Option B",
        "next_action": "Run bounded QRA generation/review outside Dewey repair-cycle, then rerun monitor-sparta health --json.",
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


__all__ = [
    "UNFIXABLE_BY_DEWEY",
    "REPAIRABLE_BY_REPAIR_CYCLE",
    "QRA_OPERATOR_REQUIRED_DIMENSIONS",
    "build_embed_step_diagnostics",
    "build_health_fix_diagnostics",
    "changed_count_from_embed_metrics",
    "compare_dimension",
    "dimension_count",
    "enrich_repair_cycle_receipt",
    "failed_dimensions",
    "parse_kv_tail",
    "qra_operator_lane_step",
    "should_skip_qra_repair_lane",
    "summarize_worker_wait",
    "write_operator_manifest_entry",
]
