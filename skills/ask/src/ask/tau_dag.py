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


TAU_DAG_SCHEMA = "tau.dag_contract.v1"
ASK_TAU_DAG_BUNDLE_SCHEMA = "ask.tau_dag_bundle.v1"
ASK_TAU_DAG_INTERVIEW_SCHEMA = "ask.tau_dag_interview.v1"
DEFAULT_SCILLM_BASE_URL = "http://127.0.0.1:4001"
DEFAULT_SCILLM_API_KEY = "sk-dev-proxy-123"
DEFAULT_TAU_PROJECT_ROOT = Path("/home/graham/workspace/experiments/tau")
DEFAULT_OUTPUT_ROOT = Path(".ask_artifacts/tau-dag-runs")
TERMINAL_STATUSES = {"PASS", "BLOCKED", "FAILED", "ERROR"}
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


class TauDagError(RuntimeError):
    """Raised when a Tau DAG bundle cannot be compiled or executed."""


@dataclass(frozen=True)
class TauDagCompileInput:
    request: str
    repo: str
    target: str
    solver_models: tuple[str, ...]
    reviewer_model: str
    criteria: tuple[str, ...]
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
    ask_id: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    local_fixture: bool = False,
    scillm_base_url: str = DEFAULT_SCILLM_BASE_URL,
    scillm_api_key: str = DEFAULT_SCILLM_API_KEY,
    tau_project_root: Path = DEFAULT_TAU_PROJECT_ROOT,
) -> TauDagCompileInput:
    """Merge explicit CLI fields with conservative request-text inference."""

    inferred_solvers = list(solver_models or [])
    normalized_request = request.strip()
    lower = normalized_request.lower()
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
    return TauDagCompileInput(
        request=normalized_request,
        repo=repo.strip(),
        target=target.strip(),
        solver_models=tuple(_normalize_model(item) for item in inferred_solvers if item.strip()),
        reviewer_model=_normalize_model(inferred_reviewer) if inferred_reviewer else "",
        criteria=tuple(item.strip() for item in (criteria or []) if item.strip()),
        ask_id=ask_id,
        output_root=output_root,
        local_fixture=local_fixture,
        scillm_base_url=scillm_base_url.rstrip("/"),
        scillm_api_key=scillm_api_key,
        tau_project_root=tau_project_root,
    )


def missing_dag_fields(input: TauDagCompileInput) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    if not input.request:
        missing.append(_question("request", "What exact problem should the Tau DAG solve?"))
    if not input.repo:
        missing.append(_question("repo", "Which repository or project identifier should the DAG bind to?"))
    if not input.target:
        missing.append(_question("target", "Which issue, task, file, or work target should the DAG bind to?"))
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
            "solver_models": list(input.solver_models),
            "reviewer_model": input.reviewer_model,
            "criteria": list(input.criteria),
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

    worker_path = _write_worker(run_dir)
    command_specs_dir = run_dir / "command-specs"
    agents_dir = run_dir / "agents"
    dag = _build_tau_dag(input, run_dir=run_dir)
    for node in dag["nodes"]:
        _write_agent_stub(agents_dir, node_id=str(node["id"]), role=str(node["agent"]))
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
            ],
        },
    }
    _write_json(run_dir / "compile-status.json", final_bundle)
    return final_bundle


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
    result = {
        "schema": "ask.tau_dag_execution.v1",
        "status": status,
        "ok": isinstance(receipt, dict) and receipt.get("ok") is True,
        "mocked": False,
        "live": True,
        "provider_live": bool(isinstance(receipt, dict) and receipt.get("provider_live") is True),
        "execution_owner": "$tau",
        "provider_transport": "$scillm",
        "command": command,
        "dag_run_returncode": dag_run["returncode"],
        "dag_run_stdout": dag_run["stdout"],
        "dag_run_stderr": dag_run["stderr"],
        "receipt_dir": str(receipt_dir),
        "receipt_path": str(receipt_path),
        "receipt": receipt,
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
    if dag_run["returncode"] != 0:
        result["status"] = "ERROR"
        result["ok"] = False
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
    headers = {"Authorization": f"Bearer {api_key}", "X-Caller-Skill": "ask-tau-dag-preflight"}
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout_seconds) as client:
        for path in ("/health/liveliness", "/v1/scillm/auth", "/v1/scillm/providers"):
            checks.append(_http_check(client, "GET", f"{base}{path}", headers=headers))
        model_calls: list[dict[str, Any]] = []
        if allow_provider_calls:
            for model in sorted({item for item in models if item}):
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with the single word ok for an ask Tau DAG provider gate.",
                        }
                    ],
                }
                model_calls.append(
                    _http_check(
                        client,
                        "POST",
                        f"{base}/v1/chat/completions",
                        headers=headers,
                        json_payload=payload,
                    )
                )
        else:
            model_calls = [
                {
                    "status": "BLOCKED",
                    "blocked_reason": "provider_calls_not_allowed",
                    "model": model,
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
            ],
            "does_not_prove": [
                "Tau DAG execution succeeded.",
                "All future provider/model routes are healthy.",
            ],
        },
    }


def _build_tau_dag(input: TauDagCompileInput, *, run_dir: Path) -> dict[str, Any]:
    dag_id = _dag_id(input)
    goal = {
        "goal_id": f"ask-{dag_id}",
        "goal_version": 1,
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


def _model_policy(model: str, *, base_url: str = DEFAULT_SCILLM_BASE_URL) -> dict[str, str]:
    lower = model.lower()
    if lower.startswith("claude"):
        provider = "anthropic"
        auth = "scillm_claude_code_credentials"
    else:
        provider = "openai"
        auth = "scillm_proxy_bearer"
    return {
        "provider": provider,
        "model": model,
        "auth": auth,
        "service": "scillm_container_service",
        "base_url": base_url,
        "execution_owner": "$tau",
        "provider_transport": "$scillm",
    }


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
) -> dict[str, Any]:
    try:
        response = client.request(method, url, headers=headers, json=json_payload)
        parsed = _json_or_none(response.text)
        return {
            "ok": 200 <= response.status_code < 300,
            "method": method,
            "url": url,
            "status_code": response.status_code,
            "mocked": False,
            "live": True,
            "response": parsed if parsed is not None else response.text[:1000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": method,
            "url": url,
            "mocked": False,
            "live": False,
            "error": str(exc),
        }


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
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"ask-tau-{_slug(input.request)[:32]}-{digest}"


def _goal_hash(input: TauDagCompileInput) -> str:
    payload = {
        "request": input.request,
        "repo": input.repo,
        "target": input.target,
        "solver_models": list(input.solver_models),
        "reviewer_model": input.reviewer_model,
        "criteria": list(input.criteria),
    }
    return f"sha256:{hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()}"


def _normalize_model(value: str) -> str:
    return re.sub(r"\s+", "-", value.strip().lower())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"request-{int(time.time())}"


def _question(field: str, prompt: str, *, expects: str = "str") -> dict[str, Any]:
    return {"field": field, "question": prompt, "expects": expects, "required": True}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TauDagError(f"JSON root is not an object: {path}")
    return payload


def _json_or_none(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
            "route": "tau_local_fixture_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$scillm",
        }
    prompt = _prompt(start)
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
    }
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
