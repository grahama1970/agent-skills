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
GOAL_DRIFT_RUN = SKILLS_ROOT / "goal-drift" / "run.sh"

EVENT_SCHEMA = "pipeline_self_repair.event.v1"
SUMMARY_SCHEMA = "pipeline_self_repair.summary.v1"
VALIDATION_SCHEMA = "pipeline_self_repair.validation.v1"
MONITOR_SCHEMA = "pipeline_self_repair.monitor.v1"
HARDENING_CYCLE_SCHEMA = "pipeline_self_repair.hardening_cycle.v1"
HARDENING_CYCLE_EVENT_SCHEMA = "pipeline_self_repair.hardening_cycle_event.v1"
DEPENDENCY_REF_RE = re.compile(r"(?:blocked-by|depends[-_ ]on):\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+)")
ISSUE_NUMBER_RE = re.compile(r"(?:issues/|#)(\d+)\b")
WATCHDOG_PROJECT_BY_REPO = {"grahama1970/graph-memory-operator": "memory", "grahama1970/agent-skills": "agent-skills"}


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
    goal_alignment: dict[str, Any] = Field(default_factory=dict)
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
    return _sha_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _goal_hash(goal_payload: dict[str, Any]) -> str:
    """Match goal-drift's content hash convention without importing its package."""
    stripped = {
        key: value
        for key, value in goal_payload.items()
        if key not in {"registered_at", "goal_hash", "seam_validation", "parent_goal_hash"}
    }
    return _sha_json(stripped)


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


def _clean_child_env() -> dict[str, str]:
    env = os.environ.copy()
    # Do not leak this skill's uv environment into sibling skills. Each skill
    # owns its own project dependencies; sharing UV_PROJECT_ENVIRONMENT causes uv
    # to uninstall/reinstall packages between composed skill calls.
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    return env


def _command_result(cmd: list[str], proc: subprocess.CompletedProcess[str]) -> CommandResult:
    return CommandResult(
        command=cmd,
        returncode=proc.returncode,
        stdout_excerpt=proc.stdout[-4000:],
        stderr_excerpt=proc.stderr[-2000:],
    )


def _run(cmd: list[str], *, timeout: int = 120) -> CommandResult:
    logger.debug("running command: {}", cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=_clean_child_env())
    return _command_result(cmd, proc)


def _run_with_stdout(cmd: list[str], *, timeout: int = 120) -> tuple[CommandResult, str]:
    """Run a command and keep full stdout for machine parsing.

    The ledger stores bounded excerpts, but JSON producers such as `memory` and
    `gh issue list` may emit bodies larger than the excerpt window. Parsing the
    excerpt would turn a successful lookup into a false failure.
    """
    logger.debug("running command: {}", cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=_clean_child_env())
    return _command_result(cmd, proc), proc.stdout


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


def _load_immutable_goal(project: str) -> tuple[dict[str, Any], CommandResult]:
    """Read the immutable goal or fail before a repair branch starts."""
    if not GOAL_DRIFT_RUN.exists():
        raise typer.BadParameter(f"immutable goal preflight failed: missing goal-drift runner {GOAL_DRIFT_RUN}")
    result, stdout = _run_with_stdout([str(GOAL_DRIFT_RUN), "goal", "--project", project], timeout=120)
    try:
        payload = json.loads(stdout or result.stdout_excerpt or "{}")
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"immutable goal preflight failed: goal-drift output was not JSON: {exc}") from exc
    if result.returncode != 0 or payload.get("status") == "NOT_ESTABLISHED":
        raise typer.BadParameter(
            f"immutable goal preflight failed for project {project!r}: {payload.get('reason') or 'no immutable goal registered'}"
        )
    if payload.get("schema") != "goal_drift.goal.v1":
        raise typer.BadParameter(f"immutable goal preflight failed for project {project!r}: unexpected schema {payload.get('schema')!r}")
    if payload.get("source") != "human_prompt":
        raise typer.BadParameter(f"immutable goal preflight failed for project {project!r}: source is not human_prompt")
    if not payload.get("goal_text"):
        raise typer.BadParameter(f"immutable goal preflight failed for project {project!r}: empty goal_text")
    return payload, result


def _goal_alignment(
    *,
    project: str,
    goal_payload: dict[str, Any],
    goal_command: CommandResult,
    expected_goal_hash: str | None,
    pipeline: str,
    step_id: str,
    target: str,
    triage: TriageResult | None,
    raw_signal: str,
    extra_context: list[str],
) -> dict[str, Any]:
    computed_hash = _goal_hash(goal_payload)
    if expected_goal_hash and expected_goal_hash != computed_hash:
        raise typer.BadParameter(
            f"immutable goal preflight failed for project {project!r}: supplied goal hash {expected_goal_hash} != current {computed_hash}"
        )
    context = "\n".join(
        part for part in [
            project,
            pipeline,
            step_id,
            target,
            raw_signal,
            triage.code if triage else "",
            triage.cause if triage and triage.cause else "",
            *(extra_context or []),
        ] if part
    ).lower()
    matches: list[dict[str, Any]] = []
    for criterion in goal_payload.get("criteria") or []:
        keywords = [str(item) for item in criterion.get("keywords") or []]
        matched = [kw for kw in keywords if kw.lower() in context]
        if matched:
            matches.append({"key": criterion.get("key"), "matched_keywords": matched})
    target_project_match = f"skills/{project}" in target or pipeline == project
    drift_risk = "LOW" if target_project_match or matches else "REVIEW_REQUIRED_NO_CRITERION_MATCH"
    return {
        "status": "PASS_COMPARED_TO_IMMUTABLE_GOAL",
        "project": project,
        "goal_hash": computed_hash,
        "goal_source": goal_payload.get("source"),
        "goal_text_sha256": _sha_bytes(str(goal_payload.get("goal_text", "")).encode("utf-8")),
        "criteria_count": len(goal_payload.get("criteria") or []),
        "matching_criteria": matches,
        "target_project_match": target_project_match,
        "drift_risk": drift_risk,
        "command": goal_command.model_dump(),
    }


def _memory_recall(query: str, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "query": query}
    if not MEMORY_RUN.exists():
        return {"status": "FAILED", "query": query, "error": "memory run.sh not found"}
    result, stdout = _run_with_stdout([str(MEMORY_RUN), "recall", "--q", query, "--brief"], timeout=180)
    payload: dict[str, Any] = {"status": "PASS" if result.returncode == 0 else "FAILED", "query": query, "command": result.model_dump()}
    if result.returncode == 0:
        try:
            data = json.loads(stdout)
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
        result, stdout = _run_with_stdout(cmd)
        commands.append(result.model_dump())
        if result.returncode != 0:
            return {"status": "FAILED", "queries": queries, "matches": matches, "commands": commands}
        try:
            rows = json.loads(stdout or "[]")
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
    category_matches = [
        row for row in matches if row.get("has_category_marker") or row.get("has_triage_code")
    ]
    if not category_matches:
        return None
    preferred = sorted(
        category_matches,
        key=lambda row: (
            not row.get("has_category_marker"),
            not row.get("has_triage_code"),
            row.get("state") != "OPEN",
            row.get("number"),
        ),
    )[0]
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


def _append_replay_ledger_event(ledger: Path, event_payload: dict[str, Any]) -> dict[str, Any]:
    """Append a flexible hash-chained hardening-cycle event.

    `record-failure` events keep the stricter PipelineFailureEvent schema.
    Hardening-cycle events are orchestration receipts: they bind WebGPT parsing,
    ticket creation, watchdog dispatch/readback, and next legal commands without
    pretending to be one failed pipeline step.
    """
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event_payload)
    payload.setdefault("schema", HARDENING_CYCLE_EVENT_SCHEMA)
    payload.setdefault("occurred_at", _now())
    payload.setdefault("event_id", "evt_" + hashlib.sha256(f"hardening-cycle:{_now()}".encode()).hexdigest()[:24])
    payload["previous_event_hash"] = _previous_hash(ledger)
    payload["event_hash"] = _sha_json({k: v for k, v in payload.items() if k != "event_hash"})
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def _append_event(ledger: Path, event_payload: dict[str, Any]) -> PipelineFailureEvent:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    event_payload["previous_event_hash"] = _previous_hash(ledger)
    event_payload["event_hash"] = _sha_json({k: v for k, v in event_payload.items() if k != "event_hash"})
    event = PipelineFailureEvent.model_validate(event_payload)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(by_alias=True), sort_keys=True) + "\n")
    return event


def _fold_categories(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fold the append-only ledger by category, keeping latest event state."""
    categories: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event.get("category_key")
        if not key:
            continue
        categories.setdefault(
            key,
            {"events": 0, "latest_state": None, "latest_event": None, "ticket": None, "triage_code": None},
        )
        categories[key]["events"] += 1
        categories[key]["latest_state"] = event.get("repair_state")
        categories[key]["latest_event"] = event
        categories[key]["ticket"] = (event.get("ticket") or {}).get("issue_ref")
        categories[key]["triage_code"] = (event.get("triage") or {}).get("code")
    return categories


def _repair_state(triage: TriageResult, ticket: TicketDisposition, dispatch_watchdog: bool, watchdog: dict[str, Any], provider_effect: dict[str, Any]) -> RepairState:
    if provider_effect.get("spend_state") == SpendState.UNKNOWN.value:
        return RepairState.NEEDS_HUMAN
    if triage.ambiguous:
        return RepairState.NEEDS_TRIAGE
    if ticket.action == "blocked_by_upstream":
        return RepairState.BLOCKED_BY_UPSTREAM
    if ticket.action == "needs_reopen":
        return RepairState.NEEDS_HUMAN
    if dispatch_watchdog and watchdog.get("status") in {"PASS", "COMPLETED"}:
        return RepairState.WATCHDOG_DISPATCHED
    if ticket.action in {"bind_existing", "created", "create_draft"}:
        return RepairState.TICKETED
    return RepairState.NEEDS_HUMAN


def _watchdog_project_for_repo(repo: str, default_project: str) -> str:
    return WATCHDOG_PROJECT_BY_REPO.get(repo, default_project)


def _dispatch_watchdog_ticket(issue_ref: str, repo: str, default_project: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "SKIPPED", "issue_ref": issue_ref, "reason": "watchdog dispatch disabled"}
    if not WATCHDOG_RUN.exists():
        return {"status": "FAILED", "issue_ref": issue_ref, "error": "project-watchdog run.sh not found"}
    if "#" not in issue_ref:
        return {"status": "FAILED", "issue_ref": issue_ref, "error": "expected owner/repo#number"}
    issue_repo, issue_number = issue_ref.rsplit("#", 1)
    project = _watchdog_project_for_repo(issue_repo or repo, default_project)
    command = [str(WATCHDOG_RUN), "tick", "--apply", "--project", project, "--issue", issue_number, "--max-tickets", "1"]
    result, stdout = _run_with_stdout(command, timeout=2400)
    parsed, _ = _parse_json_prefix(stdout)
    status = "PASS" if result.returncode == 0 else "FAILED"
    if parsed and parsed.get("status") in {"COMPLETED", "NEEDS_ATTENTION", "BLOCKED", "NOOP", "SKIPPED"}:
        status = parsed["status"]
    return {
        "status": status,
        "issue_ref": issue_ref,
        "project": project,
        "command": result.model_dump(),
        "receipt_path": parsed.get("receipt_path") if parsed else None,
        "receipt": parsed,
    }


def _dispatch_watchdog_for_ticket_projections(
    projections: list[dict[str, Any]],
    *,
    default_project: str,
    enabled: bool,
) -> list[dict[str, Any]]:
    dispatches: list[dict[str, Any]] = []
    for projection in projections:
        issue_ref = projection.get("issue_ref")
        if not issue_ref or projection.get("status") not in {"CREATED", "BOUND"}:
            continue
        dispatches.append(
            _dispatch_watchdog_ticket(
                str(issue_ref),
                str(projection.get("repo") or ""),
                default_project,
                enabled=enabled,
            )
        )
    return dispatches


def _dispatch_watchdog(project: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "SKIPPED"}
    if not WATCHDOG_RUN.exists():
        return {"status": "FAILED", "error": "project-watchdog run.sh not found"}
    result = _run([str(WATCHDOG_RUN), "tick", "--apply", "--project", project, "--max-tickets", "1"], timeout=600)
    return {"status": "PASS" if result.returncode == 0 else "FAILED", "command": result.model_dump()}


def _ledger_summary(ledger: Path | None) -> dict[str, Any]:
    if ledger is None:
        return {"status": "SKIPPED", "reason": "no ledger supplied"}
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
    return {
        "status": "PASS",
        "ledger": str(ledger),
        "event_count": len(events),
        "open_failure_count": len(open_failures),
        "categories": categories,
    }


def _watchdog_status(project: str, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED"}
    if not WATCHDOG_RUN.exists():
        return {"status": "FAILED", "error": "project-watchdog run.sh not found"}
    result = _run([str(WATCHDOG_RUN), "status"], timeout=120)
    return {"status": "PASS" if result.returncode == 0 else "FAILED", "project": project, "command": result.model_dump()}


def _push_pull_monitoring(subagent_run_ids: list[str], ask_run_dirs: list[Path], ticket_refs: list[str]) -> dict[str, Any]:
    return {
        "owner": "project-agent",
        "push": {
            "pi_wake_subscriptions": [
                f'subagent_wait({{"id":"{run_id}","nonBlocking":true}})' for run_id in subagent_run_ids
            ],
            "note": "The shell CLI cannot arm Pi wake subscriptions itself; the Pi parent project agent must call subagent_wait with nonBlocking=true for each owned async run.",
        },
        "pull": {
            "pi_status_commands": ["subagent({ action: \"status\", view: \"fleet\" })"]
            + [f'subagent({{"action":"status","id":"{run_id}"}})' for run_id in subagent_run_ids],
            "ask_status_commands": [
                f"skills/ask/run.sh status --run {run_dir} --projection --json" for run_dir in ask_run_dirs
            ],
            "ticket_status_commands": [
                f"skills/ticket/run.sh lookup --issue {ref.split('#')[-1]} --repo {ref.split('#')[0]}"
                for ref in ticket_refs
                if "#" in ref
            ],
            "ledger_commands": ["skills/pipeline-self-repair/run.sh inspect --ledger <ledger> --json"],
            "watchdog_commands": ["skills/project-watchdog/run.sh status"],
            "research_escalation": "Project agent runs $brave-search or $dogpile when receipts name an external fact, upstream behavior, provider change, or unknown root cause that local artifacts do not settle.",
        },
    }


def _ask_status(run_dir: Path, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "run_dir": str(run_dir)}
    ask_run = SKILLS_ROOT / "ask" / "run.sh"
    if not ask_run.exists():
        return {"status": "FAILED", "run_dir": str(run_dir), "error": "ask run.sh not found"}
    result = _run([str(ask_run), "status", "--run", str(run_dir), "--projection", "--json"], timeout=180)
    return {"status": "PASS" if result.returncode == 0 else "FAILED", "run_dir": str(run_dir), "command": result.model_dump()}


def _ticket_status(issue_ref: str, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "issue_ref": issue_ref}
    if not TICKET_RUN.exists():
        return {"status": "FAILED", "issue_ref": issue_ref, "error": "ticket run.sh not found"}
    if "#" not in issue_ref:
        return {"status": "FAILED", "issue_ref": issue_ref, "error": "expected owner/repo#number"}
    repo, number = issue_ref.rsplit("#", 1)
    result = _run([str(TICKET_RUN), "lookup", "--issue", number, "--repo", repo], timeout=120)
    return {"status": "PASS" if result.returncode == 0 else "FAILED", "issue_ref": issue_ref, "command": result.model_dump()}


def _github_issue_view(issue_ref: str, *, skip: bool = False) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "issue_ref": issue_ref}
    if "#" not in issue_ref:
        return {"status": "FAILED", "issue_ref": issue_ref, "error": "expected owner/repo#number"}
    repo, number = issue_ref.rsplit("#", 1)
    cmd = ["gh", "issue", "view", number, "--repo", repo, "--json", "number,title,state,labels,url"]
    result, stdout = _run_with_stdout(cmd, timeout=120)
    if result.returncode != 0:
        return {"status": "FAILED", "issue_ref": issue_ref, "command": result.model_dump()}
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"status": "FAILED", "issue_ref": issue_ref, "command": result.model_dump(), "error": f"gh issue view output was not JSON: {exc}"}
    labels = [item.get("name") for item in data.get("labels", []) if isinstance(item, dict)]
    return {
        "status": "PASS",
        "issue_ref": issue_ref,
        "state": data.get("state"),
        "title": data.get("title"),
        "url": data.get("url"),
        "labels": labels,
        "command": result.model_dump(),
    }


def _run_in_cwd(cmd: list[str], cwd: Path, *, timeout: int = 120) -> tuple[CommandResult, str]:
    logger.debug("running command in {}: {}", cwd, cmd)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False, env=_clean_child_env())
    return _command_result(cmd, proc), proc.stdout


def _parse_json_prefix(text: str) -> tuple[dict[str, Any] | None, str]:
    stripped = text.lstrip()
    if not stripped:
        return None, ""
    try:
        payload, end = json.JSONDecoder().raw_decode(stripped)
    except json.JSONDecodeError:
        return None, text
    if not isinstance(payload, dict):
        return None, text
    return payload, stripped[end:].strip()


def _scorecard_status(memory_repo: Path, *, skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED"}
    command = ["uv", "run", "python", "scripts/ops/hardening_scorecard.py"]
    result, stdout = _run_in_cwd(command, memory_repo, timeout=180)
    parsed, remainder = _parse_json_prefix(stdout)
    canonical = ""
    marker = "--- CANONICAL STATUS ANSWER ---"
    if marker in stdout:
        canonical = stdout.split(marker, 1)[1].strip()
    return {
        "status": "PASS" if result.returncode == 0 and parsed is not None else "FAILED",
        "command": result.model_dump(),
        "scorecard": parsed,
        "canonical_status_answer": canonical or remainder[:4000],
    }


def _latest_response_surface_receipt(memory_repo: Path) -> dict[str, Any]:
    root = memory_repo / "artifacts" / "validation" / "response_surface_resweep_20260827"
    if not root.exists():
        return {"status": "MISSING", "root": str(root)}
    candidates = sorted(root.glob("receipt*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return {"status": "MISSING", "root": str(root)}
    latest = candidates[0]
    return {"status": "PASS", "path": str(latest), "sha256": _sha_bytes(latest.read_bytes()), "bytes": latest.stat().st_size}


def _read_excerpt(path: Path, *, max_chars: int = 12000) -> str:
    if not path.exists():
        return f"MISSING: {path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[: max_chars // 2] + "\n\n...[truncated for WebGPT context bundle]...\n\n" + text[-max_chars // 2 :]


def _redact_local_paths(text: str) -> str:
    """Make browser-submitted prompts safe for Ask/Surf preflight.

    Browser-backed reviewers receive content, not live workstation pointers.
    Keep basename-level provenance while removing absolute, home-relative, and
    shell-relative path forms that the browser transport correctly rejects.
    """
    def absolute_repl(match: re.Match[str]) -> str:
        raw = match.group(0).rstrip(".,;:")
        suffix = match.group(0)[len(raw):]
        return f"[local-path:{Path(raw).name or 'redacted'}]{suffix}"

    text = re.sub(r"/(?:home/graham|mnt|tmp)/[^\s`\"'<>)}\]]+", absolute_repl, text)
    text = re.sub(r"~/(?:[^\s`\"'<>)}\]]+)", "[home-relative-path]", text)
    text = re.sub(r"~(?=\d)", "about ", text)
    text = text.replace("./run.sh", "run.sh")
    return text


def _browser_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_local_paths(value)
    if isinstance(value, list):
        return [_browser_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _browser_safe(item) for key, item in value.items()}
    return value


def _hardening_webgpt_prompt(
    *,
    memory_repo: Path,
    scorecard: dict[str, Any],
    receipt: dict[str, Any],
    ledgers: list[dict[str, Any]],
    ticket_refs: list[str],
    prior_ask_run_dirs: list[Path],
    focus: str,
) -> str:
    handoff = _redact_local_paths(_read_excerpt(memory_repo / "local" / "HANDOFF.md", max_chars=14000))
    scorecard = _browser_safe(scorecard)
    receipt = _browser_safe(receipt)
    ledgers = _browser_safe(ledgers)
    ticket_refs = _browser_safe(ticket_refs)
    prior_ask_run_dirs = [_redact_local_paths(str(path)) for path in prior_ask_run_dirs]
    return f"""You are WebGPT reviewing the $memory hardening process from comprehensive project-agent context.

HARD OUTPUT CONTRACT — return ONLY zero or more TICKET blocks or NO_TICKET lines. Do not write prose, summaries, rankings, or implementation essays.

Allowed output block:
TICKET
Type: bug|feature|optimization|maintenance|triage
Title: <focused issue title>
Target: <file, skill, service, or workflow>
Current state: <observed failure, limitation, or missing capability>
Requested outcome: <one concrete behavior or artifact>
Route: <canonical ticket route>
Requested repair agent: <agent id or unknown>
Scoped files: <paths or explicit unknown>
Non-goals: <what must stay out of scope>
Required proof: <live E2E proof plus retained agentic-evals guard>
Failure code: <triage-error code or TRIAGE_REQUIRED>

Or:
NO_TICKET: <why this observation is not independently actionable>

Review focus: {focus}

Constraints:
- $memory hardening is not done until all families are SEALED, response-surface resweep is 100%, and /answer plus /deflect expose zero diagnostic leaks.
- The project agent owns orchestration and monitoring.
- WebGPT should inspect the full context, but every actionable output must be a focused ticket candidate.
- If an observation needs external/upstream confirmation, set Failure code: TRIAGE_REQUIRED and say exactly what must be checked in Current state.
- Do not propose broad refactors, status dashboards, or unrelated cleanup.
- Prefer one independently verifiable acceptance criterion per ticket.

Current hardening scorecard:
```json
{json.dumps(scorecard, indent=2, sort_keys=True)}
```

Latest response-surface receipt:
```json
{json.dumps(receipt, indent=2, sort_keys=True)}
```

Replay ledger summaries:
```json
{json.dumps(ledgers, indent=2, sort_keys=True)}
```

Existing ticket refs under consideration:
```json
{json.dumps(ticket_refs, indent=2)}
```

Prior Ask run dirs under consideration:
```json
{json.dumps(prior_ask_run_dirs, indent=2)}
```

Project handoff excerpt:
```markdown
{handoff}
```
"""


def _parse_webgpt_ticket_blocks(text: str) -> dict[str, Any]:
    tickets: list[dict[str, str]] = []
    no_tickets: list[str] = []
    current: dict[str, str] | None = None
    current_key: str | None = None
    field_map = {
        "type": "type",
        "title": "title",
        "target": "target",
        "current state": "current_state",
        "requested outcome": "requested_outcome",
        "route": "route",
        "requested repair agent": "requested_repair_agent",
        "scoped files": "scoped_files",
        "non-goals": "non_goals",
        "required proof": "required_proof",
        "failure code": "failure_code",
    }
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            current_key = None
            continue
        if line.strip() == "TICKET":
            if current:
                tickets.append(current)
            current = {}
            current_key = None
            continue
        if line.startswith("NO_TICKET:"):
            if current:
                tickets.append(current)
                current = None
            no_tickets.append(line.split(":", 1)[1].strip())
            current_key = None
            continue
        if current is None:
            continue
        if ":" in line:
            raw_key, value = line.split(":", 1)
            key = field_map.get(raw_key.strip().lower())
            if key:
                current[key] = value.strip()
                current_key = key
                continue
        if current_key:
            current[current_key] = (current.get(current_key, "") + "\n" + line.strip()).strip()
    if current:
        tickets.append(current)
    required = {"type", "title", "target", "current_state", "requested_outcome", "required_proof", "failure_code"}
    normalized: list[dict[str, Any]] = []
    for index, ticket in enumerate(tickets):
        missing = sorted(required - set(ticket))
        normalized.append({"index": index, "status": "READY" if not missing else "INCOMPLETE", "missing_fields": missing, **ticket})
    return {"ticket_count": len(normalized), "tickets": normalized, "no_ticket_count": len(no_tickets), "no_tickets": no_tickets}


def _candidate_repo(candidate: dict[str, Any], default_repo: str) -> str:
    route = str(candidate.get("route") or "")
    match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", route)
    return match.group(1) if match else default_repo


def _candidate_route(candidate: dict[str, Any]) -> str:
    route = str(candidate.get("route") or "backend_python_or_skill_runtime").strip()
    if re.search(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", route):
        return "backend_python_or_skill_runtime"
    return route or "backend_python_or_skill_runtime"


def _live_proof_text(candidate: dict[str, Any], proof: str) -> str:
    target = str(candidate.get("target") or "")
    if "pipeline-self-repair" in target:
        command = (
            "Live command: cd ~/workspace/experiments/memory/.pi/skills/pipeline-self-repair "
            "&& ./sanity.sh && ./run.sh hardening-cycle --skip-scorecard --skip-watchdog --skip-triage --json; "
            "read back hardening-cycle-receipt.json."
        )
    else:
        command = (
            "Live command: cd ~/workspace/experiments/memory "
            "&& uv run python scripts/ops/hardening_scorecard.py; "
            "then run the implemented family-specific live proof and read back its receipt."
        )
    return f"{command} {proof}"


def _ticket_candidate_command(candidate: dict[str, Any], repo: str, *, apply: bool) -> list[str] | None:
    if candidate.get("status") != "READY":
        return None
    repo = _candidate_repo(candidate, repo)
    kind = str(candidate.get("type") or "triage").strip().lower()
    if kind not in {"bug", "feature", "optimization", "maintenance", "triage"}:
        kind = "triage"
    title = str(candidate.get("title") or "Untitled hardening candidate")
    target = str(candidate.get("target") or "unknown")
    route = _candidate_route(candidate)
    proof = _live_proof_text(candidate, str(candidate.get("required_proof") or "Run the named hardening proof and retained agentic-evals guard."))
    non_goals = str(candidate.get("non_goals") or "")
    agent = str(candidate.get("requested_repair_agent") or "agent-skill-maintainer")
    if kind == "feature":
        cmd = [str(TICKET_RUN), "feature", title, "--target", target, "--limitation", str(candidate.get("current_state") or "missing capability"), "--capability", str(candidate.get("requested_outcome") or "requested behavior exists"), "--workflow", "Run pipeline-self-repair hardening-cycle, then project-watchdog repair if eligible.", "--acceptance", str(candidate.get("requested_outcome") or "capability exists"), "--proof", proof]
    elif kind == "optimization":
        cmd = [str(TICKET_RUN), "optimization", title, "--target", target, "--friction", str(candidate.get("current_state") or "hardening workflow friction"), "--improvement", str(candidate.get("requested_outcome") or "smaller repeatable hardening loop"), "--measurable-target", str(candidate.get("requested_outcome") or "one command emits proof-ready ticket/watchdog artifacts"), "--proof", proof]
    elif kind == "maintenance":
        cmd = [str(TICKET_RUN), "maintenance", title, "--target", target, "--invariant", str(candidate.get("requested_outcome") or "hardening workflow remains receipt-backed"), "--cleanup", str(candidate.get("current_state") or "remove stale or manual hardening steps"), "--scoped-files", str(candidate.get("scoped_files") or "unknown"), "--proof", proof]
    elif kind == "triage":
        cmd = [str(TICKET_RUN), "triage", title, "--target", target, "--clues", str(candidate.get("current_state") or "hardening signal needs classification"), "--missing-data", str(candidate.get("requested_outcome") or "one canonical triage-error code and next command")]
    else:
        observed = f"{candidate.get('current_state') or 'hardening process gap'}\nFailure code: {candidate.get('failure_code')}"
        cmd = [str(TICKET_RUN), "bug", title, "--target", target, "--observed", observed, "--expected", str(candidate.get("requested_outcome") or "hardening process behaves correctly"), "--repro", "Run pipeline-self-repair hardening-cycle for $memory and inspect the emitted cycle receipt.", "--proof", proof]
    cmd.extend(["--route", route, "--repo", repo, "--json"])
    if agent and agent.lower() != "unknown":
        cmd.extend(["--agent", agent])
    if kind != "triage":
        cmd.extend(["--required-skill", "pipeline-self-repair", "--required-skill", "triage-error", "--label", "pipeline-self-repair"])
        if non_goals:
            cmd.extend(["--non-goals", non_goals])
        scoped = str(candidate.get("scoped_files") or "")
        if "unknown" not in scoped.lower():
            for item in [part.strip() for part in scoped.replace("\n", ",").split(",") if part.strip()]:
                cmd.extend(["--context-file", item])
    if apply:
        cmd.append("--apply")
    return cmd


def _ask_response_path_from_stdout(stdout: str) -> Path | None:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return None
    candidates: list[Path] = []
    join_path = payload.get("join_artifact_path")
    if join_path:
        path = Path(str(join_path))
        candidates.append(path.parent.parent / "handler-webgpt" / "response.md")
    execution = payload.get("execution") if isinstance(payload, dict) else None
    receipt_path = execution.get("receipt_path") if isinstance(execution, dict) else None
    if receipt_path:
        run_root = Path(str(receipt_path)).parent.parent
        candidates.append(run_root / "node-artifacts" / "handler-webgpt" / "response.md")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _triage_ticket_candidates(candidates: list[dict[str, Any]], *, skip: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        failure_code = str(candidate.get("failure_code") or "").strip()
        if failure_code and failure_code != "TRIAGE_REQUIRED":
            results.append({"index": candidate.get("index"), "status": "SKIPPED", "reason": "candidate supplied failure_code", "failure_code": failure_code})
            continue
        if skip or candidate.get("status") != "READY":
            results.append({"index": candidate.get("index"), "status": "SKIPPED", "reason": "triage skipped or candidate incomplete"})
            continue
        signal = "\n".join(str(candidate.get(key) or "") for key in ["title", "target", "current_state", "requested_outcome"])
        try:
            triage = _classify(signal, None)
            candidate["failure_code"] = triage.code
            results.append({"index": candidate.get("index"), "status": "PASS", "triage": triage.model_dump()})
        except Exception as exc:  # noqa: BLE001 - command should report degraded candidate, not hide others
            results.append({"index": candidate.get("index"), "status": "FAILED", "error": str(exc)})
    return results


def _canonical_issue_ref(issue_ref: str, repo_hint: str | None) -> str:
    if "#" not in issue_ref or not repo_hint:
        return issue_ref
    _, number = issue_ref.rsplit("#", 1)
    return f"{repo_hint}#{number}"


def _hardening_cycle_issue_refs(receipt: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for item in receipt.get("ticket_projections") or []:
        ref = item.get("issue_ref") if isinstance(item, dict) else None
        if ref:
            ref = _canonical_issue_ref(str(ref), item.get("repo"))
            if ref not in refs:
                refs.append(ref)
    if refs:
        return refs
    for item in receipt.get("watchdog_dispatches") or []:
        ref = item.get("issue_ref") if isinstance(item, dict) else None
        if ref and ref not in refs:
            refs.append(str(ref))
    return refs


def _watchdog_receipt_readback(dispatch: dict[str, Any]) -> dict[str, Any]:
    path_value = dispatch.get("receipt_path") if isinstance(dispatch, dict) else None
    if path_value:
        path = Path(str(path_value))
        if path.is_file():
            try:
                return {"status": "PASS", "path": str(path), "receipt": json.loads(path.read_text(encoding="utf-8"))}
            except json.JSONDecodeError as exc:
                return {"status": "FAILED", "path": str(path), "error": f"receipt was not JSON: {exc}"}
        return {"status": "MISSING", "path": str(path)}
    embedded = dispatch.get("receipt") if isinstance(dispatch, dict) else None
    if isinstance(embedded, dict):
        return {"status": "PASS", "receipt": embedded}
    return {"status": "SKIPPED", "reason": "no watchdog receipt path on dispatch"}


def _followup_for_ticket(issue_state: dict[str, Any], watchdog_readback: dict[str, Any], dispatch: dict[str, Any] | None) -> dict[str, Any]:
    labels = set(issue_state.get("labels") or [])
    dispatch_status = (dispatch or {}).get("status")
    receipt_status = ((watchdog_readback.get("receipt") or {}) if isinstance(watchdog_readback, dict) else {}).get("status")
    status_signal = receipt_status or dispatch_status
    if issue_state.get("status") == "FAILED":
        return {"state": "TICKET_READBACK_FAILED", "next_legal_command": "fix ticket readback before making repair claims"}
    if issue_state.get("state") == "CLOSED":
        return {
            "state": "TICKET_CLOSED_VERIFY_SCORECARD",
            "next_legal_command": "cd ~/workspace/experiments/memory && uv run python scripts/ops/hardening_scorecard.py; append CATEGORY_GREEN only if the family is sealed",
        }
    if "agent-blocked" in labels or status_signal in {"NEEDS_ATTENTION", "BLOCKED"}:
        return {
            "state": "WATCHDOG_BLOCKED_NEEDS_ATTENTION",
            "next_legal_command": "read the watchdog/Tau receipt named here, resolve the specific blocker, and do not re-dispatch the same input unchanged",
        }
    if "agent-active" in labels:
        return {"state": "WATCHDOG_ACTIVE", "next_legal_command": "monitor project-watchdog and ticket receipts; do not file a duplicate ticket"}
    if status_signal in {"COMPLETED", "PASS"}:
        return {
            "state": "WATCHDOG_REPAIR_COMMIT_READY",
            "next_legal_command": "inspect the repair receipt/commit, run the live family proof, then update the ticket and replay ledger",
        }
    return {
        "state": "TICKETED_NEEDS_WATCHDOG_DISPATCH",
        "next_legal_command": "run project-watchdog tick --apply --project <mapped-project> --issue <n> --max-tickets 1",
    }


def _hardening_cycle_repair_state(payload: dict[str, Any]) -> str:
    followups = payload.get("followups") or []
    if followups:
        states = {(item.get("followup") or {}).get("state") for item in followups if isinstance(item, dict)}
        if "WATCHDOG_BLOCKED_NEEDS_ATTENTION" in states or "TICKET_READBACK_FAILED" in states:
            return RepairState.NEEDS_HUMAN.value
        if "TICKETED_NEEDS_WATCHDOG_DISPATCH" in states:
            return RepairState.TICKETED.value
        if "WATCHDOG_ACTIVE" in states or "WATCHDOG_REPAIR_COMMIT_READY" in states:
            return RepairState.WATCHDOG_DISPATCHED.value
        if states == {"TICKET_CLOSED_VERIFY_SCORECARD"}:
            return RepairState.CATEGORY_GREEN.value
    dispatches = payload.get("watchdog_dispatches") or []
    tickets = payload.get("ticket_projections") or []
    if any(item.get("status") in {"NEEDS_ATTENTION", "BLOCKED"} for item in dispatches if isinstance(item, dict)):
        return RepairState.NEEDS_HUMAN.value
    if any(item.get("status") in {"COMPLETED", "PASS"} for item in dispatches if isinstance(item, dict)):
        return RepairState.WATCHDOG_DISPATCHED.value
    if any(item.get("issue_ref") for item in tickets if isinstance(item, dict)):
        return RepairState.TICKETED.value
    parsed = payload.get("webgpt_parse") or {}
    if parsed.get("ticket_count"):
        return RepairState.NEEDS_TRIAGE.value
    return RepairState.CATEGORY_GREEN.value


def _hardening_cycle_event_payload(payload: dict[str, Any], *, event_type: str) -> dict[str, Any]:
    issue_refs = list(payload.get("issue_refs") or _hardening_cycle_issue_refs(payload))
    return {
        "schema": HARDENING_CYCLE_EVENT_SCHEMA,
        "event_type": event_type,
        "pipeline": "memory-hardening",
        "run_id": Path(str(payload.get("output_dir") or "hardening-cycle")).name,
        "step_id": "hardening-cycle",
        "category_key": "memory-hardening/hardening-cycle/replay-ledger/v1",
        "failure_category_id": "agent-skills:pipeline-self-repair:hardening-cycle-replay-ledger",
        "blocking": False,
        "repair_state": _hardening_cycle_repair_state(payload),
        "ticket": {"action": "hardening_cycle", "issue_refs": issue_refs},
        "watchdog": {"dispatches": payload.get("watchdog_dispatches") or []},
        "receipt_path": payload.get("receipt_path"),
        "status": payload.get("status"),
        "next_legal_moves": (payload.get("project_agent_role") or {}).get("next_legal_moves") or [],
    }


def _resume_hardening_cycle_payload(
    resume_receipt: Path,
    *,
    replay_ledger: Path | None,
    watchdog_project: str,
    skip_ticket: bool,
    skip_watchdog: bool,
) -> dict[str, Any]:
    prior = json.loads(resume_receipt.read_text(encoding="utf-8"))
    issue_refs = _hardening_cycle_issue_refs(prior)
    dispatch_by_issue = {
        str(item.get("issue_ref")): item
        for item in prior.get("watchdog_dispatches") or []
        if isinstance(item, dict) and item.get("issue_ref")
    }
    dispatch_by_number = {
        str(item.get("issue_ref")).rsplit("#", 1)[1]: item
        for item in prior.get("watchdog_dispatches") or []
        if isinstance(item, dict) and item.get("issue_ref") and "#" in str(item.get("issue_ref"))
    }
    followups: list[dict[str, Any]] = []
    for issue_ref in issue_refs:
        ticket_state = _github_issue_view(issue_ref, skip=skip_ticket)
        dispatch = dispatch_by_issue.get(issue_ref) or dispatch_by_number.get(issue_ref.rsplit("#", 1)[1])
        watchdog_readback = _watchdog_receipt_readback(dispatch or {}) if not skip_watchdog else {"status": "SKIPPED"}
        followup = _followup_for_ticket(ticket_state, watchdog_readback, dispatch)
        followups.append({
            "issue_ref": issue_ref,
            "ticket": ticket_state,
            "watchdog_dispatch": dispatch,
            "watchdog_receipt_readback": watchdog_readback,
            "followup": followup,
        })
    failed = [item for item in followups if item["ticket"].get("status") == "FAILED" or item["watchdog_receipt_readback"].get("status") == "FAILED"]
    payload = {
        "schema": HARDENING_CYCLE_SCHEMA,
        "generated_at": _now(),
        "status": "PASS" if not failed else "DEGRADED",
        "mode": "resume",
        "resume_receipt": str(resume_receipt),
        "watchdog": _watchdog_status(watchdog_project, skip=skip_watchdog),
        "issue_refs": issue_refs,
        "followups": followups,
        "failed_readbacks": failed,
        "project_agent_role": {
            "owner": "project-agent",
            "next_legal_moves": [item["followup"]["next_legal_command"] for item in followups],
        },
    }
    if replay_ledger:
        event = _append_replay_ledger_event(replay_ledger, _hardening_cycle_event_payload(payload, event_type="hardening_cycle.resumed"))
        payload["replay_ledger"] = str(replay_ledger)
        payload["replay_ledger_event"] = event
    return payload


@app.command("hardening-cycle")
def hardening_cycle(
    memory_repo: Path = typer.Option(Path.home() / "workspace" / "experiments" / "memory", "--memory-repo"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    focus: str = typer.Option("make $memory hardening less kludgy by converting comprehensive review into focused ticket/watchdog work items", "--focus"),
    ledger: list[Path] = typer.Option([], "--ledger"),
    ticket_ref: list[str] = typer.Option([], "--ticket-ref"),
    ask_run_dir: list[Path] = typer.Option([], "--ask-run-dir"),
    subagent_run_id: list[str] = typer.Option([], "--subagent-run-id"),
    webgpt_response: Path | None = typer.Option(None, "--webgpt-response"),
    resume_receipt: Path | None = typer.Option(None, "--resume", help="Resume from a prior hardening-cycle receipt and emit ticket/watchdog follow-up state."),
    replay_ledger: Path | None = typer.Option(None, "--replay-ledger", help="Append a hash-chained hardening-cycle event to this replay ledger."),
    execute_ask: bool = typer.Option(False, "--execute-ask"),
    apply_ticket: bool = typer.Option(False, "--apply-ticket"),
    dispatch_watchdog: bool = typer.Option(True, "--dispatch-watchdog/--no-dispatch-watchdog"),
    skip_scorecard: bool = typer.Option(False, "--skip-scorecard"),
    skip_triage: bool = typer.Option(False, "--skip-triage"),
    skip_ticket: bool = typer.Option(False, "--skip-ticket"),
    skip_watchdog: bool = typer.Option(False, "--skip-watchdog"),
    watchdog_project: str = typer.Option("agent-skills", "--watchdog-project"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run one bounded $memory hardening orchestration cycle.

    Default mode is dry-run/safe: it builds the comprehensive WebGPT prompt,
    parses a supplied WebGPT response if present, projects ticket commands, and
    emits monitor instructions. External Ask and ticket mutations require
    --execute-ask or --apply-ticket.
    """
    if resume_receipt:
        payload = _resume_hardening_cycle_payload(
            resume_receipt,
            replay_ledger=replay_ledger,
            watchdog_project=watchdog_project,
            skip_ticket=skip_ticket,
            skip_watchdog=skip_watchdog,
        )
        _emit(payload, json_output)
        if payload["status"] == "DEGRADED":
            raise typer.Exit(1)
        return

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = output_dir or Path("/tmp") / f"pipeline-self-repair-hardening-cycle-{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    scorecard = _scorecard_status(memory_repo, skip=skip_scorecard)
    receipt = _latest_response_surface_receipt(memory_repo)
    ledger_summaries = [_ledger_summary(path) for path in ledger] or [{"status": "SKIPPED", "reason": "no ledger supplied"}]
    prompt = _hardening_webgpt_prompt(
        memory_repo=memory_repo,
        scorecard=scorecard,
        receipt=receipt,
        ledgers=ledger_summaries,
        ticket_refs=ticket_ref,
        prior_ask_run_dirs=ask_run_dir,
        focus=focus,
    )
    prompt_path = out_dir / "webgpt-ticket-only-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    ask_result: dict[str, Any] = {"status": "SKIPPED", "reason": "--execute-ask not set", "prompt_path": str(prompt_path)}
    response_text = ""
    if webgpt_response:
        response_text = _read_excerpt(webgpt_response, max_chars=80000)
        ask_result = {"status": "READ_SUPPLIED_RESPONSE", "response_path": str(webgpt_response)}
    if execute_ask:
        ask_run = SKILLS_ROOT / "ask" / "run.sh"
        if not ask_run.exists():
            ask_result = {"status": "FAILED", "error": "ask run.sh not found"}
        else:
            result, stdout = _run_in_cwd([str(ask_run), "webgpt", prompt], SKILLS_ROOT / "ask", timeout=1800)
            (out_dir / "webgpt-stdout.txt").write_text(stdout, encoding="utf-8")
            (out_dir / "webgpt-stderr.txt").write_text(result.stderr_excerpt, encoding="utf-8")
            response_path = _ask_response_path_from_stdout(stdout)
            if response_path:
                response_text = response_path.read_text(encoding="utf-8", errors="replace")
            else:
                response_text = stdout
            ask_result = {
                "status": "PASS" if result.returncode == 0 else "FAILED",
                "command": result.model_dump(),
                "stdout_path": str(out_dir / "webgpt-stdout.txt"),
                "response_path": str(response_path) if response_path else None,
            }
    parsed = _parse_webgpt_ticket_blocks(response_text) if response_text else {"ticket_count": 0, "tickets": [], "no_ticket_count": 0, "no_tickets": []}
    triage_results = _triage_ticket_candidates(parsed["tickets"], skip=skip_triage)
    ticket_projections: list[dict[str, Any]] = []
    for candidate in parsed["tickets"]:
        cmd = _ticket_candidate_command(candidate, repo, apply=apply_ticket)
        projection: dict[str, Any] = {"index": candidate.get("index"), "repo": _candidate_repo(candidate, repo), "status": "SKIPPED_INCOMPLETE" if cmd is None else "PROJECTED", "command": cmd}
        if cmd and apply_ticket:
            result = _run(cmd, timeout=180)
            projection.update({"status": "CREATED" if result.returncode == 0 else "FAILED", "result": result.model_dump(), "issue_ref": _extract_issue_ref(result.stdout_excerpt, projection["repo"])})
        ticket_projections.append(projection)
    watchdog_dispatches = _dispatch_watchdog_for_ticket_projections(
        ticket_projections,
        default_project=watchdog_project,
        enabled=apply_ticket and dispatch_watchdog and not skip_watchdog,
    )
    monitor_plan = _push_pull_monitoring(subagent_run_id, ask_run_dir, ticket_ref + [p.get("issue_ref") for p in ticket_projections if p.get("issue_ref")])
    watchdog_state = _watchdog_status(watchdog_project, skip=skip_watchdog)
    failed_ticket_projection = any(item.get("status") == "FAILED" for item in ticket_projections)
    failed_watchdog_dispatch = any(item.get("status") == "FAILED" for item in watchdog_dispatches)
    payload_status = (
        "PASS"
        if scorecard.get("status") != "FAILED"
        and ask_result.get("status") != "FAILED"
        and watchdog_state.get("status") != "FAILED"
        and not failed_ticket_projection
        and not failed_watchdog_dispatch
        else "DEGRADED"
    )
    payload = {
        "schema": HARDENING_CYCLE_SCHEMA,
        "generated_at": _now(),
        "status": payload_status,
        "project_agent_role": {
            "owner": "project-agent",
            "next_legal_moves": [
                "run the generated WebGPT prompt through $ask webgpt if no response was supplied",
                "file or bind one focused ticket per READY candidate",
                "run triage-error before ticketing candidates marked TRIAGE_REQUIRED",
                "automatically dispatch project-watchdog after focused ticket creation unless --no-dispatch-watchdog or --skip-watchdog is set",
                "monitor Ask, ticket, watchdog, Pi async, and ledger receipts until category closure",
            ],
        },
        "output_dir": str(out_dir),
        "prompt_path": str(prompt_path),
        "scorecard": scorecard,
        "latest_response_surface_receipt": receipt,
        "ledgers": ledger_summaries,
        "ask": ask_result,
        "webgpt_parse": parsed,
        "triage_results": triage_results,
        "ticket_projections": ticket_projections,
        "watchdog_dispatches": watchdog_dispatches,
        "watchdog": watchdog_state,
        "monitoring": monitor_plan,
    }
    receipt_path = out_dir / "hardening-cycle-receipt.json"
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["receipt_path"] = str(receipt_path)
    if replay_ledger:
        event = _append_replay_ledger_event(replay_ledger, _hardening_cycle_event_payload(payload, event_type="hardening_cycle.generated"))
        payload["replay_ledger"] = str(replay_ledger)
        payload["replay_ledger_event"] = event
    receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _emit(payload, json_output)
    if payload["status"] == "DEGRADED":
        raise typer.Exit(1)



@app.command("monitor")
def monitor(
    ledger: Path | None = typer.Option(None, "--ledger"),
    ask_run_dir: list[Path] = typer.Option([], "--ask-run-dir"),
    ticket_ref: list[str] = typer.Option([], "--ticket-ref"),
    subagent_run_id: list[str] = typer.Option([], "--subagent-run-id"),
    watchdog_project: str = typer.Option("agent-skills", "--watchdog-project"),
    skip_ask: bool = typer.Option(False, "--skip-ask"),
    skip_ticket: bool = typer.Option(False, "--skip-ticket"),
    skip_watchdog: bool = typer.Option(False, "--skip-watchdog"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Emit project-agent push/pull monitoring commands and optional readbacks."""
    ledger_state = _ledger_summary(ledger)
    ask_states = [_ask_status(path, skip=skip_ask) for path in ask_run_dir]
    ticket_states = [_ticket_status(ref, skip=skip_ticket) for ref in ticket_ref]
    watchdog_state = _watchdog_status(watchdog_project, skip=skip_watchdog)
    failed = [item for item in [ledger_state, watchdog_state, *ask_states, *ticket_states] if item.get("status") == "FAILED"]
    payload = {
        "schema": MONITOR_SCHEMA,
        "generated_at": _now(),
        "status": "PASS" if not failed else "DEGRADED",
        "project_agent_role": {
            "owner": "project-agent",
            "responsibilities": [
                "orchestrate the failure-to-repair loop",
                "give WebGPT comprehensive context but require focused ticket candidates or NO_TICKET",
                "file or bind focused ticket categories for project-watchdog dispatch",
                "route ambiguous raw signals through triage-error before repair",
                "monitor Ask, ticket, watchdog, ledger, and Pi async receipts until proof closes the category",
                "run brave-search or dogpile only when local receipts leave an external fact or upstream behavior unresolved",
                "avoid unrelated side quests while a blocking category remains open",
            ],
        },
        "monitoring": _push_pull_monitoring(subagent_run_id, ask_run_dir, ticket_ref),
        "ledger": ledger_state,
        "ask_runs": ask_states,
        "tickets": ticket_states,
        "watchdog": watchdog_state,
        "failed_readbacks": failed,
    }
    _emit(payload, json_output)
    if failed:
        raise typer.Exit(1)


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
    goal_project: str | None = typer.Option(None, "--goal-project", help="Registered immutable goal project. Defaults to --pipeline."),
    goal_hash: str | None = typer.Option(None, "--goal-hash", help="Optional expected immutable goal hash; mismatches fail preflight."),
    goal_context: list[str] = typer.Option([], "--goal-context", help="Extra context used when comparing this repair to the immutable goal."),
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
    signal = _read_raw_signal(raw_signal, receipt)
    effective_goal_project = goal_project or pipeline
    goal_payload, goal_command = _load_immutable_goal(effective_goal_project)
    run_root.mkdir(parents=True, exist_ok=True)
    triage = _classify(signal, layer)
    goal_alignment = _goal_alignment(
        project=effective_goal_project,
        goal_payload=goal_payload,
        goal_command=goal_command,
        expected_goal_hash=goal_hash,
        pipeline=pipeline,
        step_id=step_id,
        target=target,
        triage=triage,
        raw_signal=signal,
        extra_context=goal_context,
    )
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
        "goal_hash": goal_alignment["goal_hash"],
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
        "goal_alignment": goal_alignment,
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
    categories = _fold_categories(events)
    open_failures = [
        data["latest_event"]
        for data in categories.values()
        if (data.get("latest_event") or {}).get("blocking")
        and data.get("latest_state") not in {RepairState.CATEGORY_GREEN.value, RepairState.CLOSED.value}
    ]
    summary_categories = {key: {k: v for k, v in data.items() if k != "latest_event"} for key, data in categories.items()}
    _emit({"schema": SUMMARY_SCHEMA, "ledger": str(ledger), "event_count": len(events), "open_failure_count": len(open_failures), "categories": summary_categories}, json_output)


@app.command("mark-repaired")
def mark_repaired(
    ledger: Path = typer.Option(..., "--ledger"),
    category_key: str = typer.Option(..., "--category-key"),
    proof_report: Path = typer.Option(..., "--proof-report"),
    goal_project: str = typer.Option(..., "--goal-project"),
    goal_hash: str | None = typer.Option(None, "--goal-hash"),
    goal_context: list[str] = typer.Option([], "--goal-context"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Append a CATEGORY_GREEN disposition for a repaired failure category."""
    events = _load_events(ledger)
    previous = next((event for event in reversed(events) if event.get("category_key") == category_key), None)
    if not previous:
        raise typer.BadParameter(f"category not found in ledger: {category_key}")
    if not proof_report.is_file():
        raise typer.BadParameter(f"proof report does not exist: {proof_report}")
    goal_payload, goal_command = _load_immutable_goal(goal_project)
    observed_goal_hash = _goal_hash(goal_payload)
    if goal_hash and goal_hash != observed_goal_hash:
        raise typer.BadParameter(f"goal hash mismatch: expected {goal_hash}, observed {observed_goal_hash}")
    goal_alignment = _goal_alignment(
        project=goal_project,
        goal_payload=goal_payload,
        goal_command=goal_command,
        expected_goal_hash=goal_hash,
        pipeline=str(previous.get("pipeline") or goal_project),
        step_id=str(previous.get("step_id") or "repaired"),
        target=str(previous.get("target") or ""),
        triage=TriageResult.model_validate(previous.get("triage") or {"code": "repaired"}),
        raw_signal=f"Category repaired with proof report {proof_report}",
        extra_context=goal_context,
    )
    payload = dict(previous)
    payload.update(
        {
            "event_id": "evt_" + hashlib.sha256(f"mark-repaired:{category_key}:{_now()}".encode()).hexdigest()[:24],
            "event_type": "step.repaired",
            "occurred_at": _now(),
            "goal_hash": observed_goal_hash,
            "raw_signal_sha256": _sha_bytes(f"repaired:{category_key}".encode()),
            "raw_signal_excerpt": f"Category repaired with proof report {proof_report}",
            "repair_state": RepairState.CATEGORY_GREEN.value,
            "agentic_eval": {"report": _artifact_ref(proof_report).model_dump(), "retained_guard_required": True},
            "goal_alignment": goal_alignment,
            "outputs": [_artifact_ref(proof_report).model_dump()],
        }
    )
    payload.pop("event_hash", None)
    event = _append_event(ledger, payload)
    _emit({"schema": SUMMARY_SCHEMA, "ledger": str(ledger), "status": "CATEGORY_GREEN", "event": event.model_dump(by_alias=True)}, json_output)


@app.command("validate-ledger")
def validate_ledger(
    ledger: Path = typer.Option(..., "--ledger"),
    require_agentic_eval: bool = typer.Option(False, "--require-agentic-eval"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Fail closed if blocking failures lack repair disposition."""
    events = _load_events(ledger)
    failures: list[str] = []
    categories = _fold_categories(events)
    for index, (category_key, folded) in enumerate(categories.items()):
        event = folded.get("latest_event") or {}
        if not event.get("blocking"):
            continue
        state = event.get("repair_state")
        if state in {RepairState.CATEGORY_GREEN.value, RepairState.CLOSED.value}:
            if require_agentic_eval and not (event.get("agentic_eval") or {}).get("report"):
                failures.append(f"category[{index}] {category_key} closed without retained agentic-evals report/proof reference")
            continue
        if not (event.get("triage") or {}).get("code"):
            failures.append(f"category[{index}] {category_key} missing triage code")
        if not event.get("category_key") or not event.get("failure_category_id"):
            failures.append(f"category[{index}] {category_key} missing category binding")
        goal_alignment = event.get("goal_alignment") or {}
        if not event.get("goal_hash") or goal_alignment.get("status") != "PASS_COMPARED_TO_IMMUTABLE_GOAL":
            failures.append(f"category[{index}] {category_key} missing immutable-goal comparison")
        ticket_action = (event.get("ticket") or {}).get("action")
        if ticket_action in {None, "ticket_skipped", "ticket_failed"}:
            failures.append(f"category[{index}] {category_key} lacks ticket disposition")
        if require_agentic_eval and not (event.get("agentic_eval") or {}).get("report"):
            failures.append(f"category[{index}] {category_key} lacks retained agentic-evals report/proof reference")
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
    goal_project: str = typer.Option(..., "--goal-project", help="Registered immutable goal project that this remediation serves."),
    goal_hash: str | None = typer.Option(None, "--goal-hash", help="Optional expected immutable goal hash; mismatches fail preflight."),
    goal_context: list[str] = typer.Option([], "--goal-context", help="Extra context used when comparing this remediation to the immutable goal."),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    route: str = typer.Option("backend_python_or_skill_runtime", "--route"),
    execute: bool = typer.Option(False, "--execute"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Project a complete agentic-evals report into category tickets via agentic-evals remediate."""
    goal_payload, goal_command = _load_immutable_goal(goal_project)
    triage = TriageResult(code="agentic_eval_failure_categories", ambiguous=False)
    goal_alignment = _goal_alignment(
        project=goal_project,
        goal_payload=goal_payload,
        goal_command=goal_command,
        expected_goal_hash=goal_hash,
        pipeline="agentic-evals",
        step_id="agentic_eval_remediate",
        target=str(report),
        triage=triage,
        raw_signal=report.read_text(encoding="utf-8", errors="replace") if report.exists() else str(report),
        extra_context=goal_context,
    )
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
        "goal_hash": goal_alignment["goal_hash"],
        "goal_alignment": goal_alignment,
        "raw_signal_sha256": _sha_bytes(report.read_bytes()),
        "raw_signal_excerpt": str(report),
        "triage": triage.model_dump(),
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
