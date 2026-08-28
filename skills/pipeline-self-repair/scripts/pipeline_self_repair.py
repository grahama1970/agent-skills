"""Replayable self-repair ledger for complex sequential pipelines.

Inputs are failed pipeline-step receipts or raw error strings plus optional
provider-effect artifacts. Outputs are append-only JSONL ledger events and JSON
receipts that bind triage-error classification, prior Memory recall, GitHub
issue search, ticket disposition, optional project-watchdog dispatch, and
agentic-evals remediation projections.

Failure modes are fail-closed: missing raw signal exits non-zero, ambiguous
triage is marked NEEDS_TRIAGE, external mutations require explicit flags, and
ledger validation refuses checkpoint resume when a blocking failure lacks a
triage/category/ticket/eval disposition.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

app = typer.Typer(add_completion=False, help="Pipeline failure self-repair ledger CLI.")

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent
REPO_ROOT = SKILLS_ROOT.parent
TRIAGE_RUN = SKILLS_ROOT / "triage-error" / "run.sh"
MEMORY_RUN = SKILLS_ROOT / "memory" / "run.sh"
TICKET_RUN = SKILLS_ROOT / "ticket" / "run.sh"
WATCHDOG_RUN = SKILLS_ROOT / "project-watchdog" / "run.sh"
AGENTIC_EVALS_RUN = SKILLS_ROOT / "agentic-evals" / "run.sh"

EVENT_SCHEMA = "pipeline_self_repair.event.v1"
SUMMARY_SCHEMA = "pipeline_self_repair.summary.v1"
VALIDATION_SCHEMA = "pipeline_self_repair.validation.v1"
DEPENDENCY_REF_RE = re.compile(r"(?:blocked-by|depends[-_ ]on):\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+)")
ISSUE_NUMBER_RE = re.compile(r"(?:issues/|#)(\d+)\b")


class RepairState(StrEnum):
    """Closed vocabulary for the repair branch state."""

    NEEDS_TRIAGE = "NEEDS_TRIAGE"
    TICKETED = "TICKETED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    BLOCKED_BY_UPSTREAM = "BLOCKED_BY_UPSTREAM"
    WATCHDOG_DISPATCHED = "WATCHDOG_DISPATCHED"
    CATEGORY_GREEN = "CATEGORY_GREEN"
    CLOSED = "CLOSED"


class SpendState(StrEnum):
    """External-effect spend state for non-idempotent provider actions."""

    NONE = "none"
    INTENDED = "intended"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"


class CommandResult(BaseModel):
    """Bounded subprocess result captured into the ledger."""

    command: list[str]
    returncode: int
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


class TriageResult(BaseModel):
    """triage-error classify output."""

    code: str = Field(min_length=1)
    layer: str | None = None
    cause: str | None = None
    next_command: str | None = None
    recoverable: bool | None = None
    ambiguous: bool = False
    matched_tokens: list[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    """Content-addressed artifact reference."""

    path: str
    sha256: str
    bytes: int


class TicketDisposition(BaseModel):
    """Ticket projection result for a repair category."""

    action: str
    issue_ref: str | None = None
    issue_state: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    result: CommandResult | None = None
    note: str | None = None


class PipelineFailureEvent(BaseModel):
    """Append-only replay ledger event."""

    schema_name: str = Field(default=EVENT_SCHEMA, alias="schema")
    event_id: str
    event_type: str = "step.failed"
    occurred_at: str
    pipeline: str
    run_id: str
    step_id: str
    attempt: int = Field(default=1, ge=1)
    checkpoint_id: str | None = None
    goal_hash: str | None = None
    repo: str = "grahama1970/agent-skills"
    target: str
    layer: str | None = None
    raw_signal_sha256: str
    raw_signal_excerpt: str
    triage: TriageResult
    category_key: str
    failure_category_id: str
    fingerprint: str
    blocking: bool = True
    repair_state: RepairState
    memory_recall: dict[str, Any] = Field(default_factory=dict)
    github_issue_search: dict[str, Any] = Field(default_factory=dict)
    ticket: TicketDisposition
    watchdog: dict[str, Any] = Field(default_factory=dict)
    agentic_eval: dict[str, Any] = Field(default_factory=dict)
    provider_effect: dict[str, Any] = Field(default_factory=dict)
    inputs: list[EvidenceRef] = Field(default_factory=list)
    outputs: list[EvidenceRef] = Field(default_factory=list)
    previous_event_hash: str | None = None
    event_hash: str

    model_config = {"populate_by_name": True}

    @field_validator("occurred_at")
    @classmethod
    def _utc_timestamp(cls, value: str) -> str:
        if "+00:00" not in value and not value.endswith("Z"):
            raise ValueError("occurred_at must be timezone-aware UTC")
        return value


# Pydantic 2 keeps annotations as strings under `from __future__ import annotations`.
# Rebuild models explicitly so dynamic imports in tests and Typer subprocess runs
# both resolve the same nested types.
CommandResult.model_rebuild(_types_namespace=globals())
TriageResult.model_rebuild(_types_namespace=globals())
EvidenceRef.model_rebuild(_types_namespace=globals())
TicketDisposition.model_rebuild(_types_namespace=globals())
PipelineFailureEvent.model_rebuild(_types_namespace=globals())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str, *, limit: int = 80) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (text or "unknown")[:limit].strip("-") or "unknown"


def _sha_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha_json(payload: Any) -> str:
    return _sha_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_raw_signal(raw_signal: str, receipt: Path | None) -> str:
    if raw_signal.strip():
        return raw_signal
    if receipt and receipt.is_file():
        return _read_text(receipt)
    raise typer.BadParameter("provide --raw-signal or --receipt with content")


def _artifact_ref(path: Path) -> EvidenceRef:
    data = path.read_bytes()
    return EvidenceRef(path=str(path), sha256=_sha_bytes(data), bytes=len(data))


def _run(cmd: list[str], *, timeout: int = 120) -> CommandResult:
    logger.debug("running command: {}", cmd)
    env = os.environ.copy()
    # Do not leak this skill's uv environment into sibling skills. Each skill
    # owns its own project dependencies; sharing UV_PROJECT_ENVIRONMENT causes uv
    # to uninstall/reinstall packages between composed skill calls.
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    return CommandResult(
        command=cmd,
        returncode=proc.returncode,
        stdout_excerpt=proc.stdout[-4000:],
        stderr_excerpt=proc.stderr[-2000:],
    )


def _classify(signal: str, layer: str | None) -> TriageResult:
    if not TRIAGE_RUN.exists():
        raise RuntimeError(f"missing triage-error runner: {TRIAGE_RUN}")
    cmd = [str(TRIAGE_RUN), "classify", "--text", signal]
    if layer:
        cmd.extend(["--layer", layer])
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"triage-error classify failed: {result.stderr_excerpt or result.stdout_excerpt}")
    return TriageResult.model_validate(json.loads(result.stdout_excerpt))


def _repo_slug(repo: str) -> str:
    return _slug(repo.split("/")[-1])


def _category(pipeline: str, step_id: str, triage: TriageResult, target: str, repo: str) -> tuple[str, str]:
    category_key = f"{_slug(pipeline)}/{_slug(step_id)}/{_slug(triage.code)}/{_slug(target)}/v1"
    category_id = f"agentic-evals:{_repo_slug(repo)}:{_slug(pipeline)}-{_slug(step_id)}-{_slug(triage.code)}"
    return category_key, category_id


def _memory_query(pipeline: str, step_id: str, triage: TriageResult, category_key: str) -> str:
    return (
        f"pipeline self repair prior resolution {pipeline} {step_id} "
        f"{triage.code} {category_key} {triage.cause or ''}"
    )


def _memory_recall(query: str, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "query": query}
    if not MEMORY_RUN.exists():
        return {"status": "FAILED", "query": query, "error": "memory run.sh not found"}
    result = _run([str(MEMORY_RUN), "recall", "--q", query, "--brief"], timeout=180)
    payload: dict[str, Any] = {"status": "PASS" if result.returncode == 0 else "FAILED", "query": query, "command": result.model_dump()}
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout_excerpt)
            payload.update({
                "found": bool(data.get("found")),
                "confidence": data.get("confidence"),
                "item_count": len(data.get("items") or []),
                "top_items": data.get("items", [])[:3],
                "skill_chain": data.get("skill_chain"),
            })
        except json.JSONDecodeError as exc:
            payload.update({"status": "FAILED", "error": f"memory output was not JSON: {exc}"})
    return payload


def _issue_queries(repo: str, category_key: str, triage: TriageResult, step_id: str, target: str) -> list[str]:
    return [
        f'"repair-category:{category_key}"',
        f'"{category_key}"',
        f'"{triage.code}"',
        f'"{step_id}" "{triage.code}"',
        f'"{target}" "{triage.code}"',
        f'label:agent-work "{target}"',
    ]


def _github_issue_search(repo: str, category_key: str, triage: TriageResult, step_id: str, target: str, *, skip: bool) -> dict[str, Any]:
    queries = _issue_queries(repo, category_key, triage, step_id, target)
    if skip:
        return {"status": "SKIPPED", "queries": queries, "matches": []}
    matches: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    seen: set[int] = set()
    for query in queries:
        cmd = ["gh", "issue", "list", "--repo", repo, "--state", "all", "--limit", "20", "--search", query, "--json", "number,title,state,labels,url,body"]
        result = _run(cmd)
        commands.append(result.model_dump())
        if result.returncode != 0:
            return {"status": "FAILED", "queries": queries, "matches": matches, "commands": commands}
        try:
            rows = json.loads(result.stdout_excerpt or "[]")
        except json.JSONDecodeError:
            return {"status": "FAILED", "queries": queries, "matches": matches, "commands": commands, "error": "gh output was not JSON"}
        for row in rows:
            number = int(row.get("number") or 0)
            if not number or number in seen:
                continue
            seen.add(number)
            body = row.get("body") or ""
            label_names = [item.get("name") for item in row.get("labels", []) if isinstance(item, dict)]
            matches.append({
                "repo": repo,
                "number": number,
                "issue_ref": f"{repo}#{number}",
                "state": row.get("state"),
                "title": row.get("title"),
                "url": row.get("url"),
                "labels": label_names,
                "depends_on": sorted(set(DEPENDENCY_REF_RE.findall(body))),
                "matched_query": query,
                "has_category_marker": category_key in body,
                "has_triage_code": triage.code in body,
            })
    return {"status": "PASS", "queries": queries, "matches": matches, "commands": commands}


def _choose_ticket(matches: list[dict[str, Any]]) -> TicketDisposition | None:
    if not matches:
        return None
    preferred = sorted(matches, key=lambda row: (not row.get("has_category_marker"), row.get("state") != "OPEN", row.get("number")))[0]
    deps = preferred.get("depends_on") or []
    if deps and preferred.get("state") == "OPEN":
        return TicketDisposition(
            action="blocked_by_upstream",
            issue_ref=preferred.get("issue_ref"),
            issue_state=preferred.get("state"),
            depends_on=deps,
            note="Existing category-like ticket is blocked by upstream dependency; recheck dependency before creating another ticket.",
        )
    if preferred.get("state") == "CLOSED":
        return TicketDisposition(
            action="needs_reopen",
            issue_ref=preferred.get("issue_ref"),
            issue_state=preferred.get("state"),
            depends_on=deps,
            note="Closed issue matched this category; treat as recurrence or false closure before filing a duplicate.",
        )
    return TicketDisposition(
        action="bind_existing",
        issue_ref=preferred.get("issue_ref"),
        issue_state=preferred.get("state"),
        depends_on=deps,
        note="Open existing issue matched this failure category.",
    )


def _ticket_command(
    *,
    repo: str,
    pipeline: str,
    target: str,
    triage: TriageResult,
    category_key: str,
    category_id: str,
    run_id: str,
    step_id: str,
    apply: bool,
    agentic_eval_report: Path | None,
) -> list[str]:
    title = f"Repair {pipeline} failure: {step_id} {triage.code}"
    proof = (
        "Retain or add an agentic-evals regression for this category, run the category proof, "
        "then run the affected full suite/checkpoint replay and read back the receipt."
    )
    if agentic_eval_report:
        proof = f"Re-run agentic-evals report path {agentic_eval_report}; category must disappear, then checkpoint replay must pass."
    cmd = [
        str(TICKET_RUN), "bug", title,
        "--target", target,
        "--observed", f"<!-- repair-category:{category_key} -->\n<!-- failure-category-id:{category_id} -->\n[{triage.code}] {triage.cause or 'pipeline step failed'}; repair_category={category_key}; failure_category_id={category_id}",
        "--expected", "The required pipeline step either passes or blocks with a classified repair category, retained eval coverage, and a safe checkpoint resume path.",
        "--repro", f"Run pipeline-self-repair record-failure for run_id={run_id} step_id={step_id}; inspect ledger category {category_key}.",
        "--proof", proof,
        "--route", "backend_python_or_skill_runtime",
        "--agent", "agent-skill-maintainer",
        "--required-skill", "pipeline-self-repair",
        "--required-skill", "triage-error",
        "--required-skill", "agentic-evals",
        "--context-file", target + "/SKILL.md" if target.startswith("skills/") else target,
        "--label", "pipeline-self-repair",
        "--repo", repo,
        "--json",
    ]
    if apply:
        cmd.append("--apply")
    return cmd


def _create_or_draft_ticket(
    *,
    existing: TicketDisposition | None,
    no_ticket: bool,
    apply_ticket: bool,
    **kwargs: Any,
) -> TicketDisposition:
    if existing:
        return existing
    if no_ticket:
        return TicketDisposition(action="ticket_skipped", note="--no-ticket was set; repair category is not routable yet.")
    if not TICKET_RUN.exists():
        return TicketDisposition(action="ticket_failed", note="ticket run.sh not found")
    cmd = _ticket_command(apply=apply_ticket, **kwargs)
    result = _run(cmd, timeout=180)
    action = "created" if apply_ticket and result.returncode == 0 else "create_draft"
    issue_ref = _extract_issue_ref(result.stdout_excerpt, kwargs["repo"])
    return TicketDisposition(action=action, issue_ref=issue_ref, command=cmd, result=result)


def _extract_issue_ref(text: str, repo: str) -> str | None:
    match = ISSUE_NUMBER_RE.search(text or "")
    if match:
        return f"{repo}#{match.group(1)}"
    return None


def _provider_effect(
    *,
    request_body: Path | None,
    provider_task_id: str,
    provider_response: Path | None,
    media_urls: list[str],
    local_artifacts: list[Path],
    spend_state: SpendState,
) -> tuple[dict[str, Any], list[EvidenceRef], list[EvidenceRef]]:
    inputs: list[EvidenceRef] = []
    outputs: list[EvidenceRef] = []
    effect: dict[str, Any] = {"spend_state": spend_state.value, "resubmission_allowed": spend_state not in {SpendState.UNKNOWN, SpendState.CONFIRMED}}
    if request_body:
        ref = _artifact_ref(request_body)
        inputs.append(ref)
        effect["request_body"] = ref.model_dump()
    if provider_response:
        ref = _artifact_ref(provider_response)
        outputs.append(ref)
        effect["provider_response"] = ref.model_dump()
    if provider_task_id:
        effect["provider_task_id"] = provider_task_id
        effect["next_legal_command"] = "poll_or_reconcile_existing_task"
        effect["resubmission_allowed"] = False
    elif spend_state == SpendState.UNKNOWN:
        effect["next_legal_command"] = "reconcile_provider_effect_before_resubmit"
    else:
        effect["next_legal_command"] = "repair_input_or_request_authorization_before_resubmit"
    if media_urls:
        effect["media_urls"] = media_urls
    artifact_refs = [_artifact_ref(path) for path in local_artifacts]
    outputs.extend(artifact_refs)
    if artifact_refs:
        effect["local_artifacts"] = [ref.model_dump() for ref in artifact_refs]
    return effect, inputs, outputs


def _previous_hash(ledger: Path) -> str | None:
    if not ledger.exists():
        return None
    last = None
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = json.loads(line)
    return last.get("event_hash") if last else None


def _append_event(ledger: Path, event_payload: dict[str, Any]) -> PipelineFailureEvent:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    event_payload["previous_event_hash"] = _previous_hash(ledger)
    event_payload["event_hash"] = _sha_json({k: v for k, v in event_payload.items() if k != "event_hash"})
    event = PipelineFailureEvent.model_validate(event_payload)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(by_alias=True), sort_keys=True) + "\n")
    return event


def _repair_state(triage: TriageResult, ticket: TicketDisposition, dispatch_watchdog: bool, watchdog: dict[str, Any], provider_effect: dict[str, Any]) -> RepairState:
    if triage.ambiguous:
        return RepairState.NEEDS_TRIAGE
    if provider_effect.get("spend_state") == SpendState.UNKNOWN.value:
        return RepairState.NEEDS_HUMAN
    if ticket.action == "blocked_by_upstream":
        return RepairState.BLOCKED_BY_UPSTREAM
    if ticket.action == "needs_reopen":
        return RepairState.NEEDS_HUMAN
    if dispatch_watchdog and watchdog.get("status") in {"PASS", "COMPLETED"}:
        return RepairState.WATCHDOG_DISPATCHED
    if ticket.action in {"bind_existing", "created", "create_draft"}:
        return RepairState.TICKETED
    return RepairState.NEEDS_HUMAN


def _dispatch_watchdog(project: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "SKIPPED"}
    if not WATCHDOG_RUN.exists():
        return {"status": "FAILED", "error": "project-watchdog run.sh not found"}
    result = _run([str(WATCHDOG_RUN), "tick", "--apply", "--project", project, "--max-tickets", "1"], timeout=600)
    return {"status": "PASS" if result.returncode == 0 else "FAILED", "command": result.model_dump()}


@app.command("record-failure")
def record_failure(
    pipeline: str = typer.Option(..., "--pipeline"),
    step_id: str = typer.Option(..., "--step-id"),
    run_id: str = typer.Option(..., "--run-id"),
    target: str = typer.Option(..., "--target"),
    run_root: Path = typer.Option(..., "--run-root"),
    ledger: Path = typer.Option(..., "--ledger"),
    raw_signal: str = typer.Option("", "--raw-signal"),
    receipt: Path | None = typer.Option(None, "--receipt"),
    layer: str | None = typer.Option(None, "--layer"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    attempt: int = typer.Option(1, "--attempt", min=1),
    checkpoint_id: str | None = typer.Option(None, "--checkpoint-id"),
    goal_hash: str | None = typer.Option(None, "--goal-hash"),
    request_body: Path | None = typer.Option(None, "--request-body"),
    provider_task_id: str = typer.Option("", "--provider-task-id"),
    provider_response: Path | None = typer.Option(None, "--provider-response"),
    media_url: list[str] = typer.Option([], "--media-url"),
    local_artifact: list[Path] = typer.Option([], "--local-artifact"),
    spend_state: SpendState = typer.Option(SpendState.NONE, "--spend-state"),
    agentic_eval_report: Path | None = typer.Option(None, "--agentic-eval-report"),
    skip_memory: bool = typer.Option(False, "--skip-memory"),
    skip_github: bool = typer.Option(False, "--skip-github"),
    no_ticket: bool = typer.Option(False, "--no-ticket"),
    apply_ticket: bool = typer.Option(False, "--apply-ticket"),
    dispatch_watchdog: bool = typer.Option(False, "--dispatch-watchdog"),
    watchdog_project: str = typer.Option("agent-skills", "--watchdog-project"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Record a step failure and start the triage/ticket/watchdog repair branch."""
    run_root.mkdir(parents=True, exist_ok=True)
    signal = _read_raw_signal(raw_signal, receipt)
    triage = _classify(signal, layer)
    category_key, category_id = _category(pipeline, step_id, triage, target, repo)
    memory = _memory_recall(_memory_query(pipeline, step_id, triage, category_key), skip=skip_memory)
    github = _github_issue_search(repo, category_key, triage, step_id, target, skip=skip_github)
    existing = _choose_ticket(github.get("matches") or []) if github.get("status") == "PASS" else None
    ticket = _create_or_draft_ticket(
        existing=existing,
        no_ticket=no_ticket,
        apply_ticket=apply_ticket,
        repo=repo,
        pipeline=pipeline,
        target=target,
        triage=triage,
        category_key=category_key,
        category_id=category_id,
        run_id=run_id,
        step_id=step_id,
        agentic_eval_report=agentic_eval_report,
    )
    watchdog = _dispatch_watchdog(watchdog_project, enabled=dispatch_watchdog and ticket.action in {"created", "bind_existing"})
    effect, inputs, outputs = _provider_effect(
        request_body=request_body,
        provider_task_id=provider_task_id,
        provider_response=provider_response,
        media_urls=media_url,
        local_artifacts=local_artifact,
        spend_state=spend_state,
    )
    state = _repair_state(triage, ticket, dispatch_watchdog, watchdog, effect)
    payload = {
        "event_id": "evt_" + hashlib.sha256(f"{pipeline}:{run_id}:{step_id}:{attempt}:{_now()}".encode()).hexdigest()[:24],
        "occurred_at": _now(),
        "pipeline": pipeline,
        "run_id": run_id,
        "step_id": step_id,
        "attempt": attempt,
        "checkpoint_id": checkpoint_id,
        "goal_hash": goal_hash,
        "repo": repo,
        "target": target,
        "layer": layer,
        "raw_signal_sha256": _sha_bytes(signal.encode("utf-8", errors="replace")),
        "raw_signal_excerpt": signal[:500],
        "triage": triage.model_dump(),
        "category_key": category_key,
        "failure_category_id": category_id,
        "fingerprint": _sha_json({"category_key": category_key, "step_id": step_id, "target": target, "triage_code": triage.code}),
        "blocking": True,
        "repair_state": state.value,
        "memory_recall": memory,
        "github_issue_search": github,
        "ticket": ticket.model_dump(),
        "watchdog": watchdog,
        "agentic_eval": {"report": str(agentic_eval_report) if agentic_eval_report else None, "retained_guard_required": True},
        "provider_effect": effect,
        "inputs": [ref.model_dump() for ref in inputs],
        "outputs": [ref.model_dump() for ref in outputs],
    }
    event = _append_event(ledger, payload)
    result = {"status": "RECORDED_NEEDS_TRIAGE" if triage.ambiguous else "RECORDED_REPAIR_REQUIRED", "ledger": str(ledger), "event": event.model_dump(by_alias=True)}
    _emit(result, json_output)


@app.command("inspect")
def inspect_ledger(ledger: Path = typer.Option(..., "--ledger"), json_output: bool = typer.Option(False, "--json")) -> None:
    """Fold a replay ledger into current category and checkpoint state."""
    events = _load_events(ledger)
    categories: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event.get("category_key")
        if not key:
            continue
        categories.setdefault(key, {"events": 0, "latest_state": None, "ticket": None, "triage_code": None})
        categories[key]["events"] += 1
        categories[key]["latest_state"] = event.get("repair_state")
        categories[key]["ticket"] = (event.get("ticket") or {}).get("issue_ref")
        categories[key]["triage_code"] = (event.get("triage") or {}).get("code")
    open_failures = [e for e in events if e.get("blocking") and e.get("repair_state") not in {RepairState.CATEGORY_GREEN.value, RepairState.CLOSED.value}]
    _emit({"schema": SUMMARY_SCHEMA, "ledger": str(ledger), "event_count": len(events), "open_failure_count": len(open_failures), "categories": categories}, json_output)


@app.command("validate-ledger")
def validate_ledger(
    ledger: Path = typer.Option(..., "--ledger"),
    require_agentic_eval: bool = typer.Option(False, "--require-agentic-eval"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Fail closed if blocking failures lack repair disposition."""
    events = _load_events(ledger)
    failures: list[str] = []
    for index, event in enumerate(events):
        if not event.get("blocking"):
            continue
        state = event.get("repair_state")
        if state in {RepairState.CATEGORY_GREEN.value, RepairState.CLOSED.value}:
            continue
        if not (event.get("triage") or {}).get("code"):
            failures.append(f"event[{index}] missing triage code")
        if not event.get("category_key") or not event.get("failure_category_id"):
            failures.append(f"event[{index}] missing category binding")
        ticket_action = (event.get("ticket") or {}).get("action")
        if ticket_action in {None, "ticket_skipped", "ticket_failed"}:
            failures.append(f"event[{index}] lacks ticket disposition")
        if require_agentic_eval and not (event.get("agentic_eval") or {}).get("report"):
            failures.append(f"event[{index}] lacks retained agentic-evals report/proof reference")
    result = {"schema": VALIDATION_SCHEMA, "ledger": str(ledger), "status": "PASS" if not failures else "FAIL", "failure_count": len(failures), "failures": failures}
    _emit(result, json_output)
    if failures:
        raise typer.Exit(1)


@app.command("agentic-eval-remediate")
def agentic_eval_remediate(
    report: Path = typer.Option(..., "--report"),
    category_map: Path = typer.Option(..., "--category-map"),
    fixture: str = typer.Option(..., "--fixture"),
    ledger: Path = typer.Option(..., "--ledger"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    route: str = typer.Option("backend_python_or_skill_runtime", "--route"),
    execute: bool = typer.Option(False, "--execute"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Project a complete agentic-evals report into category tickets via agentic-evals remediate."""
    cmd = [str(AGENTIC_EVALS_RUN), "remediate", str(report), "--map", str(category_map), "--fixture", fixture, "--route", route]
    if execute:
        cmd.append("--execute")
    result = _run(cmd, timeout=300)
    payload = {
        "schema": EVENT_SCHEMA,
        "event_id": "evt_" + hashlib.sha256(f"agentic-eval:{report}:{_now()}".encode()).hexdigest()[:24],
        "event_type": "agentic_eval.remediation_projected",
        "occurred_at": _now(),
        "pipeline": "agentic-evals",
        "run_id": report.stem,
        "step_id": "agentic_eval_remediate",
        "target": str(report),
        "repo": repo,
        "raw_signal_sha256": _sha_bytes(report.read_bytes()),
        "raw_signal_excerpt": str(report),
        "triage": {"code": "agentic_eval_failure_categories", "ambiguous": False, "matched_tokens": []},
        "category_key": f"agentic-evals/{_slug(report.stem)}/remediation/v1",
        "failure_category_id": f"agentic-evals:{_repo_slug(repo)}:{_slug(report.stem)}-remediation",
        "fingerprint": _sha_json({"report": str(report), "category_map": str(category_map), "fixture": fixture}),
        "blocking": result.returncode != 0,
        "repair_state": RepairState.TICKETED.value if result.returncode == 0 else RepairState.NEEDS_HUMAN.value,
        "ticket": {"action": "agentic_evals_remediate_executed" if execute else "agentic_evals_remediate_preview", "result": result.model_dump()},
        "agentic_eval": {"report": str(report), "category_map": str(category_map), "fixture": fixture},
    }
    event = _append_event(ledger, payload)
    _emit({"status": "PASS" if result.returncode == 0 else "FAIL", "ledger": str(ledger), "event": event.model_dump(by_alias=True)}, json_output)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _load_events(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"invalid JSON on ledger line {line_no}: {exc}") from exc
    return events


def _emit(payload: dict[str, Any], json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(payload.get("status") or json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    try:
        app()
    except ValidationError as exc:
        logger.error("validation failed: {}", exc)
        typer.echo(exc.json(), err=True)
        raise typer.Exit(2) from exc
