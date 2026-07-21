#!/usr/bin/env python3
"""Monitor Herdr workspaces and restart agents that stopped too early."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
import typer

SKILL_DIR = Path(__file__).resolve().parents[1]
STATE_ROOT = Path.home() / ".local" / "state" / "monitor-confused-agents"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
STATE_PATH = STATE_ROOT / "state.json"
LOCK_DIR = STATE_ROOT / "lock"
CRON_MARKER = "# monitor-confused-agents herdr cron"
DEFAULT_SPACE = "codex"
DEFAULT_CWD_PREFIX = str(Path.home() / "workspace" / "experiments")
DEFAULT_STOPPED_STATUSES = ("done", "idle", "blocked", "unknown")
DEFAULT_COOLDOWN_SECONDS = 60 * 60
DEFAULT_SOCKET_PATH = Path.home() / ".config" / "herdr" / "herdr.sock"
GOAL_FILE_NAMES = (
    "IMMUTABLE_GOAL.md",
    "GOAL.md",
    ".goal",
    ".codex/goal.json",
    ".codex/GOAL.md",
    ".tau/goal.json",
)

EARLY_STOP_PATTERNS = [
    r"\bno active blocker\b",
    r"\bno current blocker\b",
    r"\bno active confusion\b",
    r"\bwhat remains\b",
    r"\bremaining work\b",
    r"\bif continuing\b",
    r"\bif you want\b",
    r"\bcould pursue next steps\b",
    r"\bbroader route audit\b",
    r"\bstop condition reached\b",
    r"\bstop hook \((?:blocked|stopped)\)",
    r"\bstatus response blocked as too vague\b",
    r"\bclosure claim lacks deterministic proof\b",
]

HUMAN_BLOCKER_PATTERNS = [
    r"\bneeds human\b",
    r"\bhuman intervention\b",
    r"\bhuman decision\b",
    r"\bwaiting for human\b",
    r"\bmissing credential\b",
    r"\bmissing secret\b",
    r"\bmissing api key\b",
    r"\bapproval required\b",
    r"\bexternal state\b",
    r"\bcannot obtain\b",
    r"\bblocked_by_systemic_failure\b",
]

app = typer.Typer(add_completion=False, help="Monitor Herdr spaces for stopped/confused agents.")


@dataclass(frozen=True)
class HerdrResponse:
    request: dict[str, Any]
    response: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"request": self.request, "response": self.response}


class HerdrClient:
    def __init__(self, socket_path: Path, timeout_s: float = 10.0) -> None:
        self.socket_path = socket_path
        self.timeout_s = timeout_s
        self.counter = 0
        self.trace: list[dict[str, Any]] = []

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        request = {
            "id": f"monitor_confused_agents_{self.counter}",
            "method": method,
            "params": params or {},
        }
        started = datetime.now(UTC)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.socket_path))
                sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
                data = b""
                while b"\n" not in data:
                    chunk = sock.recv(262144)
                    if not chunk:
                        break
                    data += chunk
        except OSError as exc:
            logger.error("Herdr socket call failed for {}: {}", method, exc)
            response = {"error": {"code": "socket_error", "message": str(exc)}}
        else:
            line = data.split(b"\n", 1)[0]
            try:
                response = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Herdr socket returned invalid JSON for {}: {}", method, exc)
                response = {"error": {"code": "invalid_json", "message": str(exc), "raw": line.decode("utf-8", "replace")[:2000]}}
        record = HerdrResponse(request=request, response=response).as_dict()
        record["duration_seconds"] = (datetime.now(UTC) - started).total_seconds()
        self.trace.append(redact_api_record(record))
        if "error" in response:
            raise RuntimeError(f"{method} failed: {response['error']}")
        return response["result"]


@app.command("tick")
def tick_command(
    apply: bool = typer.Option(False, "--apply", help="Send restart/intervention prompts to stopped panes."),
    space: str = typer.Option(DEFAULT_SPACE, "--space", help="Herdr workspace id, number, or label. Use '*' for all."),
    socket_path: Path = typer.Option(DEFAULT_SOCKET_PATH, "--socket-path", help="Herdr Unix socket path."),
    cwd_prefix: str = typer.Option(DEFAULT_CWD_PREFIX, "--cwd-prefix", help="Only monitor panes under this cwd prefix."),
    include_agent: list[str] = typer.Option(["codex", "claude"], "--include-agent", help="Agent labels to monitor."),
    stopped_status: list[str] = typer.Option(list(DEFAULT_STOPPED_STATUSES), "--stopped-status", help="Statuses treated as stopped."),
    cooldown_seconds: int = typer.Option(DEFAULT_COOLDOWN_SECONDS, "--cooldown-seconds", min=0, help="Per-pane prompt cooldown."),
    max_prompts: int = typer.Option(20, "--max-prompts", min=1, help="Maximum prompts per tick."),
    only_obvious_early_stops: bool = typer.Option(False, "--only-obvious-early-stops", help="Prompt only stopped panes with early-stop transcript markers."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Print JSON receipt."),
) -> None:
    """Run one bounded Herdr monitor tick."""
    ensure_dirs()
    exit_code, receipt = tick(
        apply=apply,
        space=space,
        socket_path=socket_path,
        cwd_prefix=cwd_prefix,
        include_agents={item for item in include_agent if item},
        stopped_statuses={item.lower() for item in stopped_status},
        cooldown_seconds=cooldown_seconds,
        max_prompts=max_prompts,
        only_obvious_early_stops=only_obvious_early_stops,
    )
    if json_output:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    raise typer.Exit(exit_code)


@app.command("status")
def status_command() -> None:
    """Report installed cron, latest receipts, and monitor state."""
    ensure_dirs()
    print(json.dumps(status_payload(), indent=2, sort_keys=True))


@app.command("install-cron")
def install_cron_command(
    apply: bool = typer.Option(False, "--apply", help="Install the cron entry."),
    minute: str = typer.Option("*/10", "--minute", help="Cron minute field."),
    space: str = typer.Option(DEFAULT_SPACE, "--space", help="Herdr space/workspace to monitor."),
    apply_prompts: bool = typer.Option(True, "--apply-prompts/--dry-run-prompts", help="Cron should send restart prompts."),
    cwd_prefix: str = typer.Option(DEFAULT_CWD_PREFIX, "--cwd-prefix", help="Cron cwd-prefix scope."),
) -> None:
    """Install or preview a 10 minute cron entry."""
    ensure_dirs()
    exit_code, payload = install_cron(
        apply=apply,
        minute=minute,
        space=space,
        apply_prompts=apply_prompts,
        cwd_prefix=cwd_prefix,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise typer.Exit(exit_code)


@app.command("probe-text")
def probe_text_command(
    pane_id: str = typer.Option(..., "--pane-id", help="Herdr pane id."),
    agent: str = typer.Option("agent", "--agent", help="Agent label."),
    reason: str = typer.Option("early_stop", "--reason", help="Selection reason."),
    action: str = typer.Option("restart_continue", "--action", help="restart_continue or needs_human"),
    cwd: str = typer.Option("", "--cwd", help="Pane cwd."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Render the exact prompt sent to a stopped agent."""
    text = build_prompt({
        "pane_id": pane_id,
        "agent": agent,
        "cwd": cwd,
        "selection_reasons": [reason],
        "action": action,
    })
    if json_output:
        print(json.dumps({
            "schema": "agent_skills.monitor_confused_agents.probe.v1",
            "pane_id": pane_id,
            "agent": agent,
            "action": action,
            "text": text,
        }, indent=2, sort_keys=True))
    else:
        print(text)


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log_event(run_id: str, message: str, **fields: Any) -> None:
    event = {"ts": now_iso(), "run_id": run_id, "message": message, **fields}
    with (LOG_DIR / "monitor-confused-agents.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": "agent_skills.monitor_confused_agents.state.v1", "prompts": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("Monitor state JSON is corrupt: {}", STATE_PATH)
        return {"schema": "agent_skills.monitor_confused_agents.state.v1", "prompts": {}}
    if not isinstance(payload, dict):
        return {"schema": "agent_skills.monitor_confused_agents.state.v1", "prompts": {}}
    payload.setdefault("schema", "agent_skills.monitor_confused_agents.state.v1")
    payload.setdefault("prompts", {})
    return payload


def acquire_lock(run_id: str) -> bool:
    try:
        LOCK_DIR.mkdir(parents=True)
    except FileExistsError:
        return False
    write_json(LOCK_DIR / "owner.json", {"run_id": run_id, "pid": os.getpid(), "ts": now_iso()})
    return True


def release_lock() -> None:
    try:
        (LOCK_DIR / "owner.json").unlink(missing_ok=True)
        LOCK_DIR.rmdir()
    except OSError:
        logger.error("Could not release monitor lock at {}", LOCK_DIR)
        return


def tick(
    *,
    apply: bool,
    space: str,
    socket_path: Path,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    cooldown_seconds: int,
    max_prompts: int,
    only_obvious_early_stops: bool,
) -> tuple[int, dict[str, Any]]:
    run_id = f"monitor-confused-agents-{timestamp()}"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    events_path = receipt_dir / "events.jsonl"
    receipt: dict[str, Any] = {
        "schema": "agent_skills.monitor_confused_agents.tick_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "apply": apply,
        "receipt_dir": str(receipt_dir),
        "events_path": str(events_path),
        "log_file": str(LOG_DIR / "monitor-confused-agents.log"),
        "state_path": str(STATE_PATH),
        "selection": {
            "space": space,
            "socket_path": str(socket_path),
            "cwd_prefix": cwd_prefix,
            "include_agents": sorted(include_agents),
            "stopped_statuses": sorted(stopped_statuses),
            "cooldown_seconds": cooldown_seconds,
            "max_prompts": max_prompts,
            "only_obvious_early_stops": only_obvious_early_stops,
        },
        "workspace": None,
        "api_trace": [],
        "observed_panes": 0,
        "stopped_panes": [],
        "selected_panes": [],
        "prompts": [],
        "errors": [],
    }
    append_jsonl(events_path, {"event": "tick_start", "ts": now_iso(), "apply": apply, "space": space})
    log_event(run_id, "tick_start", apply=apply, space=space)

    if not acquire_lock(run_id):
        receipt.update({"ok": False, "status": "BLOCKED", "errors": ["lock already held"]})
        return finish(receipt, 1)
    try:
        client = HerdrClient(socket_path)
        try:
            return tick_locked(
                client=client,
                receipt=receipt,
                events_path=events_path,
                apply=apply,
                space=space,
                cwd_prefix=cwd_prefix,
                include_agents=include_agents,
                stopped_statuses=stopped_statuses,
                cooldown_seconds=cooldown_seconds,
                max_prompts=max_prompts,
                only_obvious_early_stops=only_obvious_early_stops,
            )
        finally:
            receipt["api_trace"] = client.trace
    finally:
        release_lock()


def tick_locked(
    *,
    client: HerdrClient,
    receipt: dict[str, Any],
    events_path: Path,
    apply: bool,
    space: str,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    cooldown_seconds: int,
    max_prompts: int,
    only_obvious_early_stops: bool,
) -> tuple[int, dict[str, Any]]:
    try:
        workspace = resolve_workspace(client, space)
        workspace_ids = [item["workspace_id"] for item in workspace] if isinstance(workspace, list) else [workspace["workspace_id"]]
        receipt["workspace"] = workspace
        panes: list[dict[str, Any]] = []
        for workspace_id in workspace_ids:
            result = client.call("pane.list", {"workspace_id": workspace_id})
            panes.extend(result.get("panes", []))
    except RuntimeError as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
        return finish(receipt, 2)

    receipt["observed_panes"] = len(panes)
    state = load_state()
    now_epoch = int(datetime.now(UTC).timestamp())
    selected: list[dict[str, Any]] = []

    for pane in panes:
        candidate = classify_pane(
            client,
            pane,
            cwd_prefix=cwd_prefix,
            include_agents=include_agents,
            stopped_statuses=stopped_statuses,
            only_obvious_early_stops=only_obvious_early_stops,
        )
        if not candidate:
            continue
        pane_id = str(candidate["pane_id"])
        last_prompt_at = int(state.get("prompts", {}).get(pane_id, {}).get("last_prompt_epoch", 0) or 0)
        candidate["cooldown_active"] = cooldown_seconds > 0 and (now_epoch - last_prompt_at) < cooldown_seconds
        candidate["last_prompt_epoch"] = last_prompt_at or None
        receipt["stopped_panes"].append(candidate)
        append_jsonl(events_path, {"event": "stopped_pane", "ts": now_iso(), **candidate_without_text(candidate)})
        if not candidate["cooldown_active"] and len(selected) < max_prompts:
            selected.append(candidate)

    receipt["selected_panes"] = [candidate_without_text(item) for item in selected]

    for candidate in selected:
        prompt = build_prompt(candidate)
        prompt_path = Path(receipt["receipt_dir"]) / f"prompt-{candidate['pane_id'].replace(':', '_')}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_record: dict[str, Any] = {
            "pane_id": candidate["pane_id"],
            "agent": candidate.get("agent"),
            "agent_status": candidate.get("agent_status"),
            "action": candidate.get("action"),
            "classification": candidate.get("classification"),
            "selection_reasons": candidate.get("selection_reasons", []),
            "prompt_path": str(prompt_path),
            "sent": False,
            "send_api": [],
        }
        if apply:
            prompt_record["send_api"] = send_prompt(client, str(candidate["pane_id"]), prompt)
            prompt_record["sent"] = all("error" not in item.get("response", {}) for item in prompt_record["send_api"])
            if prompt_record["sent"]:
                state.setdefault("prompts", {})[str(candidate["pane_id"])] = {
                    "last_prompt_epoch": now_epoch,
                    "last_prompt_at": now_iso(),
                    "agent": candidate.get("agent"),
                    "cwd": candidate.get("cwd"),
                    "classification": candidate.get("classification"),
                    "action": candidate.get("action"),
                }
        receipt["prompts"].append(prompt_record)
        append_jsonl(events_path, {"event": "prompt", "ts": now_iso(), **prompt_record})

    if apply:
        write_json(STATE_PATH, state)

    receipt["status"] = "RESTART_PROMPTS_SENT" if apply and receipt["prompts"] else "OBSERVED"
    receipt["ok"] = all(item.get("sent", True) or not apply for item in receipt["prompts"])
    if apply and any(not item.get("sent") for item in receipt["prompts"]):
        receipt["status"] = "NEEDS_ATTENTION"
    return finish(receipt, 0 if receipt["ok"] else 1)


def resolve_workspace(client: HerdrClient, space: str) -> dict[str, Any] | list[dict[str, Any]]:
    result = client.call("workspace.list", {})
    workspaces = result.get("workspaces", [])
    if space == "*":
        return workspaces
    for workspace in workspaces:
        if str(workspace.get("workspace_id")) == space:
            return workspace
        if str(workspace.get("label")) == space:
            return workspace
        if str(workspace.get("number")) == space:
            return workspace
    raise RuntimeError(f"Herdr workspace not found for --space {space!r}")


def classify_pane(
    client: HerdrClient,
    pane: dict[str, Any],
    *,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    only_obvious_early_stops: bool,
) -> dict[str, Any] | None:
    label = str(pane.get("agent") or "")
    if include_agents and label not in include_agents:
        return None
    status = str(pane.get("agent_status") or "unknown").lower()
    if status not in stopped_statuses:
        return None
    cwd = str(pane.get("foreground_cwd") or pane.get("cwd") or "")
    if cwd_prefix and cwd and not cwd.startswith(cwd_prefix):
        return None
    pane_id = str(pane.get("pane_id") or "")
    if not pane_id:
        return None

    text = read_pane_text(client, pane_id)
    explain = explain_agent(client, pane_id)
    early_markers = find_patterns(text, EARLY_STOP_PATTERNS)
    human_markers = find_patterns(text, HUMAN_BLOCKER_PATTERNS)
    if only_obvious_early_stops and not early_markers:
        return None

    if human_markers and not early_markers:
        classification = "legitimate_human_blocker"
        action = "needs_human"
        reasons = [f"human_blocker:{item}" for item in human_markers[:5]]
    elif goal_allows_stop(text, cwd) and not early_markers:
        return None
    else:
        classification = "stopped_or_early_stop"
        action = "restart_continue"
        reasons = [f"stopped_status:{status}"]
        reasons.extend(f"early_stop:{item}" for item in early_markers[:6])
        if human_markers:
            reasons.extend(f"human_marker_overridden_by_early_stop:{item}" for item in human_markers[:3])
        immutable_goal = discover_immutable_goal(cwd)
        if immutable_goal.get("found"):
            reasons.append("immutable_goal_found")
        else:
            reasons.append("immutable_goal_unknown")

    return {
        "pane_id": pane_id,
        "terminal_id": pane.get("terminal_id"),
        "workspace_id": pane.get("workspace_id"),
        "tab_id": pane.get("tab_id"),
        "agent": label,
        "agent_status": status,
        "cwd": cwd,
        "classification": classification,
        "action": action,
        "selection_reasons": reasons,
        "early_stop_markers": early_markers,
        "human_blocker_markers": human_markers,
        "immutable_goal": discover_immutable_goal(cwd),
        "transcript_goal_claim": transcript_goal_claim(text),
        "recent_excerpt": text[-2400:],
        "explain_state": explain.get("state") if isinstance(explain, dict) else None,
    }


def read_pane_text(client: HerdrClient, pane_id: str) -> str:
    try:
        result = client.call("pane.read", {"pane_id": pane_id, "source": "recent_unwrapped", "lines": 140, "format": "text"})
    except RuntimeError:
        logger.error("Herdr pane.read failed for {}", pane_id)
        return ""
    text = result.get("read", {}).get("text")
    return text if isinstance(text, str) else ""


def explain_agent(client: HerdrClient, pane_id: str) -> dict[str, Any]:
    try:
        result = client.call("agent.explain", {"target": pane_id})
    except RuntimeError as exc:
        logger.error("Herdr agent.explain failed for {}: {}", pane_id, exc)
        return {"error": str(exc)}
    explain = result.get("explain")
    return explain if isinstance(explain, dict) else {}


def find_patterns(text: str, patterns: list[str]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for pattern in patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE | re.MULTILINE):
            matches.append(pattern)
    return matches


def send_prompt(client: HerdrClient, pane_id: str, prompt: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for method, params in [
        ("pane.send_text", {"pane_id": pane_id, "text": prompt}),
        ("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]}),
    ]:
        before = len(client.trace)
        try:
            client.call(method, params)
        except RuntimeError:
            logger.error("Herdr {} failed for pane {}", method, pane_id)
            pass
        records.extend(client.trace[before:])
    return records


def goal_allows_stop(text: str, cwd: str) -> bool:
    goal = discover_immutable_goal(cwd)
    claim = transcript_goal_claim(text)
    if not goal.get("found") and claim["state"] == "none":
        return True
    return claim["state"] == "achieved" and not find_patterns(text, EARLY_STOP_PATTERNS)


def transcript_goal_claim(text: str) -> dict[str, str]:
    lowered = text.lower()
    if re.search(r"\bimmutable goal\b.{0,160}\b(achieved|met|satisfied)\b", lowered, re.DOTALL):
        return {"state": "achieved", "source": "transcript"}
    if re.search(r"\bgoal\b.{0,160}\b(blocked|unmet|not met|not achieved|remaining)\b", lowered, re.DOTALL):
        return {"state": "unmet", "source": "transcript"}
    if "immutable goal" in lowered:
        return {"state": "mentioned", "source": "transcript"}
    return {"state": "none", "source": "transcript"}


def discover_immutable_goal(cwd: str) -> dict[str, Any]:
    if not cwd:
        return {"found": False, "source": None, "excerpt": ""}
    start = Path(cwd).expanduser()
    try:
        current = start.resolve()
    except OSError as exc:
        logger.error("Could not resolve cwd {} while discovering immutable goal: {}", cwd, exc)
        return {"found": False, "source": None, "excerpt": ""}
    for root in [current, *current.parents]:
        for name in GOAL_FILE_NAMES:
            path = root / name
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.error("Could not read immutable goal candidate {}: {}", path, exc)
                continue
            excerpt = compact_excerpt(text)
            return {"found": True, "source": str(path), "excerpt": excerpt}
        if root == root.parent:
            break
    return {"found": False, "source": None, "excerpt": ""}


def compact_excerpt(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


def build_prompt(candidate: dict[str, Any]) -> str:
    reasons = ", ".join(str(item) for item in candidate.get("selection_reasons", [])) or "stopped"
    cwd = candidate.get("cwd") or "unknown"
    pane_id = candidate.get("pane_id") or "unknown"
    agent = candidate.get("agent") or "agent"
    action = candidate.get("action") or "restart_continue"
    goal = candidate.get("immutable_goal") or {}
    goal_line = "not found in project files"
    if goal.get("found"):
        goal_line = f"{goal.get('source')}: {goal.get('excerpt')}"
    if action == "needs_human":
        instruction = (
            "You appear legitimately blocked. Do not bury the blocker in a final answer. "
            "Reply with the exact human decision, credential, authority, or external state you need. "
            "If the blocker is actually research or reviewer uncertainty, use $brave-search or $webgpt instead of stopping."
        )
    else:
        instruction = (
            "You stopped or went idle while the transcript still shows follow-up work or no real blocker. "
            "Resume the task now. Pick the next concrete remaining action, run it, and continue until a real blocker or deterministic proof exists. "
            "Use $brave-search for current external facts/docs before another stale retry. Use $webgpt/$ask with a concrete bundle when reviewer/oracle help would unblock you. "
            "Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain."
        )
    return (
        "RESTART CHECK FROM monitor-confused-agents\n\n"
        f"Herdr pane: {pane_id}\n"
        f"Agent: {agent}\n"
        f"Cwd: {cwd}\n"
        f"Immutable goal evidence: {goal_line}\n"
        f"Reason: {reasons}\n\n"
        f"{instruction}\n\n"
        "Respond and act with this operational shape:\n"
        "Status/Phase: <one line>\n"
        "Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>\n"
        "Now: <current file, command, artifact, or exact blocker>\n"
        "Evidence: <latest concrete command/result/artifact path, or NONE>\n"
        "Next: <one immediate action you will execute now, or STOP_ALLOWED because no immutable goal exists / goal is achieved>\n"
        "Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | CONFUSED_NEEDS_HUMAN | "
        "CAN_SELF_UNBLOCK_BRAVE_SEARCH | CAN_SELF_UNBLOCK_WEBGPT | DONE_WITH_RECEIPT>\n\n"
        "If the immutable goal is known and not achieved, keep going and use available tools until it is met. "
        "Do not claim complete unless you can cite deterministic local proof artifacts and there is no remaining user-requested work."
    )


def candidate_without_text(candidate: dict[str, Any]) -> dict[str, Any]:
    clean = dict(candidate)
    if "recent_excerpt" in clean and len(str(clean["recent_excerpt"])) > 400:
        clean["recent_excerpt"] = str(clean["recent_excerpt"])[-400:]
    return clean


def redact_api_record(record: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(record))
    result = clean.get("response", {}).get("result", {})
    if isinstance(result, dict):
        read = result.get("read")
        if isinstance(read, dict) and isinstance(read.get("text"), str) and len(read["text"]) > 1200:
            read["text"] = read["text"][-1200:]
        panes = result.get("panes")
        if isinstance(panes, list) and len(panes) > 30:
            result["panes"] = panes[:30]
            result["panes_truncated"] = len(panes) - 30
    return clean


def finish(receipt: dict[str, Any], exit_code: int) -> tuple[int, dict[str, Any]]:
    receipt_path = Path(receipt["receipt_dir"]) / "receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    append_jsonl(Path(receipt["events_path"]), {
        "event": "tick_finish",
        "ts": now_iso(),
        "status": receipt.get("status"),
        "ok": receipt.get("ok"),
        "receipt_path": str(receipt_path),
    })
    write_json(receipt_path, receipt)
    log_event(
        str(receipt["run_id"]),
        "tick_finish",
        status=receipt.get("status"),
        ok=receipt.get("ok"),
        receipt_path=str(receipt_path),
        exit_code=exit_code,
    )
    return exit_code, receipt


def status_payload() -> dict[str, Any]:
    receipts = sorted(RECEIPT_ROOT.glob("*/receipt.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    crontab_result = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    cron_stdout = crontab_result.stdout if crontab_result.returncode == 0 else ""
    return {
        "schema": "agent_skills.monitor_confused_agents.status.v1",
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "state_root": str(STATE_ROOT),
        "cron_installed": CRON_MARKER in cron_stdout,
        "cron_marker": CRON_MARKER,
        "log_file": str(LOG_DIR / "monitor-confused-agents.log"),
        "state_path": str(STATE_PATH),
        "latest_receipts": [str(path) for path in receipts[:5]],
    }


def install_cron(*, apply: bool, minute: str, space: str, apply_prompts: bool, cwd_prefix: str) -> tuple[int, dict[str, Any]]:
    script_path = SKILL_DIR / "run.sh"
    cron_log = LOG_DIR / "cron.log"
    tick_args = "--apply" if apply_prompts else ""
    line = (
        f"{minute} * * * * cd {shell_quote(str(SKILL_DIR))} && "
        f"{shell_quote(str(script_path))} tick {tick_args} --space {shell_quote(space)} --cwd-prefix {shell_quote(cwd_prefix)} "
        f">> {shell_quote(str(cron_log))} 2>&1 {CRON_MARKER}"
    ).replace("  ", " ").strip()
    current = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    existing = current.stdout if current.returncode == 0 else ""
    filtered = [item for item in existing.splitlines() if CRON_MARKER not in item]
    next_crontab = "\n".join(filtered + [line]).strip() + "\n"
    payload = {
        "schema": "agent_skills.monitor_confused_agents.cron_install.v1",
        "mocked": False,
        "live": True,
        "apply": apply,
        "cron_marker": CRON_MARKER,
        "cron_line": line,
        "would_replace_existing": CRON_MARKER in existing,
        "log_file": str(cron_log),
    }
    if not apply:
        payload["status"] = "DRY_RUN"
        return 0, payload
    proc = subprocess.run(["crontab", "-"], input=next_crontab, text=True, capture_output=True, check=False)
    payload["install_command"] = {"command": ["crontab", "-"], "exit_code": proc.returncode, "stderr": proc.stderr}
    payload["status"] = "INSTALLED" if proc.returncode == 0 else "BLOCKED"
    return (0 if proc.returncode == 0 else 1), payload


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise typer.Exit(130)
