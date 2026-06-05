#!/usr/bin/env python3
"""Maintain artifact-backed agent status.

This module uses only the Python standard library so it can run inside any
project checkout without dependency setup.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# dotenv_helper: not used — AGENT_STATUS_DIR / AGENT_STATUS_CAMPAIGN are optional process env only.


VALID_STATES = {
    "not_started",
    "running",
    "needs_attention",
    "blocked",
    "failed",
    "passed_scoped_gate",
    "done",
    "idle",
}

SCHEMA = "agent_status.v1"

VALID_ARTIFACT_KINDS = {
    "mockup",
    "image",
    "table",
    "report",
    "log",
    "proof",
    "other",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = value.strip("-")
    return value or "agent-status"


def default_status_dir(campaign: str | None, explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env_dir = os.environ.get("AGENT_STATUS_DIR")
    if env_dir:
        return Path(env_dir)
    slug = safe_slug(campaign or os.environ.get("AGENT_STATUS_CAMPAIGN", "agent-status"))
    return Path(".plan-iterate") / slug / "status"


def status_paths(status_dir: Path) -> dict[str, Path]:
    return {
        "dir": status_dir,
        "status": status_dir / "status.json",
        "events": status_dir / "events.jsonl",
        "proof_manifest": status_dir / "proof_manifest.json",
        "html": status_dir / "STATUS.html",
    }


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_event(paths: dict[str, Path], event: str, data: dict[str, Any]) -> None:
    paths["events"].parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": utc_now(),
        "event": event,
        "data": data,
    }
    with paths["events"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_status(paths: dict[str, Path]) -> dict[str, Any]:
    payload = read_json(paths["status"], {})
    if not payload:
        raise SystemExit(f"status not initialized: {paths['status']}")
    return payload


def normalize_list(values: list[str] | None) -> list[str]:
    return [value for value in (values or []) if value]


def parse_option(raw: str) -> dict[str, str]:
    # Accept "A=Label: meaning" or just free text.
    if "=" not in raw:
        return {"id": "", "label": raw, "meaning": ""}
    ident, rest = raw.split("=", 1)
    if ":" in rest:
        label, meaning = rest.split(":", 1)
    else:
        label, meaning = rest, ""
    return {
        "id": ident.strip(),
        "label": label.strip(),
        "meaning": meaning.strip(),
    }


def proof_manifest(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "agent_status.proof_manifest.v1",
        "campaign_id": status.get("campaign_id", ""),
        "updated_at": status.get("updated_at", ""),
        "proofs": status.get("proofs", []),
        "last_completed": status.get("last_completed", {}),
        "not_proven": status.get("not_proven", []),
        "blockers": status.get("blockers", []),
        "artifacts": status.get("artifacts", []),
    }


def validate_status(status: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if status.get("schema") != SCHEMA:
        errors.append("schema must be agent_status.v1")
    if not status.get("campaign_id"):
        errors.append("campaign_id is required")
    if status.get("state") not in VALID_STATES:
        errors.append(f"invalid state: {status.get('state')!r}")
    if not status.get("goal"):
        errors.append("goal is required")
    for key in ("blockers", "not_proven", "proofs", "do_not_do_next", "artifacts"):
        value = status.get(key, [])
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")
    if status.get("state") == "done":
        if status.get("not_proven"):
            errors.append("state=done requires not_proven to be empty or moved out of goal scope")
        proof_path = (status.get("last_completed") or {}).get("proof_path")
        if not proof_path:
            errors.append("state=done requires last_completed.proof_path")
    return errors


def render_html(status: dict[str, Any]) -> str:
    status_json = json.dumps(status, indent=2, sort_keys=True)
    escaped_status_json = status_json.replace("</", "<\\/")
    title = html.escape(str(status.get("campaign_id", "agent-status")))
    goal = html.escape(str(status.get("goal", "")))
    state = html.escape(str(status.get("state", "")))
    last = status.get("last_completed") or {}
    next_action = status.get("next_action") or {}

    def pills_for_state(value: str) -> str:
        if value in {"done", "passed_scoped_gate"}:
            cls = "good"
        elif value in {"blocked", "failed", "needs_attention"}:
            cls = "bad" if value in {"blocked", "failed"} else "warn"
        elif value == "running":
            cls = "blue"
        else:
            cls = "warn"
        return f'<span class="pill {cls}">{html.escape(value)}</span>'

    def list_items(items: list[Any]) -> str:
        if not items:
            return "<li>None recorded.</li>"
        return "\n".join(f"<li>{html.escape(str(item))}</li>" for item in items)

    def roadmap_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<tr><td colspan="3">No roadmap items recorded.</td></tr>'
        out: list[str] = []
        for row in rows:
            status_value = str(row.get("status", "unknown"))
            if status_value.lower() in {"passed", "done", "complete", "accepted"}:
                cls = "good"
            elif status_value.lower() in {"blocked", "failed"}:
                cls = "bad"
            elif status_value.lower() in {"running"}:
                cls = "blue"
            else:
                cls = "warn"
            out.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('area', '')))}</td>"
                f"<td><span class=\"pill {cls}\">{html.escape(status_value)}</span></td>"
                f"<td>{html.escape(str(row.get('evidence', row.get('next', ''))))}</td>"
                "</tr>"
            )
        return "\n".join(out)

    def decision_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<tr><td colspan="3">No human decision requested.</td></tr>'
        out = []
        for row in rows:
            out.append(
                "<tr>"
                f"<td><code>{html.escape(str(row.get('id', '')))}</code></td>"
                f"<td>{html.escape(str(row.get('label', '')))}</td>"
                f"<td>{html.escape(str(row.get('meaning', '')))}</td>"
                "</tr>"
            )
        return "\n".join(out)
    def artifact_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<tr><td colspan="4">No visual artifacts registered.</td></tr>'
        out = []
        for row in rows:
            href = html.escape(str(row.get("path", "")))
            out.append(
                "<tr>"
                f"<td><span class=\"pill blue\">{html.escape(str(row.get('kind', '')))}</span></td>"
                f"<td>{html.escape(str(row.get('label', '')))}</td>"
                f"<td><code>{href}</code></td>"
                f"<td>{html.escape(str(row.get('caption', '')))}</td>"
                "</tr>"
            )
        return "\n".join(out)



    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Status — {title}</title>
  <style>
    :root {{
      --bg: #0b1020; --panel: #111a2f; --panel2:#0f1729; --ink: #edf2ff;
      --muted: #a6b4d6; --line: #2a3a5c; --good: #63d297; --warn: #f7c56d;
      --bad: #ff6b6b; --blue: #85b7ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; max-width:1120px; padding:24px; background:var(--bg); color:var(--ink);
      font:15px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    a {{ color: var(--blue); }}
    .topline {{ color:var(--muted); font-size:12px; letter-spacing:.08em; text-transform:uppercase; margin-bottom:8px; }}
    .hero {{ border:2px solid var(--warn); background:linear-gradient(180deg, rgba(247,197,109,.13), rgba(17,26,47,.96));
      border-radius:16px; padding:22px 24px; margin-bottom:16px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(26px,4vw,42px); line-height:1.05; letter-spacing:-.03em; }}
    h2 {{ margin:0 0 8px; color:var(--muted); font-size:12px; letter-spacing:.11em; text-transform:uppercase; }}
    section {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px 18px; margin-bottom:14px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    @media (max-width:760px) {{ .grid {{ grid-template-columns:1fr; }} }}
    .card {{ background:rgba(11,16,32,.72); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
    .pill {{ display:inline-flex; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; border:1px solid currentColor; }}
    .good {{ color:var(--good); background:rgba(99,210,151,.10); }}
    .warn {{ color:var(--warn); background:rgba(247,197,109,.10); }}
    .bad {{ color:var(--bad); background:rgba(255,107,107,.10); }}
    .blue {{ color:var(--blue); background:rgba(133,183,255,.10); }}
    table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }}
    th,td {{ text-align:left; vertical-align:top; padding:9px 8px; border-bottom:1px solid var(--line); }}
    th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
    tr:last-child td {{ border-bottom:0; }}
    ul,ol {{ margin:8px 0 0; padding-left:1.25rem; }}
    li {{ margin:7px 0; }}
    .small {{ color:var(--muted); font-size:13px; }}
    .mono {{ background:#07101f; border:1px solid var(--line); color:#d9e7ff; border-radius:10px; padding:12px; overflow:auto; font-size:12px; white-space:pre-wrap; }}
    body[data-stale="true"] .stale-warning {{ display:block; }}
    .stale-warning {{ display:none; border-left:4px solid var(--bad); padding:10px 12px; background:rgba(255,107,107,.10); border-radius:8px; margin-top:12px; }}
  </style>
</head>
<body>
  <div class="topline">Agent status · artifact-backed · no dashboard theater</div>
  <header class="hero">
    <h1>{title}</h1>
    <p data-goal>{goal}</p>
    <p>Current state: <span data-state-pill>{pills_for_state(str(status.get("state", "")))}</span></p>
    <p class="small">Updated: <span data-updated>{html.escape(str(status.get("updated_at", "")))}</span></p>
    <div class="stale-warning">Status is stale. Do not infer active progress.</div>
  </header>

  <div class="grid">
    <section>
      <h2>Where we are</h2>
      <p><strong>Last completed:</strong> {html.escape(str(last.get("label", "None recorded")))}</p>
      <p><strong>Verdict:</strong> {html.escape(str(last.get("verdict", "")))}</p>
      <p><strong>Proof:</strong> <code>{html.escape(str(last.get("proof_path", "")))}</code></p>
    </section>

    <section>
      <h2>Next action</h2>
      <p><strong>Owner:</strong> {html.escape(str(next_action.get("owner", "none")))}</p>
      <p><strong>Action:</strong> {html.escape(str(next_action.get("label", "")))}</p>
      <p><strong>Why:</strong> {html.escape(str(next_action.get("why", "")))}</p>
    </section>
  </div>

  <section>
    <h2>Current step</h2>
    <p><strong>{html.escape(str((status.get("current_step") or {}).get("label", "")))}</strong></p>
    <p class="small">Status: {html.escape(str((status.get("current_step") or {}).get("status", "")))}</p>
  </section>

  <section>
    <h2>Not proven / out of current proof scope</h2>
    <ul>{list_items(status.get("not_proven", []))}</ul>
  </section>

  <section>
    <h2>Blockers</h2>
    <ul>{list_items(status.get("blockers", []))}</ul>
  </section>

  <section>
    <h2>Do not do next</h2>
    <ul>{list_items(status.get("do_not_do_next", []))}</ul>
  </section>

  <section>
    <h2>Roadmap</h2>
    <table>
      <thead><tr><th>Area</th><th>Status</th><th>Evidence / next proof</th></tr></thead>
      <tbody>{roadmap_rows(status.get("roadmap", []))}</tbody>
    </table>
  </section>

  <section>
    <h2>Human decisions</h2>
    <table>
      <thead><tr><th>Choice</th><th>Label</th><th>Meaning</th></tr></thead>
      <tbody>{decision_rows(status.get("human_decisions", []))}</tbody>
    </table>
  </section>

  <section>
    <h2>Artifacts</h2>
    <table>
      <thead><tr><th>Kind</th><th>Label</th><th>Path</th><th>Caption</th></tr></thead>
      <tbody data-artifacts>{artifact_rows(status.get("artifacts", []))}</tbody>
    </table>
  </section>

  <section>
    <h2>Proof manifest</h2>
    <pre class="mono">{html.escape(json.dumps(status.get("proofs", []), indent=2, sort_keys=True))}</pre>
  </section>

  <section>
    <h2>Raw status.json</h2>
    <pre class="mono" data-raw-status>{html.escape(status_json)}</pre>
  </section>

  <script>
    window.__INITIAL_STATUS__ = {escaped_status_json};

    async function refreshStatus() {{
      try {{
        const res = await fetch("./status.json?ts=" + Date.now(), {{ cache: "no-store" }});
        if (!res.ok) return;
        const status = await res.json();
        const raw = document.querySelector("[data-raw-status]");
        if (raw) raw.textContent = JSON.stringify(status, null, 2);
        const stateEl = document.querySelector("[data-state-pill]");
        if (stateEl) stateEl.textContent = status.state || "";
        const goalEl = document.querySelector("[data-goal]");
        if (goalEl) goalEl.textContent = status.goal || "";
        const updated = new Date(status.updated_at);
        const ageSeconds = Math.floor((Date.now() - updated.getTime()) / 1000);
        const upd = document.querySelector("[data-updated]");
        if (upd) upd.textContent = status.updated_at + " · " + ageSeconds + "s ago";
        document.body.dataset.stale = ageSeconds > 300 ? "true" : "false";
        document.body.dataset.state = status.state || "";
      }} catch (_) {{
        const status = window.__INITIAL_STATUS__;
        const updated = new Date(status.updated_at);
        const ageSeconds = Math.floor((Date.now() - updated.getTime()) / 1000);
        document.body.dataset.stale = ageSeconds > 300 ? "true" : "false";
      }}
    }}
    refreshStatus();
    setInterval(refreshStatus, 5000);
  </script>
</body>
</html>
"""


def persist(paths: dict[str, Path], status: dict[str, Any], *, event: str, event_data: dict[str, Any]) -> None:
    status["updated_at"] = utc_now()
    errors = validate_status(status)
    if errors:
        raise SystemExit("invalid status:\n- " + "\n- ".join(errors))
    write_json(paths["status"], status)
    write_json(paths["proof_manifest"], proof_manifest(status))
    paths["html"].write_text(render_html(status), encoding="utf-8")
    append_event(paths, event, event_data)


def cmd_init(args: argparse.Namespace) -> None:
    status_dir = default_status_dir(args.campaign, args.status_dir)
    paths = status_paths(status_dir)
    status = {
        "schema": SCHEMA,
        "campaign_id": args.campaign,
        "updated_at": utc_now(),
        "state": args.state,
        "goal": args.goal,
        "current_step": {"id": "", "label": "Initialized", "status": "not_started"},
        "last_completed": {"label": "", "verdict": "", "proof_path": ""},
        "next_action": {"owner": "agent", "label": "Start work", "why": "Campaign initialized."},
        "human_decision_required": False,
        "human_decisions": [],
        "blockers": [],
        "not_proven": normalize_list(args.not_proven),
        "do_not_do_next": normalize_list(args.do_not_do_next),
        "proofs": [],
        "artifacts": [],
        "roadmap": [],
        "metadata": {},
    }
    persist(paths, status, event="initialized", event_data={"campaign_id": args.campaign, "goal": args.goal})
    print(paths["html"])


def cmd_update(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    if args.state:
        status["state"] = args.state
    if args.current_step:
        status["current_step"] = {
            "id": safe_slug(args.current_step),
            "label": args.current_step,
            "status": args.step_status or status.get("state", "running"),
        }
    if args.next_action:
        status["next_action"] = {
            "owner": args.next_owner,
            "label": args.next_action,
            "why": args.next_why or "",
        }
    if args.blocker:
        status["blockers"] = normalize_list(args.blocker)
    if args.not_proven:
        status["not_proven"] = normalize_list(args.not_proven)
    if args.do_not_do_next:
        status["do_not_do_next"] = normalize_list(args.do_not_do_next)
    persist(paths, status, event="updated", event_data={"state": status.get("state"), "current_step": status.get("current_step")})
    print(paths["html"])


def cmd_gate_passed(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    status["state"] = args.state
    proof = {
        "kind": "gate",
        "label": args.label,
        "path": args.proof,
        "verdict": args.verdict,
        "recorded_at": utc_now(),
    }
    status.setdefault("proofs", []).append(proof)
    status["last_completed"] = {
        "label": args.label,
        "verdict": args.verdict,
        "proof_path": args.proof,
    }
    status["current_step"] = {
        "id": safe_slug(args.label),
        "label": args.label,
        "status": "passed",
    }
    if args.next_action:
        status["next_action"] = {
            "owner": args.next_owner,
            "label": args.next_action,
            "why": args.next_why or "Previous gate passed.",
        }
    if args.not_proven:
        status["not_proven"] = normalize_list(args.not_proven)
    if args.do_not_do_next:
        status["do_not_do_next"] = normalize_list(args.do_not_do_next)
    persist(paths, status, event="gate_passed", event_data=proof)
    print(paths["html"])


def cmd_needs_human(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    status["state"] = "needs_attention"
    status["human_decision_required"] = True
    status["next_action"] = {
        "owner": "human",
        "label": args.question,
        "why": args.why or "The agent needs a human decision before continuing.",
    }
    status["human_decisions"] = [parse_option(item) for item in (args.option or [])]
    persist(paths, status, event="needs_human", event_data={"question": args.question, "options": args.option or []})
    print(paths["html"])


def cmd_blocked(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    status["state"] = "blocked"
    status["blockers"] = normalize_list(args.blocker or [args.reason])
    status["next_action"] = {
        "owner": args.next_owner,
        "label": args.next_action or "Resolve blocker",
        "why": args.reason,
    }
    persist(paths, status, event="blocked", event_data={"reason": args.reason, "blockers": status["blockers"]})
    print(paths["html"])



def cmd_artifact_add(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    kind = str(args.kind).strip().lower()
    if kind not in VALID_ARTIFACT_KINDS:
        raise SystemExit(f"invalid artifact kind {kind!r}; use one of: {', '.join(sorted(VALID_ARTIFACT_KINDS))}")
    entry = {
        "kind": kind,
        "label": args.label,
        "path": args.path,
        "caption": args.caption or "",
        "recorded_at": utc_now(),
    }
    status.setdefault("artifacts", []).append(entry)
    persist(paths, status, event="artifact_added", event_data=entry)
    print(paths["html"])


def cmd_event(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    data = {"message": args.message}
    if args.data:
        data.update(json.loads(args.data))
    append_event(paths, args.event, data)
    print(paths["events"])


def cmd_render(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    paths["html"].parent.mkdir(parents=True, exist_ok=True)
    paths["html"].write_text(render_html(status), encoding="utf-8")
    write_json(paths["proof_manifest"], proof_manifest(status))
    print(paths["html"])


def cmd_validate(args: argparse.Namespace) -> None:
    paths = status_paths(default_status_dir(args.campaign, args.status_dir))
    status = load_status(paths)
    errors = validate_status(status)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"ok": True, "status": str(paths["status"])}, indent=2))




def main(argv: list[str] | None = None) -> int:
    """Compatibility entrypoint for tests and legacy callers."""
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from cli import app

    args = list(argv) if argv is not None else sys.argv[1:]
    app(args=args, prog_name="agent-status", standalone_mode=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
