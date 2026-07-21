#!/usr/bin/env python3
"""Monitor Herdr workspaces and restart agents that stopped too early."""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import fcntl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
import typer

from cron_support import install_cron, latest_cron_receipt_summary, latest_receipt_summary, scheduler_health, status_payload
from goal_discovery import discover_immutable_goal, path_is_relative_to, project_root_for_cwd
from herdr_terminal_control import pane_run_submit, wait_for_agent_idle
from prompt_builder import build_prompt
from transcript_classifier import exhausted_blocker_claim, goal_allows_stop, latest_transcript_region, transcript_goal_claim, valid_attempt_value

SKILL_DIR = Path(__file__).resolve().parents[1]
STATE_ROOT = Path.home() / ".local" / "state" / "monitor-herdr"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
STATE_PATH = STATE_ROOT / "state.json"
LOCK_DIR = STATE_ROOT / "lock"
LOCK_PATH = STATE_ROOT / "monitor.lock"
CRON_MARKER = "# monitor-herdr herdr cron"
DEFAULT_SPACE = "codex"
DEFAULT_CWD_PREFIX = str(Path.home() / "workspace" / "experiments")
DEFAULT_STOPPED_STATUSES = ("done", "idle", "blocked", "unknown")
DEFAULT_COOLDOWN_SECONDS = 60 * 60
DEFAULT_UNCONFIRMED_COOLDOWN_SECONDS = 10 * 60
DEFAULT_MIN_STOPPED_SECONDS = 0
DEFAULT_SOCKET_PATH = Path.home() / ".config" / "herdr" / "herdr.sock"
EARLY_STOP_PATTERNS = [
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
LOCK_HANDLE: Any | None = None


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
            "id": f"monitor_herdr_{self.counter}",
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
            if response.get("id") != request["id"]:
                response = {
                    "error": {
                        "code": "response_id_mismatch",
                        "message": f"expected {request['id']!r}, got {response.get('id')!r}",
                    }
                }
            elif "result" not in response and "error" not in response:
                response = {"error": {"code": "invalid_response_shape", "message": "missing result/error"}}
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
    unconfirmed_cooldown_seconds: int = typer.Option(DEFAULT_UNCONFIRMED_COOLDOWN_SECONDS, "--unconfirmed-cooldown-seconds", min=0, help="Cooldown for prompt attempts that modified input but were not confirmed submitted."),
    min_stopped_seconds: int = typer.Option(DEFAULT_MIN_STOPPED_SECONDS, "--min-stopped-seconds", min=0, help="Minimum observed stopped/idle age before prompting."),
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
        unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
        min_stopped_seconds=min_stopped_seconds,
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
    min_stopped_seconds: int = typer.Option(600, "--min-stopped-seconds", min=0, help="Cron prompt threshold based on observed stopped age."),
) -> None:
    """Install or preview a 10 minute cron entry."""
    ensure_dirs()
    exit_code, payload = install_cron(
        apply=apply,
        minute=minute,
        space=space,
        apply_prompts=apply_prompts,
        cwd_prefix=cwd_prefix,
        min_stopped_seconds=min_stopped_seconds,
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
            "schema": "agent_skills.monitor_herdr.probe.v1",
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
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def log_event(run_id: str, message: str, **fields: Any) -> None:
    event = {"ts": now_iso(), "run_id": run_id, "message": message, **fields}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "monitor-herdr.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def cooldown_for_prompt_state(
    prompt_state: dict[str, Any],
    *,
    cooldown_seconds: int,
    unconfirmed_cooldown_seconds: int,
) -> int:
    if prompt_state.get("input_modified") and prompt_state.get("submit_confirmed") is False:
        return min(cooldown_seconds, unconfirmed_cooldown_seconds) if cooldown_seconds > 0 else unconfirmed_cooldown_seconds
    return cooldown_seconds


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("Monitor state JSON is corrupt: {}", STATE_PATH)
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}, "input_suppressed": True, "state_error": "corrupt_json"}
    if not isinstance(payload, dict):
        return {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}, "input_suppressed": True, "state_error": "invalid_state_shape"}
    payload.setdefault("schema", "agent_skills.monitor_herdr.state.v1")
    payload.setdefault("prompts", {})
    return payload


def acquire_lock(run_id: str) -> bool:
    global LOCK_HANDLE
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_HANDLE = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        LOCK_HANDLE.close()
        LOCK_HANDLE = None
        return False
    LOCK_HANDLE.seek(0)
    LOCK_HANDLE.truncate()
    LOCK_HANDLE.write(json.dumps({"run_id": run_id, "pid": os.getpid(), "ts": now_iso()}) + "\n")
    LOCK_HANDLE.flush()
    return True


def release_lock() -> None:
    global LOCK_HANDLE
    if LOCK_HANDLE is None:
        return
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
        LOCK_HANDLE.close()
    except OSError:
        logger.error("Could not release monitor lock at {}", LOCK_PATH)
    finally:
        LOCK_HANDLE = None


def tick(
    *,
    apply: bool,
    space: str,
    socket_path: Path,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    cooldown_seconds: int,
    unconfirmed_cooldown_seconds: int,
    min_stopped_seconds: int,
    max_prompts: int,
    only_obvious_early_stops: bool,
) -> tuple[int, dict[str, Any]]:
    run_id = f"monitor-herdr-{timestamp()}"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    events_path = receipt_dir / "events.jsonl"
    receipt: dict[str, Any] = {
        "schema": "agent_skills.monitor_herdr.tick_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "apply": apply,
        "invocation_source": os.environ.get("MONITOR_HERDR_INVOCATION_SOURCE", "cli"),
        "receipt_dir": str(receipt_dir),
        "events_path": str(events_path),
        "log_file": str(LOG_DIR / "monitor-herdr.log"),
        "state_path": str(STATE_PATH),
        "selection": {
            "space": space,
            "socket_path": str(socket_path),
            "cwd_prefix": cwd_prefix,
            "include_agents": sorted(include_agents),
            "stopped_statuses": sorted(stopped_statuses),
            "cooldown_seconds": cooldown_seconds,
            "unconfirmed_cooldown_seconds": unconfirmed_cooldown_seconds,
            "min_stopped_seconds": min_stopped_seconds,
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
            result: tuple[int, dict[str, Any]]
            try:
                client.call("ping", {})
            except RuntimeError as exc:
                receipt.update({"ok": False, "status": "BLOCKED", "errors": [f"Herdr ping failed: {exc}"]})
                result = finish(receipt, 2)
            else:
                result = tick_locked(
                    client=client,
                    receipt=receipt,
                    events_path=events_path,
                    apply=apply,
                    space=space,
                    cwd_prefix=cwd_prefix,
                    include_agents=include_agents,
                    stopped_statuses=stopped_statuses,
                    cooldown_seconds=cooldown_seconds,
                    unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
                    min_stopped_seconds=min_stopped_seconds,
                    max_prompts=max_prompts,
                    only_obvious_early_stops=only_obvious_early_stops,
                )
            receipt["api_trace"] = client.trace
            if receipt.get("receipt_path"):
                write_json(Path(str(receipt["receipt_path"])), receipt)
            return result
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
    unconfirmed_cooldown_seconds: int,
    min_stopped_seconds: int,
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
    input_suppressed = bool(state.get("input_suppressed"))
    if input_suppressed:
        receipt["input_suppressed"] = True
        receipt["state_error"] = state.get("state_error")
    now_epoch = current_epoch()
    selected: list[dict[str, Any]] = []
    stopped_observations = state.setdefault("stopped_observations", {})
    observed_pane_ids = {str(pane.get("pane_id") or "") for pane in panes if pane.get("pane_id")}
    current_stopped_ids: set[str] = set()

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
        current_stopped_ids.add(pane_id)
        update_stopped_observation(stopped_observations, candidate, now_epoch=now_epoch)
        prompt_state = state.get("prompts", {}).get(pane_id, {})
        last_prompt_at = int(prompt_state.get("last_prompt_epoch", 0) or 0)
        effective_cooldown_seconds = cooldown_for_prompt_state(
            prompt_state,
            cooldown_seconds=cooldown_seconds,
            unconfirmed_cooldown_seconds=unconfirmed_cooldown_seconds,
        )
        candidate["cooldown_active"] = effective_cooldown_seconds > 0 and (now_epoch - last_prompt_at) < effective_cooldown_seconds
        candidate["cooldown_seconds_effective"] = effective_cooldown_seconds
        candidate["last_prompt_epoch"] = last_prompt_at or None
        candidate["min_stopped_seconds"] = min_stopped_seconds
        candidate["stopped_age_satisfied"] = (
            candidate.get("stopped_age_seconds") is not None
            and int(candidate.get("stopped_age_seconds") or 0) >= min_stopped_seconds
        )
        receipt["stopped_panes"].append(candidate)
        append_jsonl(events_path, {"event": "stopped_pane", "ts": now_iso(), **candidate_without_text(candidate)})
        should_prompt = candidate.get("action") != "observe_only"
        candidate["select_for_prompt"] = should_prompt
        if (
            should_prompt
            and not input_suppressed
            and not candidate["cooldown_active"]
            and candidate["stopped_age_satisfied"]
            and len(selected) < max_prompts
        ):
            selected.append(candidate)
    prune_stopped_observations(
        stopped_observations,
        observed_pane_ids=observed_pane_ids,
        current_stopped_ids=current_stopped_ids,
    )

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
            "api_sent": False,
            "submit_confirmed": False,
            "send_api": [],
        }
        if apply:
            send_result = send_prompt(client, str(candidate["pane_id"]), prompt, project_root=candidate.get("project_root"))
            prompt_record.update(send_result)
            prompt_record["sent"] = bool(send_result.get("submit_confirmed"))
            if prompt_record["submit_confirmed"] or prompt_record.get("input_modified"):
                state.setdefault("prompts", {})[str(candidate["pane_id"])] = {
                    "last_prompt_epoch": now_epoch,
                    "last_prompt_at": now_iso(),
                    "agent": candidate.get("agent"),
                    "cwd": candidate.get("cwd"),
                    "classification": candidate.get("classification"),
                    "action": candidate.get("action"),
                    "submit_confirmed": bool(prompt_record["submit_confirmed"]),
                    "input_modified": bool(prompt_record.get("input_modified")),
                }
        receipt["prompts"].append(prompt_record)
        append_jsonl(events_path, {"event": "prompt", "ts": now_iso(), **prompt_record})

    if apply or min_stopped_seconds > 0:
        write_json(STATE_PATH, state)

    receipt["status"] = "RESTART_PROMPTS_SUBMITTED" if apply and receipt["prompts"] else "OBSERVED"
    if input_suppressed:
        receipt["status"] = "NEEDS_ATTENTION"
        receipt["ok"] = False
        return finish(receipt, 1)
    receipt["ok"] = all(not prompt_send_failed(item) for item in receipt["prompts"]) or not apply
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


def update_stopped_observation(observations: dict[str, Any], candidate: dict[str, Any], *, now_epoch: int) -> None:
    pane_id = str(candidate.get("pane_id") or "")
    if not pane_id:
        return
    record = observations.get(pane_id)
    if not isinstance(record, dict):
        record = {
            "first_seen_stopped_epoch": now_epoch,
            "first_seen_stopped_at": now_iso(),
            "consecutive_stopped_ticks": 0,
        }
    record["last_seen_stopped_epoch"] = now_epoch
    record["last_seen_stopped_at"] = now_iso()
    record["consecutive_stopped_ticks"] = int(record.get("consecutive_stopped_ticks", 0) or 0) + 1
    record["agent"] = candidate.get("agent")
    record["agent_status"] = candidate.get("agent_status")
    record["cwd"] = candidate.get("cwd")
    record["classification"] = candidate.get("classification")
    observations[pane_id] = record

    api_age = candidate.get("herdr_stopped_age_seconds")
    if api_age is not None:
        candidate["stopped_age_seconds"] = int(api_age)
        candidate["stopped_age_source"] = candidate.get("herdr_stopped_age_source") or "herdr_api"
        return
    first_seen = int(record.get("first_seen_stopped_epoch", now_epoch) or now_epoch)
    candidate["stopped_age_seconds"] = max(0, now_epoch - first_seen)
    candidate["stopped_age_source"] = "monitor_state"
    candidate["stopped_first_seen_at"] = record.get("first_seen_stopped_at")
    candidate["consecutive_stopped_ticks"] = record.get("consecutive_stopped_ticks")


def prune_stopped_observations(
    observations: dict[str, Any],
    *,
    observed_pane_ids: set[str],
    current_stopped_ids: set[str],
) -> None:
    for pane_id in list(observations):
        if pane_id in observed_pane_ids and pane_id not in current_stopped_ids:
            del observations[pane_id]


def herdr_stopped_age(pane: dict[str, Any], explain: dict[str, Any], *, now_epoch: int) -> tuple[int | None, str | None]:
    for source_name, payload in (("pane", pane), ("explain", explain)):
        if not isinstance(payload, dict):
            continue
        for field in ("idle_seconds", "idle_duration_seconds", "stopped_seconds", "agent_idle_seconds", "state_age_seconds"):
            value = seconds_value(payload.get(field))
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
        for field in ("idle_since_unix", "stopped_since_unix", "agent_status_since_unix", "state_since_unix", "last_state_change_unix"):
            value = epoch_age(payload.get(field), now_epoch=now_epoch)
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
        for field in ("idle_since", "stopped_since", "agent_status_since", "state_since", "last_state_change_at"):
            value = iso_age(payload.get(field), now_epoch=now_epoch)
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
    return None, None


def seconds_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def epoch_age(value: Any, *, now_epoch: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    if epoch <= 0 or epoch > now_epoch:
        return None
    return now_epoch - epoch


def iso_age(value: Any, *, now_epoch: int) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    epoch = int(parsed.timestamp())
    if epoch > now_epoch:
        return None
    return now_epoch - epoch


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
    if cwd_prefix and (not cwd or not path_is_relative_to(cwd, cwd_prefix)):
        return None
    pane_id = str(pane.get("pane_id") or "")
    if not pane_id:
        return None

    text = read_pane_text(client, pane_id)
    current_text = latest_transcript_region(text)
    explain = explain_agent(client, pane_id)
    api_age, api_age_source = herdr_stopped_age(pane, explain, now_epoch=current_epoch())
    early_markers = find_patterns(current_text, EARLY_STOP_PATTERNS)
    human_markers = find_patterns(current_text, HUMAN_BLOCKER_PATTERNS)
    if only_obvious_early_stops and not early_markers:
        return None

    project_root = project_root_for_cwd(cwd, cwd_prefix)
    immutable_goal = discover_immutable_goal(cwd, boundary=project_root)
    goal_claim = transcript_goal_claim(current_text, project_root=project_root)
    has_goal_signal = bool(immutable_goal.get("found")) or goal_claim["state"] in {"achieved", "blocked", "unmet"}
    if status in {"blocked", "unknown"} or not explain_allows_input(explain):
        classification = "blocked_or_unknown_observe_only"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", "unsafe_or_uncertain_state_never_prompted"]
    elif not has_goal_signal and not early_markers:
        classification = "no_immutable_goal"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", "immutable_goal_unknown_stop_allowed"]
    elif goal_allows_stop(current_text, goal_found=has_goal_signal, has_early_markers=bool(early_markers), project_root=project_root):
        classification = "goal_stop_allowed"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", f"goal_claim:{goal_claim['state']}"]
    elif human_markers and not early_markers:
        classification = "legitimate_human_blocker"
        action = "needs_human"
        reasons = [f"human_blocker:{item}" for item in human_markers[:5]]
    else:
        classification = "stopped_or_early_stop"
        action = "restart_continue"
        reasons = [f"stopped_status:{status}"]
        reasons.extend(f"early_stop:{item}" for item in early_markers[:6])
        if human_markers:
            reasons.extend(f"human_marker_overridden_by_early_stop:{item}" for item in human_markers[:3])
        if immutable_goal.get("found"):
            reasons.append("immutable_goal_found")
        elif goal_claim["state"] != "none":
            reasons.append(f"transcript_goal:{goal_claim['state']}")
        elif early_markers:
            reasons.append("immutable_goal_unknown_but_early_stop_marker")
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
        "immutable_goal": immutable_goal,
        "project_root": str(project_root) if project_root else None,
        "transcript_goal_claim": goal_claim,
        "recent_excerpt": text[-2400:],
        "analysis_excerpt": current_text[-1200:],
        "explain_state": explain.get("state") if isinstance(explain, dict) else None,
        "herdr_stopped_age_seconds": api_age,
        "herdr_stopped_age_source": api_age_source,
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


def send_prompt(client: HerdrClient, pane_id: str, prompt: str, *, project_root: str | Path | None = None) -> dict[str, Any]:
    socket_path = getattr(client, "socket_path", None)
    wait_result = wait_for_agent_idle(pane_id, socket_path=socket_path)
    pre_read = read_pane_text(client, pane_id)
    if not pre_read:
        return skipped_send("pre_read_failed", wait_result=wait_result, send_failed=True)
    pre_region = latest_transcript_region(pre_read)
    root_path = Path(project_root).expanduser() if project_root else None
    if goal_allows_stop(
        pre_region,
        goal_found=True,
        has_early_markers=bool(find_patterns(pre_region, EARLY_STOP_PATTERNS)),
        project_root=root_path,
    ):
        return skipped_send("pre_submit_stop_allowed", wait_result=wait_result, pre_read=pre_read)
    explain = explain_agent(client, pane_id)
    if not wait_result.get("ok") and explain.get("state") not in {"idle", "done"}:
        return skipped_send("idle_wait_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, send_failed=True)
    if not explain_allows_input(explain):
        return skipped_send("unsafe_pre_submit_state", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read)
    records: list[dict[str, Any]] = []
    terminal_result: dict[str, Any] = {"attempted": False, "reason": "not_real_herdr_client"}
    first_read = ""
    submit_confirmed = False
    pane_run_prompt_visible = False
    if isinstance(client, HerdrClient):
        terminal_result = pane_run_submit(pane_id, prompt, socket_path=socket_path)
        if terminal_result.get("ok"):
            for _ in range(5):
                time.sleep(0.4)
                first_read = read_pane_text(client, pane_id)
                submit_confirmed = prompt_submitted(first_read, baseline=pre_read)
                if submit_confirmed:
                    break
                current = explain_agent(client, pane_id)
                if current.get("state") == "working":
                    submit_confirmed = True
                    break
            pane_run_prompt_visible = prompt_visible_after_send(first_read, baseline=pre_read, prompt=prompt)
        else:
            logger.error("Herdr pane.run submit failed for pane {}", pane_id)
    before = len(client.trace)
    needs_socket_text_fallback = not submit_confirmed and (
        not (isinstance(client, HerdrClient) and terminal_result.get("ok"))
        or pane_run_prompt_visible
    )
    socket_text_fallback_sent = False
    if needs_socket_text_fallback:
        try:
            client.call("pane.send_text", {"pane_id": pane_id, "text": prompt})
        except RuntimeError:
            logger.error("Herdr pane.send_text failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            return skipped_send("send_text_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, terminal_result=terminal_result, records=records, send_failed=True)
        records.extend(client.trace[before:])
        socket_text_fallback_sent = True
        before = len(client.trace)
        try:
            client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]})
        except RuntimeError:
            logger.error("Herdr pane.send_keys enter failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            return skipped_send("send_enter_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, terminal_result=terminal_result, records=records, input_modified=True, send_failed=True)
        records.extend(client.trace[before:])
        for _ in range(5):
            time.sleep(0.4)
            first_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(first_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    second_enter_sent = False
    second_read = ""
    ctrl_j_sent = False
    ctrl_j_read = ""
    final_read = ""
    final_grace_poll_used = False
    if not submit_confirmed:
        current = explain_agent(client, pane_id)
        if not explain_allows_input(current):
            return skipped_send(
                "post_enter_uncertain",
                wait_result=wait_result,
                pre_submit_state=explain.get("state"),
                pre_read=pre_read,
                terminal_result=terminal_result,
                records=records,
                input_modified=True,
                send_failed=True,
            )
        before = len(client.trace)
        try:
            client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]})
        except RuntimeError:
            logger.error("Herdr second pane.send_keys enter failed for pane {}", pane_id)
        records.extend(client.trace[before:])
        second_enter_sent = True
        for _ in range(5):
            time.sleep(0.4)
            second_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(second_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    if not submit_confirmed:
        current = explain_agent(client, pane_id)
        if explain_allows_input(current):
            before = len(client.trace)
            try:
                client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["ctrl+j"]})
            except RuntimeError:
                logger.error("Herdr pane.send_keys ctrl+j failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            ctrl_j_sent = True
            for _ in range(5):
                time.sleep(0.4)
                ctrl_j_read = read_pane_text(client, pane_id)
                submit_confirmed = prompt_submitted(ctrl_j_read, baseline=pre_read)
                if submit_confirmed:
                    break
                current = explain_agent(client, pane_id)
                if current.get("state") == "working":
                    submit_confirmed = True
                    break
    if not submit_confirmed and (bool(terminal_result.get("ok")) or records):
        final_grace_poll_used = True
        for _ in range(10):
            time.sleep(0.75)
            final_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(final_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    api_sent = all("error" not in item.get("response", {}) for item in records)
    transport_sent = bool(terminal_result.get("ok")) or api_sent
    return {
        "send_api": records,
        "terminal_control": terminal_result,
        "idle_wait": wait_result,
        "pre_submit_state": explain.get("state"),
        "api_sent": transport_sent,
        "submit_confirmed": submit_confirmed,
        "input_modified": transport_sent,
        "pane_run_prompt_visible": pane_run_prompt_visible,
        "socket_text_fallback_sent": socket_text_fallback_sent,
        "second_enter_sent": second_enter_sent,
        "ctrl_j_sent": ctrl_j_sent,
        "final_grace_poll_used": final_grace_poll_used,
        "post_submit_excerpt": (final_read or ctrl_j_read or second_read or first_read)[-1200:],
    }


def explain_allows_input(explain: dict[str, Any]) -> bool:
    if explain.get("error") or explain.get("state") not in {"idle", "done"}:
        return False
    if any(explain.get(key) for key in ("fallback_reason", "skip_reason", "screen_detection_skip_reason", "warning", "warnings")):
        return False
    matched_rule = str(explain.get("matched_rule") or explain.get("rule") or "")
    if not matched_rule:
        return False
    lowered = matched_rule.lower()
    if any(token in lowered for token in ["approval", "permission", "question", "blocked", "fallback", "skip"]):
        return False
    return any(token in lowered for token in ["prompt", "idle", "done", "stopped", "ready"])


def prompt_submitted(text: str, *, baseline: str = "") -> bool:
    return prompt_submission_marker(text, baseline=baseline) != ""


def prompt_submission_marker(text: str, *, baseline: str = "") -> str:
    if not text:
        return ""
    for marker in ["Running UserPromptSubmit hook", "UserPromptSubmit hook (completed)", "Working (", "Booting MCP server"]:
        if text.count(marker) > baseline.count(marker):
            return marker
    return ""


def prompt_visible_after_send(text: str, *, baseline: str, prompt: str) -> bool:
    if not text:
        return False
    if prompt in text and prompt not in baseline:
        return True
    signatures = [
        "Unblock Attempts:",
        "Disposition:",
        "CAN_SELF_UNBLOCK_WEBGPT",
        "If the immutable goal is known and not achieved",
    ]
    new_hits = sum(1 for item in signatures if text.count(item) > baseline.count(item))
    if new_hits >= 2:
        return True
    strong_visible_hits = sum(1 for item in signatures if item in text)
    return strong_visible_hits >= 3 and len(text) > len(baseline) + 200


def prompt_send_failed(prompt_record: dict[str, Any]) -> bool:
    if prompt_record.get("sent"):
        return False
    if prompt_record.get("send_failed") or prompt_record.get("input_modified"):
        return True
    return False


def skipped_send(
    reason: str,
    *,
    wait_result: dict[str, Any] | None = None,
    pre_submit_state: str | None = None,
    pre_read: str = "",
    terminal_result: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    input_modified: bool = False,
    send_failed: bool = False,
) -> dict[str, Any]:
    return {
        "send_api": records or [],
        "terminal_control": terminal_result or {"attempted": False, "reason": reason},
        "idle_wait": wait_result or {},
        "pre_submit_state": pre_submit_state,
        "api_sent": False,
        "submit_confirmed": False,
        "input_modified": input_modified,
        "send_failed": send_failed,
        "second_enter_sent": False,
        "post_submit_excerpt": "",
        "pre_submit_excerpt": pre_read[-1200:],
        "skipped": True,
        "skip_reason": reason,
    }


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


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise typer.Exit(130)
