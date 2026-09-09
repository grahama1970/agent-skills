#!/usr/bin/env python3
"""Push project-watchdog receipts to ops-discord and the Pi Switchboard.

The watchdog's built-in alerting only fires for BLOCKED/NEEDS_ATTENTION/idle
and dedupes by fingerprint per 24h, so the human and the project agent had no
continuous visibility. This bridge tails the receipts directory with a cursor
and pushes EVERY eventful receipt (COMPLETED included) to:

  1. ops-discord notify --webhook watchdog   (human push channel)
  2. Switchboard POST /emit -> agent inbox   (project-agent push channel,
     read with the emit_message inbox tool)

Each event includes: outcome, project, issue, summary, triage-error codes,
seat activity (fixer/reviewer/classifier from workflow_phases and the live
tau-stream-monitor), and any pydantic/validation violations found in the
receipt payload.

Run from cron every 5 minutes. Delivery failure never raises; it prints a
JSON result and exits 0 so the cron line stays quiet unless truly broken.

# ponytail: single-cursor sequential scan; receipts arrive ~1/5min, no need for parallelism.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STATE_ROOT = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", Path.home() / ".local/state/project-watchdog"))
RECEIPTS = STATE_ROOT / "receipts"
CURSOR = STATE_ROOT / "notify-bridge-cursor.json"
SWITCHBOARD = os.environ.get("SWITCHBOARD_URL", "http://127.0.0.1:7890")
PI_AGENT_INBOX = os.environ.get("WATCHDOG_BRIDGE_PI_INBOX", "agent-skills")
OPS_DISCORD = Path(__file__).resolve().parents[2] / "ops-discord" / "run.sh"


def _load_cursor() -> float:
    try:
        return float(json.loads(CURSOR.read_text())["last_mtime"])
    except Exception:
        return time.time() - 3600  # first run: last hour only


def _save_cursor(mtime: float) -> None:
    CURSOR.write_text(json.dumps({"last_mtime": mtime, "updated_at": time.time()}))


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
        except Exception:
            continue
        model = data.get("requested_model") or data.get("model")
        if model:
            out.setdefault(Path(f).parent.name, model)
    # planned model from the dag: nodes[].context.handler_policy.model_policy
    for f in _g.glob(str(receipt_dir / "ask/*/tau-receipts/source-dag.json")) + _g.glob(str(receipt_dir / "ask/*/dag.json")):
        try:
            data = json.loads(Path(f).read_text())
        except Exception:
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
    except Exception:
        return "-"


def _live_seat(receipt_dir: Path) -> str | None:
    mon = receipt_dir / "tau-stream-monitor.json"
    if not mon.is_file():
        return None
    try:
        m = json.loads(mon.read_text())
    except Exception:
        return None
    ev = m.get("latest_event") or {}
    node = ev.get("node_id") or m.get("current_node") or "-"
    model = _node_models(receipt_dir).get(node, "?")
    if m.get("process_running"):
        return f"RUNNING agent={node} model={model} elapsed={int(m.get('elapsed_seconds') or 0)}s"
    return f"finished status={m.get('current_status')} last-agent={node} model={model}"


def summarize(receipt_dir: Path) -> dict | None:
    rj = receipt_dir / "receipt.json"
    if not rj.is_file():
        return None
    try:
        r = json.loads(rj.read_text())
    except Exception as exc:
        return {"kind": "unreadable_receipt", "dir": receipt_dir.name, "error": str(exc)[:200]}
    handled = (r.get("handled_issues") or [{}])[0]
    triage = handled.get("triage") or {}
    return {
        "kind": "tick",
        "dir": receipt_dir.name,
        "status": r.get("status"),
        "stop_reason": r.get("stop_reason"),
        "issue": handled.get("issue_number"),
        "repo": handled.get("repo"),
        "action": handled.get("action"),
        "summary": (handled.get("summary") or r.get("stop_reason") or "")[:300],
        "requires_human_input": r.get("requires_human_input"),
        "triage_code": triage.get("code"),
        "triage_cause": (triage.get("cause") or "")[:200],
        "seats": _seats(handled),
        "live": _live_seat(receipt_dir),
        "pydantic_violations": _pydantic_violations(r),
        "next_steps": (handled.get("authorized_agent_next_steps") or [])[:2],
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
    if ev.get("status") == "COMPLETED":
        return True
    if ev.get("requires_human_input") is True:
        return True
    if ev.get("requires_human_input") is False and ev.get("next_steps"):
        return False
    return ev.get("status") in {"BLOCKED", "NEEDS_ATTENTION"}


def push_webhook(ev: dict) -> str:
    if not requires_human_push(ev):
        return "skipped_machine_actionable"
    title = f"project-watchdog {ev.get('status')} — {ev.get('repo')}#{ev.get('issue')}"
    try:
        p = subprocess.run(
            [str(OPS_DISCORD), "notify", "--webhook", "watchdog", "--title", title,
             "--content", _fmt(ev), "--json"],
            capture_output=True, text=True, timeout=60,
        )
        for line in reversed(p.stdout.splitlines()):
            if '"status"' in line:
                return line.strip()
        return f"exit={p.returncode}"
    except Exception as exc:  # delivery failure never blocks
        return f"webhook_error: {exc}"[:200]


def switchboard_delivery_decision(ev: dict, *, fresh: bool) -> str | None:
    if not fresh:
        return "skipped_stale"
    if not requires_human_push(ev):
        return "skipped_machine_actionable"
    return None


def push_switchboard(ev: dict) -> str:
    body = json.dumps({
        "from": "project-watchdog-bridge",
        "to": PI_AGENT_INBOX,
        "type": "alert" if ev.get("status") != "COMPLETED" else "info",
        "priority": "high" if ev.get("status") in ("BLOCKED", "NEEDS_ATTENTION") else "normal",
        "subject": f"watchdog {ev.get('status')} {ev.get('repo')}#{ev.get('issue')}",
        "message": _fmt(ev),
    }).encode()
    req = urllib.request.Request(f"{SWITCHBOARD}/emit", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return f"http={resp.status}"
    except Exception as exc:
        return f"switchboard_error: {exc}"[:200]


def main() -> None:
    once = "--once" in sys.argv
    cursor = 0.0 if "--replay-last" in sys.argv else _load_cursor()
    if "--replay-last" in sys.argv:
        dirs = sorted(RECEIPTS.iterdir(), key=lambda p: p.stat().st_mtime)[-1:]
    else:
        dirs = sorted(
            (d for d in RECEIPTS.iterdir() if d.is_dir() and d.stat().st_mtime > cursor),
            key=lambda p: p.stat().st_mtime,
        )
    stream = STATE_ROOT / "events.jsonl"  # one JSON object per line; tail -F | jq
    results = []
    max_mtime = cursor
    for d in dirs:
        ev = summarize(d)
        max_mtime = max(max_mtime, d.stat().st_mtime)
        if ev is None or ev.get("kind") != "tick":
            continue
        with stream.open("a") as fh:
            fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": "receipt",
                "status": ev.get("status"),
                "issue": ev.get("issue"),
                "repo": ev.get("repo"),
                "summary": ev.get("summary"),
                "seat": ev.get("live"),
                "triage": ev.get("triage_code"),
                "pydantic": ev.get("pydantic_violations") or [],
                "next": (ev.get("next_steps") or [None])[0],
                "receipt": str(RECEIPTS / ev["dir"]),
            }) + "\n")
        fresh = (time.time() - d.stat().st_mtime) < 900  # stale receipts: log+webhook only, no session pings
        results.append({
            "dir": d.name, "status": ev.get("status"), "issue": ev.get("issue"),
            "webhook": push_webhook(ev),
            "switchboard": switchboard_delivery_decision(ev, fresh=fresh) or push_switchboard(ev),
        })
    if not results:
        # Heartbeat: a silent stream is indistinguishable from a dead one.
        import glob as _glob
        mons = sorted(_glob.glob(str(RECEIPTS / "*/tau-stream-monitor.json")), key=os.path.getmtime)
        live = ""
        if mons:
            try:
                m = json.loads(Path(mons[-1]).read_text())
                ev = m.get("latest_event") or {}
                run_dir = Path(mons[-1]).parent
                node = ev.get("node_id") or "-"
                model = _node_models(run_dir).get(node, "?")
                issue = _dispatched_issue(run_dir)
                state = "LIVE" if m.get("process_running") else m.get("current_status")
                live = {"state": state, "issue": issue, "agent": node, "model": model,
                        "elapsed_s": int(m.get("elapsed_seconds") or 0)}
            except Exception:
                pass
        with stream.open("a") as fh:
            fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": "heartbeat",
                **(live if isinstance(live, dict) else {"state": "no_active_run"}),
            }) + "\n")
    if max_mtime > cursor and "--replay-last" not in sys.argv:
        _save_cursor(max_mtime)
    print(json.dumps({"schema": "project_watchdog.notify_bridge_result.v1",
                      "scanned": len(dirs), "pushed": results}, indent=1))
    _ = once


if __name__ == "__main__":
    main()
