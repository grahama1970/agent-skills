from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watchdog_graph import GraphError, canonical_bytes, compile_script, read_graph, revision, validate_graph

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
DEFAULT_REGISTRY = Path(os.environ.get("PROJECT_WATCHDOG_REGISTRY", str(ROOT / "registry" / "projects.json"))).expanduser()
STATE_ROOT = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", "~/.local/state/project-watchdog-v2")).expanduser()
DEFAULT_STATE = STATE_ROOT / "state.json"
DEFAULT_RECEIPTS = STATE_ROOT / "receipts"
LOCK_PATH = Path(os.environ.get("PROJECT_WATCHDOG_LOCK", "/tmp/project-watchdog-v2.lock"))
LOG_PATH = Path(os.environ.get("PROJECT_WATCHDOG_LOG", str(STATE_ROOT / "events.jsonl"))).expanduser()
COOLDOWN_SECONDS = int(os.environ.get("PROJECT_WATCHDOG_COOLDOWN_SECONDS", "1800"))
OWNER = os.environ.get("PROJECT_WATCHDOG_OWNER", f"project-watchdog-v2:{os.uname().nodename}:{os.getpid()}")
PI_EXTENSION = Path(os.environ.get("PROJECT_WATCHDOG_PI_EXTENSION", "/home/graham/workspace/experiments/pi-subagents/index.ts"))
MAINTENANCE_ROOT = STATE_ROOT / "maintenance"
MONITOR_PROJECTS_STATE = MAINTENANCE_ROOT / "monitor-projects.json"
MONITOR_PROJECTS_LOCK = MAINTENANCE_ROOT / "monitor-projects.lock"
MONITOR_PROJECTS_LOG = MAINTENANCE_ROOT / "monitor-projects.log"

HUMAN_HOLD_LABELS = {
    "agent-blocked", "maintainer-active", "maintainer-blocked", "next:human", "human-hold",
    "needs-human", "blocked:human", "status:deferred",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def pi_executable() -> str:
    override = os.environ.get("PROJECT_WATCHDOG_PI_BIN")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise OSError("PROJECT_WATCHDOG_PI_BIN must name an executable absolute path")
        return str(path)
    clean_path = os.pathsep.join(part for part in os.environ.get("PATH", "").split(os.pathsep) if not part.endswith("node_modules/.bin"))
    path = shutil.which("pi", path=clean_path)
    if path is None:
        raise OSError("Pi executable not found outside project node_modules/.bin; set PROJECT_WATCHDOG_PI_BIN")
    return path


def pi_environment() -> dict[str, str]:
    env = os.environ.copy()
    selected = pi_executable()
    clean_parts = [part for part in env.get("PATH", "").split(os.pathsep) if not part.endswith("node_modules/.bin") and part != str(Path(selected).parent)]
    env["PATH"] = os.pathsep.join([str(Path(selected).parent), *clean_parts])
    env["PI_SUBAGENT_PI_BINARY"] = selected
    return env


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, sort_keys=True))


def log_event(stage: str, status: str, **fields: Any) -> None:
    """Append one bounded event for stream-view.sh; logging never owns control flow."""
    event = {"at": utc_now(), "stage": stage, "status": status, **fields}
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        pass


@dataclass(frozen=True)
class Project:
    project_id: str
    repo: str
    cwd: str
    ready_label: str
    active_label: str
    done_label: str
    target_prefixes: tuple[str, ...]
    target_excludes: tuple[str, ...]
    default_state: str
    proof_command: tuple[str, ...] | None


@dataclass(frozen=True)
class Ticket:
    project: Project
    number: int
    title: str
    url: str
    labels: tuple[str, ...]
    body: str = ""

    @property
    def key(self) -> str:
        return f"{self.project.repo}#{self.number}"


class Gh:
    def _run(self, args: list[str], cwd: str | None = None) -> dict[str, Any]:
        proc = subprocess.run(["gh", *args], cwd=cwd, text=True, capture_output=True, check=False)
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "args": ["gh", *args]}

    def list_open(self, project: Project) -> list[dict[str, Any]]:
        res = self._run([
            "issue", "list", "--repo", project.repo, "--state", "open", "--label", project.ready_label,
            "--json", "number,title,url,labels,body", "--limit", "100",
        ])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])
        return json.loads(res["stdout"] or "[]")

    def add_lease(self, ticket: Ticket, owner: str) -> None:
        marker = f"project-watchdog-v2 lease owner={owner} ticket={ticket.key}"
        # Write the owner marker before the active label. If labeling fails the
        # ticket is not stranded in an active state without recoverable ownership.
        res = self._run(["issue", "comment", str(ticket.number), "--repo", ticket.project.repo, "--body", marker])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])
        res = self._run(["issue", "edit", str(ticket.number), "--repo", ticket.project.repo, "--add-label", ticket.project.active_label])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])

    def lease_owner(self, ticket: Ticket) -> str | None:
        res = self._run(["issue", "view", str(ticket.number), "--repo", ticket.project.repo, "--json", "comments,labels"])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])
        data = json.loads(res["stdout"] or "{}")
        labels = {item.get("name") for item in data.get("labels") or []}
        if ticket.project.active_label not in labels:
            return None
        comments = data.get("comments") or []
        for item in reversed(comments):
            body = item.get("body") or ""
            match = re.search(r"project-watchdog-v2 lease owner=([^\s]+)", body)
            if match:
                return match.group(1)
        return None

    def release_lease(self, ticket: Ticket, owner: str) -> bool:
        if self.lease_owner(ticket) != owner:
            return False
        res = self._run(["issue", "edit", str(ticket.number), "--repo", ticket.project.repo, "--remove-label", ticket.project.active_label])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])
        return True

    def close(self, ticket: Ticket) -> dict[str, Any]:
        res = self._run(["issue", "close", str(ticket.number), "--repo", ticket.project.repo, "--comment", "project-watchdog-v2 reviewer and deterministic proof passed."])
        if res["returncode"] != 0:
            raise RuntimeError(res["stderr"] or res["stdout"])
        view = self._run(["issue", "view", str(ticket.number), "--repo", ticket.project.repo, "--json", "state,labels"])
        if view["returncode"] != 0:
            raise RuntimeError(view["stderr"] or view["stdout"])
        data = json.loads(view["stdout"] or "{}")
        if data.get("state") == "CLOSED":
            cleanup = self._run([
                "issue", "edit", str(ticket.number), "--repo", ticket.project.repo,
                "--remove-label", ticket.project.active_label, "--remove-label", ticket.project.ready_label,
                "--add-label", ticket.project.done_label,
            ])
            data["label_cleanup"] = {"ok": cleanup["returncode"] == 0, "stderr": cleanup["stderr"]}
            if cleanup["returncode"] == 0:
                final = self._run(["issue", "view", str(ticket.number), "--repo", ticket.project.repo, "--json", "state,labels"])
                if final["returncode"] == 0:
                    data = {**json.loads(final["stdout"] or "{}"), "label_cleanup": data["label_cleanup"]}
        return data


class PiSubagents:
    def run(self, ticket: Ticket, on_stage: Any = None, graph: dict[str, Any] | None = None) -> dict[str, Any]:
        if on_stage:
            on_stage("workflow", "STARTED")
        model = os.environ.get("PROJECT_WATCHDOG_PI_MODEL", "zai/glm-5.3")
        selected_graph = graph if graph is not None else read_graph("active")[0]
        graph_hash = revision(canonical_bytes(selected_graph))
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="workflow-", dir=STATE_ROOT) as workdir:
            script_path = Path(workdir) / "ticket.js"
            script_path.write_text(workflow_script(ticket, selected_graph), encoding="utf-8")
            prompt = workflow_prompt(ticket, script_path)
            cmd = [pi_executable(), "--no-session", "--mode", "json", "--model", model, "--extension", str(PI_EXTENSION), "--tools", "subagent", "--approve", "-p", prompt]
            proc = subprocess.run(cmd, cwd=ticket.project.cwd, env=pi_environment(), text=True, capture_output=True, check=False, timeout=int(os.environ.get("PROJECT_WATCHDOG_PI_TIMEOUT", "7200")))
            result = parse_workflow_events(proc.stdout, script_path, ticket.project.cwd) if proc.returncode == 0 else {"ok": False, "failed_role": "workflow", "error": "Pi process failed"}
            events_dir = STATE_ROOT / "workflow-events"
            events_dir.mkdir(mode=0o700, exist_ok=True)
            events_path = events_dir / f"{uuid.uuid4().hex}.jsonl"
            fd = os.open(events_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(proc.stdout)
        if on_stage:
            on_stage("workflow", "PASS" if result["ok"] else "FAIL")
        return {
            **result,
            "graph_hash": graph_hash,
            "returncode": proc.returncode,
            "stderr": proc.stderr[-4000:],
            "events_path": str(events_path),
            "events_sha256": hashlib.sha256(proc.stdout.encode("utf-8")).hexdigest(),
            "command": [*redact_cmd(cmd[:-1]), "<workflow prompt>"],
        }

class Triage:
    def classify(self, stage: str, signal: str) -> dict[str, Any]:
        cmd = [str(SKILLS / "triage-error" / "run.sh"), "classify", "--layer", "project-watchdog", "--text", f"stage={stage}\n{signal}"]
        try:
            proc = subprocess.run(cmd, cwd=str(SKILLS.parent), text=True, capture_output=True, check=False, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "classifier": {"command": redact_cmd(cmd), "error": repr(exc)}}
        out = {"command": redact_cmd(cmd), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        if proc.returncode != 0:
            return {"ok": False, "classifier": out}
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "classifier": out}
        data = data.get("report", data)  # CLI emits {"report": ..., "jev_shadow": ...}
        return {
            "ok": True,
            "code": data.get("code"),
            "cause": data.get("cause"),
            "next_command": data.get("next_command"),
            "classifier": out,
        }


def canonical_triage(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok") and result.get("code") and result.get("cause"):
        result["next_command"] = result.get("next_command") or "Read the retained project-watchdog receipt and repair the classified stage."
        return result
    result.update({
        "code": "triage_classifier_unreachable",
        "cause": "triage-error classify could not be invoked or returned invalid JSON.",
        "next_command": "skills/triage-error/run.sh classify --layer project-watchdog --text '<original failure signal>'",
    })
    return result


def redact_cmd(cmd: list[str]) -> list[str]:
    return ["<text>" if i and cmd[i - 1] == "--text" else part for i, part in enumerate(cmd)]


def parse_json_from_text(text: str) -> Any:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


def workflow_script(ticket: Ticket, graph: dict[str, Any] | None = None) -> str:
    selected_graph = graph if graph is not None else read_graph("active")[0]
    child_model = os.environ.get("PROJECT_WATCHDOG_CHILD_MODEL", "zai/glm-5.3")
    return compile_script(
        selected_graph,
        {
            "key": ticket.key,
            "title": ticket.title,
            "body": ticket.body,
            "proof_command": json.dumps(list(ticket.project.proof_command or ())),
        },
        child_model,
    )


def workflow_prompt(ticket: Ticket, script_path: Path) -> str:
    params = {"workflowScriptPath": str(script_path), "cwd": ticket.project.cwd, "async": False}
    return (
        "Call the native subagent tool exactly once with these parameters. Wait for its result. "
        "Do not call any other tool or launch background work.\n"
        + json.dumps(params, sort_keys=True)
    )


def parse_workflow_events(stream: str, script_path: Path, cwd: str) -> dict[str, Any]:
    calls = []
    results = []
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") or {}
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            calls.extend(item for item in message.get("content") or [] if item.get("type") == "toolCall")
        if event.get("type") == "message_end" and message.get("role") == "toolResult" and message.get("toolName") == "subagent":
            results.append(message)
    expected = {"workflowScriptPath": str(script_path), "cwd": cwd, "async": False}
    if len(calls) != 1 or calls[0].get("name") != "subagent" or calls[0].get("arguments") != expected:
        return {"ok": False, "failed_role": "workflow", "error": "expected one exact native workflow call"}
    if len(results) != 1 or results[0].get("toolCallId") != calls[0].get("id"):
        return {"ok": False, "failed_role": "workflow", "error": "native workflow result missing or unmatched"}
    message = results[0]
    details = message.get("details") or {}
    workflow = details.get("workflow") or {}
    value = workflow.get("value") or {}
    child_inventory = details.get("workflowChildren") or {}
    children = child_inventory.get("children") or []
    by_key = {child.get("childId"): child for child in children}
    if (
        message.get("isError")
        or details.get("mode") != "workflow"
        or value.get("schema") != "project_watchdog.v2.workflow"
        or not child_inventory.get("inventoryComplete")
        or child_inventory.get("workflowState") != "completed"
    ):
        result_text = "\n".join(item.get("text", "") for item in message.get("content") or [] if item.get("type") == "text")
        return {
            "ok": False, "failed_role": "workflow", "error": "native workflow result missing or failed",
            "native": {
                "is_error": message.get("isError"), "mode": details.get("mode"),
                "workflow_state": child_inventory.get("workflowState"),
                "inventory_complete": child_inventory.get("inventoryComplete"),
                "value_schema": value.get("schema"), "value_error": value.get("error"),
                "message": result_text[-2000:],
                "children": [{"childId": child.get("childId"), "state": child.get("state"), "error": child.get("error")} for child in children],
            },
        }
    fixer = value.get("fixer") or {}
    node_results = value.get("results") or {"fixer": fixer, "reviewer": value.get("reviewer") or {}}
    node_inventory = {child.get("childId"): child for child in children if child.get("childId")}
    if not isinstance(node_results, dict):
        return {"ok": False, "failed_role": "workflow", "error": "native node results missing", "workflow_run_id": details.get("runId")}
    for node_id, node_result in node_results.items():
        if not isinstance(node_result, dict) or not node_result.get("ok") or node_inventory.get(node_id, {}).get("state") != "completed":
            return {"ok": False, "failed_role": node_id, "nodes": node_results, "inventory": node_inventory, "workflow_run_id": details.get("runId")}
    if value.get("failed_role"):
        return {"ok": False, "failed_role": value["failed_role"], "nodes": node_results, "inventory": node_inventory, "workflow_run_id": details.get("runId")}
    fixer_status = parse_json_from_text(fixer.get("output") or "")
    if not fixer.get("ok") or not by_key.get("fixer", {}).get("state") == "completed" or not isinstance(fixer_status, dict) or fixer_status.get("status") != "COMPLETE":
        return {"ok": False, "failed_role": "fixer", "fixer": {"result": fixer, "status": fixer_status}, "nodes": node_results, "inventory": node_inventory, "workflow_run_id": details.get("runId")}
    reviewer = value.get("reviewer") or {}
    reviewer_status = parse_json_from_text(reviewer.get("output") or "")
    if not reviewer.get("ok") or by_key.get("reviewer", {}).get("state") != "completed" or not isinstance(reviewer_status, dict) or reviewer_status.get("verdict") != "PASS":
        return {"ok": False, "failed_role": "reviewer", "fixer": {"result": fixer, "status": fixer_status}, "reviewer": {"result": reviewer, "status": reviewer_status}, "nodes": node_results, "inventory": node_inventory, "workflow_run_id": details.get("runId")}
    return {
        "ok": True,
        "workflow_run_id": details.get("runId"),
        "fixer": {"result": fixer, "status": fixer_status},
        "reviewer": {"result": reviewer, "status": reviewer_status},
        "nodes": node_results,
        "inventory": node_inventory,
    }


def load_projects(registry_path: Path = DEFAULT_REGISTRY) -> list[Project]:
    data = read_json(registry_path, {"projects": []})
    defaults = data.get("defaults") or {}
    labels = defaults.get("labels") or {}
    out: list[Project] = []
    for raw in data.get("projects") or []:
        if not raw.get("project_id") or not raw.get("repo"):
            continue
        runner = raw.get("runner") or {}
        cwd = runner.get("cwd") or raw.get("root") or str(SKILLS.parent)
        configured_proof = raw.get("proof_command") or runner.get("proof_command") or runner.get("command")
        if isinstance(configured_proof, str):
            configured_proof = tuple(shlex.split(configured_proof))
        elif isinstance(configured_proof, list) and all(isinstance(part, str) for part in configured_proof):
            configured_proof = tuple(configured_proof)
        else:
            configured_proof = None
        out.append(Project(
            project_id=raw["project_id"],
            repo=raw["repo"],
            cwd=cwd,
            ready_label=(raw.get("labels") or {}).get("ready") or labels.get("ready") or "agent-work",
            active_label=(raw.get("labels") or {}).get("active") or labels.get("active") or "agent-active",
            done_label=(raw.get("labels") or {}).get("done") or labels.get("done") or "agent-done",
            target_prefixes=tuple(raw.get("issue_target_prefixes") or ()),
            target_excludes=tuple(raw.get("issue_target_exclude_prefixes") or ()),
            default_state=(raw.get("state_policy") or {}).get("default_state") or defaults.get("state") or "paused",
            proof_command=configured_proof,
        ))
    return sorted(out, key=lambda p: p.project_id)


def load_state(path: Path = DEFAULT_STATE) -> dict[str, Any]:
    return read_json(path, {"schema": "agent_skills.project_watchdog.state.v2", "global": {"state": "paused"}, "projects": {}, "rotation": {}})


def project_state(state: dict[str, Any], project: Project) -> str:
    if (state.get("global") or {}).get("state") != "active":
        return "paused"
    return ((state.get("projects") or {}).get(project.project_id) or {}).get("state", project.default_state)


def set_cooldown(state: dict[str, Any], ticket: Ticket, now: float) -> None:
    state.setdefault("cooldowns", {})[ticket.key] = int(now + COOLDOWN_SECONDS)


def cooldown_active(state: dict[str, Any], ticket: Ticket, now: float) -> int | None:
    until = int((state.get("cooldowns") or {}).get(ticket.key) or 0)
    return until if until > now else None


def select_project(projects: list[Project], state: dict[str, Any], wanted: str) -> Project | None:
    active = [p for p in projects if project_state(state, p) == "active"]
    if wanted != "all":
        for p in projects:
            if p.project_id == wanted:
                return p if p in active else None
        raise KeyError(wanted)
    if not active:
        return None
    last = (state.get("rotation") or {}).get("last_project")
    ids = [p.project_id for p in active]
    idx = (ids.index(last) + 1) % len(active) if last in ids else 0
    picked = active[idx]
    state.setdefault("rotation", {})["last_project"] = picked.project_id
    return picked


def eligible(issue: dict[str, Any], project: Project) -> bool:
    labels = {item.get("name") for item in issue.get("labels") or []}
    if labels & HUMAN_HOLD_LABELS:
        return False
    if project.active_label in labels or project.done_label in labels:
        return False
    text = f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    if project.target_prefixes and not any(prefix in text for prefix in project.target_prefixes):
        return False
    if project.target_excludes and any(prefix in text for prefix in project.target_excludes):
        return False
    return True


def select_ticket(gh: Gh, project: Project, state: dict[str, Any], now: float) -> Ticket | None:
    candidates = []
    for issue in gh.list_open(project):
        if not eligible(issue, project):
            continue
        labels = tuple(sorted(item.get("name") for item in issue.get("labels") or [] if item.get("name")))
        body = issue.get("body") or ""
        ticket = Ticket(
            project, int(issue["number"]), issue.get("title") or "",
            issue.get("url") or "", labels, body,
        )
        candidates.append(ticket)
    ordered = sorted(candidates, key=lambda t: (t.project.repo, t.number))
    for ticket in ordered:
        if cooldown_active(state, ticket, now) is None:
            return ticket
    return ordered[0] if ordered else None


def reviewer_passed(pi_result: dict[str, Any]) -> bool:
    reviewer = pi_result.get("reviewer") or {}
    fixer = pi_result.get("fixer") or {}
    return bool(
        pi_result.get("ok")
        and (fixer.get("result") or {}).get("ok")
        and (fixer.get("status") or {}).get("status") == "COMPLETE"
        and (reviewer.get("result") or {}).get("ok")
        and (reviewer.get("status") or {}).get("verdict") == "PASS"
    )


def run_proof(ticket: Ticket) -> dict[str, Any]:
    command = ticket.project.proof_command
    if not command:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "project has no trusted proof_command", "command": None}
    proc = subprocess.run(command, cwd=ticket.project.cwd, text=True, capture_output=True, check=False, timeout=int(os.environ.get("PROJECT_WATCHDOG_PROOF_TIMEOUT", "1800")))
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:], "command": list(command)}


class Watchdog:
    def __init__(self, gh: Gh | None = None, pi: PiSubagents | None = None, triage: Triage | None = None, registry_path: Path = DEFAULT_REGISTRY, state_path: Path = DEFAULT_STATE, receipts_dir: Path = DEFAULT_RECEIPTS):
        self.gh = gh or Gh()
        self.pi = pi or PiSubagents()
        self.triage = triage or Triage()
        self.registry_path = registry_path
        self.state_path = state_path
        self.receipts_dir = receipts_dir

    def status(self) -> dict[str, Any]:
        return {"schema": "project_watchdog.v2.status", "state": load_state(self.state_path), "projects": [p.project_id for p in load_projects(self.registry_path)], "cron_line": cron_line()}

    def tick(self, apply: bool, wanted: str, lock_held: bool = False) -> dict[str, Any]:
        log_event("tick", "STARTED", project=wanted, apply=apply)
        if lock_held:
            return self._tick_locked(apply, wanted)
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_PATH.open("w") as lock:
            try:
                fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log_event("tick", "SKIPPED", reason="overlap")
                return {"outcome": "overlap", "receipt": None}
            return self._tick_locked(apply, wanted)

    def _tick_locked(self, apply: bool, wanted: str) -> dict[str, Any]:
        now = time.time()
        state = load_state(self.state_path)
        projects = load_projects(self.registry_path)
        if wanted != "all" and wanted not in {p.project_id for p in projects}:
            return {"outcome": "invalid_project", "project": wanted, "receipt": None}
        project = select_project(projects, state, wanted)
        write_json(self.state_path, state)
        if project is None:
            log_event("tick", "SKIPPED", reason="paused")
            return {"outcome": "paused", "receipt": None}
        try:
            ticket = select_ticket(self.gh, project, state, now)
        except Exception as exc:
            return self._scan_fail(project, "scan", repr(exc))
        if ticket is None:
            log_event("scan", "NOOP", project=project.project_id)
            return {"outcome": "NOOP", "project": project.project_id, "receipt": None}
        log_event("scan", "SELECTED", project=project.project_id, ticket=ticket.key)
        until = cooldown_active(state, ticket, now)
        if until:
            log_event("scan", "SKIPPED", ticket=ticket.key, reason="cooldown")
            return {"outcome": "cooldown", "ticket": ticket.key, "cooldown_until": until, "receipt": None}
        if not apply:
            return {"outcome": "dry_run", "project": project.project_id, "ticket": ticket.key, "receipt": None}
        write_json(self.state_path, state)

        receipt: dict[str, Any] = {"schema": "project_watchdog.v2.receipt", "started_at": utc_now(), "project": project.project_id, "ticket": ticket.key, "owner": OWNER, "events": []}
        leased = False
        if not project.proof_command:
            return self._fail(receipt, state, ticket, "proof_config", "project has no trusted proof_command", leased)
        try:
            log_event("lease", "STARTED", ticket=ticket.key)
            self.gh.add_lease(ticket, OWNER)
            leased = True
            if self.gh.lease_owner(ticket) != OWNER:
                raise RuntimeError("lease readback did not match owner")
            receipt["events"].append({"stage": "lease", "status": "PASS"})
            log_event("lease", "PASS", ticket=ticket.key)

            log_event("subagents", "STARTED", ticket=ticket.key, sequence=["fixer", "reviewer"])
            pi_result = self.pi.run(
                ticket,
                on_stage=lambda stage, status: log_event(stage, status, ticket=ticket.key),
            )
            receipt["pi_subagents"] = pi_result
            if not pi_result.get("ok"):
                failed_role = pi_result.get("failed_role") or "reviewer"
                return self._fail(receipt, state, ticket, failed_role, json.dumps(pi_result), leased)
            receipt["events"].append({"stage": "fixer", "status": "PASS"})
            if not reviewer_passed(pi_result):
                return self._fail(receipt, state, ticket, "reviewer", json.dumps(pi_result), leased)
            receipt["events"].append({"stage": "reviewer", "status": "PASS"})
            log_event("reviewer", "PASS", ticket=ticket.key)

            log_event("proof", "STARTED", ticket=ticket.key, command=list(ticket.project.proof_command or ()))
            proof = run_proof(ticket)
            receipt["proof"] = proof
            if not proof.get("ok"):
                return self._fail(receipt, state, ticket, "proof", json.dumps(proof), leased)
            receipt["events"].append({"stage": "proof", "status": "PASS"})
            log_event("proof", "PASS", ticket=ticket.key)

            log_event("close", "STARTED", ticket=ticket.key)
            try:
                closed = self.gh.close(ticket)
            except Exception as exc:
                return self._fail(receipt, state, ticket, "close", repr(exc), leased)
            receipt["close_readback"] = closed
            if closed.get("state") != "CLOSED":
                return self._fail(receipt, state, ticket, "close", json.dumps(closed), leased)
            receipt["outcome"] = "success"
            receipt["finished_at"] = utc_now()
            path = self._write_receipt(receipt)
            log_event("close", "PASS", ticket=ticket.key, receipt=str(path))
            return {"outcome": "success", "ticket": ticket.key, "receipt": str(path)}
        except Exception as exc:
            return self._fail(receipt, state, ticket, "boundary", repr(exc), leased)

    def _fail(self, receipt: dict[str, Any], state: dict[str, Any], ticket: Ticket, stage: str, signal: str, leased: bool) -> dict[str, Any]:
        release = {"attempted": False, "released": False}
        if leased:
            try:
                release = {"attempted": True, "released": self.gh.release_lease(ticket, OWNER)}
            except Exception as exc:
                release = {"attempted": True, "released": False, "error": repr(exc)}
        set_cooldown(state, ticket, time.time())
        write_json(self.state_path, state)
        triage = canonical_triage(self.triage.classify(stage, signal))
        receipt.update({"outcome": "failure", "failed_stage": stage, "triage": triage, "lease_release": release, "finished_at": utc_now()})
        path = self._write_receipt(receipt)
        log_event(stage, "FAIL", ticket=ticket.key, receipt=str(path), triage={k: triage.get(k) for k in ("code", "cause", "next_command")})
        return {"outcome": "failure", "stage": stage, "ticket": ticket.key, "receipt": str(path), "triage": {k: triage.get(k) for k in ("code", "cause", "next_command") if k in triage}}

    def _scan_fail(self, project: Project, stage: str, signal: str) -> dict[str, Any]:
        triage = canonical_triage(self.triage.classify(stage, signal))
        receipt = {
            "schema": "project_watchdog.v2.receipt",
            "started_at": utc_now(),
            "finished_at": utc_now(),
            "project": project.project_id,
            "ticket": None,
            "owner": OWNER,
            "events": [],
            "outcome": "failure",
            "failed_stage": stage,
            "triage": triage,
        }
        path = self._write_receipt(receipt)
        log_event(stage, "FAIL", project=project.project_id, receipt=str(path), triage={k: triage.get(k) for k in ("code", "cause", "next_command")})
        return {"outcome": "failure", "stage": stage, "project": project.project_id, "receipt": str(path), "triage": {k: triage.get(k) for k in ("code", "cause", "next_command")}}

    def _write_receipt(self, receipt: dict[str, Any]) -> Path:
        suffix = str(receipt.get("ticket") or "scan").split("#")[-1]
        name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{receipt['project']}-{suffix}.json"
        path = self.receipts_dir / name
        write_json(path, receipt)
        return path


def _claim_monitor_projects_day(now: datetime | None = None) -> dict[str, Any]:
    """Atomically claim today's post-02:30 Monitor Projects maintenance slot."""
    local_now = now or datetime.now().astimezone()
    if (local_now.hour, local_now.minute) < (2, 30):
        return {"due": False, "reason": "before_02_30_local"}
    day = local_now.date().isoformat()
    MAINTENANCE_ROOT.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(MONITOR_PROJECTS_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        state: dict[str, Any] = {}
        if MONITOR_PROJECTS_STATE.is_file():
            try:
                state = json.loads(MONITOR_PROJECTS_STATE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                log_event("monitor-projects-maintenance", "STATE_INVALID", error=str(exc))
        if state.get("claimed_day") == day:
            return {"due": False, "reason": "already_claimed", **state}
        state = {
            "schema": "project_watchdog.monitor_projects_maintenance.v1",
            "claimed_day": day,
            "claimed_at": utc_now(),
            "status": "launching",
        }
        temporary = MONITOR_PROJECTS_STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(MONITOR_PROJECTS_STATE)
        return {"due": True, **state}
    finally:
        os.close(lock_fd)


def maybe_launch_monitor_projects(now: datetime | None = None) -> dict[str, Any]:
    """Launch Monitor Projects once daily without holding the ticket cron lock."""
    claim = _claim_monitor_projects_day(now)
    if not claim.get("due"):
        return claim
    command = [
        "flock", "-n", str(MONITOR_PROJECTS_LOCK),
        str(SKILLS / "monitor-projects" / "run.sh"), "nightly",
    ]
    MAINTENANCE_ROOT.mkdir(parents=True, exist_ok=True)
    log_handle = MONITOR_PROJECTS_LOG.open("ab")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        log_handle.close()
        failed = {**claim, "due": False, "status": "launch_failed", "error": str(exc)}
        write_json(MONITOR_PROJECTS_STATE, failed)
        log_event("monitor-projects-maintenance", "LAUNCH_FAILED", error=str(exc))
        return failed
    log_handle.close()
    launched = {
        **claim,
        "due": False,
        "status": "launched",
        "pid": process.pid,
        "command": command,
        "log_path": str(MONITOR_PROJECTS_LOG),
    }
    write_json(MONITOR_PROJECTS_STATE, launched)
    log_event("monitor-projects-maintenance", "LAUNCHED", pid=process.pid, log=str(MONITOR_PROJECTS_LOG))
    return launched


def cron_line() -> str:
    return f"*/15 * * * * flock -n {shlex.quote(str(LOCK_PATH))} {shlex.quote(str(ROOT / 'run.sh'))} tick --apply --project all --lock-held"


def install_cron(apply: bool = False) -> dict[str, Any]:
    if not apply:
        return {"installed": False, "dry_run": True, "line": cron_line()}
    line = cron_line()
    target = os.environ.get("PROJECT_WATCHDOG_CRONTAB")
    if target:
        path = Path(target)
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        kept = [x for x in existing if "project-watchdog" not in x]
        kept.append(line)
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return {"installed": True, "target": str(path), "line": line}
    old = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    existing = old.stdout.splitlines() if old.returncode == 0 else []
    kept = [x for x in existing if "project-watchdog" not in x]
    kept.append(line)
    proc = subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, capture_output=True, check=False)
    return {"installed": proc.returncode == 0, "line": line, "stderr": proc.stderr}


def set_state(scope: str, value: str, reason: str, project: str | None, state_path: Path = DEFAULT_STATE) -> dict[str, Any]:
    data = load_state(state_path)
    if scope == "global":
        data.setdefault("global", {})["state"] = value
        data["global"]["reason"] = reason
    else:
        if not project:
            raise ValueError("--project is required for project scope")
        data.setdefault("projects", {}).setdefault(project, {})["state"] = value
        data["projects"][project]["reason"] = reason
    data["updated_at"] = utc_now()
    write_json(state_path, data)
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-watchdog")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    tick = sub.add_parser("tick")
    tick.add_argument("--apply", action="store_true")
    tick.add_argument("--project", default="all")
    tick.add_argument("--lock-held", action="store_true", help=argparse.SUPPRESS)
    ss = sub.add_parser("set-state")
    ss.add_argument("state", choices=["active", "paused"])
    ss.add_argument("--scope", choices=["global", "project"], default="global")
    ss.add_argument("--project")
    ss.add_argument("--reason", default="operator update")
    install = sub.add_parser("install-cron")
    install.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wd = Watchdog(
        registry_path=Path(os.environ.get("PROJECT_WATCHDOG_REGISTRY", DEFAULT_REGISTRY)),
        state_path=Path(os.environ.get("PROJECT_WATCHDOG_STATE", DEFAULT_STATE)),
        receipts_dir=Path(os.environ.get("PROJECT_WATCHDOG_RECEIPTS", DEFAULT_RECEIPTS)),
    )
    try:
        if args.cmd == "status":
            emit(wd.status())
        elif args.cmd == "tick":
            result = wd.tick(args.apply, args.project, args.lock_held)
            if args.apply and args.project == "all":
                result["maintenance"] = maybe_launch_monitor_projects()
            emit(result)
            if result.get("outcome") == "invalid_project":
                return 2
            if result.get("outcome") == "failure":
                return 1
        elif args.cmd == "set-state":
            emit(set_state(args.scope, args.state, args.reason, args.project, wd.state_path))
        elif args.cmd == "install-cron":
            result = install_cron(args.apply)
            emit(result)
            if args.apply and not result.get("installed"):
                return 1
    except KeyError as exc:
        emit({"outcome": "invalid_project", "project": str(exc).strip("'"), "receipt": None})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
