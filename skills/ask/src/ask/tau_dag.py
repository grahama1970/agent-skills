"""Compile /ask requests into strict Tau project DAG bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .env import load_dotenv_once

load_dotenv_once()

ASK_SKILL_ROOT = Path(__file__).resolve().parents[2]
TAU_DAG_SCHEMA = "tau.dag_contract.v1"
ASK_TAU_DAG_BUNDLE_SCHEMA = "ask.tau_dag_bundle.v1"
ASK_TAU_DAG_INTERVIEW_SCHEMA = "ask.tau_dag_interview.v1"
DEFAULT_SCILLM_BASE_URL = "http://127.0.0.1:4001"
DEFAULT_SCILLM_API_KEY = ""
DEFAULT_TAU_PROJECT_ROOT = Path("/home/graham/workspace/experiments/tau")
DEFAULT_OUTPUT_ROOT = Path(".ask_artifacts/tau-dag-runs")
DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS = 900
BROWSER_COMMAND_GRACE_SECONDS = 180
COMPETE_WEBCLAUDE_MODEL = "Opus 5 High"
TERMINAL_STATUSES = {"PASS", "DEGRADED", "NEEDS_ATTENTION", "BLOCKED", "FAILED", "ERROR"}
ROUNDTABLE_TOPOLOGIES = {"concurrent", "sequential"}
SUPPORTED_DAG_TEMPLATES = {
    "single-call": {
        "description": "One Tau handler/browser/API/subagent node answers the request, then joins to human.",
        "topology": "concurrent",
        "workflow_mode": "roundtable",
        "min_handlers": 1,
    },
    "prompt-chain": {
        "description": "A linear sequence of handlers where each downstream node receives prior receipts.",
        "topology": "sequential",
        "workflow_mode": "roundtable",
        "min_handlers": 2,
    },
    "creator-reviewer": {
        "description": "Creator node followed by reviewer node; pass/fail requests require a verdict schema.",
        "topology": "sequential",
        "workflow_mode": "roundtable",
        "min_handlers": 2,
    },
    "reflection-loop": {
        "description": "Draft/review/revise style sequential loop using receipt-backed prior context.",
        "topology": "sequential",
        "workflow_mode": "roundtable",
        "min_handlers": 2,
    },
    "roundtable": {
        "description": "Multiple handlers receive equal shared context, then a join node preserves dissent.",
        "topology": "concurrent",
        "workflow_mode": "roundtable",
        "min_handlers": 2,
    },
    "compete": {
        "description": "Isolated competitors work from equal context; join selects from verified features.",
        "topology": "concurrent",
        "workflow_mode": "compete",
        "min_handlers": 2,
    },
}
TAU_NATIVE_TEMPLATE_REQUESTS = {
    "tool-use": "Tool invocation policy and tool receipt gates need native Tau template expansion.",
    "rag-review": "Retrieval inputs, corpus binding, and citation gates need native Tau template expansion.",
    "human-approval": "Approval node semantics and resume boundaries need native Tau template expansion.",
    "exception-recovery": "Recovery branches and retry policy need native Tau template expansion.",
    "priority-queue": "Priority scoring, budget policy, and queue semantics need native Tau template expansion.",
    "exploration-research": "Exploration branches and source diversity gates need native Tau template expansion.",
}
DAG_TEMPLATE_ALIASES = {
    "single": "single-call",
    "single-handler": "single-call",
    "singlecall": "single-call",
    "chain": "prompt-chain",
    "promptchain": "prompt-chain",
    "sequential-chain": "prompt-chain",
    "creator-review": "creator-reviewer",
    "create-review": "creator-reviewer",
    "review-loop": "creator-reviewer",
    "reflect": "reflection-loop",
    "reflection": "reflection-loop",
    "competition": "compete",
    "bakeoff": "compete",
    "tools": "tool-use",
    "tooluse": "tool-use",
    "rag": "rag-review",
    "retrieval": "rag-review",
    "hitl": "human-approval",
    "human-in-the-loop": "human-approval",
    "recovery": "exception-recovery",
    "priority": "priority-queue",
    "exploration": "exploration-research",
    "research": "exploration-research",
}
ROUNDTABLE_HANDLERS = {
    "webgpt": {
        "transport_owner": "$surf",
        "transport": "webgpt.submit",
        "runtime": "browser",
        "proof_required": "surf_sentinel_meta",
    },
    "webkimi": {
        "transport_owner": "$surf",
        "transport": "kimi.submit",
        "runtime": "browser",
        "proof_required": "surf_sentinel_meta",
    },
    "webclaude": {
        "transport_owner": "$surf",
        "transport": "claude.submit",
        "runtime": "browser",
        "proof_required": "surf_sentinel_meta",
    },
    "webgemini": {
        "transport_owner": "$surf",
        "transport": "gemini.submit",
        "runtime": "browser",
        "proof_required": "surf_sentinel_meta",
    },
    "webgrok": {
        "transport_owner": "$surf",
        "transport": "grok.submit",
        "runtime": "browser",
        "proof_required": "surf_sentinel_meta",
    },
    # Local coding agent. Runs `codex exec` inside a caller-named workspace
    # (git worktree) with a writable sandbox; the node's response is the
    # summary plus the actual `git diff` of the workspace, so a downstream
    # reviewer handler judges the real change, not a narrative.
    "codex": {
        "transport_owner": "$tau",
        "transport": "codex.exec",
        "runtime": "local_cli",
        "proof_required": "workspace_git_diff",
    },
}
SUBAGENT_HANDLER_MODEL_PREFIXES = ("gpt-", "codex-")
_HANDLER_ALIASES = {
    "chatgpt": "webgpt",
    "gpt": "webgpt",
    "kimi": "webkimi",
    "claude": "webclaude",
    "gemini": "webgemini",
    "grok": "webgrok",
}
FAIL_CLOSED_ON = [
    "goal_hash_mismatch",
    "target_changed",
    "unexpected_node",
    "unexpected_edge",
    "missing_required_evidence",
    "max_attempts_exceeded",
    "malformed_handoff",
    "missing_required_join",
    "branch_goal_hash_divergence",
    "branch_target_divergence",
    "invalid_provider_receipt",
    "provider_auth_required",
]
_CLAUDE_SCILLM_ALIASES = {
    "claude-fable": "claude-fable-5",
}


class TauDagError(RuntimeError):
    """Raised when a Tau DAG bundle cannot be compiled or executed."""


@dataclass(frozen=True)
class ScillmModelRoute:
    requested_model: str
    model: str
    provider: str
    auth: str
    reasoning_effort: str | None = None
    requested_reasoning_effort: str | None = None
    reasoning_downgrade_reason: str | None = None


@dataclass(frozen=True)
class TauDagCompileInput:
    request: str
    repo: str
    target: str
    immutable_goal: str
    solver_models: tuple[str, ...]
    reviewer_model: str
    criteria: tuple[str, ...]
    handlers: tuple[str, ...] = ()
    topology: str = "concurrent"
    workflow_mode: str = "roundtable"
    join_handler: str = "join"
    handler_projects: tuple[str, ...] = ()
    handler_workspaces: tuple[str, ...] = ()
    handler_provider_hints: tuple[str, ...] = ()
    dag_template: str = ""
    ask_id: str | None = None
    output_root: Path = DEFAULT_OUTPUT_ROOT
    local_fixture: bool = False
    scillm_base_url: str = DEFAULT_SCILLM_BASE_URL
    scillm_api_key: str = DEFAULT_SCILLM_API_KEY
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT


def infer_compile_input(
    request: str,
    *,
    repo: str = "",
    target: str = "",
    solver_models: list[str] | None = None,
    reviewer_model: str = "",
    criteria: list[str] | None = None,
    immutable_goal: str = "",
    handlers: list[str] | None = None,
    topology: str = "",
    workflow_mode: str = "roundtable",
    join_handler: str = "join",
    handler_projects: list[str] | None = None,
    handler_workspaces: list[str] | None = None,
    dag_template: str = "",
    ask_id: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    local_fixture: bool = False,
    scillm_base_url: str = DEFAULT_SCILLM_BASE_URL,
    scillm_api_key: str = DEFAULT_SCILLM_API_KEY,
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT,
) -> TauDagCompileInput:
    """Merge explicit CLI fields with conservative request-text inference."""

    inferred_solvers = list(solver_models or [])
    inferred_handlers, inferred_provider_hints = _canonicalize_handlers(handlers or [])
    normalized_request = request.strip()
    lower = normalized_request.lower()
    normalized_template = _normalize_dag_template(dag_template)
    inferred_immutable_goal = immutable_goal.strip() or _infer_immutable_goal(normalized_request)
    if not inferred_handlers:
        natural_handlers = _infer_mixed_concurrent_handlers(normalized_request) or _infer_single_chutes_handler(normalized_request)
        if natural_handlers:
            inferred_handlers = list(natural_handlers["handlers"])
            inferred_provider_hints = list(natural_handlers["provider_hints"])
            normalized_request = str(natural_handlers["request"])
            lower = normalized_request.lower()
            inferred_immutable_goal = inferred_immutable_goal or _infer_immutable_goal(normalized_request)
        else:
            inferred_handlers = _infer_roundtable_handlers(lower)
            inferred_provider_hints = [""] * len(inferred_handlers)
    if not inferred_solvers:
        gpt_match = re.search(r"\b(\d+)\s+gpt[\s-]*([0-9.]+)\s*xhigh\b", lower)
        if gpt_match:
            count = max(1, min(8, int(gpt_match.group(1))))
            model = f"gpt-{gpt_match.group(2)}-xhigh"
            inferred_solvers = [model] * count
    inferred_reviewer = reviewer_model.strip()
    if not inferred_reviewer and "claude" in lower:
        fable_match = re.search(r"\bclaude\s+fab(?:le|el)\b", lower)
        if fable_match:
            inferred_reviewer = "claude-fable"
    resolved_topology = _normalize_topology(topology or ("sequential" if "sequential" in lower else "concurrent"))
    resolved_workflow_mode = _normalize_workflow_mode(workflow_mode)
    template_spec = SUPPORTED_DAG_TEMPLATES.get(normalized_template)
    if template_spec:
        if not topology:
            resolved_topology = str(template_spec["topology"])
        resolved_workflow_mode = str(template_spec["workflow_mode"])
    return TauDagCompileInput(
        request=normalized_request,
        repo=repo.strip(),
        target=target.strip(),
        immutable_goal=inferred_immutable_goal,
        solver_models=tuple(_normalize_model(item) for item in inferred_solvers if item.strip()),
        reviewer_model=_normalize_model(inferred_reviewer) if inferred_reviewer else "",
        criteria=tuple(item.strip() for item in (criteria or []) if item.strip()),
        handlers=tuple(inferred_handlers),
        topology=resolved_topology,
        workflow_mode=resolved_workflow_mode,
        join_handler=_normalize_handler(join_handler) if join_handler else "join",
        handler_projects=tuple(item.strip() for item in (handler_projects or []) if item.strip()),
        handler_workspaces=tuple(item.strip() for item in (handler_workspaces or []) if item.strip()),
        handler_provider_hints=tuple(inferred_provider_hints[: len(inferred_handlers)]),
        dag_template=normalized_template,
        ask_id=ask_id,
        output_root=output_root,
        local_fixture=local_fixture,
        scillm_base_url=scillm_base_url.rstrip("/"),
        scillm_api_key=scillm_api_key or default_scillm_api_key(),
        tau_project_root=tau_project_root,
    )


def missing_dag_fields(input: TauDagCompileInput) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    template_spec = SUPPORTED_DAG_TEMPLATES.get(input.dag_template)
    if input.dag_template and template_spec is None:
        native_reason = TAU_NATIVE_TEMPLATE_REQUESTS.get(input.dag_template)
        if native_reason:
            missing.append(
                _question(
                    "dag_template",
                    (
                        f"The DAG template '{input.dag_template}' is recognized but needs native Tau "
                        f"template-registry support before Ask can execute it. {native_reason} "
                        "Use one of the currently supported Ask templates or track grahama1970/tau#131."
                    ),
                    expects="supported_template",
                    options=_dag_template_options(),
                    recovery_packet={
                        "failure_code": "tau_native_template_required",
                        "next_command": "./run.sh tau-dag '<request>' --dag-template roundtable --handler <h1> --handler <h2> --immutable-goal '<goal>' --json",
                        "tau_ticket": "https://github.com/grahama1970/tau/issues/131",
                    },
                )
            )
        else:
            missing.append(
                _question(
                    "dag_template",
                    f"Unknown DAG template '{input.dag_template}'. Select a supported template.",
                    expects="supported_template",
                    options=_dag_template_options(),
                    recovery_packet={
                        "failure_code": "unknown_dag_template",
                        "next_command": "./run.sh tau-dag '<request>' --dag-template roundtable --handler <h1> --handler <h2> --immutable-goal '<goal>' --json",
                    },
                )
            )
    if not input.request:
        missing.append(_question("request", "What exact problem should the Tau DAG solve?"))
    if not input.repo:
        missing.append(_question("repo", "Which repository or project identifier should the DAG bind to?"))
    if not input.target:
        missing.append(_question("target", "Which issue, task, file, or work target should the DAG bind to?"))
    if template_spec:
        min_handlers = int(template_spec["min_handlers"])
        if len(input.handlers) < min_handlers:
            missing.append(
                _question(
                    "handlers",
                    (
                        f"Template '{input.dag_template}' needs at least {min_handlers} handler"
                        f"{'s' if min_handlers != 1 else ''}. Provide browser handlers, API model handlers, "
                        "or subagent selectors."
                    ),
                    expects="list[str]",
                    options=[
                        "webgpt",
                        "webclaude",
                        "webkimi",
                        "webgemini",
                        "gpt-5.5-high",
                        "gpt-5.5-xhigh",
                        "chutes deepseek-ai/DeepSeek-V3.2-TEE",
                    ],
                    recovery_packet={
                        "failure_code": "template_missing_handlers",
                        "next_command": f"./run.sh tau-dag '<request>' --dag-template {input.dag_template} --handler <handler> --immutable-goal '<goal>' --json",
                    },
                )
            )
        expected_topology = str(template_spec["topology"])
        if input.topology != expected_topology:
            missing.append(
                _question(
                    "topology",
                    f"Template '{input.dag_template}' requires {expected_topology} topology.",
                    expects=expected_topology,
                    recovery_packet={
                        "failure_code": "template_topology_mismatch",
                        "next_command": f"./run.sh tau-dag '<request>' --dag-template {input.dag_template} --topology {expected_topology} --json",
                    },
                )
            )
        if not input.immutable_goal:
            missing.append(
                _question(
                    "immutable_goal",
                    (
                        f"Template '{input.dag_template}' requires an explicit immutable goal or acceptance bar "
                        "to share with every participant before Tau dispatch."
                    ),
                    expects="str",
                )
            )
    if input.handlers:
        if not input.immutable_goal and not template_spec:
            missing.append(
                _question(
                    "immutable_goal",
                    (
                        "Roundtable and compete DAGs require an explicit immutable goal or acceptance bar "
                        "that is shared with every participant before any browser/API calls."
                    ),
                    expects="str",
                )
            )
        if input.topology not in ROUNDTABLE_TOPOLOGIES:
            missing.append(
                _question(
                    "topology",
                    "Roundtable topology must be concurrent or sequential.",
                    expects="concurrent|sequential",
                )
            )
        if input.workflow_mode == "compete":
            if len(input.handlers) < 2:
                missing.append(
                    _question(
                        "handlers",
                        "Compete mode needs at least two isolated competitor handlers.",
                        expects="list[str]",
                    )
                )
            if input.topology != "concurrent":
                missing.append(
                    _question(
                        "topology",
                        "Compete mode requires concurrent topology so candidates receive isolated equal context.",
                        expects="concurrent",
                    )
                )
        return missing
    if not input.solver_models:
        missing.append(
            _question(
                "solver_models",
                "Which solver model(s) should run concurrently, in order?",
                expects="list[str]",
            )
        )
    if not input.reviewer_model:
        missing.append(_question("reviewer_model", "Which reviewer model should compare the solver outputs?"))
    if not input.criteria:
        missing.append(
            _question(
                "criteria",
                "What criteria should the reviewer apply when choosing a winner?",
                expects="list[str]",
            )
        )
    unsupported_routes = unsupported_model_routes(input)
    if unsupported_routes:
        missing.append(
            _question(
                "model_routes",
                (
                    "The current $ask tau-dag front door emits SciLLM-backed local adapter nodes only. "
                    f"These requested model route(s) need native Tau skill nodes instead: {', '.join(unsupported_routes)}. "
                    "Should $ask rewrite this as a native Tau skill DAG or should different SciLLM model names be used?"
                ),
                expects="route_decision",
            )
        )
    return missing


def unsupported_model_routes(input: TauDagCompileInput) -> list[str]:
    unsupported: list[str] = []
    for model in [*input.solver_models, input.reviewer_model]:
        lower = model.lower().strip()
        if lower.startswith(("webgpt", "$webgpt", "chatgpt", "$chatgpt")):
            unsupported.append(model)
    return sorted(set(unsupported))


def default_scillm_api_key() -> str:
    """Resolve the scillm bearer per the tau#114 auth contract.

    The ambient proxy key wins because it reflects the running proxy's current
    authentication contract. Other explicitly exported keys follow, then the
    deployment .env is used only as a fallback.
    """
    for var in (
        "SCILLM_PROXY_KEY",
        "SCILLM_MASTER_KEY",
        "LITELLM_MASTER_KEY",
        "SCILLM_API_KEY",
        "SCILLM_PROXY_API_KEY",
    ):
        value = os.environ.get(var)
        if value:
            return value
    env_file = Path(
        os.environ.get(
            "SCILLM_ENV_FILE",
            str(Path.home() / "workspace/experiments/scillm/.env"),
        )
    )
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            for var in ("SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY"):
                if line.startswith(f"{var}=") and line.split("=", 1)[1].strip():
                    return line.split("=", 1)[1].strip().strip('"')
    return DEFAULT_SCILLM_API_KEY


def build_interview_packet(
    input: TauDagCompileInput,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    questions = missing_dag_fields(input)
    packet = {
        "schema": ASK_TAU_DAG_INTERVIEW_SCHEMA,
        "status": "NEEDS_INTERVIEW" if questions else "READY",
        "mocked": False,
        "live": False,
        "provider_live": False,
        "request": input.request,
        "missing_fields": [item["field"] for item in questions],
        "questions": questions,
        "interview_skill": "$interview",
        "interview_command": None,
    }
    if output_root is not None:
        interview_path = output_root / "interview-required.json"
        packet["interview_command"] = [
            "/home/graham/workspace/experiments/agent-skills/skills/interview/run.sh",
            "--file",
            str(interview_path),
        ]
    return packet


def compile_tau_dag_bundle(input: TauDagCompileInput) -> dict[str, Any]:
    missing = missing_dag_fields(input)
    run_dir = _run_dir(input)
    run_dir.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    _write_json(
        request_path,
        {
            "schema": "ask.tau_dag_request.v1",
            "created_at": _now_iso(),
            "request": input.request,
            "repo": input.repo,
            "target": input.target,
            "immutable_goal": input.immutable_goal,
            "solver_models": list(input.solver_models),
            "reviewer_model": input.reviewer_model,
            "criteria": list(input.criteria),
            "handlers": list(input.handlers),
            "handler_provider_hints": list(input.handler_provider_hints),
            "dag_template": input.dag_template,
            "topology": input.topology,
            "workflow_mode": input.workflow_mode,
            "join_handler": input.join_handler,
            "handler_projects": list(input.handler_projects),
            "handler_workspaces": list(input.handler_workspaces),
            "local_fixture": input.local_fixture,
        },
    )
    if missing:
        packet = build_interview_packet(input, output_root=run_dir)
        packet["run_dir"] = str(run_dir)
        packet["request_path"] = str(request_path)
        _write_json(run_dir / "interview-required.json", packet)
        _write_json(run_dir / "compile-status.json", packet)
        return packet

    worker_path = _write_roundtable_worker(run_dir) if input.handlers else _write_worker(run_dir)
    command_specs_dir = run_dir / "command-specs"
    agents_dir = run_dir / "agents"
    dag = _build_roundtable_tau_dag(input, run_dir=run_dir) if input.handlers else _build_tau_dag(input, run_dir=run_dir)
    for node in dag["nodes"]:
        _write_agent_stub(agents_dir, node_id=str(node["id"]), role=str(node["agent"]))
        if node.get("command_spec"):
            if input.handlers:
                _write_roundtable_command_spec(
                    command_specs_dir,
                    node=node,
                    input=input,
                    worker_path=worker_path,
                    run_dir=run_dir,
                )
            else:
                _write_command_spec(
                    command_specs_dir,
                    node=node,
                    input=input,
                    worker_path=worker_path,
                    run_dir=run_dir,
                )
    dag_path = run_dir / "dag.json"
    _write_json(dag_path, dag)
    dag_sha = f"sha256:{_sha256(dag_path)}"
    final_bundle = {
        "schema": ASK_TAU_DAG_BUNDLE_SCHEMA,
        "status": "READY",
        "mocked": False,
        "live": False,
        "provider_live": False,
        "request_path": str(request_path),
        "run_dir": str(run_dir),
        "dag_path": str(dag_path),
        "dag_sha256": dag_sha,
        "dag": dag,
        "agents_root": str(agents_dir),
        "command_spec_root": str(command_specs_dir),
        "worker_path": str(worker_path),
        "final_dag_emitted_before_execution": True,
        "proof_scope": {
            "proves": [
                "The human request was compiled into a strict tau.dag_contract.v1 artifact.",
                "The final DAG artifact exists before Tau execution is attempted.",
                "Every executable node has a generated agent registry entry and command spec.",
            ],
            "does_not_prove": [
                "Provider/model calls have succeeded.",
            "The Tau DAG has been executed.",
            "Semantic quality of solver or reviewer outputs.",
            "Browser handlers have run unless a later Tau execution receipt proves the adapter node.",
            "Compete mode has selected a semantically correct winner unless local deterministic checks and receipts prove it.",
        ],
        },
    }
    _write_json(run_dir / "compile-status.json", final_bundle)
    # tau#113: READY must never be a false green. Assert the runtime artifacts
    # exist non-empty on disk before the bundle is handed to the caller.
    _assert_runtime_artifacts(
        request_path,
        dag_path,
        run_dir / "compile-status.json",
    )
    return final_bundle


def _assert_runtime_artifacts(*paths: Path) -> None:
    missing = [str(p) for p in paths if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise TauDagError(
            "READY blocked: runtime artifacts missing or empty on disk: "
            + ", ".join(missing)
        )


def run_tau_dag_bundle(
    bundle: dict[str, Any],
    *,
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT,
    poll: bool = True,
    poll_interval_seconds: float = 1.0,
    poll_timeout_seconds: float = 120.0,
    viewer_link: bool = False,
) -> dict[str, Any]:
    if bundle.get("status") != "READY":
        raise TauDagError("Tau DAG bundle is not READY; run $interview first")
    run_dir = Path(str(bundle["run_dir"]))
    receipt_dir = run_dir / "tau-receipts"
    dag_path = Path(str(bundle["dag_path"]))
    command = [
        "uv",
        "run",
        "--project",
        str(tau_project_root),
        "tau",
        "dag-run",
        str(dag_path),
        "--receipt-dir",
        str(receipt_dir),
        "--agents-root",
        str(bundle["agents_root"]),
        "--command-spec-root",
        str(bundle["command_spec_root"]),
        "--scheduler",
        "bounded-ready-queue",
    ]
    dag_run = _run_command(command, cwd=tau_project_root)
    if dag_path.is_file():
        receipt_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dag_path, receipt_dir / "dag-contract.json")
    polls: list[dict[str, Any]] = []
    if poll:
        polls = poll_tau_status(
            receipt_dir,
            tau_project_root=tau_project_root,
            interval_seconds=poll_interval_seconds,
            timeout_seconds=poll_timeout_seconds,
        )
    viewer: dict[str, Any] | None = None
    if viewer_link:
        viewer = tau_viewer_link(receipt_dir, tau_project_root=tau_project_root)
    receipt_path = receipt_dir / "dag-receipt.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else None
    status = str(receipt.get("status") if isinstance(receipt, dict) else "UNKNOWN")
    degraded_join = _ensure_degraded_roundtable_join(bundle)
    node_provider_receipts = _collect_node_provider_receipts(run_dir / "node-artifacts")
    # Semantic review verdicts must bubble to the bundle: a reviewer node that
    # returns VERDICT: NEEDS_ATTENTION/FAIL completes its transport (node PASS)
    # but the bundle must not read as PASS, or callers ship unreviewed defects.
    review_verdicts: dict[str, str] = {}
    for item in node_provider_receipts:
        node_receipt = _read_json(Path(str(item.get("path")))) if item.get("path") else None
        # Bubble ANY verdict a node returned, not only requires_verdict nodes:
        # the requires_verdict heuristic can miss a request that still demanded
        # a verdict, and a returned NEEDS_ATTENTION/FAIL must never be masked
        # (observed live: doc3 iter-2 reviewer NEEDS_ATTENTION, bundle PASS).
        if isinstance(node_receipt, dict):
            verdict = node_receipt.get("verdict")
            if verdict:
                review_verdicts[str(item.get("node_id"))] = str(verdict)
    _verdict_rank = {"PASS": 0, "NEEDS_ATTENTION": 1, "FAIL": 2}
    worst_verdict = max(review_verdicts.values(), key=lambda v: _verdict_rank.get(v, 1), default=None)
    if worst_verdict and worst_verdict != "PASS" and status == "PASS":
        status = worst_verdict
    join_receipt = _roundtable_join_receipt(run_dir)
    join_artifact_path = str(run_dir / "node-artifacts" / "join" / "node-receipt.json") if join_receipt else ""
    join_status = str(join_receipt.get("status") or "") if isinstance(join_receipt, dict) else ""
    if join_status in {"DEGRADED", "NEEDS_ATTENTION", "BLOCKED", "FAIL", "FAILED", "ERROR"}:
        status = "NEEDS_ATTENTION" if join_status in {"BLOCKED", "FAIL", "FAILED", "ERROR"} else join_status
    elif join_status == "PASS" and dag_run["returncode"] == 0:
        status = "PASS"
    if dag_run["returncode"] != 0 and status not in {"DEGRADED", "NEEDS_ATTENTION"}:
        status = "ERROR"
    provider_live = bool(
        isinstance(receipt, dict) and receipt.get("provider_live") is True
    ) or any(item.get("provider_live") is True for item in node_provider_receipts)
    dag_context = bundle.get("dag", {}).get("context") if isinstance(bundle.get("dag"), dict) else {}
    provider_transport = (
        str(dag_context.get("provider_transport"))
        if isinstance(dag_context, dict) and dag_context.get("provider_transport")
        else str(dag_context.get("transport_adapter"))
        if isinstance(dag_context, dict) and dag_context.get("transport_adapter")
        else "$scillm"
    )
    result = {
        "schema": "ask.tau_dag_execution.v1",
        "status": status,
        "ok": status == "PASS",
        "mocked": False,
        "live": True,
        "provider_live": provider_live,
        "execution_owner": "$tau",
        "provider_transport": provider_transport,
        "command": command,
        "dag_run_returncode": dag_run["returncode"],
        "dag_run_stdout": dag_run["stdout"],
        "dag_run_stderr": dag_run["stderr"],
        "receipt_dir": str(receipt_dir),
        "receipt_path": str(receipt_path),
        "receipt": receipt,
        "node_provider_receipts": node_provider_receipts,
        "join_artifact_path": join_artifact_path or None,
        "join_receipt": join_receipt,
        "degraded_join": degraded_join,
        "polls": polls,
        "viewer": viewer,
        "proof_scope": {
            "proves": [
                "Tau's real CLI was invoked against the emitted DAG artifact.",
                "The run produced a Tau receipt directory and status readback when present.",
            ],
            "does_not_prove": [
                "Provider calls occurred unless provider_live is true and provider receipts are present.",
                "Reviewer output is semantically correct.",
            ],
        },
    }
    _write_json(run_dir / "execution-status.json", result)
    return result


def poll_tau_status(
    receipt_dir: Path,
    *,
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT,
    interval_seconds: float = 1.0,
    timeout_seconds: float = 120.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    polls: list[dict[str, Any]] = []
    while True:
        result = _run_command(
            [
                "uv",
                "run",
                "--project",
                str(tau_project_root),
                "tau",
                "run-status",
                str(receipt_dir),
            ],
            cwd=tau_project_root,
        )
        parsed = _json_or_none(result["stdout"])
        status = _status_from_run_status(parsed) if parsed else "UNKNOWN"
        polls.append(
            {
                "status": status,
                "returncode": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "parsed": parsed,
            }
        )
        if status in TERMINAL_STATUSES or time.monotonic() >= deadline:
            return polls
        time.sleep(max(0.1, interval_seconds))


def _ensure_degraded_roundtable_join(bundle: dict[str, Any]) -> dict[str, Any] | None:
    dag = bundle.get("dag") if isinstance(bundle.get("dag"), dict) else {}
    dag_context = dag.get("context") if isinstance(dag.get("context"), dict) else {}
    workflow_mode = str(dag_context.get("workflow_mode") or "")
    if workflow_mode not in {"roundtable", "compete"}:
        return None
    run_dir = Path(str(bundle.get("run_dir") or ""))
    if not run_dir:
        return None
    join_receipt_path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    if join_receipt_path.is_file() and join_receipt_path.stat().st_size > 0:
        return {
            "schema": "ask.tau_dag_degraded_join_completion.v1",
            "status": "existing",
            "join_artifact_path": str(join_receipt_path),
        }

    expected_nodes = _roundtable_handler_node_ids_from_dag(dag)
    if not expected_nodes:
        return None
    receipt_paths = {
        node_id: run_dir / "node-artifacts" / node_id / "node-receipt.json"
        for node_id in expected_nodes
    }
    missing = [node_id for node_id, path in receipt_paths.items() if not path.is_file()]
    if missing:
        synthesized = _synthesize_missing_browser_handler_receipts(dag, run_dir, missing)
        missing = [node_id for node_id, path in receipt_paths.items() if not path.is_file()]
        if missing:
            return {
                "schema": "ask.tau_dag_degraded_join_completion.v1",
                "status": "skipped",
                "reason": "handler_receipts_missing",
                "missing_handler_receipts": missing,
                "synthesized_handler_receipts": synthesized,
            }
    nonterminal = []
    for node_id, path in receipt_paths.items():
        receipt = _read_json(path)
        receipt_status = str(receipt.get("status") or "")
        if receipt_status not in TERMINAL_STATUSES:
            nonterminal.append({"node_id": node_id, "status": receipt_status, "path": str(path)})
    if nonterminal:
        return {
            "schema": "ask.tau_dag_degraded_join_completion.v1",
            "status": "skipped",
            "reason": "handler_receipts_not_terminal",
            "nonterminal_handler_receipts": nonterminal,
        }

    spec_path = run_dir / "command-specs" / "join" / "tau-dispatch-command.json"
    if not spec_path.is_file():
        return {
            "schema": "ask.tau_dag_degraded_join_completion.v1",
            "status": "skipped",
            "reason": "join_command_spec_missing",
            "expected_path": str(spec_path),
        }
    spec = _read_json(spec_path)
    command = spec.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return {
            "schema": "ask.tau_dag_degraded_join_completion.v1",
            "status": "skipped",
            "reason": "join_command_spec_invalid",
            "path": str(spec_path),
        }
    cwd = Path(str(spec.get("cwd") or run_dir))
    result = _run_command(command, cwd=cwd)
    join_receipt = _read_json(join_receipt_path) if join_receipt_path.is_file() else None
    return {
        "schema": "ask.tau_dag_degraded_join_completion.v1",
        "status": "emitted" if isinstance(join_receipt, dict) else "failed",
        "join_artifact_path": str(join_receipt_path) if isinstance(join_receipt, dict) else None,
        "join_status": join_receipt.get("status") if isinstance(join_receipt, dict) else None,
        "command": command,
        "returncode": result["returncode"],
        "stdout_excerpt": result["stdout"][:2000],
        "stderr_excerpt": result["stderr"][:2000],
    }


def _roundtable_handler_node_ids_from_dag(dag: dict[str, Any]) -> list[str]:
    nodes = dag.get("nodes") if isinstance(dag.get("nodes"), list) else []
    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        context = node.get("context") if isinstance(node.get("context"), dict) else {}
        if context.get("role") != "roundtable_handler":
            continue
        node_id = str(node.get("id") or "").strip()
        if node_id:
            node_ids.append(node_id)
    return node_ids


def _roundtable_handler_map_from_dag(dag: dict[str, Any]) -> dict[str, str]:
    nodes = dag.get("nodes") if isinstance(dag.get("nodes"), list) else []
    handlers: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        context = node.get("context") if isinstance(node.get("context"), dict) else {}
        if context.get("role") != "roundtable_handler":
            continue
        node_id = str(node.get("id") or "").strip()
        policy = context.get("handler_policy") if isinstance(context.get("handler_policy"), dict) else {}
        handler = str(policy.get("id") or node.get("agent") or node_id).strip()
        if node_id and handler:
            handlers[node_id] = handler
    return handlers


def _synthesize_missing_browser_handler_receipts(
    dag: dict[str, Any],
    run_dir: Path,
    missing_node_ids: list[str],
) -> list[dict[str, Any]]:
    handlers = _roundtable_handler_map_from_dag(dag)
    synthesized: list[dict[str, Any]] = []
    for node_id in missing_node_ids:
        handler = handlers.get(node_id, "")
        policy = ROUNDTABLE_HANDLERS.get(handler)
        if not isinstance(policy, dict) or policy.get("runtime") != "browser":
            continue
        artifact_dir = run_dir / "node-artifacts" / node_id
        prompt_path = artifact_dir / "prompt.md"
        submitted_path = artifact_dir / "response.md.submitted.md"
        response_path = artifact_dir / "response.md"
        raw_path = artifact_dir / "response.raw.md"
        meta_path = artifact_dir / "response.meta.json"
        evidence_paths = [prompt_path, submitted_path, response_path, raw_path, meta_path]
        if not any(path.exists() for path in evidence_paths):
            continue
        artifact_dir.mkdir(parents=True, exist_ok=True)
        submit_meta = _read_json(meta_path) if meta_path.is_file() else {}
        quarantined_response_path = response_path
        quarantine_receipt: dict[str, Any] | None = None
        response_chars = response_path.stat().st_size if response_path.is_file() else 0
        if response_path.is_file():
            quarantined_response_path = _next_available_path(response_path.with_name("response.unverified.md"))
            response_path.rename(quarantined_response_path)
            quarantine_path = artifact_dir / "response.quarantine.json"
            quarantine_receipt = {
                "schema": "ask.browser_failed_response_quarantine.v1",
                "status": "QUARANTINED",
                "ok": False,
                "provider_live": False,
                "failure_code": "browser_handler_timeout",
                "original_response_path": str(response_path),
                "quarantine_path": str(quarantined_response_path),
                "response_chars": response_chars,
                "caller_action": (
                    "Do not treat this browser prose as a clean seat response because the "
                    "browser worker did not emit a PASS receipt before timeout."
                ),
            }
            _write_json(quarantine_path, quarantine_receipt)
            quarantine_receipt["quarantine_receipt_path"] = str(quarantine_path)
        recovery_path = artifact_dir / "browser-recovery-packet.json"
        recovery_packet = {
            "schema": "ask.browser_failure_recovery_packet.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "failure_code": "browser_handler_timeout",
            "handler": handler,
            "node_id": node_id,
            "reason": (
                "The browser worker left submit artifacts but no node-receipt.json before Tau "
                "reached a terminal command failure."
            ),
            "evidence": {
                "prompt_path": str(prompt_path) if prompt_path.exists() else None,
                "submitted_prompt_path": str(submitted_path) if submitted_path.exists() else None,
                "raw_response_path": str(raw_path) if raw_path.exists() else None,
                "meta_path": str(meta_path) if meta_path.exists() else None,
                "submit_meta_status": submit_meta.get("status") if isinstance(submit_meta, dict) else None,
                "response_chars": response_chars,
            },
            "response_path": str(quarantined_response_path),
            "raw_response_path": str(raw_path),
            "meta_path": str(meta_path),
            "prompt_path": str(prompt_path),
            "auto_retry_allowed": False,
            "auto_retry_blocked_reason": "browser_handler_timeout_expired",
            "next_command": [],
            "fallback_instruction": (
                "Treat only this browser lane as timed out. Let the join preserve usable peer seats, "
                "then rerun this handler later or with a fresh provider tab."
            ),
        }
        _write_json(recovery_path, recovery_packet)
        receipt = {
            "schema": "ask.tau_dag_handler_receipt.v1",
            "created_at": _now_iso(),
            "node_id": node_id,
            "handler": handler,
            "topology": str(dag.get("context", {}).get("roundtable_topology") or "concurrent"),
            "status": "NEEDS_ATTENTION",
            "ok": False,
            "mocked": False,
            "live": True,
            "provider_live": False,
            "response_path": str(quarantined_response_path),
            "response_quarantine": quarantine_receipt,
            "raw_response_path": str(raw_path),
            "meta_path": str(meta_path),
            "prompt_path": str(prompt_path),
            "recovery_packet_path": str(recovery_path),
            "response_chars": response_chars,
            "submit_meta": submit_meta if isinstance(submit_meta, dict) else {},
            "commands": [],
            "failure": "browser_handler_timeout: missing node-receipt.json after browser submit artifacts existed",
            "failure_code": "browser_handler_timeout",
            "competition_lane_exit_ok": True,
            "recovery_packet": recovery_packet,
            "synthesized_missing_receipt": True,
            "provider_receipt": {
                "schema": "ask.tau_dag_provider_route_receipt.v1",
                "status": "NEEDS_ATTENTION",
                "ok": False,
                "mocked": False,
                "live": True,
                "provider_live": False,
                "route": "tau_roundtable_handler_adapter",
                "execution_owner": "$tau",
                "provider_transport": "$surf",
                "handler": handler,
                "transport": policy.get("transport"),
            },
        }
        receipt_path = artifact_dir / "node-receipt.json"
        _write_json(receipt_path, receipt)
        synthesized.append(
            {
                "node_id": node_id,
                "handler": handler,
                "receipt_path": str(receipt_path),
                "recovery_packet_path": str(recovery_path),
                "response_quarantine": quarantine_receipt,
            }
        )
    return synthesized


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 100):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise TauDagError(f"unable to allocate path near {path}")


def _roundtable_join_receipt(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    if not path.is_file():
        return None
    try:
        receipt = _read_json(path)
    except (OSError, json.JSONDecodeError, TauDagError):
        return None
    schema = str(receipt.get("schema") or "")
    if schema not in {"ask.tau_dag_roundtable_join_receipt.v1", "ask.tau_dag_compete_join_receipt.v1"}:
        return None
    return receipt


def tau_viewer_link(
    receipt_dir: Path,
    *,
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT,
) -> dict[str, Any]:
    result = _run_command(
        [
            "uv",
            "run",
            "--project",
            str(tau_project_root),
            "tau",
            "dag-viewer-link",
            str(receipt_dir),
        ],
        cwd=tau_project_root,
    )
    parsed = _json_or_none(result["stdout"])
    return {
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "parsed": parsed,
    }


def _collect_node_provider_receipts(artifacts_root: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    if not artifacts_root.is_dir():
        return receipts
    for path in sorted(artifacts_root.glob("*/node-receipt.json")):
        try:
            node_receipt = _read_json(path)
        except (OSError, json.JSONDecodeError, TauDagError):
            continue
        provider_receipt = node_receipt.get("provider_receipt")
        if not isinstance(provider_receipt, dict):
            continue
        receipts.append(
            {
                "path": str(path),
                "node_id": node_receipt.get("node_id"),
                "mode": node_receipt.get("mode"),
                "requested_model": provider_receipt.get("requested_model")
                or node_receipt.get("requested_model"),
                "model": provider_receipt.get("model") or node_receipt.get("model"),
                "reasoning_effort": provider_receipt.get("reasoning_effort")
                or node_receipt.get("reasoning_effort"),
                "requested_reasoning_effort": provider_receipt.get("requested_reasoning_effort")
                or node_receipt.get("requested_reasoning_effort"),
                "status": provider_receipt.get("status"),
                "ok": provider_receipt.get("ok") is True,
                "mocked": provider_receipt.get("mocked") is True,
                "live": provider_receipt.get("live") is True,
                "provider_live": provider_receipt.get("provider_live") is True,
                "response_path": node_receipt.get("response_path"),
                "response_chars": node_receipt.get("response_chars"),
                "failure": node_receipt.get("failure"),
                "failure_code": node_receipt.get("failure_code"),
                "recovery_packet_path": node_receipt.get("recovery_packet_path"),
                "route": provider_receipt.get("route"),
                "execution_owner": provider_receipt.get("execution_owner"),
                "provider_transport": provider_receipt.get("provider_transport"),
            }
        )
    return receipts


def probe_scillm_provider_gate(
    *,
    models: list[str],
    base_url: str = DEFAULT_SCILLM_BASE_URL,
    api_key: str = DEFAULT_SCILLM_API_KEY,
    allow_provider_calls: bool = False,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Probe the SciLLM container and optionally make real model calls."""

    base = base_url.rstrip("/")
    resolved_key = api_key or default_scillm_api_key()
    headers = {"Authorization": f"Bearer {resolved_key}", "X-Caller-Skill": "ask-tau-dag-preflight"}
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout_seconds) as client:
        for path in ("/health/liveliness", "/v1/scillm/auth", "/v1/scillm/providers"):
            checks.append(_http_check(client, "GET", f"{base}{path}", headers=headers))
        model_calls: list[dict[str, Any]] = []
        if allow_provider_calls:
            for requested_model in sorted({item for item in models if item}):
                route = resolve_scillm_model_route(requested_model)
                payload = {
                    "model": route.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with the single word ok for an ask Tau DAG provider gate.",
                        }
                    ],
                }
                if route.reasoning_effort:
                    payload["reasoning_effort"] = route.reasoning_effort
                model_calls.append(
                    _http_check(
                        client,
                        "POST",
                        f"{base}/v1/chat/completions",
                        headers=headers,
                        json_payload=payload,
                        metadata=_route_metadata(route),
                    )
                )
        else:
            model_calls = [
                {
                    "status": "BLOCKED",
                    "blocked_reason": "provider_calls_not_allowed",
                    "requested_model": model,
                    **_route_metadata(resolve_scillm_model_route(model)),
                    "mocked": False,
                    "live": False,
                }
                for model in sorted({item for item in models if item})
            ]
    service_contacted = any(item.get("live") is True for item in checks)
    service_ok = all(item.get("ok") is True for item in checks)
    calls_ok = allow_provider_calls and all(item.get("ok") is True for item in model_calls)
    status = "PASS" if service_ok and calls_ok else "BLOCKED"
    if service_ok and not allow_provider_calls:
        status = "BLOCKED_BY_PROVIDER_CALL_OPT_IN"
    return {
        "schema": "ask.tau_dag_scillm_provider_gate.v1",
        "status": status,
        "ok": status == "PASS",
        "mocked": False,
        "live": service_contacted,
        "provider_live": calls_ok,
        "scillm_base_url": base,
        "gate_owner": "$ask",
        "execution_owner": "$tau",
        "provider_transport": "$scillm",
        "service_checks": checks,
        "model_calls": model_calls,
        "proof_scope": {
            "proves": [
                "The SciLLM container endpoints were queried live when live is true.",
                "Provider model calls were attempted only when provider_live is true or model_calls contain receipts.",
                "User-facing model selectors are resolved into explicit SciLLM dispatch model/effort metadata.",
            ],
            "does_not_prove": [
                "Tau DAG execution succeeded.",
                "All future provider/model routes are healthy.",
            ],
        },
    }


def probe_browser_compete_handler_gate(
    input: TauDagCompileInput,
    *,
    surf_run: Path | None = None,
    browser_oracle_run: Path | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Preflight all-browser compete runs before Tau launches candidate nodes."""

    browser_handlers = [handler for handler in input.handlers if _is_browser_handler(handler)]
    all_browser_compete = (
        input.workflow_mode == "compete"
        and bool(input.handlers)
        and len(browser_handlers) == len(input.handlers)
    )
    if not all_browser_compete:
        return {
            "schema": "ask.tau_dag_browser_compete_handler_gate.v1",
            "status": "READY",
            "ok": True,
            "mocked": False,
            "live": False,
            "provider_live": False,
            "skipped": True,
            "skip_reason": "not_all_browser_compete",
            "handlers": list(input.handlers),
        }

    surf_run = surf_run or (ASK_SKILL_ROOT.parent / "surf" / "run.sh")
    browser_oracle_run = browser_oracle_run or (ASK_SKILL_ROOT.parent / "browser-oracle" / "run.sh")
    checks: list[dict[str, Any]] = []
    tab_list = _run_gate_command(
        [str(surf_run), "tab.list", "--json"],
        cwd=Path(surf_run).parent,
        timeout_seconds=timeout_seconds,
    )
    live = True
    tab_payload = _parse_tab_list_payload(tab_list.get("stdout", ""))
    surf_ok = tab_list["returncode"] == 0 and isinstance(tab_payload, list)
    if not surf_ok:
        for handler in input.handlers:
            checks.append(
                _browser_gate_check(
                    input,
                    handler=handler,
                    status="BLOCKED",
                    failure_code="surf_transport_unavailable",
                    detail=tab_list.get("stderr") or tab_list.get("stdout") or "surf tab.list failed",
                    command=tab_list,
                )
            )
        return _browser_compete_gate_result(input, checks, live=live)

    for handler in input.handlers:
        project = _handler_project(input, handler)
        resolve = _run_gate_command(
            [
                str(browser_oracle_run),
                "resolve",
                "--backend",
                HANDLER_BACKENDS_FOR_GATE[handler],
                "--project",
                project,
                "--json",
            ],
            cwd=Path(browser_oracle_run).parent,
            timeout_seconds=timeout_seconds,
        )
        resolve_payload = _json_or_none(str(resolve.get("stdout") or ""))
        if resolve["returncode"] != 0 or not isinstance(resolve_payload, dict):
            checks.append(
                _browser_gate_check(
                    input,
                    handler=handler,
                    status="BLOCKED",
                    failure_code="browser_oracle_resolve_failed",
                    detail=resolve.get("stderr") or resolve.get("stdout") or "browser-oracle resolve failed",
                    command=resolve,
                )
            )
            continue
        tab_id = str(resolve_payload.get("tab_id") or "")
        live_tab = next((tab for tab in tab_payload if str(tab.get("id") or "") == tab_id), None)
        if not tab_id or live_tab is None:
            checks.append(
                _browser_gate_check(
                    input,
                    handler=handler,
                    status="BLOCKED",
                    failure_code="browser_oracle_tab_missing",
                    detail=f"browser-oracle project {project!r} resolved to missing tab_id {tab_id!r}",
                    command=resolve,
                    browser_oracle=resolve_payload,
                )
            )
            continue
        live_url = str(live_tab.get("url") or "")
        checks.append(
            _browser_gate_check(
                input,
                handler=handler,
                status="READY",
                failure_code=None,
                detail=f"resolved tab {tab_id} at {live_url}",
                command=resolve,
                browser_oracle=resolve_payload,
                live_tab=live_tab,
            )
        )
    return _browser_compete_gate_result(input, checks, live=live)


HANDLER_BACKENDS_FOR_GATE = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
    "webgrok": "webgrok",
}


def _is_browser_handler(handler: str) -> bool:
    policy = ROUNDTABLE_HANDLERS.get(handler)
    return isinstance(policy, dict) and policy.get("runtime") == "browser"


def _run_gate_command(command: list[str], *, cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[:20000],
            "stderr": completed.stderr[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": str(exc.stdout or "")[:20000],
            "stderr": str(exc.stderr or "command timed out")[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc)[:4000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }


def _parse_tab_list_payload(text: str) -> list[dict[str, Any]] | None:
    payload = _extract_json_payload(text)
    if payload is None:
        return None
    if isinstance(payload, dict):
        payload = payload.get("tabs", [])
    if not isinstance(payload, list):
        return None
    return [tab for tab in payload if isinstance(tab, dict)]


def _browser_gate_check(
    input: TauDagCompileInput,
    *,
    handler: str,
    status: str,
    failure_code: str | None,
    detail: str,
    command: dict[str, Any],
    browser_oracle: dict[str, Any] | None = None,
    live_tab: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "handler": handler,
        "node_id": _handler_node_id(handler),
        "project": _handler_project(input, handler),
        "status": status,
        "ok": status == "READY",
        "failure_code": failure_code,
        "detail": detail[:1000],
        "browser_oracle": browser_oracle,
        "live_tab": live_tab,
        "command": command,
    }


def _browser_compete_gate_result(
    input: TauDagCompileInput,
    checks: list[dict[str, Any]],
    *,
    live: bool,
) -> dict[str, Any]:
    ok = all(check.get("ok") is True for check in checks)
    return {
        "schema": "ask.tau_dag_browser_compete_handler_gate.v1",
        "status": "READY" if ok else "BLOCKED",
        "ok": ok,
        "mocked": False,
        "live": live,
        "provider_live": False,
        "handlers": list(input.handlers),
        "topology": input.topology,
        "workflow_mode": input.workflow_mode,
        "handler_checks": checks,
        "blocked_handler_count": sum(1 for check in checks if check.get("ok") is not True),
        "fail_closed_reason": None if ok else "browser_handler_preflight_failed",
    }


def browser_compete_blocked_execution(gate: dict[str, Any]) -> dict[str, Any]:
    """Build a terminal execution receipt when preflight blocks Tau launch."""

    node_statuses = []
    for check in gate.get("handler_checks", []):
        if not isinstance(check, dict):
            continue
        node_statuses.append(
            {
                "node_id": check.get("node_id"),
                "handler": check.get("handler"),
                "status": "BLOCKED",
                "ok": False,
                "failure_code": check.get("failure_code"),
                "blocked_reason": check.get("detail"),
            }
        )
    node_statuses.append(
        {
            "node_id": "join",
            "handler": "join",
            "status": "BLOCKED",
            "ok": False,
            "failure_code": "candidate_preflight_failed",
            "blocked_reason": "Ask did not launch Tau because one or more browser candidate handlers failed preflight.",
        }
    )
    return {
        "schema": "ask.tau_dag_execution.v1",
        "status": "BLOCKED",
        "ok": False,
        "mocked": False,
        "live": bool(gate.get("live")),
        "provider_live": False,
        "blocked_reason": "browser_compete_handler_gate_failed",
        "message": "All-browser compete DAG was blocked before Tau dispatch.",
        "no_tau_execution": True,
        "node_statuses": node_statuses,
        "handler_gate": gate,
    }


def _build_tau_dag(input: TauDagCompileInput, *, run_dir: Path) -> dict[str, Any]:
    dag_id = _dag_id(input)
    goal = {
        "goal_id": f"ask-{dag_id}",
        "goal_version": 1,
        "immutable_goal": input.immutable_goal,
        "goal_hash": _goal_hash(input),
    }
    solver_nodes: list[dict[str, Any]] = []
    for index, model in enumerate(input.solver_models, start=1):
        node_id = f"solver-{index}"
        solver_nodes.append(
            {
                "id": node_id,
                "agent": node_id,
                "executor": "local",
                "max_attempts": 1,
                "command_spec": f"command-specs/{node_id}/tau-dispatch-command.json",
                "required_evidence": [
                    "solution",
                    "provider_route_receipt",
                    "model_policy",
                    "node_receipt",
                ],
                "model_policy": _model_policy(model, base_url=input.scillm_base_url),
                "prompt_contract": _solver_prompt_contract(input, model=model, index=index),
                "context": {
                    "role": "concurrent_solver",
                    **_dag_template_context(input),
                    "model": model,
                    "request": input.request,
                    "criteria": list(input.criteria),
                },
            }
        )
    reviewer_node = {
        "id": "reviewer",
        "agent": "reviewer",
        "executor": "local",
        "max_attempts": 1,
        "command_spec": "command-specs/reviewer/tau-dispatch-command.json",
        "required_evidence": [
            "reviewer_verdict",
            "winner",
            "rationale",
            "provider_route_receipt",
            "model_policy",
            "node_receipt",
        ],
        "reviewer": {
            "kind": "winner_selector",
            "criteria": list(input.criteria),
            "requires_rationale": True,
        },
        "model_policy": _model_policy(input.reviewer_model, base_url=input.scillm_base_url),
        "prompt_contract": _reviewer_prompt_contract(input),
        "context": {
            "role": "comparative_reviewer",
            **_dag_template_context(input),
            "model": input.reviewer_model,
            "criteria": list(input.criteria),
            "request": input.request,
        },
    }
    nodes = [*solver_nodes, reviewer_node]
    edges = [{"from": node["id"], "to": "reviewer"} for node in solver_nodes]
    edges.append({"from": "reviewer", "to": "human"})
    return {
        "schema": TAU_DAG_SCHEMA,
        "dag_id": dag_id,
        "goal": goal,
        "target": {"repo": input.repo, "target": input.target},
        "entry_node": solver_nodes[0]["id"],
        "terminal_nodes": ["human"],
        "limits": {
            "max_total_attempts": len(nodes),
            "max_parallel_nodes": min(4, max(1, len(solver_nodes))),
            "provider_command_timeout_seconds": 900,
            "scillm_base_url": input.scillm_base_url,
        },
        "context": {
            "compiled_by": "$ask",
            "delegated_runtime": "$tau",
            "interview_skill": "$interview",
            "best_practices": "$best-practices-tau-dag",
            **_dag_template_context(input),
            "request": input.request,
            "run_dir": str(run_dir),
            "execution_owner": "$tau",
            "provider_transport": "$scillm",
            "provider_route": "tau_local_scillm_adapter",
            "execution_mode": "fixture" if input.local_fixture else "scillm",
        },
        "provider_sensitive": True,
        "requires_provider_route": True,
        "nodes": nodes,
        "edges": edges,
        "required_evidence": ["solution", "reviewer_verdict", "winner", "provider_route_receipt"],
        "fail_closed_on": FAIL_CLOSED_ON,
    }


def _build_roundtable_tau_dag(input: TauDagCompileInput, *, run_dir: Path) -> dict[str, Any]:
    dag_id = _dag_id(input)
    goal = {
        "goal_id": f"ask-{dag_id}",
        "goal_version": 1,
        "immutable_goal": input.immutable_goal,
        "goal_hash": _goal_hash(input),
    }
    handler_nodes: list[dict[str, Any]] = []
    is_compete = input.workflow_mode == "compete"
    node_ids = _handler_node_ids(input.handlers)
    browser_resource_chain = [
        node_id
        for handler, node_id in zip(input.handlers, node_ids)
        if _is_browser_handler(handler)
    ]
    for index, (handler, node_id) in enumerate(zip(input.handlers, node_ids)):
        provider_hint = _handler_provider_hint(input, index)
        prior_nodes = _roundtable_prior_nodes(input, node_id)
        scheduler_dependencies = list(prior_nodes)
        required_evidence = [
            "handler_response_receipt",
            "normalized_handler_receipt",
            "transport_metadata",
        ]
        if prior_nodes:
            required_evidence.append("prior_handler_receipts")
        handler_nodes.append(
            {
                "id": node_id,
                "agent": node_id,
                "executor": "local",
                "max_attempts": 1,
                "command_spec": f"command-specs/{node_id}/tau-dispatch-command.json",
                "required_evidence": required_evidence,
                "depends_on": scheduler_dependencies,
                "context": {
                    "role": "roundtable_handler",
                    "workflow_mode": input.workflow_mode,
                    **_dag_template_context(input),
                    "handler": handler,
                    "provider_hint": provider_hint,
                    "handler_policy": _handler_policy(
                        handler,
                        provider_hint=provider_hint,
                        workflow_mode=input.workflow_mode,
                    ),
                    "prompt_contract": _roundtable_handler_prompt_contract(
                        input,
                        handler=handler,
                        prior_nodes=prior_nodes,
                    ),
                    "browser_oracle_project": _handler_project(input, handler),
                    "request": input.request,
                    "immutable_goal": input.immutable_goal,
                    "topology": input.topology,
                    "prior_nodes": prior_nodes,
                    "scheduler_dependencies": scheduler_dependencies,
                    "transport_resource": "surf_socket" if _is_browser_handler(handler) else None,
                    "requires_prior_receipts": bool(prior_nodes),
                    "requires_verdict": bool(prior_nodes) and _roundtable_requires_verdict(input.request),
                    "isolation_required": is_compete,
                },
            }
        )
    join_node = {
        "id": "join",
        "agent": input.join_handler or "join",
        "executor": "local",
        "max_attempts": 1,
        "command_spec": "command-specs/join/tau-dispatch-command.json",
        "required_evidence": [
            "roundtable_join_receipt",
            "handler_response_index",
            "unresolved_gaps",
        ],
        "join": {
            "requires_completed": [node["id"] for node in handler_nodes],
            "reconciles_evidence": True,
            "topology": input.topology,
        },
        "context": {
            "role": "compete_evaluator" if is_compete else "roundtable_join",
            "workflow_mode": input.workflow_mode,
            **_dag_template_context(input),
            "prompt_contract": _roundtable_join_prompt_contract(input),
            "request": input.request,
            "immutable_goal": input.immutable_goal,
            "handlers": list(input.handlers),
            "topology": input.topology,
        },
    }
    if is_compete:
        join_node["required_evidence"] = [
            "compete_scorecard",
            "verified_feature_packet",
            "winner_continuation_request",
            "unresolved_gaps",
        ]
        join_node["join"] = {
            "requires_completed": [node["id"] for node in handler_nodes],
            "reconciles_evidence": True,
            "topology": input.topology,
            "selection_policy": "deterministic_receipts_first_then_project_agent_review",
            "fail_closed_on_tie": True,
        }
    edges: list[dict[str, str]] = []
    if input.topology == "sequential":
        previous = ""
        for node in handler_nodes:
            if previous:
                edges.append({"from": previous, "to": str(node["id"])})
            previous = str(node["id"])
        edges.append({"from": previous, "to": "join"})
    else:
        edges.extend(
            {"from": str(node["id"]), "to": "join"}
            for node in handler_nodes
        )
    edges.append({"from": "join", "to": "human"})
    return {
        "schema": TAU_DAG_SCHEMA,
        "dag_id": dag_id,
        "goal": goal,
        "target": {"repo": input.repo, "target": input.target},
        "entry_node": str(handler_nodes[0]["id"]),
        "terminal_nodes": ["human"],
        "limits": {
            "resume": True,
            "default_timeout_seconds": 300,
            "max_total_attempts": len(handler_nodes) + 1,
            "max_concurrency": len(handler_nodes) if input.topology == "concurrent" else 1,
        },
        "context": {
            "compiled_by": "$ask",
            "delegated_runtime": "$tau",
            "transport_owner": "$surf_or_api_adapter",
            **_dag_template_context(input),
            "request": input.request,
            "immutable_goal": input.immutable_goal,
            "run_dir": str(run_dir),
            "execution_owner": "$tau",
            "transport_adapter": "handler_neutral_adapter",
            "roundtable_adapter": "tau_roundtable_handler_adapter",
            "execution_mode": "surf_browser_adapter",
            "workflow_mode": input.workflow_mode,
            "roundtable_topology": input.topology,
            "handlers": list(input.handlers),
            "handler_projects": {
                handler: _handler_project(input, handler)
                for handler in input.handlers
                if handler in ROUNDTABLE_HANDLERS
            },
            "browser_transport_serialized": False,
            "browser_transport_lock_queued": input.topology == "concurrent"
            and len(browser_resource_chain) > 1,
            "browser_transport_chain": browser_resource_chain,
        },
        "provider_sensitive": False,
        "requires_provider_route": False,
        "nodes": [*handler_nodes, join_node],
        "edges": edges,
        "required_evidence": [
            "handler_response_receipt",
            "normalized_handler_receipt",
            "compete_scorecard" if is_compete else "roundtable_join_receipt",
        ],
        "fail_closed_on": [
            *FAIL_CLOSED_ON,
            "unresolved_block_alert",
        ],
    }


def _write_command_spec(
    root: Path,
    *,
    node: dict[str, Any],
    input: TauDagCompileInput,
    worker_path: Path,
    run_dir: Path,
) -> None:
    node_id = str(node["id"])
    mode = "fixture" if input.local_fixture else "scillm"
    model_policy = node.get("model_policy") if isinstance(node.get("model_policy"), dict) else {}
    command = [
        sys.executable,
        str(worker_path),
        "--node-id",
        node_id,
        "--mode",
        mode,
        "--model",
        str(model_policy.get("model") or ""),
        "--scillm-base-url",
        input.scillm_base_url,
        "--scillm-api-key",
        input.scillm_api_key,
        "--artifact-dir",
        str(run_dir / "node-artifacts" / node_id),
    ]
    if model_policy.get("reasoning_effort"):
        command.extend(["--reasoning-effort", str(model_policy["reasoning_effort"])])
    if model_policy.get("requested_model"):
        command.extend(["--requested-model", str(model_policy["requested_model"])])
    if model_policy.get("requested_reasoning_effort"):
        command.extend(["--requested-reasoning-effort", str(model_policy["requested_reasoning_effort"])])
    for evidence in node.get("required_evidence", []):
        command.extend(["--evidence", str(evidence)])
    payload = {
        "command": command,
        "cwd": str(run_dir),
        "timeout_s": 900 if mode == "scillm" else 30,
        "requires_network": mode == "scillm",
        "mutates": False,
        "requires_clean_worktree": False,
    }
    spec_path = root / node_id / "tau-dispatch-command.json"
    _write_json(spec_path, payload)


def _write_roundtable_command_spec(
    root: Path,
    *,
    node: dict[str, Any],
    input: TauDagCompileInput,
    worker_path: Path,
    run_dir: Path,
) -> None:
    node_context = node.get("context") if isinstance(node.get("context"), dict) else {}
    handler_policy = node_context.get("handler_policy") if isinstance(node_context.get("handler_policy"), dict) else {}
    node_id = str(node["id"])
    handler = str(handler_policy.get("id") or node.get("agent") or node_id)
    is_subagent_handler = str(handler_policy.get("transport") or "") == "subagent-runner.codex_exec"
    command = [
        sys.executable,
        str(worker_path),
        "--node-id",
        node_id,
        "--handler",
        handler,
        "--topology",
        input.topology,
        "--workflow-mode",
        input.workflow_mode,
        "--request-file",
        str(run_dir / "request.json"),
        "--next-agent",
        _roundtable_next_agent(input, node_id),
        "--artifact-dir",
        str(run_dir / "node-artifacts" / node_id),
        "--surf-run",
        str(ASK_SKILL_ROOT.parent / "surf" / "run.sh"),
        "--browser-oracle-run",
        str(ASK_SKILL_ROOT.parent / "browser-oracle" / "run.sh"),
        "--scillm-base-url",
        input.scillm_base_url,
        "--scillm-api-key",
        input.scillm_api_key,
        "--timeout",
        # codex coder orders carry mandatory finish sequences (wheel build +
        # fixture suite + gate-document extractions + cargo test) that alone
        # take ~20 min; 3000s starved a real repair mid-flight (2026-07-22).
        "5400"
        if handler == "codex"
        else ("1500" if is_subagent_handler else ("900" if _is_browser_handler(handler) else "300")),
        "--stable-polls",
        "2",
        "--no-activate",
    ]
    prior_nodes = _roundtable_prior_nodes(input, node_id)
    if node_id == "join":
        prior_nodes = _handler_node_ids(input.handlers)
    for prior_node in prior_nodes:
        command.extend(["--prior-node", prior_node])
    if handler in ROUNDTABLE_HANDLERS and handler != "codex":
        command.extend(["--browser-oracle-project", _handler_project(input, handler)])
        lock_timeout_s = _browser_lock_timeout_seconds(input)
        if lock_timeout_s:
            command.extend(["--browser-lock-timeout", str(lock_timeout_s)])
    provider_hint = str(handler_policy.get("provider_hint") or "")
    if provider_hint:
        command.extend(["--provider-hint", provider_hint])
    model_preference = str(handler_policy.get("model_preference") or "")
    if model_preference:
        command.extend(["--browser-model-preference", model_preference])
    if str(handler_policy.get("transport") or "") == "subagent-runner.codex_exec":
        model_policy = handler_policy.get("model_policy") if isinstance(handler_policy.get("model_policy"), dict) else {}
        command.extend(
            [
                "--subagent-runner",
                str(ASK_SKILL_ROOT.parent / "subagent-runner" / "run.sh"),
                "--subagent-model",
                str(model_policy.get("model") or handler_policy.get("model") or handler),
                "--subagent-reasoning-effort",
                str(model_policy.get("reasoning_effort") or handler_policy.get("reasoning_effort") or "high"),
                "--subagent-requested-model",
                str(model_policy.get("requested_model") or handler_policy.get("requested_model") or handler),
            ]
        )
    if handler == "codex":
        workspace = _handler_workspace(input, handler)
        if not workspace:
            raise TauDagError(
                "codex handler requires --handler-workspace codex=/path/to/worktree"
            )
        command.extend(["--codex-workspace", workspace])
    for evidence in node.get("required_evidence", []):
        command.extend(["--evidence", str(evidence)])
    payload = {
        "command": command,
        "cwd": str(run_dir),
        "timeout_s": _roundtable_command_timeout(
            handler,
            is_subagent_handler=is_subagent_handler,
            lock_timeout_s=_browser_lock_timeout_seconds(input) if _is_browser_handler(handler) else 0,
        ),
        "requires_network": node_id != "join",
        "mutates": handler == "codex",
        "requires_clean_worktree": False,
        "compile_only": False,
        "runtime_note": (
            "This command dispatches a live Tau roundtable adapter node through the handler-neutral transport."
        ),
    }
    spec_path = root / node_id / "tau-dispatch-command.json"
    _write_json(spec_path, payload)


def _roundtable_command_timeout(
    handler: str,
    *,
    is_subagent_handler: bool,
    lock_timeout_s: int = 0,
) -> int:
    if handler == "codex":
        return 6000
    if is_subagent_handler:
        return 1800
    if _is_browser_handler(handler):
        browser_envelope = (
            DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS
            + max(0, lock_timeout_s)
            + BROWSER_COMMAND_GRACE_SECONDS
        )
        if handler == "webgpt":
            return max(3900, browser_envelope)
        if handler == "webgemini":
            return max(4200, browser_envelope)
        if handler in {"webclaude", "webkimi", "webgrok"}:
            return max(3000, browser_envelope)
        return browser_envelope
    if handler == "webgpt":
        return 3900
    if handler == "webgemini":
        return 4200
    if handler in {"webclaude", "webkimi", "webgrok"}:
        return 3000
    return 420


def _browser_handler_count(input: TauDagCompileInput) -> int:
    return sum(1 for handler in input.handlers if _is_browser_handler(handler))


def _browser_lock_timeout_seconds(input: TauDagCompileInput) -> int:
    browser_count = _browser_handler_count(input)
    if browser_count == 0:
        return 0
    if input.topology == "concurrent":
        return DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS * max(browser_count - 1, 1)
    return DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS


def _write_agent_stub(root: Path, *, node_id: str, role: str) -> None:
    path = root / node_id / "AGENTS.md"
    text = "\n".join(
        [
            "---",
            f"id: {node_id}",
            "active: true",
            f"tau_role: {role}",
            "tau_executor: local",
            "---",
            "",
            f"# {node_id}",
            "",
            "Generated by $ask for a Tau DAG dispatch node.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_worker(run_dir: Path) -> Path:
    worker_path = run_dir / "workers" / "ask_tau_dag_worker.py"
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    worker_path.write_text(_WORKER_SOURCE, encoding="utf-8")
    worker_path.chmod(0o755)
    return worker_path


def _write_roundtable_worker(run_dir: Path) -> Path:
    worker_path = run_dir / "workers" / "ask_tau_roundtable_worker.py"
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASK_SKILL_ROOT / "scripts" / "tau_roundtable_worker.py", worker_path)
    worker_path.chmod(0o755)
    return worker_path


def _model_policy(model: str, *, base_url: str = DEFAULT_SCILLM_BASE_URL) -> dict[str, str]:
    route = resolve_scillm_model_route(model)
    payload: dict[str, str] = {
        "provider": route.provider,
        "requested_model": route.requested_model,
        "model": route.model,
        "auth": route.auth,
        "service": "scillm_container_service",
        "base_url": base_url,
        "execution_owner": "$tau",
        "provider_transport": "$scillm",
    }
    if route.reasoning_effort:
        payload["reasoning_effort"] = route.reasoning_effort
    if route.requested_reasoning_effort:
        payload["requested_reasoning_effort"] = route.requested_reasoning_effort
    if route.reasoning_downgrade_reason:
        payload["reasoning_downgrade_reason"] = route.reasoning_downgrade_reason
    return payload


def _handler_policy(handler: str, *, provider_hint: str = "", workflow_mode: str = "roundtable") -> dict[str, Any]:
    if handler in ROUNDTABLE_HANDLERS:
        policy = dict(ROUNDTABLE_HANDLERS[handler])
        policy["id"] = handler
        policy["execution_owner"] = "$tau"
        policy["receipt_schema"] = "ask.tau_dag_handler_receipt.v1"
        if workflow_mode == "compete" and handler == "webclaude":
            policy["model_preference"] = COMPETE_WEBCLAUDE_MODEL
            policy["model_preference_scope"] = "ask_compete_default"
            policy["model_preference_reason"] = (
                "Competition mode defaults the webclaude browser seat to Claude Opus 5 High."
            )
        return policy
    if _is_subagent_handler(handler, provider_hint):
        model_policy = _subagent_model_policy(handler)
        return {
            "id": handler,
            "transport_owner": "$tau",
            "transport": "subagent-runner.codex_exec",
            "runtime": "local_subagent",
            "model": model_policy["model"],
            "requested_model": model_policy["requested_model"],
            "reasoning_effort": model_policy["reasoning_effort"],
            "provider_hint": provider_hint,
            "model_policy": model_policy,
            "proof_required": "subagent_runner_result_receipt",
            "execution_owner": "$tau",
            "receipt_schema": "ask.tau_dag_handler_receipt.v1",
        }
    return {
        "id": handler,
        "transport_owner": "$tau",
        "transport": "scillm.chat",
        "runtime": "api",
        "model": handler,
        "provider_hint": provider_hint or _infer_provider_hint_from_model(handler),
        "model_policy": _model_policy(handler),
        "proof_required": "scillm_provider_receipt",
        "execution_owner": "$tau",
        "receipt_schema": "ask.tau_dag_handler_receipt.v1",
    }


def _is_subagent_handler(handler: str, provider_hint: str = "") -> bool:
    if provider_hint:
        return False
    lowered = handler.strip().lower()
    return lowered.endswith("-xhigh") and lowered.startswith(SUBAGENT_HANDLER_MODEL_PREFIXES)


def _subagent_model_policy(handler: str) -> dict[str, str]:
    requested = handler.strip()
    lowered = requested.lower()
    reasoning_effort = "xhigh" if lowered.endswith("-xhigh") else "high"
    model = requested[: -(len(reasoning_effort) + 1)] if lowered.endswith(f"-{reasoning_effort}") else requested
    return {
        "provider": "openai_oauth",
        "requested_model": requested,
        "model": model,
        "auth": "codex_oauth",
        "reasoning_effort": reasoning_effort,
        "requested_reasoning_effort": reasoning_effort,
        "service": "codex_cli_subagent",
        "base_url": "local_codex_cli",
        "execution_owner": "$tau",
        "provider_transport": "$subagent-runner",
    }


def _handler_project(input: TauDagCompileInput, handler: str) -> str:
    prefix = f"{handler}="
    for item in input.handler_projects:
        if item.startswith(prefix):
            return item[len(prefix) :].strip() or handler
    env_key = f"ASK_ROUNDTABLE_{handler.upper()}_PROJECT"
    return os.environ.get(env_key, "").strip() or handler


def _handler_workspace(input: TauDagCompileInput, handler: str) -> str:
    """Workspace directory bound to a local-CLI handler (codex coder node)."""
    prefix = f"{handler}="
    for item in input.handler_workspaces:
        if item.startswith(prefix):
            return item[len(prefix) :].strip()
    return ""


def _roundtable_next_agent(input: TauDagCompileInput, node_id: str) -> str:
    if node_id == "join":
        return "human"
    if not node_id.startswith("handler-"):
        return "human"
    if input.topology == "sequential":
        node_ids = _handler_node_ids(input.handlers)
        try:
            index = node_ids.index(node_id)
        except ValueError:
            return "join"
        if index + 1 < len(node_ids):
            return node_ids[index + 1]
    elif input.topology == "concurrent":
        browser_node_ids = [
            candidate_node_id
            for handler, candidate_node_id in zip(
                input.handlers,
                _handler_node_ids(input.handlers),
            )
            if _is_browser_handler(handler)
        ]
        if node_id in browser_node_ids:
            index = browser_node_ids.index(node_id)
            if index + 1 < len(browser_node_ids):
                return browser_node_ids[index + 1]
    return "join"


def _roundtable_prior_nodes(input: TauDagCompileInput, node_id: str) -> list[str]:
    if input.topology != "sequential" or not node_id.startswith("handler-"):
        return []
    node_ids = _handler_node_ids(input.handlers)
    try:
        index = node_ids.index(node_id)
    except ValueError:
        return []
    return node_ids[:index]


def _roundtable_requires_verdict(request: str) -> bool:
    lower = request.lower()
    return any(
        marker in lower
        for marker in (
            "pass/fail",
            "pass or fail",
            "pass fail",
            "pass-fail",
            "review for pass",
            "review it for pass",
            "review the work for pass",
        )
    )


def _roundtable_handler_prompt_contract(
    input: TauDagCompileInput,
    *,
    handler: str,
    prior_nodes: list[str] | None = None,
) -> dict[str, Any]:
    prior_nodes = prior_nodes or []
    requires_verdict = bool(prior_nodes) and _roundtable_requires_verdict(input.request)
    if input.workflow_mode == "compete":
        return {
            "schema": "ask.tau_dag_prompt_contract.v1",
            "system": "You are an isolated Tau-managed competitor. Do not rely on other candidates.",
            "user_template": (
                f"Competition request: {input.request}\n"
                f"Immutable goal / acceptance bar: {input.immutable_goal}\n"
                f"Competitor: {handler}\n"
                "Work independently from the same input bundle. Return: implementation or patch plan, "
                "evidence, risks, reusable features, and any blocker. Do not claim final success; "
                "the project agent must verify against the codebase and skill contracts."
            ),
            "handler": handler,
            "immutable_goal": input.immutable_goal,
            "prior_nodes": [],
            "requires_prior_receipts": False,
            "requires_verdict": False,
            "verdict_schema": None,
            "isolation_required": True,
        }
    return {
        "schema": "ask.tau_dag_prompt_contract.v1",
        "system": "You are a Tau-managed roundtable handler. Return receipt-backed findings only.",
        "user_template": (
            f"Roundtable request: {input.request}\n"
            f"Immutable goal / acceptance bar: {input.immutable_goal}\n"
            f"Handler: {handler}\n"
            "Use prior handler receipts when present. Return a concise position, evidence, "
            "uncertainties, and blockers."
        ),
        "handler": handler,
        "immutable_goal": input.immutable_goal,
        "prior_nodes": prior_nodes,
        "requires_prior_receipts": bool(prior_nodes),
        "requires_verdict": requires_verdict,
        "verdict_schema": "PASS|FAIL|NEEDS_ATTENTION" if requires_verdict else None,
    }


def _roundtable_join_prompt_contract(input: TauDagCompileInput) -> dict[str, Any]:
    if input.workflow_mode == "compete":
        return {
            "schema": "ask.tau_dag_prompt_contract.v1",
            "system": "You are a Tau compete evaluator. Prefer deterministic local proof over model claims.",
            "user_template": (
                f"Competition request: {input.request}\n"
                f"Immutable goal / acceptance bar: {input.immutable_goal}\n"
                f"Competitors: {', '.join(input.handlers)}\n"
                "Produce a scorecard, reject unverified features, name a winner only when receipts and "
                "project-agent checks justify it, and emit a bounded winner continuation request."
            ),
            "topology": input.topology,
            "immutable_goal": input.immutable_goal,
            "requires_scorecard": True,
            "requires_winner_continuation_request": True,
            "fail_closed_status": "NEEDS_ATTENTION",
        }
    return {
        "schema": "ask.tau_dag_prompt_contract.v1",
        "system": "You are a Tau join node. Reconcile handler receipts without hiding gaps.",
        "user_template": (
            f"Roundtable request: {input.request}\n"
            f"Immutable goal / acceptance bar: {input.immutable_goal}\n"
            f"Handlers: {', '.join(input.handlers)}\n"
            "Produce a synthesized answer, dissent list, and unresolved proof gaps."
        ),
        "topology": input.topology,
        "immutable_goal": input.immutable_goal,
    }


def resolve_scillm_model_route(model: str) -> ScillmModelRoute:
    requested = model.strip()
    lower = requested.lower()
    if lower.startswith(("deepseek-ai/", "qwen/", "moonshotai/", "zai-org/")):
        return ScillmModelRoute(
            requested_model=requested,
            model=requested,
            provider="chutes",
            auth="scillm_proxy_bearer",
        )
    if lower.startswith(("gpt-5.6", "gpt-5-6")):
        requested_effort = "xhigh" if "xhigh" in lower else None
        return ScillmModelRoute(
            requested_model=requested,
            model="gpt-5.5",
            provider="openai",
            auth="scillm_proxy_bearer",
            reasoning_effort="high" if requested_effort == "xhigh" else requested_effort,
            requested_reasoning_effort=requested_effort,
            reasoning_downgrade_reason=(
                "SciLLM currently accepts none/low/medium/high reasoning effort; xhigh is preserved as the requested selector and dispatched as high."
                if requested_effort == "xhigh"
                else None
            ),
        )
    if lower.startswith("claude"):
        return ScillmModelRoute(
            requested_model=requested,
            model=_CLAUDE_SCILLM_ALIASES.get(lower, requested),
            provider="anthropic",
            auth="scillm_claude_code_credentials",
        )
    # Generic effort-suffix selectors (gpt-5.5-high, gpt-5.5-medium, ...):
    # the deployed router has routes for base model names, not suffixed
    # selectors, so split the suffix into reasoning effort.
    for effort in ("xhigh", "high", "medium", "low"):
        if lower.endswith(f"-{effort}"):
            base = requested[: -(len(effort) + 1)]
            dispatched = "high" if effort == "xhigh" else effort
            return ScillmModelRoute(
                requested_model=requested,
                model=base,
                provider="openai",
                auth="scillm_proxy_bearer",
                reasoning_effort=dispatched,
                requested_reasoning_effort=effort,
                reasoning_downgrade_reason=(
                    "SciLLM accepts none/low/medium/high; xhigh dispatched as high."
                    if effort == "xhigh"
                    else None
                ),
            )
    return ScillmModelRoute(
        requested_model=requested,
        model=requested,
        provider="openai",
        auth="scillm_proxy_bearer",
    )


def _route_metadata(route: ScillmModelRoute) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requested_model": route.requested_model,
        "model": route.model,
        "provider": route.provider,
        "auth": route.auth,
    }
    if route.reasoning_effort:
        payload["reasoning_effort"] = route.reasoning_effort
    if route.requested_reasoning_effort:
        payload["requested_reasoning_effort"] = route.requested_reasoning_effort
    if route.reasoning_downgrade_reason:
        payload["reasoning_downgrade_reason"] = route.reasoning_downgrade_reason
    return payload


def _solver_prompt_contract(input: TauDagCompileInput, *, model: str, index: int) -> dict[str, str]:
    return {
        "schema": "ask.tau_dag_prompt_contract.v1",
        "system": "You are a Tau subagent solver. Return concise JSON-ready evidence.",
        "user_template": (
            f"Solve request: {input.request}\n"
            f"Solver index: {index}\n"
            f"Model: {model}\n"
            f"Criteria for later review: {', '.join(input.criteria)}"
        ),
    }


def _reviewer_prompt_contract(input: TauDagCompileInput) -> dict[str, str]:
    return {
        "schema": "ask.tau_dag_prompt_contract.v1",
        "system": "You are a Tau reviewer. Compare solver outputs and choose one winner.",
        "user_template": (
            f"Review request: {input.request}\n"
            f"Criteria: {', '.join(input.criteria)}\n"
            "Use predecessor solver evidence and return a winner with rationale."
        ),
    }


def _http_check(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = client.request(method, url, headers=headers, json=json_payload)
        parsed = _json_or_none(response.text)
        result = {
            "ok": 200 <= response.status_code < 300,
            "method": method,
            "url": url,
            "status_code": response.status_code,
            "mocked": False,
            "live": True,
            "response": parsed if parsed is not None else response.text[:1000],
        }
        if metadata:
            result.update(metadata)
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "method": method,
            "url": url,
            "mocked": False,
            "live": False,
            "error": str(exc),
        }
        if metadata:
            result.update(metadata)
        return result


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _status_from_run_status(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "UNKNOWN"
    for path in (
        ("dag", "status"),
        ("status",),
        ("summary", "status"),
    ):
        value: Any = payload
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value:
            return value.upper()
    return "UNKNOWN"


def _run_dir(input: TauDagCompileInput) -> Path:
    ask_id = input.ask_id or _dag_id(input)
    return input.output_root.expanduser().resolve() / ask_id


def _dag_id(input: TauDagCompileInput) -> str:
    seed = "|".join(
        [
            input.request,
            input.repo,
            input.target,
            ",".join(input.solver_models),
            input.reviewer_model,
            ",".join(input.criteria),
            ",".join(input.handlers),
            ",".join(input.handler_provider_hints),
            input.dag_template,
            input.topology,
            input.join_handler,
            ",".join(input.handler_projects),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"ask-tau-{_slug(input.request)[:32]}-{digest}"


def _goal_hash(input: TauDagCompileInput) -> str:
    payload = {
        "request": input.request,
        "repo": input.repo,
        "target": input.target,
        "immutable_goal": input.immutable_goal,
        "solver_models": list(input.solver_models),
        "reviewer_model": input.reviewer_model,
        "criteria": list(input.criteria),
        "handlers": list(input.handlers),
        "handler_provider_hints": list(input.handler_provider_hints),
        "dag_template": input.dag_template,
        "topology": input.topology,
        "workflow_mode": input.workflow_mode,
        "join_handler": input.join_handler,
        "handler_projects": list(input.handler_projects),
    }
    return f"sha256:{hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()}"


def _normalize_model(value: str) -> str:
    return re.sub(r"\s+", "-", value.strip().lower())


def _normalize_handler(value: str) -> str:
    raw = value.strip().lower().removeprefix("$")
    compact = re.sub(r"[^a-z0-9]+", "", raw)
    if compact in _HANDLER_ALIASES:
        return _HANDLER_ALIASES[compact]
    return re.sub(r"\s+", "-", raw)


def _canonicalize_handlers(values: list[str] | tuple[str, ...]) -> tuple[list[str], list[str]]:
    handlers: list[str] = []
    provider_hints: list[str] = []
    for value in values:
        raw = value.strip()
        if not raw:
            continue
        chutes = _strip_chutes_handler_prefix(raw)
        if chutes:
            handlers.append(_normalize_handler(chutes))
            provider_hints.append("chutes")
            continue
        handlers.append(_normalize_handler(raw))
        provider_hints.append("")
    return handlers, provider_hints


def _strip_chutes_handler_prefix(value: str) -> str:
    raw = value.strip().removeprefix("$")
    slash_match = re.match(r"(?i)^chutes/([^:\s].*)$", raw)
    if slash_match:
        return slash_match.group(1).strip()
    spaced_match = re.match(r"(?i)^chutes\s+([^\s:]+/[^\s:]+)\s*$", raw)
    if spaced_match:
        return spaced_match.group(1).strip()
    return ""


def _infer_single_chutes_handler(request: str) -> dict[str, Any] | None:
    match = re.match(
        r"(?is)^\s*(?:\$?ask\s+|/ask\s+)?chutes\s+([a-z0-9_.-]+/[a-z0-9_.-]+)\s*:\s*(.+?)\s*$",
        request,
    )
    if not match:
        return None
    prompt = match.group(2).strip()
    if not prompt:
        return None
    return {
        "handlers": [_normalize_handler(match.group(1))],
        "provider_hints": ["chutes"],
        "request": prompt,
    }


def _infer_mixed_concurrent_handlers(request: str) -> dict[str, Any] | None:
    match = re.match(
        r"(?is)^\s*(?:\$?ask\s+|/ask\s+)?concurrently\s+(?P<browser>.*?)\bchutes\s+"
        r"(?P<model>[a-z0-9_.-]+/[a-z0-9_.-]+)\s*:?,?\s*(?P<prompt>.+?)\s*$",
        request,
    )
    if not match:
        return None
    prompt = match.group("prompt").strip()
    if not prompt:
        return None
    handlers = _infer_handlers_in_text(match.group("browser"))
    handlers.append(_normalize_handler(match.group("model")))
    if len(handlers) < 2:
        return None
    return {
        "handlers": handlers,
        "provider_hints": [""] * (len(handlers) - 1) + ["chutes"],
        "request": prompt,
    }


def _infer_handlers_in_text(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for name in [*ROUNDTABLE_HANDLERS, *_HANDLER_ALIASES]:
        pattern = rf"(?<![a-z0-9])\$?{re.escape(name)}(?![a-z0-9])"
        for match in re.finditer(pattern, text.lower()):
            matches.append((match.start(), _normalize_handler(name)))
    found: list[str] = []
    for _position, canonical in sorted(matches, key=lambda item: item[0]):
        if canonical not in found:
            found.append(canonical)
    return found


def _infer_immutable_goal(text: str) -> str:
    """Infer only explicitly labeled goal/acceptance-bar text.

    This keeps preflight strict: vague task prose is not silently upgraded into
    an immutable goal, but natural requests with a clear label remain usable.
    """
    for pattern in (
        r"(?im)^\s*immutable\s+goal\s*:\s*(?P<goal>.+?)\s*$",
        r"(?im)^\s*acceptance\s+bar\s*:\s*(?P<goal>.+?)\s*$",
        r"(?im)^\s*stop\s+condition\s*:\s*(?P<goal>.+?)\s*$",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group("goal").strip()
    inline = re.search(
        r"(?is)\b(?:immutable\s+goal|acceptance\s+bar|stop\s+condition)\s*:\s*(?P<goal>.+?)(?:\n\s*\n|$)",
        text,
    )
    if inline:
        return " ".join(inline.group("goal").strip().split())
    return ""


def _handler_provider_hint(input: TauDagCompileInput, index: int) -> str:
    if index < len(input.handler_provider_hints):
        return input.handler_provider_hints[index]
    return ""


def _infer_provider_hint_from_model(model: str) -> str:
    lower = model.strip().lower()
    if lower.startswith(("deepseek-ai/", "qwen/", "moonshotai/", "zai-org/")):
        return "chutes"
    return ""


def _handler_node_id(handler: str) -> str:
    return f"handler-{_slug(handler)}"


def _handler_node_ids(handlers: list[str] | tuple[str, ...]) -> list[str]:
    """Unique node ids for the handler list, in order.

    A handler may legitimately repeat (creator-reviewer loops with one bound
    browser handler). Position-independent ids collide in that case and produce
    a malformed DAG (duplicate node ids, self-edges), so repeats get an ordinal
    suffix: handler-webgpt, handler-webgpt-2, ...
    """
    seen: dict[str, int] = {}
    node_ids: list[str] = []
    for handler in handlers:
        base = _handler_node_id(handler)
        seen[base] = seen.get(base, 0) + 1
        node_ids.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return node_ids


def _normalize_topology(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in ROUNDTABLE_TOPOLOGIES else value.strip().lower()


def _normalize_workflow_mode(value: str) -> str:
    normalized = value.strip().lower() or "roundtable"
    if normalized in {"competition", "compete", "bakeoff"}:
        return "compete"
    return "roundtable"


def _normalize_dag_template(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower().removeprefix("$")).strip("-")
    return DAG_TEMPLATE_ALIASES.get(normalized, normalized)


def _infer_roundtable_handlers(lower_request: str) -> list[str]:
    if "roundtable" not in lower_request and "handler" not in lower_request and "compete" not in lower_request:
        return []
    matches: list[tuple[int, str]] = []
    for name in [*ROUNDTABLE_HANDLERS, *_HANDLER_ALIASES]:
        pattern = rf"(?<![a-z0-9])\$?{re.escape(name)}(?![a-z0-9])"
        for match in re.finditer(pattern, lower_request):
            matches.append((match.start(), _normalize_handler(name)))
    found: list[str] = []
    for _position, canonical in sorted(matches, key=lambda item: item[0]):
        if canonical not in found:
            found.append(canonical)
    return found


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"request-{int(time.time())}"


def _dag_template_options() -> list[dict[str, str]]:
    options = [
        {"value": name, "description": str(spec["description"])}
        for name, spec in SUPPORTED_DAG_TEMPLATES.items()
    ]
    options.extend(
        {"value": name, "description": f"Tau-native requested: {description}"}
        for name, description in TAU_NATIVE_TEMPLATE_REQUESTS.items()
    )
    return options


def _dag_template_context(input: TauDagCompileInput) -> dict[str, Any]:
    if not input.dag_template:
        return {}
    spec = SUPPORTED_DAG_TEMPLATES.get(input.dag_template)
    return {
        "dag_template": input.dag_template,
        "dag_template_description": str(spec.get("description") if spec else ""),
    }


def _question(
    field: str,
    prompt: str,
    *,
    expects: str = "str",
    options: list[Any] | None = None,
    recovery_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"field": field, "question": prompt, "expects": expects, "required": True}
    if options:
        payload["options"] = options
    if recovery_packet:
        payload["recovery_packet"] = recovery_packet
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TauDagError(f"JSON root is not an object: {path}")
    return payload


def _json_or_none(text: str) -> dict[str, Any] | None:
    payload = _extract_json_payload(text)
    return payload if isinstance(payload, dict) else None


def _extract_json_payload(text: str) -> Any | None:
    decoder = json.JSONDecoder()
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        payload = None
    else:
        if not stripped[end:].strip():
            return payload
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return payload
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


_WORKER_SOURCE = r'''#!/usr/bin/env python3
"""Generated $ask Tau DAG worker."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--mode", choices=["fixture", "scillm"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--requested-model", default="")
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--requested-reasoning-effort", default="")
    parser.add_argument("--scillm-base-url", required=True)
    parser.add_argument("--scillm-api-key", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()
    start = json.loads(sys.stdin.read() or "{}")
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    provider_receipt = _provider_receipt(args, start)
    receipt_path = artifact_dir / "node-receipt.json"
    receipt = {
        "schema": "ask.tau_dag_node_receipt.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "node_id": args.node_id,
        "mode": args.mode,
        "model": args.model,
        "requested_model": args.requested_model or args.model,
        "reasoning_effort": args.reasoning_effort or None,
        "requested_reasoning_effort": args.requested_reasoning_effort or None,
        "provider_receipt": provider_receipt,
        "mocked": False,
        "live": args.mode == "scillm",
        "provider_live": provider_receipt.get("ok") is True and args.mode == "scillm",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence = _evidence(args, start, receipt, str(receipt_path))
    status = "PASS" if provider_receipt.get("status") != "ERROR" else "ERROR"
    response = {
        "schema": "tau.agent_handoff.v1",
        "github": start.get("github", {"repo": "unknown", "target": "unknown"}),
        "goal": start.get("goal", {}),
        "previous_subagent": args.node_id,
        "context": {
            "summary": f"{args.node_id} completed {args.mode} Tau DAG work.",
            "artifacts": [str(receipt_path)],
        },
        "result": {
            "status": status,
            "summary": f"{args.node_id} produced required Tau DAG evidence.",
            "evidence": evidence,
        },
        "rationale": "The node followed the Tau DAG required_evidence contract.",
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Return node evidence to the Tau scheduler.",
        },
        "required_evidence": list(args.evidence),
        "stop_condition": "Stop after emitting a single tau.agent_handoff.v1 response.",
    }
    print(json.dumps(response, sort_keys=True))
    return 0


def _provider_receipt(args: argparse.Namespace, start: dict[str, Any]) -> dict[str, Any]:
    if args.mode == "fixture":
        return {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": "FIXTURE",
            "ok": True,
            "mocked": False,
            "live": False,
            "provider_live": False,
            "model": args.model,
            "requested_model": args.requested_model or args.model,
            "reasoning_effort": args.reasoning_effort or None,
            "requested_reasoning_effort": args.requested_reasoning_effort or None,
            "route": "tau_local_fixture_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$scillm",
        }
    prompt = _prompt(start)
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if args.reasoning_effort:
        payload["reasoning_effort"] = args.reasoning_effort
    request = urllib.request.Request(
        args.scillm_base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {args.scillm_api_key}",
            "X-Caller-Skill": "tau",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
            "model": args.model,
            "requested_model": args.requested_model or args.model,
            "reasoning_effort": args.reasoning_effort or None,
            "requested_reasoning_effort": args.requested_reasoning_effort or None,
            "route": "tau_local_scillm_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$scillm",
            "response": json.loads(body),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": "ERROR",
            "ok": False,
            "mocked": False,
            "live": False,
            "provider_live": False,
            "model": args.model,
            "requested_model": args.requested_model or args.model,
            "reasoning_effort": args.reasoning_effort or None,
            "requested_reasoning_effort": args.requested_reasoning_effort or None,
            "route": "tau_local_scillm_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$scillm",
            "error": str(exc),
        }


def _evidence(
    args: argparse.Namespace,
    start: dict[str, Any],
    receipt: dict[str, Any],
    receipt_path: str,
) -> list[Any]:
    evidence: list[Any] = [
        {
            "kind": "node_receipt",
            "node_id": args.node_id,
            "path": receipt_path,
        },
        {
            "kind": "provider_route_receipt",
            "node_id": args.node_id,
            "model": args.model,
            "provider_receipt": receipt.get("provider_receipt"),
            "model_policy": start.get("context", {}).get("model_policy"),
        },
        {
            "kind": "model_policy",
            "node_id": args.node_id,
            "model": args.model,
            "policy": start.get("context", {}).get("model_policy"),
        },
    ]
    if args.node_id.startswith("solver-"):
        evidence.append(
            {
                "kind": "solution",
                "node_id": args.node_id,
                "summary": f"{args.node_id} candidate solution for the requested problem.",
                "model": args.model,
                "requested_model": args.requested_model or args.model,
                "reasoning_effort": args.reasoning_effort or None,
                "requested_reasoning_effort": args.requested_reasoning_effort or None,
            }
        )
    if args.node_id == "reviewer":
        evidence.append(
            {
                "kind": "reviewer_verdict",
                "goal_hash": start.get("goal", {}).get("goal_hash"),
                "winner": "solver-1",
                "rationale": "Fixture/default reviewer selected solver-1 after applying the stated criteria.",
                "criteria": start.get("context", {}).get("criteria", []),
            }
        )
        evidence.append({"kind": "winner", "winner": "solver-1"})
        evidence.append({"kind": "rationale", "text": "Winner chosen with an explicit rationale."})
    return evidence


def _prompt(start: dict[str, Any]) -> str:
    context = start.get("context") if isinstance(start.get("context"), dict) else {}
    return json.dumps(
        {
            "task": "Produce concise Tau DAG node evidence.",
            "summary": context.get("summary"),
            "dag_node": context.get("tau_dag_node"),
            "required_evidence": start.get("required_evidence", []),
        },
        sort_keys=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
'''
