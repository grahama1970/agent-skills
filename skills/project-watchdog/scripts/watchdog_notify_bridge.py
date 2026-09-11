#!/usr/bin/env python3
"""Deliver project-watchdog receipt events to terminal, Pi, and ops-discord.

The bridge tails the watchdog receipts directory and normalizes each eventful
receipt into one correlated delivery event. Each destination has its own durable
checkpoint, and a checkpoint advances only after that destination acknowledges
delivery:

  1. terminal JSONL at ``events.jsonl`` for shared operator/agent visibility
  2. Switchboard ``POST /emit`` for the owning Pi agent session
  3. ``ops-discord notify --discord-bot`` only for explicit human-only blockers

Machine-actionable failures stay agent-owned but visible. Unknown identity is
rendered as ``UNKNOWN(field:reason)``, never as ``None#None``. Heartbeats prove
observer freshness separately from execution progress and never report stale Tau
progress as ``LIVE``.

Run from cron every 5 minutes. Delivery failure never raises; it prints a
JSON result and exits 0 so the cron line stays quiet unless truly broken.

# ponytail: one sequential scanner with per-destination checkpoints; receipts arrive ~1/5min, no need for parallelism.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

STATE_ROOT = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", Path.home() / ".local/state/project-watchdog"))
RECEIPTS = STATE_ROOT / "receipts"
CURSOR = STATE_ROOT / "notify-bridge-cursor.json"
CHECKPOINTS = STATE_ROOT / "notify-bridge-checkpoints.json"
BRIDGE_LOCK = STATE_ROOT / "notify-bridge.lock"
SWITCHBOARD_DEDUP = STATE_ROOT / "notify-bridge-dedup.json"
SWITCHBOARD = os.environ.get("SWITCHBOARD_URL", "http://127.0.0.1:7890")
PI_AGENT_INBOX = os.environ.get("WATCHDOG_BRIDGE_PI_INBOX", "agent-skills")
OPS_DISCORD = Path(
    os.environ.get(
        "PROJECT_WATCHDOG_OPS_DISCORD_RUN_SH",
        str(Path(__file__).resolve().parents[2] / "ops-discord" / "run.sh"),
    )
)
UNKNOWN = "UNKNOWN"


class BridgeCheckpoint(BaseModel):
    """Durable notification bridge checkpoint.

    ``destinations`` advances independently for terminal JSONL, Pi agent push,
    and ops-discord. A failed destination leaves the event in ``pending`` so the
    next run can retry without replaying the whole receipt history.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: str = Field(
        default="project_watchdog.notify_bridge_checkpoint.v1",
        alias="schema",
    )
    last_mtime: float = 0.0
    pending_dirs: list[str] = Field(default_factory=list)
    pending: dict[str, dict[str, Any]] = Field(default_factory=dict)
    destinations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    updated_at: str | None = None


class DeliveryEvent(BaseModel):
    """Normalized event sent to terminal, Pi agent, and human transports."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    schema_: str = Field(default="project_watchdog.delivery_event.v1", alias="schema")
    event_id: str
    run_id: str
    repo: str
    issue: str
    node: str
    attempt: str
    status: str
    phase: str
    source_time: str
    observed_at: str
    receipt: str
    identity: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_cursor() -> float:
    try:
        return float(json.loads(CURSOR.read_text())["last_mtime"])
    except (OSError, ValueError, KeyError, TypeError):
        return time.time() - 3600  # first run: last hour only


def _load_checkpoint() -> BridgeCheckpoint:
    try:
        return BridgeCheckpoint.model_validate(json.loads(CHECKPOINTS.read_text()))
    except FileNotFoundError:
        return BridgeCheckpoint(last_mtime=_load_cursor())
    except (OSError, ValueError, ValidationError):
        return BridgeCheckpoint(last_mtime=_load_cursor())


def _save_checkpoint(checkpoint: BridgeCheckpoint) -> None:
    checkpoint.updated_at = _now_iso()
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    _write_text_durable(
        CHECKPOINTS,
        checkpoint.model_dump_json(indent=2, by_alias=True) + "\n",
    )
    _write_text_durable(
        CURSOR,
        json.dumps({"last_mtime": checkpoint.last_mtime, "updated_at": time.time()})
        + "\n",
    )


def _write_text_durable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _dest(checkpoint: BridgeCheckpoint, name: str) -> dict[str, Any]:
    return checkpoint.destinations.setdefault(
        name, {"delivered_event_ids": [], "receipts": {}}
    )


def _delivered(checkpoint: BridgeCheckpoint, name: str, event_id: str) -> bool:
    return event_id in set(_dest(checkpoint, name).get("delivered_event_ids") or [])


def _mark_delivered(
    checkpoint: BridgeCheckpoint,
    name: str,
    event_id: str,
    receipt: dict[str, Any],
) -> None:
    destination = _dest(checkpoint, name)
    delivered = list(destination.get("delivered_event_ids") or [])
    if event_id not in delivered:
        delivered.append(event_id)
    destination["delivered_event_ids"] = delivered[-1000:]
    destination.setdefault("receipts", {})[event_id] = receipt


def _pydantic_violations(receipt: dict) -> list[str]:
    """Collect validation-error signals embedded anywhere in the receipt."""
    hits: list[str] = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("validation_errors", "pydantic_errors") and v:
                    hits.append(f"{path}.{k}: {json.dumps(v)[:200]}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        elif isinstance(obj, str) and ("ValidationError" in obj or "validation error" in obj):
            hits.append(f"{path}: {obj[:200]}")

    walk(receipt)
    return hits[:5]


def _unknown(field: str, reason: str) -> str:
    return f"{UNKNOWN}({field}:{reason})"


def _identity_value(value: Any, field: str, reason: str) -> str:
    if value is None or value == "":
        return _unknown(field, reason)
    return str(value)


def _source_time(receipt: dict[str, Any], receipt_dir: Path) -> str:
    for key in ("source_time", "emitted_at", "finished_at", "timestamp", "ts"):
        value = receipt.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.fromtimestamp(receipt_dir.stat().st_mtime, UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _seats(handled: dict) -> list[str]:
    out = []
    for ph in handled.get("workflow_phases") or []:
        pid = ph.get("id", "")
        if any(t in pid for t in ("fixer", "reviewer", "creator", "triaged", "lease", "close")):
            out.append(f"{pid}={ph.get('status')}({ph.get('agent') or ph.get('executor')})")
    return out


def _node_models(receipt_dir: Path) -> dict[str, str]:
    """node_id -> model, read from the run's source-dag.json handler bindings."""
    import glob as _g
    out: dict[str, str] = {}
    # exact model from finished nodes
    for f in _g.glob(str(receipt_dir / "ask/*/node-artifacts/*/response.meta.json")):
        try:
            data = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        model = data.get("requested_model") or data.get("model")
        if model:
            out.setdefault(Path(f).parent.name, model)
    # planned model from the dag: nodes[].context.handler_policy.model_policy
    for f in _g.glob(str(receipt_dir / "ask/*/tau-receipts/source-dag.json")) + _g.glob(str(receipt_dir / "ask/*/dag.json")):
        try:
            data = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for node in data.get("nodes") or []:
            nid = node.get("id")
            pol = ((node.get("context") or {}).get("handler_policy") or {})
            mp = pol.get("model_policy") or {}
            model = mp.get("requested_model") or mp.get("model") or pol.get("model")
            if nid and model:
                out.setdefault(nid, model)
    return out


def _dispatched_issue(receipt_dir: Path) -> str:
    try:
        d = json.loads((receipt_dir / "dispatch-issue.json").read_text())
        return str(d.get("issue") or d.get("number") or "-")
    except (OSError, json.JSONDecodeError):
        return "-"


def _live_seat(receipt_dir: Path) -> str | None:
    mon = receipt_dir / "tau-stream-monitor.json"
    if not mon.is_file():
        return None
    try:
        m = json.loads(mon.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    ev = m.get("latest_event") or {}
    node = ev.get("node_id") or m.get("current_node") or "-"
    model = _node_models(receipt_dir).get(node, "?")
    if m.get("process_running"):
        return f"RUNNING agent={node} model={model} elapsed={int(m.get('elapsed_seconds') or 0)}s"
    return f"finished status={m.get('current_status')} last-agent={node} model={model}"


def _active_operation(r: dict) -> dict:
    rows = r.get("primary_observations") or []
    for row in rows:
        if row.get("writer_active"):
            for op in row.get("operations") or []:
                return op
    for row in rows:
        for op in row.get("operations") or []:
            return op
    return {}


def _agent_next_steps(r: dict, handled: dict) -> list[str]:
    steps = handled.get("authorized_agent_next_steps") or r.get("authorized_agent_next_steps") or []
    if steps:
        return steps[:2]
    rows = r.get("primary_observations") or []
    for row in rows:
        if row.get("writer_active") and row.get("recovery_command"):
            return [row["recovery_command"]]
    for row in rows:
        cmd = row.get("recovery_command")
        if cmd:
            return [cmd]
    return []


def summarize(receipt_dir: Path) -> dict | None:
    rj = receipt_dir / "receipt.json"
    if not rj.is_file():
        return {"kind": "pending_receipt", "dir": receipt_dir.name, "reason": "missing_receipt_json"}
    try:
        r = json.loads(rj.read_text())
    except json.JSONDecodeError as exc:
        return {
            "kind": "pending_receipt",
            "dir": receipt_dir.name,
            "reason": "partial_or_malformed_json",
            "error": str(exc)[:200],
        }
    except OSError as exc:
        return {
            "kind": "malformed_receipt",
            "dir": receipt_dir.name,
            "status": "NEEDS_ATTENTION",
            "error": str(exc)[:200],
        }
    handled = (r.get("handled_issues") or [{}])[0]
    op = _active_operation(r)
    triage = handled.get("triage") or r.get("triage") or {}
    repo = _identity_value(handled.get("repo") or op.get("repo"), "repo", "receipt_missing_repo")
    issue = _identity_value(
        handled.get("issue_number") or op.get("issue_number"),
        "issue",
        "receipt_missing_issue_number",
    )
    run_id = _identity_value(r.get("run_id") or receipt_dir.name, "run_id", "receipt_missing_run_id")
    live = _live_seat(receipt_dir)
    node = "-"
    if live and "agent=" in live:
        node = live.split("agent=", 1)[1].split()[0]
    elif live and "last-agent=" in live:
        node = live.split("last-agent=", 1)[1].split()[0]
    attempt = _identity_value(handled.get("attempt") or op.get("attempt"), "attempt", "not_recorded")
    source_time = _source_time(r, receipt_dir)
    event_key = {
        "run_id": run_id,
        "repo": repo,
        "issue": issue,
        "node": node,
        "attempt": attempt,
        "status": _identity_value(r.get("status"), "status", "receipt_missing_status"),
        "stop_reason": r.get("stop_reason"),
        "receipt_dir": receipt_dir.name,
    }
    import hashlib

    event_id = hashlib.sha256(json.dumps(event_key, sort_keys=True).encode()).hexdigest()[:24]
    return {
        "schema": "project_watchdog.delivery_event.v1",
        "kind": "tick",
        "event_id": event_id,
        "dir": receipt_dir.name,
        "status": _identity_value(r.get("status"), "status", "receipt_missing_status"),
        "stop_reason": r.get("stop_reason"),
        "run_id": run_id,
        "issue": issue,
        "repo": repo,
        "node": node,
        "attempt": attempt,
        "source_time": source_time,
        "observed_at": _now_iso(),
        "phase": handled.get("action") or op.get("phase") or r.get("stop_reason") or "receipt",
        "action": handled.get("action") or op.get("action"),
        "summary": (handled.get("summary") or r.get("summary") or r.get("reason") or r.get("stop_reason") or "")[:300],
        "requires_human_input": (
            True if handled.get("requires_human_input") is True else r.get("requires_human_input")
        ),
        "triage_code": triage.get("code"),
        "triage_cause": (triage.get("cause") or "")[:200],
        "seats": _seats(handled),
        "live": live,
        "pydantic_violations": _pydantic_violations(r),
        "original_errors": (r.get("errors") or [])[:3],
        "exit_code": r.get("exit_code") or handled.get("exit_code") or op.get("exit_code"),
        "retry_budget": handled.get("retry_budget") or r.get("retry_budget"),
        "not_before": handled.get("not_before") or r.get("not_before"),
        "resolution_ref": handled.get("resolution_ref") or r.get("resolution_ref"),
        "next_steps": _agent_next_steps(r, handled),
        "identity": {
            "event_id": event_id,
            "run_id": run_id,
            "repo": repo,
            "issue": issue,
            "node": _identity_value(node if node != "-" else None, "node", "not_recorded"),
            "attempt": attempt,
        },
    }


def _fmt(ev: dict) -> str:
    lines = [
        f"[{ev.get('status')}] issue {ev.get('repo')}#{ev.get('issue')} ({ev.get('action')})",
        f"summary: {ev.get('summary')}",
    ]
    if ev.get("triage_code"):
        lines.append(f"triage-error: {ev['triage_code']} — {ev.get('triage_cause')}")
    if ev.get("seats"):
        lines.append("seats: " + "; ".join(ev["seats"]))
    if ev.get("live"):
        lines.append(f"live: {ev['live']}")
    if ev.get("pydantic_violations"):
        lines.append("PYDANTIC VIOLATIONS: " + " | ".join(ev["pydantic_violations"]))
    if ev.get("requires_human_input"):
        lines.append("NEEDS HUMAN INPUT")
    elif ev.get("next_steps"):
        lines.append("agent next: " + "; ".join(ev["next_steps"]))
    lines.append(f"receipt: {RECEIPTS / ev['dir']}")
    return "\n".join(lines)


def requires_human_push(ev: dict) -> bool:
    """Only page humans for human decisions, not machine-actionable repair receipts."""
    if ev.get("requires_human_input") is True:
        return True
    return False


def _is_non_ticket_event(ev: dict) -> bool:
    """Install/state/fleet-scan receipts are operational, not ticket work.

    They carry no repo/issue and were rendering as
    ``UNKNOWN(repo:receipt_missing_repo)#UNKNOWN(...)`` NEEDS_ATTENTION pushes
    (2026-09-10 log noise, #1648). Identify them by the UNKNOWN identity
    sentinels so a genuinely malformed ticket receipt still surfaces.
    """
    repo, issue = str(ev.get("repo") or ""), str(ev.get("issue") or "")
    return ("receipt_missing_repo" in repo and "receipt_missing_issue" in issue)


def _subject_target(ev: dict) -> str:
    """Human-readable subject target.

    Ticket events render ``repo#issue``. Non-ticket lifecycle receipts (cron
    install, runtime state change, fleet scan) have no repo/issue, so instead of
    the cryptic ``UNKNOWN(repo:receipt_missing_repo)#UNKNOWN(...)`` sentinel we
    render a plain lifecycle label derived from the run_id.
    """
    if not _is_non_ticket_event(ev):
        return f"{ev.get('repo')}#{ev.get('issue')}"
    run_id = str(ev.get("run_id") or "")
    if "-install" in run_id:
        kind = "cron-install"
    elif "-state" in run_id:
        kind = "runtime-state-change"
    else:
        kind = "fleet-scan"
    return f"lifecycle:{kind} (no ticket)"


def requires_agent_push(ev: dict) -> bool:
    """Project-agent visibility is broader than human paging."""
    if ev.get("status") in {"NOOP", "SKIPPED"}:
        return False
    if _is_non_ticket_event(ev):
        # Not a ticket: write the terminal JSONL record but do not push an
        # UNKNOWN#UNKNOWN NEEDS_ATTENTION alert to the project agent.
        return False
    return True


def push_webhook(ev: dict) -> dict[str, Any]:
    if not requires_human_push(ev):
        return {"status": "SKIPPED", "reason": "not_human_only_blocker"}
    title = f"project-watchdog {ev.get('status')} — {_subject_target(ev)}"
    try:
        p = subprocess.run(
            [
                str(OPS_DISCORD),
                "notify",
                "--discord-bot",
                "--channel-name",
                os.environ.get("PROJECT_WATCHDOG_ALERT_CHANNEL", "horus"),
                "--title",
                title,
                "--content",
                _fmt(ev),
                "--json",
            ],
            capture_output=True, text=True, timeout=60,
        )
        try:
            receipt = json.loads(p.stdout)
        except ValueError:
            receipt = {"raw_stdout": p.stdout[-500:]}
        receipt["exit_code"] = p.returncode
        if p.returncode != 0:
            receipt["status"] = "ALERT_DELIVERY_FAILED"
            receipt["stderr"] = p.stderr[-500:]
        return receipt
    except Exception as exc:  # noqa: BLE001 - delivery failure never blocks
        return {"status": "ALERT_DELIVERY_FAILED", "error": str(exc)[:200]}


def _renotify_seconds() -> int:
    try:
        return int(os.environ.get("PROJECT_WATCHDOG_ALERT_RENOTIFY_SECONDS") or 86400)
    except ValueError:
        return 86400


def _event_fingerprint(ev: dict[str, Any]) -> str:
    """Stable identity of the condition, not the receipt.

    The watchdog mints a new receipt (new event_id) every tick for the same
    stuck ticket, so per-event_id dedup alone let the identical
    NEEDS_ATTENTION push reach Switchboard every 5 minutes (2026-09-10:
    ownership-conflict/seat-refusal spam). Fingerprint on repo+issue+status+
    triage code so one condition pushes once per renotify window.
    """
    return json.dumps(
        [ev.get("repo"), ev.get("issue"), ev.get("status"), ev.get("triage_code")],
        sort_keys=True,
    )


def _load_dedup_state() -> dict[str, float]:
    try:
        parsed = json.loads(SWITCHBOARD_DEDUP.read_text())
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, ValueError):
        return {}


def switchboard_delivery_decision(ev: dict, *, fresh: bool) -> str | None:
    if not fresh:
        return "skipped_stale"
    if not requires_agent_push(ev):
        return "skipped_no_agent_action"
    return None


def switchboard_payload(ev: dict) -> dict[str, Any]:
    human = requires_human_push(ev)
    return {
        "from": "project-watchdog-bridge",
        "to": PI_AGENT_INBOX,
        "type": "alert" if human else "info",
        "priority": "high" if human else "normal",
        "subject": f"watchdog {ev.get('status')} {_subject_target(ev)}",
        "message": _fmt(ev),
        "event": ev,
        "owning_next_action": (ev.get("next_steps") or [None])[0],
    }


def push_switchboard(ev: dict) -> dict[str, Any]:
    if not requires_agent_push(ev):
        return {"status": "SKIPPED", "reason": "no_agent_action"}
    body = json.dumps(switchboard_payload(ev)).encode()
    req = urllib.request.Request(f"{SWITCHBOARD}/emit", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {"raw_body": raw[-500:]}
            parsed.update({"status": "SENT", "http_status": resp.status})
            _write_agent_action_receipt(ev, parsed)
            return parsed
    except Exception as exc:  # noqa: BLE001 - retry through checkpoint
        return {"status": "AGENT_PUSH_FAILED", "error": str(exc)[:200]}


def _write_agent_action_receipt(ev: dict[str, Any], delivery: dict[str, Any]) -> None:
    out = STATE_ROOT / "agent-push-receipts" / f"{ev['event_id']}.json"
    _write_text_durable(
        out,
        json.dumps(
            {
                "schema": "project_watchdog.agent_push_receipt.v1",
                "event_id": ev["event_id"],
                "delivered_at": _now_iso(),
                "delivery": delivery,
                "owning_next_action": (ev.get("next_steps") or [None])[0],
                "consumed_or_action_receipt": delivery.get("consumed")
                or delivery.get("action_receipt")
                or delivery.get("message_id")
                or delivery.get("id"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def write_stream_event(ev: dict[str, Any]) -> dict[str, Any]:
    stream = STATE_ROOT / "events.jsonl"
    stream.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "project_watchdog.terminal_event.v1",
        "ts": _now_iso(),
        "source_time": ev.get("source_time"),
        "observed_at": ev.get("observed_at"),
        "kind": "receipt",
        "event_id": ev.get("event_id"),
        "run_id": ev.get("run_id"),
        "status": ev.get("status"),
        "phase": ev.get("phase"),
        "issue": ev.get("issue"),
        "repo": ev.get("repo"),
        "node": ev.get("node"),
        "attempt": ev.get("attempt"),
        "summary": ev.get("summary"),
        "seat": ev.get("live"),
        "triage": ev.get("triage_code"),
        "pydantic": ev.get("pydantic_violations") or [],
        "original_errors": ev.get("original_errors") or [],
        "exit_code": ev.get("exit_code"),
        "next": (ev.get("next_steps") or [None])[0],
        "retry_budget": ev.get("retry_budget"),
        "not_before": ev.get("not_before"),
        "resolution_ref": ev.get("resolution_ref"),
        "identity": ev.get("identity"),
        "receipt": str(RECEIPTS / ev["dir"]),
    }
    DeliveryEvent.model_validate(
        {
            **{k: row[k] for k in ("event_id", "run_id", "repo", "issue", "node", "attempt", "status", "phase", "source_time", "observed_at", "receipt", "identity")},
            "schema": "project_watchdog.delivery_event.v1",
        }
    )
    with stream.open("a", encoding="utf-8") as fh:
        offset = fh.tell()
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return {"status": "ACK", "path": str(stream), "offset": offset}


def _event_complete(checkpoint: BridgeCheckpoint, ev: dict[str, Any]) -> bool:
    event_id = ev["event_id"]
    required = ["terminal"]
    if requires_agent_push(ev):
        required.append("pi_agent")
    if requires_human_push(ev):
        required.append("ops_discord")
    return all(_delivered(checkpoint, dest, event_id) for dest in required)


def deliver(ev: dict[str, Any], checkpoint: BridgeCheckpoint, *, fresh: bool) -> dict[str, Any]:
    event_id = ev["event_id"]
    result: dict[str, Any] = {"event_id": event_id, "dir": ev["dir"], "status": ev.get("status")}
    if not _delivered(checkpoint, "terminal", event_id):
        receipt = write_stream_event(ev)
        _mark_delivered(checkpoint, "terminal", event_id, receipt)
        result["terminal"] = receipt
    else:
        result["terminal"] = {"status": "DEDUPED"}
    decision = switchboard_delivery_decision(ev, fresh=fresh)
    if decision:
        result["switchboard"] = {"status": "SKIPPED", "reason": decision}
    elif not _delivered(checkpoint, "pi_agent", event_id):
        fp = _event_fingerprint(ev)
        state = _load_dedup_state()
        now = time.time()
        if now - state.get(fp, 0) < _renotify_seconds():
            receipt = {"status": "DEDUPED", "fingerprint": fp,
                       "last_sent_at": state.get(fp)}
            result["switchboard"] = receipt
            _mark_delivered(checkpoint, "pi_agent", event_id, receipt)
        else:
            receipt = push_switchboard(ev)
            result["switchboard"] = receipt
            if receipt.get("status") == "SENT":
                # Only a real delivery advances the dedupe clock (alerts.py rule).
                state[fp] = now
                _write_text_durable(SWITCHBOARD_DEDUP, json.dumps(state, sort_keys=True) + "\n")
                _mark_delivered(checkpoint, "pi_agent", event_id, receipt)
    else:
        result["switchboard"] = {"status": "DEDUPED"}
    if not requires_human_push(ev):
        result["ops_discord"] = {"status": "SKIPPED", "reason": "not_human_only_blocker"}
    elif not _delivered(checkpoint, "ops_discord", event_id):
        receipt = push_webhook(ev)
        result["ops_discord"] = receipt
        message_ref = receipt.get("message_id") or receipt.get("message_url") or receipt.get("discord_message_id")
        if receipt.get("status") == "SENT" and message_ref:
            _mark_delivered(checkpoint, "ops_discord", event_id, receipt)
    else:
        result["ops_discord"] = {"status": "DEDUPED"}
    if _event_complete(checkpoint, ev):
        checkpoint.pending.pop(event_id, None)
    else:
        checkpoint.pending[event_id] = ev
    return result


def _heartbeat_payload() -> dict[str, Any]:
    import glob as _glob

    mons = sorted(_glob.glob(str(RECEIPTS / "*/tau-stream-monitor.json")), key=os.path.getmtime)
    if not mons:
        return {"state": "observer_fresh_no_active_run"}
    try:
        monitor_path = Path(mons[-1])
        m = json.loads(monitor_path.read_text())
        ev = m.get("latest_event") or {}
        run_dir = monitor_path.parent
        node = ev.get("node_id") or m.get("current_node") or "-"
        model = _node_models(run_dir).get(node, "?")
        issue = _dispatched_issue(run_dir)
        monitor_age_s = time.time() - monitor_path.stat().st_mtime
        # STALE_PROGRESS means a run that CLAIMS to be running has not progressed
        # in 15 min -- a genuine stall. A finished/dead run (process_running=False)
        # whose monitor file is merely old is NOT stalled progress; it reports its
        # terminal status. Without this ordering a dead BLOCKED run re-emitted
        # STALE_PROGRESS every bridge cycle forever while the fleet was parked
        # (e.g. #1500 after the codex outage killed its run).
        if m.get("process_running"):
            state = "STALE_PROGRESS" if monitor_age_s > 900 else "LIVE"
        else:
            state = m.get("current_status") or "NO_ACTIVE_PROCESS"
        return {
            "state": state,
            "observer_fresh": True,
            "progress_age_s": int(monitor_age_s),
            "issue": issue,
            "agent": node,
            "model": model,
            "elapsed_s": int(m.get("elapsed_seconds") or 0),
        }
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"state": "observer_fresh_monitor_unreadable", "observer_fresh": True, "error": str(exc)[:200]}


def _candidate_dirs(checkpoint: BridgeCheckpoint, replay_last: bool) -> list[Path]:
    if replay_last:
        return sorted(RECEIPTS.iterdir(), key=lambda p: p.stat().st_mtime)[-1:]
    pending = [RECEIPTS / name for name in checkpoint.pending_dirs]
    new_dirs = [
        d
        for d in RECEIPTS.iterdir()
        if d.is_dir() and d.stat().st_mtime > checkpoint.last_mtime
    ]
    by_name = {p.name: p for p in pending + new_dirs if p.exists() and p.is_dir()}
    return sorted(by_name.values(), key=lambda p: p.stat().st_mtime)


def main() -> None:
    once = "--once" in sys.argv
    replay_last = "--replay-last" in sys.argv
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(BRIDGE_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"schema": "project_watchdog.notify_bridge_result.v1", "status": "LOCKED", "scanned": 0, "pushed": []}, indent=1))
        os.close(lock_fd)
        return
    checkpoint = _load_checkpoint()
    dirs = _candidate_dirs(checkpoint, replay_last)
    results = []
    max_mtime = checkpoint.last_mtime
    pending_dirs = set(checkpoint.pending_dirs)
    try:
        for ev in list(checkpoint.pending.values()):
            results.append(deliver(ev, checkpoint, fresh=True))
        for d in dirs:
            ev = summarize(d)
            if ev is None:
                continue
            if ev.get("kind") == "pending_receipt":
                pending_dirs.add(d.name)
                continue
            pending_dirs.discard(d.name)
            if ev.get("kind") != "tick":
                continue
            fresh = (time.time() - d.stat().st_mtime) < 900
            results.append(deliver(ev, checkpoint, fresh=fresh))
            max_mtime = max(max_mtime, d.stat().st_mtime)
        checkpoint.pending_dirs = sorted(pending_dirs)
        if not replay_last:
            checkpoint.last_mtime = max_mtime
        if not results:
            stream = STATE_ROOT / "events.jsonl"
            with stream.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "schema": "project_watchdog.terminal_event.v1",
                    "ts": _now_iso(),
                    "kind": "heartbeat",
                    **_heartbeat_payload(),
                }, sort_keys=True) + "\n")
        _save_checkpoint(checkpoint)
    finally:
        os.close(lock_fd)
    print(json.dumps({"schema": "project_watchdog.notify_bridge_result.v1",
                      "status": "OK", "scanned": len(dirs), "pushed": results}, indent=1))
    _ = once


if __name__ == "__main__":
    main()
