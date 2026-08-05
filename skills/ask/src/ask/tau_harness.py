"""Tau-native execution boundary for /ask model calls (agent-skills#1220).

Every /ask production model/subagent call must enter Tau first. This module is
the shared seam: it compiles a single-agent ``tau.generic_dag_spec.v1`` and
executes it through Tau's canonical compiler + scheduler on the tau#310
``tau_native_agent_loop`` adapter, with the model addressed as a ``profile:``
SciLLM transport (scillm#27/28). /ask never talks to a provider directly.

``run_single_tau_agent`` accepts an injected ``execute_node`` for
deterministic tests; the default executor is the live SciLLM-backed Tau-native
loop, the same path proven by ``scripts/ask_tau_native_canary.py``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_TAU_REPO = Path.home() / "workspace" / "experiments" / "tau"
DEFAULT_SCILLM_ENV = Path.home() / "workspace" / "experiments" / "scillm" / ".env"
_DEV_FALLBACK_KEY = "sk-dev-proxy-123"


class ScillmAuthUnresolved(RuntimeError):
    """No candidate key was accepted by the live proxy; names the chain tried."""


def resolve_scillm_key(base_url: str | None = None) -> str:
    """Resolve the currently-valid SciLLM key deterministically (issue #1223).

    Chain: SCILLM_MASTER_KEY env -> scillm repo .env -> dev fallback. Each
    candidate is verified with one live auth probe; the first accepted key
    wins. The deployed proxy's accepted key has flip-flopped across redeploys
    (scillm#32), so a static default silently turns every live run into a
    BLOCKED node — this resolver fails loudly instead.
    """
    url = (base_url or os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")).rstrip("/")
    candidates: list[tuple[str, str]] = []
    env_key = os.environ.get("SCILLM_MASTER_KEY", "").strip()
    if env_key:
        candidates.append(("env:SCILLM_MASTER_KEY", env_key))
    env_path = Path(os.environ.get("SCILLM_ENV_FILE", str(DEFAULT_SCILLM_ENV)))
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SCILLM_MASTER_KEY=") or line.startswith("LITELLM_MASTER_KEY="):
                value = line.split("=", 1)[1].strip()
                if value and all(value != c[1] for c in candidates):
                    candidates.append((f"file:{env_path.name}:{line.split('=', 1)[0]}", value))
    if all(_DEV_FALLBACK_KEY != c[1] for c in candidates):
        candidates.append(("dev-fallback", _DEV_FALLBACK_KEY))

    import httpx

    tried: list[str] = []
    for source, key in candidates:
        tried.append(source)
        try:
            resp = httpx.get(
                f"{url}/v1/scillm/profiles",
                headers={"Authorization": f"Bearer {key}", "X-Caller-Skill": "ask"},
                timeout=10.0,
            )
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            return key
    raise ScillmAuthUnresolved(
        f"no candidate key accepted by {url} (tried: {', '.join(tried)}); "
        "set SCILLM_MASTER_KEY or fix the proxy key source (scillm#32)"
    )


class TauHarnessUnavailable(RuntimeError):
    """Raised when the Tau runtime cannot be imported or reached."""


def _tau_src() -> Path:
    root = Path(os.environ.get("TAU_REPO", str(DEFAULT_TAU_REPO)))
    src = root / "src"
    if not src.is_dir():
        raise TauHarnessUnavailable(f"tau src not found at {src}; set TAU_REPO")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src


def build_single_agent_spec(
    *,
    prompt: str,
    profile_id: str,
    run_id: str,
    run_dir: Path,
    role: str = "backend",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """One-node tau.generic_dag_spec.v1 for a bounded, tool-less model turn."""
    return {
        "schema": "tau.generic_dag_spec.v1",
        "run_id": run_id,
        "run_dir": str(run_dir / "run"),
        "nodes": [
            {
                "node_id": "agent",
                "role": role,
                "tau_agent": {
                    "prompt": prompt,
                    "role": role,
                    "model": f"profile:{profile_id}",
                    "allowed_paths": [],
                    "required_evidence": [],
                },
                "depends_on": [],
                "accepted_context_from": [],
                "receipt_path": str(run_dir / "receipts" / "agent.json"),
                "timeout_seconds": timeout_seconds,
                "max_attempts": 1,
            }
        ],
    }


def run_single_tau_agent(
    *,
    prompt: str,
    profile_id: str,
    purpose: str,
    role: str = "backend",
    timeout_seconds: int = 120,
    execute_node: Callable[..., dict[str, Any]] | None = None,
    run_root: Path | None = None,
    source: str | None = None,
    grounding_threshold: float | None = None,
    grounding_retries: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one bounded model turn as a Tau-native agent node.

    Returns ``{"final_text": str, "run_id": str, "run_dir": str,
    "scheduler_status": str, "settlement": dict}``. Raises
    TauHarnessUnavailable when Tau cannot be loaded — callers decide their own
    degradation; this seam never silently falls back to a direct provider call.
    """
    _tau_src()
    try:
        from tau_coding.dag_runtime.compiler import compile_generic_dag_plan
        from tau_coding.dag_runtime.model import canonical_sha256
        from tau_coding.dag_runtime.scheduler import run_dag_plan
    except Exception as exc:  # pragma: no cover - import environment failure
        raise TauHarnessUnavailable(f"tau runtime import failed: {exc}") from exc

    run_id = f"ask-{purpose}-{int(time.time() * 1000)}"
    base = run_root or (Path(os.environ.get("ASK_TAU_RUN_ROOT", "")) if os.environ.get("ASK_TAU_RUN_ROOT") else Path.home() / ".cache" / "ask-tau-runs")
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spec = build_single_agent_spec(
        prompt=prompt,
        profile_id=profile_id,
        run_id=run_id,
        run_dir=run_dir,
        role=role,
        timeout_seconds=timeout_seconds,
    )
    spec_path = run_dir / "dag-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    plan = compile_generic_dag_plan(spec, source_path=spec_path)
    goal_hash = canonical_sha256({"purpose": purpose, "prompt": prompt})

    if execute_node is None:
        execute_node = _live_executor(
            profile_id=profile_id,
            run_id=run_id,
            goal_hash=goal_hash,
            source=source,
            grounding_threshold=grounding_threshold,
            grounding_retries=grounding_retries,
            response_format=response_format,
        )

    result = run_dag_plan(plan, execute_node=execute_node)
    by_id = {item["node_id"]: item for item in result.node_results}
    accepted = by_id.get("agent", {}).get("accepted_output") or {}
    outcome = {
        "schema": "ask.tau_harness_outcome.v1",
        "final_text": str(accepted.get("final_text", "")),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "purpose": purpose,
        "profile_id": profile_id,
        "goal_hash": goal_hash,
        "scheduler_status": result.status,
        "scheduler_verdict": result.verdict,
        "settlement": accepted.get("settlement", {}),
    }
    (run_dir / "outcome.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    return outcome


def _live_executor(
    *,
    profile_id: str,
    run_id: str,
    goal_hash: str,
    required_capabilities: tuple[str, ...] = ("streaming",),
    source: str | None = None,
    grounding_threshold: float | None = None,
    grounding_retries: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> Callable[..., dict[str, Any]]:
    from tau_ai.scillm_transport import ScillmTransportProvider
    from tau_coding.dag_runtime.agent_node_adapter import (
        TAU_NATIVE_ADAPTER_KIND,
        execute_tau_agent_node,
    )

    base_url = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")
    api_key = resolve_scillm_key(base_url)

    def provider_factory(node: Any, config: Any) -> Any:
        return ScillmTransportProvider(
            base_url=base_url,
            api_key=api_key,
            profile_id=profile_id,
            correlation={
                "tau_run_id": run_id,
                "node_id": node.node_id,
                "attempt": 1,
                "goal_hash": goal_hash,
            },
            # Tool-less single turns must not demand tool_calling: small local
            # profiles (e.g. ollama local-text) fail the capability gate and
            # surface as empty_terminal_output. Tools imply the richer set.
            required_capabilities=list(required_capabilities),
            timeout_seconds=110,
            # tau#311: grounding/response_format carried on the Tau transport.
            source=source,
            grounding_threshold=grounding_threshold,
            grounding_retries=grounding_retries,
            response_format=response_format,
        )

    def execute(plan_node: Any, accepted_inputs: Any, execution: Any) -> dict[str, Any]:
        assert plan_node.adapter_kind == TAU_NATIVE_ADAPTER_KIND
        return execute_tau_agent_node(
            plan_node,
            accepted_inputs,
            execution,
            goal_hash=goal_hash,
            provider_factory=provider_factory,
            tools_factory=lambda node, config: [],
        )

    return execute


def run_chat_via_tau(
    *,
    user_prompt: str,
    system_prompt: str = "",
    profile_id: str,
    purpose: str,
    timeout_seconds: int = 120,
    execute_node: Callable[..., dict[str, Any]] | None = None,
) -> str | None:
    """One system+user chat turn as a Tau-native node; returns final text or None.

    The migration shim for direct chat/completions call sites: same
    text-in/text-out shape, but the turn enters Tau first and the model is
    profile-owned. Returns None on any failure so callers keep their existing
    degradation behavior; it never falls back to a direct provider call.
    """
    prompt = user_prompt if not system_prompt else f"{system_prompt}\n\n---\n\n{user_prompt}"
    try:
        outcome = run_single_tau_agent(
            prompt=prompt,
            profile_id=profile_id,
            purpose=purpose,
            timeout_seconds=timeout_seconds,
            execute_node=execute_node,
        )
    except TauHarnessUnavailable:
        return None
    if outcome["scheduler_status"] != "PASS":
        return None
    text = outcome["final_text"].strip()
    return text or None


def run_plan_spec(
    spec: dict[str, Any],
    *,
    run_dir: Path,
    goal_hash: str | None = None,
    execute_node: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a compiled multi-node tau.generic_dag_spec.v1 through Tau.

    Per-node transport profiles come from each node's ``profile:`` model.
    Returns a summary with per-node status/settlement/final_text and writes
    ``execution-summary.json`` into ``run_dir``. Tau owns scheduling, joins,
    and settlement; /ask only submits and reads back.
    """
    _tau_src()
    from tau_coding.dag_runtime.compiler import compile_generic_dag_plan
    from tau_coding.dag_runtime.model import canonical_sha256
    from tau_coding.dag_runtime.scheduler import run_dag_plan

    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path = run_dir / "dag-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    plan = compile_generic_dag_plan(spec, source_path=spec_path)
    resolved_goal_hash = goal_hash or canonical_sha256(
        {"run_id": spec.get("run_id"), "nodes": [n["node_id"] for n in spec["nodes"]]}
    )
    profile_by_node = {
        n["node_id"]: str(n["tau_agent"]["model"]).removeprefix("profile:")
        for n in spec["nodes"]
        if isinstance(n.get("tau_agent"), dict)
    }

    if execute_node is None:
        executors = {
            node_id: _live_executor(
                profile_id=profile, run_id=str(spec.get("run_id")), goal_hash=resolved_goal_hash
            )
            for node_id, profile in profile_by_node.items()
        }

        def execute_node(plan_node: Any, accepted_inputs: Any, execution: Any) -> dict[str, Any]:
            return executors[plan_node.node_id](plan_node, accepted_inputs, execution)

    result = run_dag_plan(plan, execute_node=execute_node)
    by_id = {item["node_id"]: item for item in result.node_results}
    nodes = {}
    for node_id in profile_by_node:
        accepted = by_id.get(node_id, {}).get("accepted_output") or {}
        nodes[node_id] = {
            "profile": profile_by_node[node_id],
            "status": by_id.get(node_id, {}).get("status"),
            "settlement": (accepted.get("settlement") or {}).get("state"),
            "final_text": str(accepted.get("final_text", ""))[:2000],
        }
    summary = {
        "schema": "ask.tau_plan_execution_summary.v1",
        "run_id": spec.get("run_id"),
        "goal_hash": resolved_goal_hash,
        "scheduler_status": result.status,
        "scheduler_verdict": result.verdict,
        "completed_node_ids": sorted(result.completed_node_ids),
        "nodes": nodes,
        "run_dir": str(run_dir),
    }
    (run_dir / "execution-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
