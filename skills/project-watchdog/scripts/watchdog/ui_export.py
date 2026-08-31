"""Build read-only project-watchdog UI snapshots.

Purpose
    Convert watchdog status payloads plus retained receipt JSON into one typed
    snapshot for a React/Tailwind/ShadCN operator interface.

Inputs
    ``status_payload()`` output and ``receipt.json`` files under the configured
    project-watchdog receipt root.

Outputs
    A JSON-serializable ``project_watchdog.ui_snapshot.v1`` payload with
    filterable items, explicit gate status, optional triage details, receipt
    paths, and Tau DAG linkage hints.

Failure modes
    Unreadable receipt files are skipped with an explicit snapshot warning.
    The exporter is read-only: it never calls GitHub, Tau, Ask, or shell tools,
    and never mutates watchdog state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger

from . import config


class GateStatus(StrEnum):
    """Closed UI vocabulary for operator-visible gate states."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    DRY_RUN = "DRY_RUN"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class TriageSummary:
    """Canonical triage projection shown beside failed or blocked gates."""

    code: str | None
    cause: str | None
    next_command: str | None
    recoverable: bool | None
    source: str


@dataclass(frozen=True, slots=True)
class TauDagLink:
    """Read-only linkage from a watchdog row to a Tau/Ask DAG artifact."""

    expected: bool
    available: bool
    run_dir: str | None
    progress_path: str | None
    stream_monitor_path: str | None
    viewer_hint: str


@dataclass(frozen=True, slots=True)
class WatchdogUiItem:
    """One filterable row/card in the project-watchdog control tower."""

    item_id: str
    kind: str
    project_id: str | None
    repo: str | None
    issue_number: int | None
    issue_url: str | None
    action: str | None
    status: str
    gate_status: GateStatus
    summary: str
    targets: list[str] = field(default_factory=list)
    receipt_path: str | None = None
    receipt_dir: str | None = None
    run_id: str | None = None
    updated_at: str | None = None
    stop_reason: str | None = None
    triage: TriageSummary | None = None
    tau_dag: TauDagLink | None = None
    evidence_paths: list[str] = field(default_factory=list)


def build_snapshot(status: dict[str, Any], *, receipt_limit: int = 100) -> dict[str, Any]:
    """Return the read-only UI snapshot for the current watchdog state."""
    receipt_root = Path(str(status.get("receipt_root") or config.receipt_root()))
    items, warnings = _load_recent_items(receipt_root, limit=receipt_limit)
    counts = _count_by_gate(items)
    now = datetime.now(UTC).isoformat()
    return {
        "schema": "agent_skills.project_watchdog.ui_snapshot.v1",
        "generated_at": now,
        "source": {
            "status_schema": status.get("schema"),
            "receipt_root": str(receipt_root),
            "cron_log_file": status.get("cron_log_file"),
            "log_file": status.get("log_file"),
        },
        "global_state": (status.get("state") or {}).get("global", {}),
        "project_count": status.get("project_count", 0),
        "project_ids": status.get("project_ids", []),
        "lock_held": bool(status.get("lock_held")),
        "idle_streaks": status.get("idle_streaks", {}),
        "receipt_count_reported": status.get("stored_receipt_dirs"),
        "receipt_limit": receipt_limit,
        "counts": counts,
        "items": [asdict(item) for item in items],
        "warnings": warnings,
    }


def _load_recent_items(receipt_root: Path, *, limit: int) -> tuple[list[WatchdogUiItem], list[str]]:
    warnings: list[str] = []
    items: list[WatchdogUiItem] = []
    if not receipt_root.is_dir():
        return items, [f"receipt root does not exist: {receipt_root}"]

    receipt_paths = sorted(
        receipt_root.glob("project-watchdog-*/receipt.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[: max(limit, 0)]

    for receipt_path in receipt_paths:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("could not read watchdog receipt {}: {}", receipt_path, exc)
            warnings.append(f"unreadable receipt: {receipt_path}")
            continue
        items.extend(_items_from_receipt(receipt_path, receipt))
    return items, warnings


def _items_from_receipt(receipt_path: Path, receipt: dict[str, Any]) -> list[WatchdogUiItem]:
    handled = receipt.get("handled_issues")
    if isinstance(handled, list) and handled:
        return [_item_from_issue(receipt_path, receipt, issue) for issue in handled]
    return [_item_from_tick(receipt_path, receipt)]


def _item_from_issue(
    receipt_path: Path,
    receipt: dict[str, Any],
    issue: dict[str, Any],
) -> WatchdogUiItem:
    run_id = _str_or_none(receipt.get("run_id"))
    issue_number = _int_or_none(issue.get("issue_number"))
    repo = _str_or_none(issue.get("repo") or receipt.get("repo"))
    action = _str_or_none(issue.get("action"))
    status = str(issue.get("status") or receipt.get("status") or "UNKNOWN")
    item_id = f"{repo or 'repo'}#{issue_number or 'no-issue'}:{run_id or receipt_path.parent.name}"
    evidence = _evidence_paths(issue) + _evidence_paths(receipt)
    return WatchdogUiItem(
        item_id=item_id,
        kind="ticket",
        project_id=_str_or_none(issue.get("project_id") or receipt.get("project_id")),
        repo=repo,
        issue_number=issue_number,
        issue_url=_str_or_none(issue.get("issue_url")),
        action=action,
        status=status,
        gate_status=_derive_gate_status(issue, fallback=receipt),
        summary=str(issue.get("summary") or receipt.get("summary") or "No summary recorded."),
        targets=[str(target) for target in issue.get("targets", []) if str(target)],
        receipt_path=str(receipt_path),
        receipt_dir=_str_or_none(receipt.get("receipt_dir") or receipt_path.parent),
        run_id=run_id,
        updated_at=_mtime_utc(receipt_path),
        stop_reason=_str_or_none(issue.get("stop_reason") or receipt.get("stop_reason")),
        triage=_triage_from_payload(issue) or _triage_from_payload(receipt),
        tau_dag=_tau_dag_from_payload(issue, receipt_path),
        evidence_paths=sorted(set(evidence)),
    )


def _item_from_tick(receipt_path: Path, receipt: dict[str, Any]) -> WatchdogUiItem:
    run_id = _str_or_none(receipt.get("run_id")) or receipt_path.parent.name
    return WatchdogUiItem(
        item_id=f"tick:{run_id}",
        kind="tick",
        project_id=_str_or_none(receipt.get("project_id")),
        repo=_str_or_none(receipt.get("repo")),
        issue_number=None,
        issue_url=None,
        action="tick",
        status=str(receipt.get("status") or "UNKNOWN"),
        gate_status=_derive_gate_status(receipt),
        summary=str(receipt.get("summary") or "Watchdog tick receipt."),
        targets=[],
        receipt_path=str(receipt_path),
        receipt_dir=_str_or_none(receipt.get("receipt_dir") or receipt_path.parent),
        run_id=run_id,
        updated_at=_mtime_utc(receipt_path),
        stop_reason=_str_or_none(receipt.get("stop_reason")),
        triage=_triage_from_payload(receipt),
        tau_dag=_tau_dag_from_payload(receipt, receipt_path),
        evidence_paths=sorted(set(_evidence_paths(receipt))),
    )


def _derive_gate_status(payload: dict[str, Any], *, fallback: dict[str, Any] | None = None) -> GateStatus:
    status = str(payload.get("status") or (fallback or {}).get("status") or "UNKNOWN").upper()
    ok = payload.get("ok", (fallback or {}).get("ok"))
    if status == "DRY_RUN":
        return GateStatus.DRY_RUN
    if status in {"SKIPPED", "NOOP"}:
        return GateStatus.SKIPPED
    if status == "BLOCKED":
        return GateStatus.BLOCKED
    if status == "NEEDS_ATTENTION":
        return GateStatus.NEEDS_ATTENTION
    if status in {"FAIL", "FAILED"} or ok is False:
        return GateStatus.FAIL
    if status in {"PASS", "PASSED", "COMPLETED"} and ok is True:
        return GateStatus.PASS
    return GateStatus.UNKNOWN


def _triage_from_payload(payload: dict[str, Any]) -> TriageSummary | None:
    triage = payload.get("triage") or payload.get("audit_triage") or payload.get("failure_triage")
    if not isinstance(triage, dict):
        return _triage_from_flat_payload(payload)
    return TriageSummary(
        code=_str_or_none(triage.get("code")),
        cause=_str_or_none(triage.get("cause")),
        next_command=_str_or_none(triage.get("next_command")),
        recoverable=_bool_or_none(triage.get("recoverable")),
        source="triage-error",
    )


def _triage_from_flat_payload(payload: dict[str, Any]) -> TriageSummary | None:
    code = _str_or_none(payload.get("failure_code") or payload.get("code"))
    cause = _str_or_none(payload.get("cause") or payload.get("error"))
    next_command = _str_or_none(payload.get("next_command"))
    if not any([code, cause, next_command]):
        return None
    return TriageSummary(
        code=code,
        cause=cause,
        next_command=next_command,
        recoverable=_bool_or_none(payload.get("recoverable")),
        source="receipt",
    )


def _tau_dag_from_payload(payload: dict[str, Any], receipt_path: Path) -> TauDagLink | None:
    action = str(payload.get("action") or "")
    expects_dag = action == "ticket_repair" or "tau" in action
    run_dir = _first_existing_path(
        payload.get("ask_run_dir"),
        payload.get("ask_run"),
        payload.get("tau_run_dir"),
        payload.get("dag_run_dir"),
    )
    progress_path = _find_progress_path(run_dir)
    stream_monitor_path = _first_existing_path(
        payload.get("tau_stream_monitor_path"),
        receipt_path.parent / "tau-stream-monitor.json",
    )
    if not expects_dag and not run_dir and not progress_path and not stream_monitor_path:
        return None
    return TauDagLink(
        expected=expects_dag,
        available=bool(run_dir or progress_path or stream_monitor_path),
        run_dir=str(run_dir) if run_dir else None,
        progress_path=str(progress_path) if progress_path else None,
        stream_monitor_path=str(stream_monitor_path) if stream_monitor_path else None,
        viewer_hint="Open the Tau React Flow viewer with this run directory when available.",
    )


def _find_progress_path(run_dir: Path | None) -> Path | None:
    if not run_dir or not run_dir.exists():
        return None
    for candidate in [run_dir / "dag-progress.json", run_dir / "tau-receipts" / "dag-progress.json"]:
        if candidate.exists():
            return candidate
    return None


def _first_existing_path(*values: object) -> Path | None:
    for value in values:
        if value is None:
            continue
        path = Path(str(value)).expanduser()
        if path.exists():
            return path
    return None


def _evidence_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("receipt_path", "tau_stream_monitor_path"):
        value = payload.get(key)
        if value:
            paths.append(str(value))
    for collection_key in ("artifacts", "closure_artifacts", "proof_artifacts"):
        entries = payload.get(collection_key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("path"):
                paths.append(str(entry["path"]))
            elif isinstance(entry, str):
                paths.append(entry)
    return paths


def _count_by_gate(items: list[WatchdogUiItem]) -> dict[str, int]:
    counts = {status.value: 0 for status in GateStatus}
    for item in items:
        counts[item.gate_status.value] += 1
    counts["TOTAL"] = len(items)
    return counts


def _mtime_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
