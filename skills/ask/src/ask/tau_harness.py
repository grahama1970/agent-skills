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
import signal
import subprocess
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


def _run_plan_cli(spec: dict[str, Any], *, run_dir: Path, goal_hash: str | None,
                  watch: bool, on_viewer_url: Callable[[str], None] | None,
                  progress: Callable[[str], None] | None) -> dict[str, Any]:
    """Production plan execution uses the same native boundary as `tau run`."""
    declared_goal = (spec.get("goal") or {}).get("goal_hash")
    if not declared_goal or (goal_hash is not None and goal_hash != declared_goal):
        raise ValueError("native plan requires its unchanged human-goal hash")
    for node in spec["nodes"]:
        config = node.get("tau_agent") or {}
        if "tool_effect_receipt" in config.get("required_evidence", []) and not config.get("allowed_tools"):
            raise ValueError(f"node {node['node_id']} requires explicit allowed_tools before native CLI execution")
    native_dir = Path(spec["run_dir"]).resolve()
    if native_dir.exists():
        raise ValueError("native run directory already exists; resume it through Tau instead of overwriting it")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "dag-spec.json"
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    command = ["uv", "run", "--project", str(DEFAULT_TAU_REPO), "tau", "run", str(path), "--no-resume"]
    viewer: subprocess.Popen | None = None
    viewer_info: dict[str, Any] = {}
    last_state = None
    with (run_dir / "tau-cli.stdout.json").open("w") as stdout, (run_dir / "tau-cli.stderr.log").open("w") as stderr:
        proc = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while proc.poll() is None:
                try:
                    state = json.loads((native_dir / "current-state.json").read_text())
                    selected = (state.get("status"), state.get("active_node_id"))
                    if progress and selected != last_state:
                        progress(f"Tau {selected[0]}: {selected[1] or 'scheduler'}; {native_dir}")
                    last_state = selected
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                if watch and viewer is None and (native_dir / "current-state.json").exists():
                    viewer_command = ["uv", "run", "--project", str(DEFAULT_TAU_REPO), "tau", "dag-view", "--run-dir", str(native_dir)]
                    with (run_dir / "viewer.stdout.json").open("w") as view_out, (run_dir / "viewer.stderr.log").open("w") as view_err:
                        viewer = subprocess.Popen(viewer_command, stdout=view_out, stderr=view_err, start_new_session=True)
                    viewer_info = {"source": "native Tau CLI", "command": viewer_command}
                if viewer is not None and not viewer_info.get("url"):
                    try:
                        data = json.loads((run_dir / "viewer.stdout.json").read_text())
                        if data.get("url"):
                            viewer_info["url"] = data["url"]
                            if on_viewer_url:
                                on_viewer_url(data["url"])
                    except (FileNotFoundError, json.JSONDecodeError):
                        pass
                    if viewer.poll() is not None:
                        viewer_info["error"] = (run_dir / "viewer.stderr.log").read_text()[-1000:]
                time.sleep(0.2)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGINT)
                proc.wait(timeout=30)
            if viewer is not None and viewer.poll() is None:
                os.killpg(viewer.pid, signal.SIGINT)
                viewer.wait(timeout=10)
                viewer_info["closed_after_run"] = True
    receipt_path = native_dir / "run-receipt.json"
    if not receipt_path.is_file():
        detail = (run_dir / "tau-cli.stderr.log").read_text(errors="replace")[-2000:]
        raise ValueError(f"Tau CLI exited {proc.returncode} without a receipt: {detail}")
    receipt = json.loads(receipt_path.read_text())
    nodes = {}
    for node in receipt["nodes"]:
        accepted = node.get("accepted_output") or {}
        nodes[node["node_id"]] = {
            "profile": (node.get("transport_profile") or {}).get("profile_id"),
            "status": node.get("status"), "verdict": node.get("verdict"),
            "settlement": (accepted.get("settlement") or {}).get("state"),
            "final_text": str(accepted.get("final_text", "")),
            "receipt_path": node.get("receipt_path"),
        }
    if proc.returncode != 0 and receipt.get("status") == "PASS":
        raise ValueError("Tau CLI exit disagrees with its success receipt")
    summary = {"schema": "ask.tau_plan_execution_summary.v1", "run_id": spec["run_id"],
               "goal_hash": declared_goal, "scheduler_status": receipt["status"],
               "scheduler_verdict": receipt["verdict"],
               "completed_node_ids": [n["node_id"] for n in receipt["nodes"] if n.get("status") == "PASS"],
               "nodes": nodes, "run_dir": str(run_dir),
               "native_run_dir": str(native_dir), "native_receipt": str(receipt_path),
               "command": command, "exit_code": proc.returncode, "viewer": viewer_info or None,
               "proof_boundary": "Native execution/settlement only; node completion is not project acceptance."}
    (run_dir / "execution-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_plan_spec(
    spec: dict[str, Any],
    *,
    run_dir: Path,
    goal_hash: str | None = None,
    execute_node: Callable[..., dict[str, Any]] | None = None,
    watch: bool = False,
    on_viewer_url: Callable[[str], None] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute a compiled multi-node tau.generic_dag_spec.v1 through Tau.

    Per-node transport profiles come from each node's ``profile:`` model.
    Returns a summary with per-node status/settlement/final_text and writes
    ``execution-summary.json`` into ``run_dir``. Tau owns scheduling, joins,
    and settlement; /ask only submits and reads back.
    """
    if execute_node is None:
        return _run_plan_cli(spec, run_dir=run_dir, goal_hash=goal_hash, watch=watch,
                             on_viewer_url=on_viewer_url, progress=progress)
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

    viewer_info: dict[str, Any] = {}
    node_started_at: dict[str, float] = {}

    def _event_sink(event: dict[str, Any]) -> None:
        if progress is None:
            return
        kind = event.get("event")
        nid = event.get("node_id")
        now = time.strftime("%H:%M:%S")
        if kind == "node_started" and nid:
            node_started_at[str(nid)] = time.monotonic()
            node = next((n for n in spec["nodes"] if n["node_id"] == nid), {})
            profile = str(node.get("tau_agent", {}).get("model", "")).removeprefix("profile:")
            progress(f"[{now}] > {nid} ({node.get('role', '?')} :: {profile}) running")
        elif kind == "node_completed" and nid:
            took = time.monotonic() - node_started_at.get(str(nid), time.monotonic())
            progress(f"[{now}] + {nid} completed in {took:.1f}s")
        elif kind in ("node_attempt_failed", "node_blocked", "node_retry_scheduled") and nid:
            progress(f"[{now}] ! {nid} {kind.removeprefix('node_')}")
        elif kind == "scheduler_finished":
            progress(f"[{now}] scheduler finished: {event.get('status', '')}")
    if watch:
        from tau_coding.dag_runtime.watched_run import run_dag_plan_watched

        def _capture_url(url: str) -> None:
            viewer_info["url"] = url
            # Probe at t0 so the receipt proves the page served mid-run.
            try:
                import httpx

                viewer_info["served_at_t0"] = "Tau Live DAG" in httpx.get(url, timeout=5.0).text
            except Exception as exc:  # pragma: no cover - best-effort probe
                viewer_info["served_at_t0"] = False
                viewer_info["probe_error"] = str(exc)[:200]
            if on_viewer_url is not None:
                on_viewer_url(url)

        watched = run_dag_plan_watched(
            plan,
            execute_node=execute_node,
            run_dir=run_dir,
            watch=True,
            on_viewer_url=_capture_url,
            event_sink=_event_sink,
        )
        result = watched.result
    else:
        result = run_dag_plan(plan, execute_node=execute_node, event_sink=_event_sink)
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
        "viewer": viewer_info or None,
    }
    (run_dir / "execution-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def fetch_profile_registry(base_url: str | None = None) -> list[dict[str, Any]]:
    """Live read of the scillm transport-profile registry (scillm#33).

    Preview-time readiness query only — profile selection authority for
    execution remains with Tau (tau#308).
    """
    import httpx

    url = (base_url or os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")).rstrip("/")
    key = resolve_scillm_key(url)
    resp = httpx.get(
        f"{url}/v1/scillm/profiles",
        headers={"Authorization": f"Bearer {key}", "X-Caller-Skill": "ask"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return list(resp.json().get("profiles", []))
