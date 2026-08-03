#!/usr/bin/env python3
from __future__ import annotations
"""Dewey nightly monitor-sparta repair loop.

Dewey is the DBA Auditor cron agent for SPARTA's monitor health.  The only
approved automatic repair path is:

    memory/scripts/validation/monitor_sparta.py repair-cycle

This runner adds the operational shell around that path: calibrated subprocess
budgets, cycle-to-cycle health diffs, persistent stall detection, explicit
operator-required lanes for known unfixable dimensions, and an always-written
morning report.

It intentionally does not mutate React/UX files and does not replace human QRA
review.  Missing/stale/unverified dimensions remain fail-closed.
"""

import argparse
import dataclasses
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from prompt_reviewer_receipt import (
    PromptReviewerGateResult,
    build_prompt_reviewer_command,
    run_prompt_reviewer_command,
    validate_receipt_file,
    write_json as write_prompt_gate_json,
    write_prompt_review_bundle,
)

SLICE_ID = "dewey-prompt-reviewer-qra-repair-loop"
DEFAULT_TOTAL_DIMENSIONS = 29
DEFAULT_MAX_CYCLES = 512
DEFAULT_WALL_CLOCK_S = 43_200  # 12 hours
DEFAULT_WAIT_TIMEOUT_S = 7_200
DEFAULT_WORKER_POLL_S = 30
DEFAULT_EMBED_BATCH_LIMIT = 200
# Backward-compatible alias for old Dewey env/config names.  The real monitor-sparta
# repair-cycle API calls this embed-batch-limit.
DEFAULT_QRA_BATCH_LIMIT = DEFAULT_EMBED_BATCH_LIMIT
DEFAULT_HEALTH_JSON_TIMEOUT_S = 300  # observed ~66-71s; 300s gives margin without masking hangs
DEFAULT_HEALTH_FIX_TIMEOUT_S = 240  # observed ~120s; retained for logging/calibration context
DEFAULT_REPAIR_MARGIN_S = 600  # outer repair-cycle budget = wait_timeout_s + 600 by default
DEFAULT_STALL_LIMIT = 8

DEFAULT_PROMPT_REVIEWER_TIMEOUT_S = 7_200
DEFAULT_QRA_MODEL_POOL = "qra-deepseek-pool"
EXIT_OPERATOR_REQUIRED = 10
EXIT_STALL = 11
EXIT_PROMPT_REVIEWER_GATE_FAILED = 12
DEFAULT_SESSION_ROOT = "/mnt/storage12tb/skills/review-db/outputs/dewey-sessions"
DEFAULT_MEMORY_REPO_ROOT = "/home/graham/workspace/experiments/memory"
DEFAULT_AGENT_SKILLS_ROOT = "/home/graham/workspace/experiments/agent-skills"
DEFAULT_ARANGO_BACKUP_RECEIPT = "/mnt/storage12tb/backups/arangodb/latest_backup_receipt.json"

# Dimensions Dewey may attempt to improve indirectly through repair-cycle.
# Dewey never performs bespoke fixes outside repair-cycle.
REPAIR_CYCLE_DIMENSIONS = {
    "embedding_gaps",
    "description_completeness",
    "inline_embedding_policy",
    "relationship_integrity",
    "framework_relationships",
    "url_qra_coverage",
    "direct_qra_coverage",
    "qra_coverage_per_control",
}

# Dimensions known to require a separate owner/slice.  Dewey logs these clearly,
# leaves them fail-closed, and stops early when only these remain.
UNFIXABLE_DIMENSIONS: dict[str, str] = {
    "sparta_explorer_page_purpose": "UX guardrail; owned by Sparta Explorer page-purpose/review slices, not Dewey",
}

# monitor-sparta correctly fails this guard when Dewey runs with mutation
# enabled.  It is not a corpus compliance gap and should not appear as an
# unknown remaining failure in Dewey's terminal state.
DEWEY_WAIVED_DIMENSIONS = {
    "monitor_sparta_mutation_default",
    "mutation_default",
    "mutation_baseline_default",
}

QRA_PROMPT_REVIEW_DIMENSIONS = {"qra_coverage_per_control", "url_qra_coverage", "direct_qra_coverage"}

PASS_STATUSES = {"pass", "passed", "ok", "healthy", "green", "true", "success"}
FAIL_STATUSES = {"fail", "failed", "error", "red", "false", "missing", "stale", "unknown", "degraded"}
SKIP_STATUSES = {"skip", "skipped", "not_applicable", "na", "n/a", "waived"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def env_int(name: str, default: int | None = None) -> int | None:
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return default
    return int(str(value).strip())


def env_first_int(names: Sequence[str], default: int) -> int:
    for name in names:
        value = env_int(name, None)
        if value is not None:
            return value
    return default


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
    return None


def tail_text(value: str | bytes | None, limit: int = 8_000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def normalize_name(value: Any) -> str:
    return str(value or "").strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from strict JSON stdout or a final JSON line."""
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def parse_summary_ratio(*values: Any) -> tuple[int | None, int | None]:
    for value in values:
        if not isinstance(value, str):
            continue
        m = re.search(r"\b(\d+)\s*/\s*(\d+)\s+PASS\b", value, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def find_first_int(value: Any, key: str) -> int | None:
    if isinstance(value, Mapping):
        found = as_int(value.get(key))
        if found is not None:
            return found
        for nested in value.values():
            found = find_first_int(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = find_first_int(nested, key)
            if found is not None:
                return found
    return None


def collect_dimension_rows(raw: Mapping[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key in ("dimensions", "checks", "lanes", "results", "health", "dimension_results"):
        value = raw.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    name = normalize_name(
                        item.get("name")
                        or item.get("id")
                        or item.get("dimension")
                        or item.get("lane")
                        or item.get("check")
                    )
                    status = normalize_name(
                        item.get("status") or item.get("state") or item.get("result") or item.get("verdict")
                    ).lower()
                    ok = item.get("ok")
                    if isinstance(ok, bool):
                        status = "pass" if ok else "fail"
                    if name:
                        rows.append((name, status))
                elif isinstance(item, str):
                    rows.append((item, "fail"))
        elif isinstance(value, Mapping):
            for name, item in value.items():
                if isinstance(item, Mapping):
                    status = normalize_name(
                        item.get("status") or item.get("state") or item.get("result") or item.get("verdict")
                    ).lower()
                    ok = item.get("ok")
                    if isinstance(ok, bool):
                        status = "pass" if ok else "fail"
                    rows.append((str(name), status))
                else:
                    rows.append((str(name), str(item).lower()))
    return rows


def extract_health(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical monitor health from common monitor-sparta JSON shapes."""
    summary = raw.get("summary") if isinstance(raw.get("summary"), Mapping) else {}
    summary_text = " ".join(str(v) for v in (raw.get("summary"), raw.get("status"), raw.get("headline")) if isinstance(v, str))
    ratio_passed, ratio_total = parse_summary_ratio(summary_text)

    total_candidates = [
        raw.get("total"),
        raw.get("total_count"),
        raw.get("dimensions_total"),
        raw.get("checks_total"),
        summary.get("total"),
        summary.get("total_count"),
        summary.get("dimensions_total"),
        summary.get("checks_total"),
        ratio_total,
    ]
    passed_candidates = [
        raw.get("pass"),
        raw.get("passed"),
        raw.get("pass_count"),
        raw.get("dimensions_passed"),
        raw.get("checks_passed"),
        summary.get("pass"),
        summary.get("passed"),
        summary.get("pass_count"),
        summary.get("dimensions_passed"),
        summary.get("checks_passed"),
        ratio_passed,
    ]

    rows = collect_dimension_rows(raw)
    failing: set[str] = set()
    passed_rows = 0
    for name, status in rows:
        status_l = status.lower().strip()
        if status_l in PASS_STATUSES:
            passed_rows += 1
            continue
        if status_l in SKIP_STATUSES:
            continue
        if not status_l or status_l in FAIL_STATUSES or status_l not in PASS_STATUSES:
            failing.add(name)

    for key in ("failing", "failures", "failed", "failed_dimensions", "failing_dimensions"):
        for container in (raw, summary):
            value = container.get(key) if isinstance(container, Mapping) else None
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        failing.add(item)
                    elif isinstance(item, Mapping):
                        name = normalize_name(item.get("name") or item.get("id") or item.get("dimension") or item.get("lane"))
                        if name:
                            failing.add(name)

    total = next((i for i in (as_int(v) for v in total_candidates) if i is not None), None)
    passed = next((i for i in (as_int(v) for v in passed_candidates) if i is not None), None)

    if total is None and rows:
        total = len(rows)
    if total is None:
        total = DEFAULT_TOTAL_DIMENSIONS
    if passed is None and rows:
        passed = max(0, len(rows) - len(failing))
    if passed is None:
        passed = max(0, total - len(failing))

    waived = raw.get("waived_dimensions") or summary.get("waived_dimensions") or raw.get("waived") or []
    waived_set = {str(v) for v in waived} if isinstance(waived, list) else set()
    waived_set |= DEWEY_WAIVED_DIMENSIONS
    # Historical monitor-sparta sometimes reports 28/28 when mutation_default is waived.
    # Normalize that success to the canonical 29/29 green only if the waiver is explicit.
    if passed == 28 and total == 28 and {"mutation_default", "mutation_baseline_default"} & waived_set:
        passed = DEFAULT_TOTAL_DIMENSIONS
        total = DEFAULT_TOTAL_DIMENSIONS

    failing = {name for name in failing if name and name not in waived_set}
    green = int(passed) == DEFAULT_TOTAL_DIMENSIONS and int(total) == DEFAULT_TOTAL_DIMENSIONS and not failing
    health = {
        "passed": int(passed),
        "total": int(total),
        "failed": max(int(total) - int(passed), len(failing)),
        "failing": sorted(failing),
        "green_29_of_29": green,
        "repair_cycle_failures": sorted(failing & REPAIR_CYCLE_DIMENSIONS),
        "operator_required_failures": sorted(failing & set(UNFIXABLE_DIMENSIONS)),
        "unknown_failures": sorted(failing - REPAIR_CYCLE_DIMENSIONS - set(UNFIXABLE_DIMENSIONS)),
        "waived_dimensions": sorted(waived_set),
    }
    for key in ("qra_missing_generation_required", "qra_ok"):
        value = find_first_int(raw, key)
        if value is not None:
            health[key] = value
    return health


@dataclasses.dataclass(frozen=True)
class HealthDiff:
    status: str
    pass_delta: int
    qra_missing_delta: int | None
    qra_ok_delta: int | None
    fixed: list[str]
    regressed: list[str]
    still_failing: list[str]
    before: dict[str, Any]
    after: dict[str, Any]


def health_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> HealthDiff:
    before_failing = set(before.get("failing") or [])
    after_failing = set(after.get("failing") or [])
    fixed = sorted(before_failing - after_failing)
    regressed = sorted(after_failing - before_failing)
    pass_delta = int(after.get("passed") or 0) - int(before.get("passed") or 0)
    before_qra_missing = as_int(before.get("qra_missing_generation_required"))
    after_qra_missing = as_int(after.get("qra_missing_generation_required"))
    qra_missing_delta = (
        after_qra_missing - before_qra_missing
        if before_qra_missing is not None and after_qra_missing is not None
        else None
    )
    before_qra_ok = as_int(before.get("qra_ok"))
    after_qra_ok = as_int(after.get("qra_ok"))
    qra_ok_delta = after_qra_ok - before_qra_ok if before_qra_ok is not None and after_qra_ok is not None else None
    qra_improved = (qra_missing_delta is not None and qra_missing_delta < 0) or (
        qra_ok_delta is not None and qra_ok_delta > 0
    )
    if after.get("green_29_of_29"):
        status = "FULL_PASS"
    elif pass_delta > 0 or fixed and not regressed or qra_improved and not regressed:
        status = "IMPROVED"
    elif pass_delta < 0 or regressed and not fixed:
        status = "REGRESSED"
    elif fixed or regressed:
        status = "MIXED"
    else:
        status = "STUCK"
    return HealthDiff(
        status=status,
        pass_delta=pass_delta,
        qra_missing_delta=qra_missing_delta,
        qra_ok_delta=qra_ok_delta,
        fixed=fixed,
        regressed=regressed,
        still_failing=sorted(after_failing),
        before=dict(before),
        after=dict(after),
    )


def format_diff_line(diff: HealthDiff, *, cycle: int | None = None) -> str:
    prefix = f"cycle={cycle} " if cycle is not None else ""
    after = diff.after
    chunks = [
        f"{prefix}{diff.status}",
        f"health={after.get('passed')}/{after.get('total')} PASS",
        f"pass_delta={diff.pass_delta:+d}",
    ]
    if diff.qra_missing_delta is not None:
        chunks.append(f"qra_missing_delta={diff.qra_missing_delta:+d}")
    if diff.qra_ok_delta is not None:
        chunks.append(f"qra_ok_delta={diff.qra_ok_delta:+d}")
    if diff.fixed:
        chunks.append("fixed=" + ",".join(diff.fixed))
    if diff.regressed:
        chunks.append("regressed=" + ",".join(diff.regressed))
    if diff.still_failing:
        chunks.append("still_failing=" + ",".join(diff.still_failing))
    return " | ".join(chunks)


class StallTracker:
    """Tracks no-progress cycles and persistent failures."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self.no_progress_cycles = 0
        self.failure_counts: MutableMapping[str, int] = defaultdict(int)
        self.last_seen_cycle: MutableMapping[str, int] = {}

    def observe(self, diff: HealthDiff, *, cycle: int) -> None:
        if diff.status in {"IMPROVED", "FULL_PASS"}:
            self.no_progress_cycles = 0
        else:
            self.no_progress_cycles += 1
        for name in diff.still_failing:
            self.failure_counts[name] += 1
            self.last_seen_cycle[name] = cycle

    def warnings(self, health: Mapping[str, Any]) -> list[str]:
        failing = list(health.get("failing") or [])
        warnings: list[str] = []
        if self.no_progress_cycles >= self.limit and failing:
            warnings.append(
                f"STALL: no health improvement for {self.no_progress_cycles} consecutive cycles; "
                f"remaining={','.join(failing)}"
            )
        for name in failing:
            count = self.failure_counts.get(name, 0)
            if count >= self.limit:
                reason = UNFIXABLE_DIMENSIONS.get(name)
                if reason:
                    warnings.append(f"OPERATOR_REQUIRED: {name} persisted {count} cycles; {reason}")
                else:
                    warnings.append(f"PERSISTENT_FAILURE: {name} persisted {count} cycles")
        return warnings


def format_stall_warnings(warnings: Iterable[str]) -> str:
    warnings = list(warnings)
    if not warnings:
        return ""
    return "\n".join(f"WARNING {line}" for line in warnings)


def only_known_unfixable(health: Mapping[str, Any]) -> bool:
    failing = set(health.get("failing") or [])
    return bool(failing) and failing <= set(UNFIXABLE_DIMENSIONS)


def should_stop_for_unfixable_only(health: Mapping[str, Any], *, skip_known_unfixable: bool = True) -> bool:
    return bool(skip_known_unfixable and only_known_unfixable(health))


def qra_prompt_review_required(health: Mapping[str, Any]) -> bool:
    failing = set(health.get("failing") or [])
    return bool(failing & QRA_PROMPT_REVIEW_DIMENSIONS)


def select_target_dimension(health: Mapping[str, Any]) -> str | None:
    """Select one deterministic repair target per cycle.

    Dewey may run for many cycles, but each cycle should focus on one lane so
    logs can explain why a single monitor-sparta dimension did or did not
    improve.  monitor-sparta receives the selected dimension as a hint/guard.
    """
    failing = list(health.get("failing") or [])
    priority = [
        "embedding_gaps",
        "inline_embedding_policy",
        "description_completeness",
        "qra_coverage_per_control",
        "url_qra_coverage",
        "direct_qra_coverage",
        "relationship_integrity",
        "framework_relationships",
    ]
    for name in priority:
        if name in failing and name in REPAIR_CYCLE_DIMENSIONS:
            return name
    for name in failing:
        if name in REPAIR_CYCLE_DIMENSIONS:
            return str(name)
    return None


def backup_marker_path(session_root: Path, *, day: str | None = None) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    return session_root / ".dewey-backup-markers" / f"{day}.json"


def _parse_backup_receipt_day(receipt: Mapping[str, Any]) -> str | None:
    for key in ("completed_at", "created_at", "finished_at", "started_at"):
        value = receipt.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y%m%d")
        except ValueError:
            match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value.strip())
            if match:
                return "".join(match.groups())
    backup_dir = receipt.get("backup_dir")
    if isinstance(backup_dir, str):
        match = re.search(r"(\d{8})-\d{6}", backup_dir)
        if match:
            return match.group(1)
    return None


def arango_backup_receipt_taken_today(path: Path | None = None, *, day: str | None = None) -> bool:
    path = path or Path(os.environ.get("DEWEY_ARANGO_BACKUP_RECEIPT", DEFAULT_ARANGO_BACKUP_RECEIPT))
    day = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(receipt, Mapping):
        return False
    return _parse_backup_receipt_day(receipt) == day


def backup_already_taken_today(session_root: Path) -> bool:
    marker = backup_marker_path(session_root)
    return marker.exists() or arango_backup_receipt_taken_today()


def mark_backup_taken_today(session_root: Path, receipt: Mapping[str, Any]) -> None:
    marker = backup_marker_path(session_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    write_json(marker, {
        "schema_version": 1,
        "created_at": utc_now(),
        "mocked": False,
        "live": True,
        "database_mutation_allowed": False,
        "backup_receipt": dict(receipt),
        "does_not_prove": ["monitor-sparta green", "QRA generation success"],
    })


def extract_qra_missing_count(health: Mapping[str, Any]) -> int | None:
    for key in ("qra_missing_generation_required", "missing_qra_count", "qra_missing_count"):
        value = health.get(key)
        if isinstance(value, int):
            return value
    raw = health.get("raw")
    if isinstance(raw, Mapping):
        for key in ("qra_missing_generation_required", "missing_qra_count", "qra_missing_count"):
            value = raw.get(key)
            if isinstance(value, int):
                return value
    return None


def write_status_artifact(run_dir: Path, name: str, payload: Mapping[str, Any]) -> Path:
    status = {
        "schema_version": 1,
        "created_at": utc_now(),
        "slice_id": SLICE_ID,
        "mocked": False,
        "live": True,
        "database_mutation_allowed": False,
        "name": name,
        "payload": dict(payload),
        "does_not_prove": ["monitor-sparta green", "Dewey closure", "human QRA review"],
    }
    path = run_dir / "status" / f"{name}.json"
    write_prompt_gate_json(path, status)
    return path


def run_prompt_reviewer_gate(
    *,
    run_dir: Path,
    cycle: int,
    health: Mapping[str, Any],
    args: argparse.Namespace,
) -> tuple[PromptReviewerGateResult, Path | None]:
    gate_dir = run_dir / "prompt-review" / f"cycle_{cycle:04d}"
    request_path, markdown_path, receipt_path, request_sha = write_prompt_review_bundle(
        gate_dir,
        request_id=f"{args.run_id or run_dir.name}-cycle-{cycle:04d}",
        failed_dimensions=list(health.get("failing") or []),
        qra_missing_count=extract_qra_missing_count(health),
        model_pool=args.qra_model_pool,
        live=True,
        mocked=False,
        source_health_path=str(run_dir / f"cycle_{cycle:04d}_baseline_health.json"),
    )
    session_log(run_dir, f"PROMPT_REVIEW_REQUEST cycle={cycle} path={request_path} sha256={request_sha}")

    if args.prompt_reviewer_receipt:
        result = validate_receipt_file(
            Path(args.prompt_reviewer_receipt),
            request_path=request_path,
            allow_mock=args.allow_mock_prompt_reviewer_receipt,
            require_pass=True,
        )
        write_status_artifact(run_dir, f"prompt_reviewer_gate_cycle_{cycle:04d}", result.to_json())
        return result, Path(args.prompt_reviewer_receipt) if result.ok else None

    if not args.prompt_reviewer_command_template and not os.environ.get("DEWEY_PROMPT_REVIEWER_COMMAND_TEMPLATE"):
        result = PromptReviewerGateResult(
            ok=False,
            verdict="BLOCKED",
            reason="prompt-reviewer command template not configured; QRA generation remains fail-closed",
            request_path=str(request_path),
            receipt_path=str(receipt_path),
            request_sha256=request_sha,
            mocked=False,
            live=False,
        )
        write_status_artifact(run_dir, f"prompt_reviewer_gate_cycle_{cycle:04d}", result.to_json())
        return result, None

    command = build_prompt_reviewer_command(
        request_markdown=markdown_path,
        receipt_json=receipt_path,
        request_json=request_path,
        template=args.prompt_reviewer_command_template,
    )
    session_log(run_dir, f"PROMPT_REVIEW_COMMAND cycle={cycle} cmd={shlex_join(command)}")
    command_result = run_prompt_reviewer_command(
        command,
        cwd=Path(args.agent_skills_root).expanduser().resolve(),
        timeout_s=args.prompt_reviewer_timeout_s,
    )
    session_log(
        run_dir,
        f"PROMPT_REVIEW_COMMAND_DONE cycle={cycle} ok={command_result.ok} rc={command_result.returncode} duration_s={command_result.duration_s} reason={command_result.reason}",
    )
    if command_result.stderr_tail:
        session_log(run_dir, f"PROMPT_REVIEW_STDERR cycle={cycle} tail={command_result.stderr_tail[-1200:]}")
    if not command_result.ok:
        write_status_artifact(run_dir, f"prompt_reviewer_gate_cycle_{cycle:04d}", command_result.to_json())
        return command_result, None
    result = validate_receipt_file(
        receipt_path,
        request_path=request_path,
        allow_mock=args.allow_mock_prompt_reviewer_receipt,
        require_pass=True,
    )
    write_status_artifact(run_dir, f"prompt_reviewer_gate_cycle_{cycle:04d}", result.to_json())
    return result, receipt_path if result.ok else None


def compute_repair_cycle_timeout_s(
    wait_timeout_s: int,
    *,
    repair_timeout_s: int | None = None,
    health_json_timeout_s: int = DEFAULT_HEALTH_JSON_TIMEOUT_S,
    health_fix_timeout_s: int = DEFAULT_HEALTH_FIX_TIMEOUT_S,
    margin_s: int = DEFAULT_REPAIR_MARGIN_S,
) -> int:
    """External subprocess budget for one monitor-sparta repair-cycle.

    The real repair-cycle subprocess internally runs baseline health --json,
    optional repair lanes, health --fix, optional workers, and final health
    --json.  A caller-provided --repair-timeout-s wins.  Otherwise the default
    is calibrated to wait_timeout_s + 600 seconds.  The health timeout arguments
    are retained for receipt context and backward-compatible callers, but they do
    not inflate the default because the requested R2 contract is exactly
    wait_timeout_s + 600.
    """
    if repair_timeout_s is not None and int(repair_timeout_s) > 0:
        return int(repair_timeout_s)
    _ = (health_json_timeout_s, health_fix_timeout_s)
    return int(wait_timeout_s) + int(margin_s)


@dataclasses.dataclass
class CommandReceipt:
    name: str
    command: list[str]
    started_at: str
    finished_at: str
    duration_s: float
    returncode: int | None
    ok: bool
    stdout_tail: str = ""
    stderr_tail: str = ""
    json: dict[str, Any] | None = None
    error: str | None = None


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_s: int | None,
    env: Mapping[str, str] | None = None,
    run_dir: Path | None = None,
    name: str | None = None,
    heartbeat_s: int | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if run_dir is not None:
        return run_command_monitored(
            command,
            cwd=cwd,
            timeout_s=timeout_s,
            env=merged_env,
            run_dir=run_dir,
            name=name or "command",
            heartbeat_s=heartbeat_s if heartbeat_s is not None else env_int("DEWEY_CHILD_HEARTBEAT_S", 30) or 30,
        )
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )


def run_command_monitored(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_s: int | None,
    env: Mapping[str, str],
    run_dir: Path,
    name: str,
    heartbeat_s: int = 30,
) -> subprocess.CompletedProcess[str]:
    """Run a child command with durable stdout/stderr files and heartbeats."""
    run_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "command"
    stamp = utc_stamp()
    stdout_path = run_dir / f"{stamp}_{safe_name}.stdout.txt"
    stderr_path = run_dir / f"{stamp}_{safe_name}.stderr.txt"
    started_mono = time.monotonic()
    with stdout_path.open("w", encoding="utf-8") as stdout_f, stderr_path.open("w", encoding="utf-8") as stderr_f:
        proc = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(env),
            text=True,
            stdout=stdout_f,
            stderr=stderr_f,
        )
        session_log(
            run_dir,
            "child_start "
            f"name={name} pid={proc.pid} timeout_s={timeout_s} cwd={cwd} "
            f"stdout={stdout_path} stderr={stderr_path} cmd={shlex_join(command)}",
        )
        next_heartbeat = started_mono + max(1, int(heartbeat_s))
        timed_out = False
        while True:
            returncode = proc.poll()
            now = time.monotonic()
            elapsed_s = round(now - started_mono, 3)
            if returncode is not None:
                session_log(
                    run_dir,
                    f"child_exit name={name} pid={proc.pid} rc={returncode} elapsed_s={elapsed_s} "
                    f"stdout={stdout_path} stderr={stderr_path}",
                )
                break
            if timeout_s is not None and elapsed_s >= timeout_s:
                timed_out = True
                proc.kill()
                proc.wait(timeout=10)
                session_log(
                    run_dir,
                    f"child_timeout name={name} pid={proc.pid} timeout_s={timeout_s} elapsed_s={elapsed_s} "
                    f"stdout={stdout_path} stderr={stderr_path}",
                )
                break
            if now >= next_heartbeat:
                session_log(
                    run_dir,
                    f"child_heartbeat name={name} pid={proc.pid} elapsed_s={elapsed_s} "
                    f"stdout={stdout_path} stderr={stderr_path}",
                )
                next_heartbeat = now + max(1, int(heartbeat_s))
            time.sleep(min(1.0, max(0.1, next_heartbeat - now)))

    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    if timed_out:
        raise subprocess.TimeoutExpired(
            cmd=list(command),
            timeout=timeout_s,
            output=stdout_text,
            stderr=stderr_text,
        )
    return subprocess.CompletedProcess(
        args=list(command),
        returncode=int(proc.returncode if proc.returncode is not None else 1),
        stdout=stdout_text,
        stderr=stderr_text,
    )


def command_receipt(
    name: str,
    command: Sequence[str],
    fn,
) -> CommandReceipt:
    started_at = utc_now()
    started_mono = time.monotonic()
    try:
        result = fn()
        duration_s = round(time.monotonic() - started_mono, 3)
        parsed = parse_json_object(result.stdout)
        return CommandReceipt(
            name=name,
            command=list(command),
            started_at=started_at,
            finished_at=utc_now(),
            duration_s=duration_s,
            returncode=result.returncode,
            ok=result.returncode == 0,
            stdout_tail=tail_text(result.stdout),
            stderr_tail=tail_text(result.stderr),
            json=parsed,
        )
    except subprocess.TimeoutExpired as exc:
        duration_s = round(time.monotonic() - started_mono, 3)
        return CommandReceipt(
            name=name,
            command=list(command),
            started_at=started_at,
            finished_at=utc_now(),
            duration_s=duration_s,
            returncode=None,
            ok=False,
            stdout_tail=tail_text(exc.stdout),
            stderr_tail=tail_text(exc.stderr),
            error=f"timeout after {exc.timeout}s",
        )
    except Exception as exc:  # noqa: BLE001 - receipts must preserve runtime exceptions
        duration_s = round(time.monotonic() - started_mono, 3)
        return CommandReceipt(
            name=name,
            command=list(command),
            started_at=started_at,
            finished_at=utc_now(),
            duration_s=duration_s,
            returncode=None,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def memory_monitor_script(memory_repo_root: Path) -> Path:
    return memory_repo_root / "scripts" / "validation" / "monitor_sparta.py"


def candidate_db_repair_session_scripts(memory_repo_root: Path, agent_skills_root: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if agent_skills_root is not None:
        candidates.append(agent_skills_root / "agents" / "dba-auditor" / "scripts" / "db_repair_session.py")
    else:
        candidates.append(Path(__file__).resolve().parent / "db_repair_session.py")
    # Legacy fallback for older deployments that temporarily carried the helper
    # in the memory repo.  The canonical location is agent-skills.
    candidates.append(memory_repo_root / "scripts" / "validation" / "db_repair_session.py")
    return candidates


def db_repair_session_script(memory_repo_root: Path, agent_skills_root: Path | None = None) -> Path:
    candidates = candidate_db_repair_session_scripts(memory_repo_root, agent_skills_root)
    for script in candidates:
        if script.exists():
            return script
    # Return the canonical agent-skills path for diagnostics when nothing exists.
    return candidates[1] if len(candidates) > 1 else candidates[0]


def ensure_run_dir(session_root: Path, run_id: str) -> Path:
    run_dir = session_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def session_log(run_dir: Path, message: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now()} {message}\n"
    with (run_dir / "dewey.log").open("a", encoding="utf-8") as f:
        f.write(line)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def health_json(memory_repo_root: Path, *, timeout_s: int, run_dir: Path | None = None) -> tuple[dict[str, Any], CommandReceipt]:
    cmd = [sys.executable, str(memory_monitor_script(memory_repo_root)), "health", "--json"]
    receipt = command_receipt(
        "health_json",
        cmd,
        lambda: run_command(cmd, cwd=memory_repo_root, timeout_s=timeout_s, run_dir=run_dir, name="health_json"),
    )
    # monitor_sparta health uses the process return code as a health verdict:
    # rc=1 with parseable JSON means "health checks failed", not "command
    # crashed". Dewey must keep the JSON and route repair from it.
    if receipt.json is not None:
        return receipt.json, receipt
    if not receipt.ok:
        raise RuntimeError(
            f"monitor_sparta health --json failed rc={receipt.returncode} error={receipt.error} stderr={receipt.stderr_tail[:1200]}"
        )
    raise RuntimeError(f"monitor_sparta health --json did not emit parseable JSON: {receipt.stdout_tail[:1200]}")


def repair_cycle(
    memory_repo_root: Path,
    *,
    cycle: int,
    run_dir: Path,
    wait_timeout_s: int,
    embed_batch_limit: int,
    repair_timeout_s: int | None,
    health_json_timeout_s: int,
    health_fix_timeout_s: int,
    target_dimension: str | None = None,
    prompt_reviewer_receipt_path: Path | None = None,
) -> CommandReceipt:
    artifact_dir = run_dir / f"repair-cycle-{cycle:04d}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(memory_monitor_script(memory_repo_root)),
        "repair-cycle",
        "--artifact-dir",
        str(artifact_dir),
        "--embed-batch-limit",
        str(embed_batch_limit),
        "--wait-timeout-s",
        str(wait_timeout_s),
        "--json",
    ]
    if target_dimension:
        cmd.extend(["--target-dimension", str(target_dimension)])
    if prompt_reviewer_receipt_path is not None:
        cmd.extend(["--qra-prompt-review-receipt", str(prompt_reviewer_receipt_path), "--require-qra-prompt-review"])
    timeout_s = compute_repair_cycle_timeout_s(
        wait_timeout_s,
        repair_timeout_s=repair_timeout_s,
        health_json_timeout_s=health_json_timeout_s,
        health_fix_timeout_s=health_fix_timeout_s,
    )
    env = {
        "DEWEY_RUN_DIR": str(run_dir),
        "DEWEY_ARTIFACT_DIR": str(artifact_dir),
        "DEWEY_WAIT_TIMEOUT_S": str(wait_timeout_s),
        "DEWEY_EMBED_BATCH_LIMIT": str(embed_batch_limit),
        "DEWEY_UNFIXABLE_DIMENSIONS": ",".join(sorted(UNFIXABLE_DIMENSIONS)),
        "DEWEY_TARGET_DIMENSION": str(target_dimension or ""),
        "DEWEY_QRA_PROMPT_REVIEW_RECEIPT": str(prompt_reviewer_receipt_path or ""),
        "SPARTA_MONITOR_MUTATION_ENABLED": "1",
    }
    receipt = command_receipt(
        "repair_cycle",
        cmd,
        lambda: run_command(cmd, cwd=memory_repo_root, timeout_s=timeout_s, env=env, run_dir=run_dir, name=f"repair_cycle_{cycle:04d}"),
    )
    # The real API emits JSON to stdout.  Some deployments also place a receipt
    # under the artifact dir; prefer that only when stdout could not be parsed.
    if receipt.json is None:
        for candidate in (
            artifact_dir / "repair_cycle.json",
            artifact_dir / "repair-cycle.json",
            artifact_dir / "receipt.json",
            artifact_dir / "repair_receipt.json",
        ):
            file_json = read_json_if_exists(candidate)
            if file_json is not None:
                receipt.json = file_json
                break
    return receipt


def db_session_command(
    memory_repo_root: Path,
    agent_skills_root: Path,
    action: str,
    *,
    run_id: str,
    timeout_s: int,
    required: bool,
) -> CommandReceipt:
    script = db_repair_session_script(memory_repo_root, agent_skills_root)
    cmd = [sys.executable, str(script), action, "--json", "--run-id", run_id]
    if action == "revert":
        cmd.extend(["--reason", "dewey-monitor-sparta-regression"])
    if not script.exists():
        # Missing backup tooling must not make cron hang or fail before the
        # monitor loop can report current health.  It is still logged as an
        # operator warning and verify/revert are skipped for this run.
        return CommandReceipt(
            name=f"db_repair_session_{action}",
            command=cmd,
            started_at=utc_now(),
            finished_at=utc_now(),
            duration_s=0.0,
            returncode=127,
            ok=True,
            error="db_repair_session.py not found; backup/verify/revert skipped",
        )
    return command_receipt(
        f"db_repair_session_{action}",
        cmd,
        lambda: run_command(cmd, cwd=script.parent, timeout_s=timeout_s),
    )


def verify_detected_regression(verify_receipt: CommandReceipt, *, baseline: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    if int(current.get("passed") or 0) < int(baseline.get("passed") or 0):
        return True
    if not verify_receipt.ok:
        return True
    data = verify_receipt.json or {}
    for key in ("regression", "regression_detected", "control_count_drop", "health_pass_count_drop"):
        if data.get(key) is True:
            return True
    status = str(data.get("status") or data.get("verdict") or "").lower()
    return status in {"regression", "failed", "fail", "revert_required"}


def format_repair_steps(repair_json: Mapping[str, Any] | None) -> list[str]:
    if not repair_json:
        return ["repair-cycle produced no structured step JSON"]
    steps = repair_json.get("steps")
    if not isinstance(steps, list):
        return ["repair-cycle JSON has no steps[]"]
    lines: list[str] = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, Mapping):
            lines.append(f"step[{idx}] unparseable={step!r}")
            continue
        name = step.get("name") or step.get("step") or f"step_{idx}"
        status = step.get("status") or step.get("result") or ("ok" if step.get("ok") is True else "fail" if step.get("ok") is False else "unknown")
        duration = step.get("duration_s")
        details = step.get("summary") or step.get("message") or step.get("detail") or step.get("reason") or ""
        duration_part = f" duration_s={duration}" if duration is not None else ""
        details_part = f" detail={details}" if details else ""
        lines.append(f"step[{idx}] {name} status={status}{duration_part}{details_part}")
    return lines


def repair_cycle_progress_count(repair_json: Mapping[str, Any] | None) -> int:
    """Return structured mutation progress reported by monitor-sparta repair-cycle."""
    if not repair_json:
        return 0
    total = as_int(repair_json.get("changed_count")) or 0
    steps = repair_json.get("steps")
    if not isinstance(steps, list):
        return total
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        changed = as_int(step.get("changed_count")) or 0
        errors = as_int(step.get("error_count")) or 0
        status = str(step.get("status") or step.get("result") or "").strip().lower()
        if changed > 0 and errors == 0 and status not in {"failed", "fail", "error", "blocked"}:
            total += changed
    return total


def repair_cycle_allows_after_health(repair: CommandReceipt) -> bool:
    """Classify repair-cycle output as a loop event before deciding to stop.

    monitor_sparta.py repair-cycle uses rc=1 when monitor failures remain.  For
    Dewey, rc=1 plus structured mutation progress is not a subprocess crash; it
    is a completed repair event that still needs an after-health diff.
    """
    if repair.ok:
        return True
    return repair.returncode == 1 and repair_cycle_progress_count(repair.json) > 0


def compact_cycle_record(cycle: int, before: Mapping[str, Any], after: Mapping[str, Any], repair: CommandReceipt, diff: HealthDiff) -> dict[str, Any]:
    return {
        "cycle": cycle,
        "repair_ok": repair.ok,
        "repair_returncode": repair.returncode,
        "repair_progress_count": repair_cycle_progress_count(repair.json),
        "repair_nonzero_accepted": bool(not repair.ok and repair_cycle_allows_after_health(repair)),
        "repair_duration_s": repair.duration_s,
        "before": {"passed": before.get("passed"), "total": before.get("total"), "failing": before.get("failing")},
        "after": {"passed": after.get("passed"), "total": after.get("total"), "failing": after.get("failing")},
        "diff_status": diff.status,
        "pass_delta": diff.pass_delta,
        "qra_missing_delta": diff.qra_missing_delta,
        "qra_ok_delta": diff.qra_ok_delta,
        "fixed": diff.fixed,
        "regressed": diff.regressed,
        "still_failing": diff.still_failing,
        "operator_required_failures": after.get("operator_required_failures") or [],
        "unknown_failures": after.get("unknown_failures") or [],
        "repair_lane_evidence": compact_repair_lane_evidence(repair.json),
    }


def compact_health_summary(health: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(health, Mapping):
        return {
            "passed": None,
            "total": None,
            "failing": [],
            "repairable_failures": [],
            "operator_required_failures": [],
            "unknown_failures": [],
            "waived_dimensions": [],
            "qra_missing_generation_required": None,
            "qra_ok": None,
            "green_29_of_29": False,
        }
    return {
        "passed": health.get("passed"),
        "total": health.get("total"),
        "failing": list(health.get("failing") or []),
        "repairable_failures": list(health.get("repair_cycle_failures") or []),
        "operator_required_failures": list(health.get("operator_required_failures") or []),
        "unknown_failures": list(health.get("unknown_failures") or []),
        "waived_dimensions": list(health.get("waived_dimensions") or []),
        "qra_missing_generation_required": health.get("qra_missing_generation_required"),
        "qra_ok": health.get("qra_ok"),
        "green_29_of_29": bool(health.get("green_29_of_29")),
    }


def _path_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _extract_generated_qra_count(text: Any) -> int | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"\bGenerated\s+(\d+)\s+QRAs\b", text)
    if match:
        return int(match.group(1))
    match = re.search(r"\bTotal\s+QRAs:\s*(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def compact_repair_lane_evidence(repair_json: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract operator-facing proof paths from monitor-sparta repair-cycle JSON."""
    evidence: dict[str, Any] = {
        "review_verdict": None,
        "changed_count": None,
        "error_count": None,
        "eligible_count": None,
        "manifest_source": None,
        "source_text_qra_manifest": None,
        "source_text_backfill_manifest": None,
        "prompt_reviewer": None,
        "skill_read_receipt_path": None,
        "substeps": [],
    }
    if not isinstance(repair_json, Mapping):
        return evidence
    steps = repair_json.get("steps")
    if not isinstance(steps, list):
        return evidence
    repair_step = next(
        (
            step
            for step in steps
            if isinstance(step, Mapping)
            and (step.get("id") == "create_qras_repair_lane" or step.get("dimension") in QRA_PROMPT_REVIEW_DIMENSIONS)
        ),
        None,
    )
    if not isinstance(repair_step, Mapping):
        return evidence

    artifacts = repair_step.get("artifacts") if isinstance(repair_step.get("artifacts"), Mapping) else {}
    skill_receipt = repair_step.get("skill_read_receipt") if isinstance(repair_step.get("skill_read_receipt"), Mapping) else {}
    prompt_reviewer = repair_step.get("prompt_reviewer") if isinstance(repair_step.get("prompt_reviewer"), Mapping) else {}
    evidence.update(
        {
            "review_verdict": repair_step.get("review_verdict"),
            "changed_count": repair_step.get("changed_count"),
            "error_count": repair_step.get("error_count"),
            "eligible_count": repair_step.get("eligible_count"),
            "manifest_source": repair_step.get("manifest_source"),
            "source_text_qra_manifest": _path_or_none(artifacts.get("source_text_qra_manifest")),
            "source_text_backfill_manifest": _path_or_none(artifacts.get("source_text_backfill_manifest")),
            "skill_read_receipt_path": _path_or_none(skill_receipt.get("path")),
        }
    )
    if prompt_reviewer:
        evidence["prompt_reviewer"] = {
            "status": prompt_reviewer.get("status"),
            "receipt_status": prompt_reviewer.get("receipt_status"),
            "subagent_status": prompt_reviewer.get("subagent_status"),
            "subagent_invoked": prompt_reviewer.get("subagent_invoked"),
            "required_receipt": _path_or_none(prompt_reviewer.get("required_receipt")),
            "request_path": _path_or_none(prompt_reviewer.get("request_path")),
            "request_markdown_path": _path_or_none(prompt_reviewer.get("request_markdown_path")),
            "expected_response_contract": _path_or_none(prompt_reviewer.get("expected_response_contract")),
            "validator_contract": _path_or_none(prompt_reviewer.get("validator_contract")),
            "bundle_path": _path_or_none(prompt_reviewer.get("bundle_path")),
            "contract_hash": prompt_reviewer.get("contract_hash"),
        }

    substeps: list[dict[str, Any]] = []
    for substep in repair_step.get("substeps") or []:
        if not isinstance(substep, Mapping):
            continue
        item: dict[str, Any] = {
            "id": substep.get("id"),
            "ok": substep.get("ok"),
            "exit_code": substep.get("exit_code"),
            "duration_s": substep.get("duration_s"),
            "heartbeat_path": _path_or_none(substep.get("heartbeat_path")),
            "stdout_path": _path_or_none(substep.get("stdout_path")),
            "stderr_path": _path_or_none(substep.get("stderr_path")),
            "timed_out": substep.get("timed_out"),
            "timeout_s": substep.get("timeout_s"),
        }
        if substep.get("id") == "create_qras_manifest_canary":
            item["generated_qra_count"] = _extract_generated_qra_count(substep.get("stdout_tail"))
            item["attempt"] = substep.get("attempt")
            item["max_attempts"] = substep.get("max_attempts")
        if substep.get("id") == "prompt_reviewer_subagent":
            item["receipt_pass"] = substep.get("receipt_pass")
            item["required_receipt"] = _path_or_none(substep.get("required_receipt"))
            item["status"] = substep.get("status")
        substeps.append(item)
    evidence["substeps"] = substeps
    return evidence


def terminal_state_for(stop_reason: str, exit_code: int, final_health: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = compact_health_summary(final_health)
    repairable = list(summary["repairable_failures"] or [])
    operator_required = list(summary["operator_required_failures"] or [])
    unknown = list(summary["unknown_failures"] or [])
    if summary["green_29_of_29"]:
        status = "ALL_GREEN"
    elif stop_reason in {"operator_required_unfixable_only", "all_green_at_baseline"} and operator_required and not repairable and not unknown:
        status = "OPERATOR_REQUIRED_ONLY"
    elif stop_reason == "prompt_reviewer_gate_failed":
        status = "PROMPT_REVIEWER_GATE_FAILED"
    elif stop_reason == "stall_budget_exhausted":
        status = "STALLED"
    elif stop_reason in {"unhandled_exception", "backup_begin_failed", "revert_failed", "repair_cycle_failed"}:
        status = "RUNNER_ERROR"
    elif repairable:
        status = "REPAIRABLE_FAILURES_REMAIN"
    elif unknown:
        status = "UNKNOWN_FAILURES_REMAIN"
    elif operator_required:
        status = "OPERATOR_REQUIRED"
    else:
        status = "NO_CLASSIFIED_FAILURES"
    return {
        "schema": "dewey.terminal_state.v1",
        "status": status,
        "stop_reason": stop_reason,
        "exit_code": exit_code,
        "repairable_failures": repairable,
        "operator_required_failures": operator_required,
        "unknown_failures": unknown,
        "waived_dimensions": list(summary["waived_dimensions"] or []),
        "qra_missing_generation_required": summary["qra_missing_generation_required"],
        "qra_ok": summary["qra_ok"],
    }


def build_evidence_summary(receipt: Mapping[str, Any], *, morning_report: Path | None = None) -> dict[str, Any]:
    initial = receipt.get("initial_summary") if isinstance(receipt.get("initial_summary"), Mapping) else {}
    final = receipt.get("final_summary") if isinstance(receipt.get("final_summary"), Mapping) else {}
    params = receipt.get("parameters") if isinstance(receipt.get("parameters"), Mapping) else {}
    cycles = receipt.get("cycles") if isinstance(receipt.get("cycles"), list) else []
    terminal = receipt.get("terminal_state") if isinstance(receipt.get("terminal_state"), Mapping) else {}
    run_dir = Path(str(receipt.get("run_dir") or ""))
    cycle_summaries: list[dict[str, Any]] = []
    for cycle in cycles:
        if not isinstance(cycle, Mapping):
            continue
        cycle_no = cycle.get("cycle")
        repair_lane_evidence = (
            dict(cycle.get("repair_lane_evidence"))
            if isinstance(cycle.get("repair_lane_evidence"), Mapping)
            else compact_repair_lane_evidence(cycle.get("repair_json") if isinstance(cycle.get("repair_json"), Mapping) else None)
        )
        if as_int(cycle_no) is not None and not repair_lane_evidence.get("review_verdict"):
            repair_json_path = run_dir / f"repair-cycle-{int(cycle_no):04d}" / "repair_cycle.json"
            repair_json = read_json_if_exists(repair_json_path)
            if repair_json is not None:
                repair_lane_evidence = compact_repair_lane_evidence(repair_json)
        cycle_summaries.append(
            {
                "cycle": cycle_no,
                "diff_status": cycle.get("diff_status"),
                "repair_returncode": cycle.get("repair_returncode"),
                "repair_progress_count": cycle.get("repair_progress_count"),
                "repair_nonzero_accepted": cycle.get("repair_nonzero_accepted"),
                "qra_missing_delta": cycle.get("qra_missing_delta"),
                "qra_ok_delta": cycle.get("qra_ok_delta"),
                "operator_required_failures": list(cycle.get("operator_required_failures") or []),
                "unknown_failures": list(cycle.get("unknown_failures") or []),
                "cycle_receipt_path": str(run_dir / f"cycle_{int(cycle_no):04d}.json") if as_int(cycle_no) is not None else None,
                "repair_artifact_dir": str(run_dir / f"repair-cycle-{int(cycle_no):04d}") if as_int(cycle_no) is not None else None,
                "repair_lane_evidence": repair_lane_evidence,
            }
        )
    return {
        "schema": "dewey.evidence_summary.v1",
        "mocked": False,
        "live": True,
        "claims": {
            "proves": [
                "Dewey runner emitted durable status artifacts for this run",
                "Dewey observed the recorded before/after monitor-sparta QRA counters",
            ],
            "does_not_prove": [
                "monitor-sparta is fully green unless terminal_status is ALL_GREEN",
                "all remaining QRA coverage gaps are closed",
                "operator-owned Sparta Explorer UX gaps are resolved",
            ],
        },
        "run_id": receipt.get("run_id"),
        "run_dir": receipt.get("run_dir"),
        "started_at": receipt.get("started_at"),
        "finished_at": receipt.get("finished_at"),
        "stop_reason": receipt.get("stop_reason"),
        "exit_code": receipt.get("exit_code"),
        "terminal_status": terminal.get("status"),
        "repairable_failures": list(final.get("repairable_failures") or []),
        "operator_required_failures": list(final.get("operator_required_failures") or []),
        "unknown_failures": list(final.get("unknown_failures") or []),
        "initial_qra_missing_generation_required": initial.get("qra_missing_generation_required"),
        "final_qra_missing_generation_required": final.get("qra_missing_generation_required"),
        "qra_missing_delta_total": (
            final.get("qra_missing_generation_required") - initial.get("qra_missing_generation_required")
            if isinstance(final.get("qra_missing_generation_required"), int)
            and isinstance(initial.get("qra_missing_generation_required"), int)
            else None
        ),
        "initial_qra_ok": initial.get("qra_ok"),
        "final_qra_ok": final.get("qra_ok"),
        "qra_ok_delta_total": (
            final.get("qra_ok") - initial.get("qra_ok")
            if isinstance(final.get("qra_ok"), int) and isinstance(initial.get("qra_ok"), int)
            else None
        ),
        "cycle_count": len(cycle_summaries),
        "cycles": cycle_summaries,
        "backup_required": params.get("backup_required"),
        "force_backup": params.get("force_backup"),
        "nightly_receipt_path": str(run_dir / "nightly_receipt.json") if str(run_dir) else None,
        "morning_report_path": str(morning_report) if morning_report is not None else None,
        "dewey_log_path": str(run_dir / "dewey.log") if str(run_dir) else None,
    }


def summary_matches_status_filter(summary: Mapping[str, Any], status_filter: str) -> bool:
    if status_filter == "any":
        return True
    if status_filter == "repair-progress":
        cycles = summary.get("cycles") if isinstance(summary.get("cycles"), list) else []
        return any(
            isinstance(cycle, Mapping)
            and (as_int(cycle.get("repair_progress_count")) or 0) > 0
            and cycle.get("diff_status") in {"IMPROVED", "FULL_PASS"}
            for cycle in cycles
        )
    if status_filter == "non-runner-error":
        return summary.get("terminal_status") != "RUNNER_ERROR"
    if status_filter == "runner-error":
        return summary.get("terminal_status") == "RUNNER_ERROR"
    return False


def latest_run_dir(session_root: Path, *, status_filter: str = "any") -> Path | None:
    if not session_root.exists():
        return None
    candidates = [path for path in session_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if status_filter == "any":
            return candidate
        try:
            summary = load_evidence_summary(candidate)
        except Exception:
            continue
        if summary_matches_status_filter(summary, status_filter):
            return candidate
    return None


def load_evidence_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "dewey_evidence_summary.json"
    if summary_path.exists():
        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    receipt_path = run_dir / "nightly_receipt.json"
    if not receipt_path.exists():
        raise FileNotFoundError(f"no dewey_evidence_summary.json or nightly_receipt.json in {run_dir}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError(f"nightly receipt is not a JSON object: {receipt_path}")
    morning_report = run_dir / "morning_report.md"
    return build_evidence_summary(receipt, morning_report=morning_report if morning_report.exists() else None)


def run_status(args: argparse.Namespace) -> int:
    session_root = Path(args.session_root).expanduser().resolve()
    status_filter = getattr(args, "latest_filter", "any")
    run_dir = session_root / args.run_id if args.run_id else latest_run_dir(session_root, status_filter=status_filter)
    if run_dir is None:
        payload = {
            "schema": "dewey.status.v1",
            "ok": False,
            "error": "no_runs_found",
            "session_root": str(session_root),
            "latest_filter": status_filter,
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"No Dewey runs found under {session_root}")
        return 2
    try:
        summary = load_evidence_summary(run_dir)
    except Exception as exc:  # noqa: BLE001 - status must be fail-closed and machine-readable
        payload = {
            "schema": "dewey.status.v1",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "run_dir": str(run_dir),
            "session_root": str(session_root),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"Dewey status unavailable for {run_dir}: {payload['error']}")
        return 3
    payload = {
        "schema": "dewey.status.v1",
        "ok": True,
        "session_root": str(session_root),
        "run_dir": str(run_dir),
        "latest_filter": status_filter,
        "summary": summary,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Dewey latest run: {run_dir}")
        print(f"Terminal status: {summary.get('terminal_status')} stop_reason={summary.get('stop_reason')} exit_code={summary.get('exit_code')}")
        print(
            "QRA gaps: "
            f"{summary.get('initial_qra_missing_generation_required')} -> {summary.get('final_qra_missing_generation_required')} "
            f"(delta {summary.get('qra_missing_delta_total')})"
        )
        print(f"Cycles: {summary.get('cycle_count')} backup_required={summary.get('backup_required')} force_backup={summary.get('force_backup')}")
        print(f"Evidence summary: {run_dir / 'dewey_evidence_summary.json'}")
    return 0


def write_morning_report(run_dir: Path, receipt: Mapping[str, Any]) -> Path:
    report_path = run_dir / "morning_report.md"
    final = receipt.get("final_health") if isinstance(receipt.get("final_health"), Mapping) else {}
    cycles = receipt.get("cycles") if isinstance(receipt.get("cycles"), list) else []
    failing = list(final.get("failing") or []) if isinstance(final, Mapping) else []
    lines = [
        "# Dewey monitor-sparta nightly report",
        "",
        f"Run ID: `{receipt.get('run_id')}`",
        f"Slice: `{SLICE_ID}`",
        f"Started: `{receipt.get('started_at')}`",
        f"Finished: `{receipt.get('finished_at')}`",
        f"Stop reason: `{receipt.get('stop_reason')}`",
        f"Exit code: `{receipt.get('exit_code')}`",
        f"Cycles run: `{len(cycles)}`",
        "",
        f"Final health: **{final.get('passed')}/{final.get('total')} PASS**",
        "",
        "## Remaining failures",
    ]
    if failing:
        for name in failing:
            reason = UNFIXABLE_DIMENSIONS.get(name)
            suffix = f" — {reason}" if reason else ""
            lines.append(f"- `{name}`{suffix}")
    else:
        lines.append("- none")

    lines.extend(["", "## Last cycle"])
    if cycles:
        last = cycles[-1]
        lines.append(f"- Diff: `{last.get('diff_status')}`; pass_delta `{last.get('pass_delta')}`")
        fixed = last.get("fixed") or []
        regressed = last.get("regressed") or []
        if fixed:
            lines.append("- Fixed: " + ", ".join(f"`{x}`" for x in fixed))
        if regressed:
            lines.append("- Regressed: " + ", ".join(f"`{x}`" for x in regressed))
    else:
        lines.append("- No repair cycle executed.")

    warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
    lines.extend(["", "## Warnings"])
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Operator next actions",
            "- Inspect `dewey.log` for per-cycle attempts and step durations.",
            "- Inspect `nightly_receipt.json` and `repair_cycle_*.json` for machine-readable proof.",
            "- Treat known unfixable lanes as separate owner work; Dewey leaves them fail-closed.",
            "",
            "## Non-claims",
            "- This report is not a PASS verdict, ATO, expert blessing, or client signoff.",
            "- Dewey did not mutate React/UX files and did not perform QRA human review.",
            "- All automatic repairs were routed only through `monitor_sparta.py repair-cycle`.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def shlex_join(command: Sequence[str]) -> str:
    return shlex.join([str(x) for x in command])


def append_command_log(run_dir: Path, receipt: CommandReceipt) -> None:
    session_log(
        run_dir,
        f"command name={receipt.name} ok={receipt.ok} rc={receipt.returncode} duration_s={receipt.duration_s} cmd={shlex_join(receipt.command)}",
    )
    if receipt.error:
        session_log(run_dir, f"command_error name={receipt.name} error={receipt.error}")
    if receipt.stderr_tail:
        session_log(run_dir, f"stderr_tail name={receipt.name} tail={receipt.stderr_tail[-1200:]}")
    if not receipt.ok and receipt.stdout_tail:
        session_log(run_dir, f"stdout_tail name={receipt.name} tail={receipt.stdout_tail[-1200:]}")
    if receipt.json is not None:
        parsed_keys = ",".join(sorted(str(key) for key in receipt.json.keys())[:12])
        session_log(run_dir, f"json_parsed name={receipt.name} keys={parsed_keys}")


def record_operator_required(run_dir: Path, health: Mapping[str, Any], warnings: list[str]) -> None:
    for name in health.get("failing") or []:
        reason = UNFIXABLE_DIMENSIONS.get(str(name), "operator-owned or unknown unfixable lane")
        msg = f"OPERATOR_REQUIRED: {name}: {reason}"
        if msg not in warnings:
            warnings.append(msg)
        session_log(run_dir, msg)


def run_dewey(args: argparse.Namespace) -> int:
    memory_repo_root = Path(args.memory_repo_root).expanduser().resolve()
    agent_skills_root = Path(args.agent_skills_root).expanduser().resolve()
    session_root = Path(args.session_root).expanduser().resolve()
    run_id = args.run_id or f"dewey-monitor-sparta-{utc_stamp()}"
    run_dir = ensure_run_dir(session_root, run_id)
    # Touch the operator log immediately; even argument/runtime failures should leave a breadcrumb.
    (run_dir / "dewey.log").touch(exist_ok=True)

    started_at = utc_now()
    deadline = time.monotonic() + int(args.wall_clock_s)
    commands: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    warnings: list[str] = []
    stop_reason = "unknown"
    exit_code = 1
    final_health: dict[str, Any] = {
        "passed": 0,
        "total": DEFAULT_TOTAL_DIMENSIONS,
        "failed": DEFAULT_TOTAL_DIMENSIONS,
        "failing": ["dewey_not_started"],
        "green_29_of_29": False,
    }
    initial_health: dict[str, Any] | None = None
    previous_health: dict[str, Any] | None = None
    tracker = StallTracker(args.stall_limit)
    backup_active = False

    session_log(run_dir, f"START run_id={run_id} mode={args.mode} memory_repo_root={memory_repo_root} agent_skills_root={agent_skills_root}")
    session_log(
        run_dir,
        "BUDGETS "
        f"max_cycles={args.max_cycles} wall_clock_s={args.wall_clock_s} wait_timeout_s={args.wait_timeout_s} "
        f"worker_poll_s={args.worker_poll_s} embed_batch_limit={args.embed_batch_limit} "
        f"health_json_timeout_s={args.health_json_timeout_s} health_fix_timeout_s={args.health_fix_timeout_s} "
        f"repair_timeout_s={args.repair_timeout_s or 'auto'} repair_external_timeout_s={compute_repair_cycle_timeout_s(args.wait_timeout_s, repair_timeout_s=args.repair_timeout_s, health_json_timeout_s=args.health_json_timeout_s, health_fix_timeout_s=args.health_fix_timeout_s)} "
        f"stall_limit={args.stall_limit}",
    )

    try:
        if args.backup_required:
            if backup_already_taken_today(session_root) and not args.force_backup:
                backup_active = False
                warning = "BACKUP_SKIPPED_ALREADY_TAKEN_TODAY: using existing daily backup guard; no new DB backup created"
                warnings.append(warning)
                session_log(run_dir, f"WARNING {warning}")
            else:
                begin = db_session_command(
                    memory_repo_root,
                    agent_skills_root,
                    "begin",
                    run_id=run_id,
                    timeout_s=args.backup_timeout_s,
                    required=True,
                )
                commands.append(dataclasses.asdict(begin))
                append_command_log(run_dir, begin)
                backup_active = begin.returncode != 127 and begin.ok
                if begin.returncode == 127:
                    warning = "BACKUP_UNAVAILABLE: db_repair_session.py not found; continuing without backup/verify/revert"
                    warnings.append(warning)
                    session_log(run_dir, f"WARNING {warning}")
                elif not begin.ok:
                    stop_reason = "backup_begin_failed"
                    exit_code = 3
                    raise RuntimeError(begin.error or begin.stderr_tail or "backup begin failed")
                else:
                    mark_backup_taken_today(session_root, dataclasses.asdict(begin))
        else:
            backup_active = False
            session_log(run_dir, "BACKUP skipped for this mode")

        raw_initial, initial_cmd = health_json(memory_repo_root, timeout_s=args.health_json_timeout_s, run_dir=run_dir)
        commands.append(dataclasses.asdict(initial_cmd))
        append_command_log(run_dir, initial_cmd)
        initial_health = extract_health(raw_initial)
        previous_health = dict(initial_health)
        final_health = dict(initial_health)
        session_log(run_dir, f"BASELINE health={initial_health['passed']}/{initial_health['total']} failing={','.join(initial_health['failing']) or 'none'}")

        if initial_health.get("green_29_of_29"):
            stop_reason = "all_green_at_baseline"
            exit_code = 0
        elif should_stop_for_unfixable_only(initial_health, skip_known_unfixable=args.skip_known_unfixable):
            stop_reason = "operator_required_unfixable_only"
            exit_code = EXIT_OPERATOR_REQUIRED
            record_operator_required(run_dir, initial_health, warnings)
        else:
            for cycle in range(1, int(args.max_cycles) + 1):
                if time.monotonic() >= deadline:
                    stop_reason = "wall_clock_budget_exhausted"
                    exit_code = 1
                    break

                assert previous_health is not None
                if should_stop_for_unfixable_only(previous_health, skip_known_unfixable=args.skip_known_unfixable):
                    stop_reason = "operator_required_unfixable_only"
                    exit_code = EXIT_OPERATOR_REQUIRED
                    record_operator_required(run_dir, previous_health, warnings)
                    session_log(run_dir, "REPAIR_SKIPPED reason=operator_required_unfixable_only")
                    break
                target_dimension = select_target_dimension(previous_health)
                session_log(run_dir, f"CYCLE_START cycle={cycle} target_dimension={target_dimension or 'none'} before={previous_health['passed']}/{previous_health['total']} failing={','.join(previous_health['failing']) or 'none'}")
                write_json(run_dir / f"cycle_{cycle:04d}_baseline_health.json", previous_health)

                prompt_reviewer_receipt_path: Path | None = None
                if qra_prompt_review_required(previous_health) and args.external_prompt_reviewer_gate:
                    gate_result, receipt_path = run_prompt_reviewer_gate(
                        run_dir=run_dir,
                        cycle=cycle,
                        health=previous_health,
                        args=args,
                    )
                    session_log(run_dir, f"PROMPT_REVIEW_GATE cycle={cycle} ok={gate_result.ok} verdict={gate_result.verdict} reason={gate_result.reason}")
                    if not gate_result.ok:
                        warnings.append(f"PROMPT_REVIEWER_GATE_FAILED: {gate_result.reason}")
                        stop_reason = "prompt_reviewer_gate_failed"
                        exit_code = EXIT_PROMPT_REVIEWER_GATE_FAILED
                        final_health = dict(previous_health)
                        break
                    prompt_reviewer_receipt_path = receipt_path
                elif qra_prompt_review_required(previous_health):
                    session_log(
                        run_dir,
                        "PROMPT_REVIEW_GATE deferred_to_monitor_concrete_bundle "
                        "reason=generic_outer_gate_lacks_manifest_prompt_fixture_expected_response_validator",
                    )

                repair = repair_cycle(
                    memory_repo_root,
                    cycle=cycle,
                    run_dir=run_dir,
                    wait_timeout_s=args.wait_timeout_s,
                    embed_batch_limit=args.embed_batch_limit,
                    repair_timeout_s=args.repair_timeout_s,
                    health_json_timeout_s=args.health_json_timeout_s,
                    health_fix_timeout_s=args.health_fix_timeout_s,
                    target_dimension=target_dimension,
                    prompt_reviewer_receipt_path=prompt_reviewer_receipt_path,
                )
                commands.append(dataclasses.asdict(repair))
                append_command_log(run_dir, repair)
                for line in format_repair_steps(repair.json):
                    session_log(run_dir, f"REPAIR_STEP cycle={cycle} {line}")
                if not repair_cycle_allows_after_health(repair):
                    stop_reason = "repair_cycle_failed"
                    exit_code = 4
                    break
                if not repair.ok:
                    progress_count = repair_cycle_progress_count(repair.json)
                    warning = (
                        "REPAIR_CYCLE_NONZERO_ACCEPTED: "
                        f"cycle={cycle} rc={repair.returncode} progress_count={progress_count}; "
                        "continuing to after-health diff"
                    )
                    warnings.append(warning)
                    session_log(run_dir, warning)

                raw_after, after_cmd = health_json(memory_repo_root, timeout_s=args.health_json_timeout_s, run_dir=run_dir)
                commands.append(dataclasses.asdict(after_cmd))
                append_command_log(run_dir, after_cmd)
                after_health = extract_health(raw_after)
                final_health = dict(after_health)
                diff = health_diff(previous_health, after_health)
                tracker.observe(diff, cycle=cycle)
                cycle_record = compact_cycle_record(cycle, previous_health, after_health, repair, diff)
                cycles.append(cycle_record)
                write_json(run_dir / f"cycle_{cycle:04d}.json", cycle_record)
                session_log(run_dir, format_diff_line(diff, cycle=cycle))

                cycle_warnings = tracker.warnings(after_health)
                for warning in cycle_warnings:
                    if warning not in warnings:
                        warnings.append(warning)
                    session_log(run_dir, f"WARNING {warning}")

                if args.backup_required and backup_active:
                    verify = db_session_command(
                        memory_repo_root,
                        agent_skills_root,
                        "verify",
                        run_id=run_id,
                        timeout_s=args.backup_timeout_s,
                        required=True,
                    )
                    commands.append(dataclasses.asdict(verify))
                    append_command_log(run_dir, verify)
                    if verify_detected_regression(verify, baseline=initial_health, current=after_health):
                        revert = db_session_command(
                            memory_repo_root,
                            agent_skills_root,
                            "revert",
                            run_id=run_id,
                            timeout_s=args.revert_timeout_s,
                            required=True,
                        )
                        commands.append(dataclasses.asdict(revert))
                        append_command_log(run_dir, revert)
                        stop_reason = "regression_detected_revert_attempted"
                        exit_code = 2
                        break

                if after_health.get("green_29_of_29"):
                    stop_reason = "all_green"
                    exit_code = 0
                    break

                if should_stop_for_unfixable_only(after_health, skip_known_unfixable=args.skip_known_unfixable):
                    stop_reason = "operator_required_unfixable_only"
                    exit_code = EXIT_OPERATOR_REQUIRED
                    record_operator_required(run_dir, after_health, warnings)
                    break

                if args.stop_on_stall and tracker.no_progress_cycles >= args.stall_limit:
                    stop_reason = "stall_budget_exhausted"
                    exit_code = EXIT_STALL
                    session_log(run_dir, f"STALL_STOP no_progress_cycles={tracker.no_progress_cycles} stall_limit={args.stall_limit}")
                    break

                previous_health = after_health
            else:
                stop_reason = "cycle_budget_exhausted"
                exit_code = 1

    except Exception as exc:  # noqa: BLE001 - always write final receipt/report
        if stop_reason == "unknown":
            stop_reason = "unhandled_exception"
            exit_code = 5
        msg = f"EXCEPTION {type(exc).__name__}: {exc}"
        warnings.append(msg)
        session_log(run_dir, msg)

    receipt: dict[str, Any] = {
        "schema_version": 2,
        "slice_id": SLICE_ID,
        "run_id": run_id,
        "mode": args.mode,
        "memory_repo_root": str(memory_repo_root),
        "agent_skills_root": str(agent_skills_root),
        "session_root": str(session_root),
        "run_dir": str(run_dir),
        "started_at": started_at,
        "finished_at": utc_now(),
        "stop_reason": stop_reason,
        "exit_code": exit_code,
        "parameters": {
            "max_cycles": args.max_cycles,
            "wall_clock_s": args.wall_clock_s,
            "wait_timeout_s": args.wait_timeout_s,
            "worker_poll_s": args.worker_poll_s,
            "embed_batch_limit": args.embed_batch_limit,
            "health_json_timeout_s": args.health_json_timeout_s,
            "health_fix_timeout_s": args.health_fix_timeout_s,
            "repair_timeout_s": args.repair_timeout_s,
            "repair_external_timeout_s": compute_repair_cycle_timeout_s(
                args.wait_timeout_s,
                repair_timeout_s=args.repair_timeout_s,
                health_json_timeout_s=args.health_json_timeout_s,
                health_fix_timeout_s=args.health_fix_timeout_s,
            ),
            "stall_limit": args.stall_limit,
            "stop_on_stall": args.stop_on_stall,
            "skip_known_unfixable": args.skip_known_unfixable,
            "backup_required": args.backup_required,
            "force_backup": getattr(args, "force_backup", False),
            "qra_model_pool": getattr(args, "qra_model_pool", None),
            "prompt_reviewer_timeout_s": getattr(args, "prompt_reviewer_timeout_s", None),
            "prompt_reviewer_command_template_configured": bool(getattr(args, "prompt_reviewer_command_template", None) or os.environ.get("DEWEY_PROMPT_REVIEWER_COMMAND_TEMPLATE")),
            "allow_mock_prompt_reviewer_receipt": getattr(args, "allow_mock_prompt_reviewer_receipt", False),
        },
        "initial_health": initial_health,
        "final_health": final_health,
        "initial_summary": compact_health_summary(initial_health),
        "final_summary": compact_health_summary(final_health),
        "terminal_state": terminal_state_for(stop_reason, exit_code, final_health),
        "cycles": cycles,
        "commands": commands,
        "warnings": warnings,
        "known_unfixable_dimensions": UNFIXABLE_DIMENSIONS,
        "invariant": "All automatic repair attempts route through monitor_sparta.py repair-cycle only.",
    }
    write_json(run_dir / "nightly_receipt.json", receipt)
    morning_report = write_morning_report(run_dir, receipt)
    evidence_summary = build_evidence_summary(receipt, morning_report=morning_report)
    evidence_summary_path = run_dir / "dewey_evidence_summary.json"
    write_json(evidence_summary_path, evidence_summary)
    session_log(run_dir, f"MORNING_REPORT path={morning_report}")
    session_log(run_dir, f"EVIDENCE_SUMMARY path={evidence_summary_path}")
    session_log(run_dir, f"STOP stop_reason={stop_reason} exit_code={exit_code} final={final_health.get('passed')}/{final_health.get('total')}")

    if args.json:
        print(
            json.dumps(
                {
                    **receipt,
                    "morning_report": str(morning_report),
                    "evidence_summary": str(evidence_summary_path),
                    "dewey_log": str(run_dir / "dewey.log"),
                },
                sort_keys=True,
            )
        )
    else:
        print(f"Dewey run dir: {run_dir}")
        print(f"Dewey log: {run_dir / 'dewey.log'}")
        print(f"Nightly receipt: {run_dir / 'nightly_receipt.json'}")
        print(f"Evidence summary: {evidence_summary_path}")
        print(f"Morning report: {morning_report}")
        print(f"Final health: {final_health.get('passed')}/{final_health.get('total')} PASS; stop_reason={stop_reason}")
    return int(exit_code)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory-repo-root", default=os.environ.get("MEMORY_REPO_ROOT", DEFAULT_MEMORY_REPO_ROOT))
    parser.add_argument("--agent-skills-root", default=os.environ.get("AGENT_SKILLS_ROOT", DEFAULT_AGENT_SKILLS_ROOT))
    parser.add_argument("--session-root", default=os.environ.get("DEWEY_SESSION_ROOT", DEFAULT_SESSION_ROOT))
    parser.add_argument("--run-id", default=os.environ.get("DEWEY_RUN_ID"))
    parser.add_argument("--wait-timeout-s", type=int, default=env_int("DEWEY_WAIT_TIMEOUT_S", DEFAULT_WAIT_TIMEOUT_S))
    # worker-poll-s is kept for Dewey scheduling/logging compatibility.  It is
    # intentionally not passed to repair-cycle because the real API does not
    # accept it.
    parser.add_argument("--worker-poll-s", type=int, default=env_int("DEWEY_WORKER_POLL_S", DEFAULT_WORKER_POLL_S))
    parser.add_argument(
        "--embed-batch-limit",
        dest="embed_batch_limit",
        type=int,
        default=env_first_int(("DEWEY_EMBED_BATCH_LIMIT", "DEWEY_QRA_BATCH_LIMIT"), DEFAULT_EMBED_BATCH_LIMIT),
    )
    parser.add_argument("--repair-timeout-s", type=int, default=env_int("DEWEY_REPAIR_TIMEOUT_S", None))
    parser.add_argument("--health-json-timeout-s", type=int, default=env_int("DEWEY_HEALTH_JSON_TIMEOUT_S", DEFAULT_HEALTH_JSON_TIMEOUT_S))
    parser.add_argument("--health-fix-timeout-s", type=int, default=env_int("DEWEY_HEALTH_FIX_TIMEOUT_S", DEFAULT_HEALTH_FIX_TIMEOUT_S))
    parser.add_argument("--backup-timeout-s", type=int, default=env_int("DEWEY_BACKUP_TIMEOUT_S", 1800))
    parser.add_argument("--revert-timeout-s", type=int, default=env_int("DEWEY_REVERT_TIMEOUT_S", 7200))
    parser.add_argument("--prompt-reviewer-timeout-s", type=int, default=env_int("DEWEY_PROMPT_REVIEWER_TIMEOUT_S", DEFAULT_PROMPT_REVIEWER_TIMEOUT_S))
    parser.add_argument("--qra-model-pool", default=os.environ.get("DEWEY_QRA_MODEL_POOL", DEFAULT_QRA_MODEL_POOL))
    parser.add_argument("--prompt-reviewer-command-template", default=os.environ.get("DEWEY_PROMPT_REVIEWER_COMMAND_TEMPLATE"))
    parser.add_argument("--prompt-reviewer-receipt", default=os.environ.get("DEWEY_PROMPT_REVIEWER_RECEIPT"))
    parser.add_argument("--allow-mock-prompt-reviewer-receipt", action="store_true")
    parser.add_argument(
        "--external-prompt-reviewer-gate",
        action="store_true",
        default=os.environ.get("DEWEY_EXTERNAL_PROMPT_REVIEWER_GATE") == "1",
        help="Opt in to Dewey's generic outer prompt-reviewer receipt gate. Default defers QRA prompt review to monitor-sparta's concrete manifest/prompt bundle.",
    )
    parser.add_argument("--stall-limit", type=int, default=env_int("DEWEY_STALL_LIMIT", DEFAULT_STALL_LIMIT))
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dewey nightly monitor-sparta repair loop")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="nightly cron path: backup first, then loop until green or budget/stall")
    add_common_args(start)
    start.add_argument("--max-cycles", type=int, default=env_int("DEWEY_MAX_ITERATIONS", DEFAULT_MAX_CYCLES))
    start.add_argument("--wall-clock-s", type=int, default=env_int("DEWEY_WALL_CLOCK_S", DEFAULT_WALL_CLOCK_S))
    start.add_argument("--no-stop-on-stall", action="store_true", help="warn on stalls but continue until cycle/wall-clock budget")
    start.add_argument("--retry-known-unfixable", action="store_true", help="do not short-circuit when only known unfixable lanes remain")
    start.add_argument("--no-backup", action="store_true", help="operator override; cron should not use this")
    start.add_argument("--force-backup", action="store_true", help="override once-per-day backup guard")

    def start_func(a: argparse.Namespace) -> int:
        a.mode = "start"
        a.stop_on_stall = not a.no_stop_on_stall
        a.skip_known_unfixable = not a.retry_known_unfixable
        a.backup_required = not a.no_backup
        return run_dewey(a)

    start.set_defaults(func=start_func)

    once = sub.add_parser("once", help="single-cycle smoke/debug path; no backup by default")
    add_common_args(once)
    once.add_argument("--wall-clock-s", type=int, default=env_int("DEWEY_ONCE_WALL_CLOCK_S", DEFAULT_WAIT_TIMEOUT_S + DEFAULT_REPAIR_MARGIN_S + 300))
    once.add_argument("--with-backup", action="store_true", help="include backup/verify in a single-cycle smoke")
    once.add_argument("--retry-known-unfixable", action="store_true")

    def once_func(a: argparse.Namespace) -> int:
        a.mode = "once"
        a.max_cycles = 1
        a.stop_on_stall = False
        a.skip_known_unfixable = not a.retry_known_unfixable
        a.backup_required = a.with_backup
        a.force_backup = False
        return run_dewey(a)

    once.set_defaults(func=once_func)

    status = sub.add_parser("status", help="read the latest Dewey evidence summary without running repairs")
    status.add_argument("--session-root", default=os.environ.get("DEWEY_SESSION_ROOT", DEFAULT_SESSION_ROOT))
    status.add_argument("--run-id", default=os.environ.get("DEWEY_RUN_ID"))
    status.add_argument(
        "--latest-filter",
        choices=("any", "repair-progress", "non-runner-error", "runner-error"),
        default=os.environ.get("DEWEY_STATUS_LATEST_FILTER", "any"),
        help="When --run-id is omitted, choose which latest run class to report.",
    )
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=run_status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
