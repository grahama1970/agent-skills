"""Live #1220 canary: natural /ask request → plan → frozen Tau DAG → live agents.

Chain proven here, end to end and non-mocked:

1. a natural-language request renders an editable ``ask.project_plan.v1``;
2. /ask compiles it into a frozen ``tau.generic_dag_spec.v1`` with two
   heterogeneous ``profile:`` SciLLM transports (tau#308/scillm#27 ids);
3. Tau's canonical compiler + scheduler (tau#310 ``tau_native_agent_loop``)
   executes both agent nodes with a real tool effect;
4. settlement receipts and the workspace artifact are read back from disk.

/ask owns steps 1–2; Tau owns 3–4. Refuses to run without ``--live``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ASK_ROOT = Path(__file__).resolve().parent.parent
TAU_ROOT = Path(os.environ.get("TAU_REPO", str(Path.home() / "workspace/experiments/tau")))
sys.path.insert(0, str(ASK_ROOT / "src"))
sys.path.insert(0, str(TAU_ROOT / "src"))

from ask.project_plan import SCHEMA_ID  # noqa: E402
from ask.project_plan_to_tau import (  # noqa: E402
    compile_plan_to_tau_spec,
    heterogeneous_profile_count,
)

CONTENT = "ask-to-tau native canary for agent-skills#1220"


def render_plan(request: str) -> dict[str, Any]:
    """Render the natural request into an editable ask.project_plan.v1 proposal."""
    return {
        "schema": SCHEMA_ID,
        "goal": request,
        "target": {"repo": "grahama1970/agent-skills"},
        "deliverables": [
            {
                "name": "canary artifact",
                "acceptance_criteria": [
                    "worker writes proof.txt via a Tau tool effect",
                    "independent reviewer reads it back and issues VERDICT: PASS",
                ],
            }
        ],
        "workstreams": [
            {
                "id": "worker",
                "role": "backend",
                "prompt": (
                    "Call write_file exactly once with path='proof.txt' and "
                    f"content='{CONTENT}'. Then state what you wrote."
                ),
                "allowed_paths": ["proof.txt"],
            },
            {
                "id": "reviewer",
                "role": "independent_reviewer",
                "prompt": (
                    "Call read_file with path='proof.txt'. Answer exactly "
                    f"'VERDICT: PASS' if its content is '{CONTENT}', else "
                    "'VERDICT: FAIL' plus the reason."
                ),
                "allowed_paths": ["proof.txt"],
                "depends_on": ["worker"],
            },
        ],
        "team": {"preset": "fullstack-premium"},
        "execution": {"topology": "sequential", "max_concurrency": 1, "max_retries": 0},
        "unresolved": [],
    }


def main() -> int:
    from tau_agent.tools import AgentTool, AgentToolResult
    from tau_ai.scillm_transport import ScillmTransportProvider
    from tau_coding.dag_runtime.agent_node_adapter import (
        TAU_NATIVE_ADAPTER_KIND,
        execute_tau_agent_node,
    )
    from tau_coding.dag_runtime.compiler import compile_generic_dag_plan
    from tau_coding.dag_runtime.model import canonical_sha256
    from tau_coding.dag_runtime.scheduler import run_dag_plan

    base_url = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")
    from ask.tau_harness import resolve_scillm_key

    api_key = resolve_scillm_key(base_url)
    request = (
        "Have a backend agent write the canary proof artifact, then an "
        "independent reviewer verifies it"
    )

    run_id = f"ask-tau-native-canary-{int(time.time())}"
    out_dir = ASK_ROOT / "artifacts" / "tau-native-canary" / run_id
    workspace = out_dir / "workspace"
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = render_plan(request)
    (out_dir / "project-plan.json").write_text(json.dumps(plan, indent=2))
    spec = compile_plan_to_tau_spec(plan, run_id=run_id, run_dir=out_dir)
    (out_dir / "dag-spec.json").write_text(json.dumps(spec, indent=2))
    assert heterogeneous_profile_count(spec) >= 2, "canary requires >= 2 distinct profiles"

    goal_hash = canonical_sha256({"goal": plan["goal"], "ticket": "agent-skills#1220"})
    profile_by_node = {
        node["node_id"]: node["tau_agent"]["model"].removeprefix("profile:")
        for node in spec["nodes"]
    }
    plan_compiled = compile_generic_dag_plan(spec, source_path=out_dir / "dag-spec.json")

    def _tools(node: Any, config: Any) -> list[AgentTool]:
        write = node.node_id == "worker"

        async def _executor(arguments: Any, signal: Any = None) -> AgentToolResult:
            name = "write_file" if write else "read_file"
            rel = str(arguments.get("path", ""))
            target = (workspace / rel).resolve()
            if not str(target).startswith(str(workspace.resolve())):
                return AgentToolResult(tool_call_id="", name=name, ok=False, content="escape", error="escape")
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(arguments.get("content", "")))
                return AgentToolResult(tool_call_id="", name=name, ok=True, content=f"wrote {rel}")
            if not target.exists():
                return AgentToolResult(tool_call_id="", name=name, ok=False, content="missing", error="missing")
            return AgentToolResult(tool_call_id="", name=name, ok=True, content=target.read_text())

        name = "write_file" if write else "read_file"
        properties: dict[str, Any] = {"path": {"type": "string"}}
        required = ["path"]
        if write:
            properties["content"] = {"type": "string"}
            required = ["path", "content"]
        return [
            AgentTool(
                name=name,
                description=f"{name} under the node workspace",
                input_schema={"type": "object", "properties": properties, "required": required},
                executor=_executor,
            )
        ]

    def provider_factory(node: Any, config: Any) -> ScillmTransportProvider:
        return ScillmTransportProvider(
            base_url=base_url,
            api_key=api_key,
            profile_id=profile_by_node[node.node_id],
            correlation={
                "tau_run_id": run_id,
                "node_id": node.node_id,
                "attempt": 1,
                "goal_hash": goal_hash,
            },
            required_capabilities=["tool_calling", "structured_events"],
            timeout_seconds=240,
        )

    def execute(plan_node: Any, accepted_inputs: Any, execution: Any) -> dict[str, Any]:
        assert plan_node.adapter_kind == TAU_NATIVE_ADAPTER_KIND
        return execute_tau_agent_node(
            plan_node,
            accepted_inputs,
            execution,
            goal_hash=goal_hash,
            provider_factory=provider_factory,
            tools_factory=_tools,
        )

    result = run_dag_plan(plan_compiled, execute_node=execute)
    by_id = {item["node_id"]: item for item in result.node_results}
    artifact = workspace / "proof.txt"
    artifact_ok = artifact.exists() and artifact.read_text() == CONTENT
    verdict = str((by_id.get("reviewer", {}).get("accepted_output") or {}).get("final_text", ""))
    summary = {
        "schema": "ask.tau_native_canary_summary.v1",
        "ticket": "agent-skills#1220",
        "run_id": run_id,
        "request": request,
        "goal_hash": goal_hash,
        "spec_sha256": spec["extensions"]["spec_sha256"],
        "profiles": profile_by_node,
        "scheduler_status": result.status,
        "completed_node_ids": list(result.completed_node_ids),
        "worker_settlement": (by_id.get("worker", {}).get("accepted_output") or {}).get("settlement", {}),
        "reviewer_settlement": (by_id.get("reviewer", {}).get("accepted_output") or {}).get("settlement", {}),
        "artifact_readback_ok": artifact_ok,
        "review_verdict_pass": "VERDICT: PASS" in verdict,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in (
        "run_id", "profiles", "scheduler_status", "completed_node_ids",
        "artifact_readback_ok", "review_verdict_pass", "spec_sha256",
    )}, indent=2))
    ok = (
        result.status == "PASS"
        and artifact_ok
        and summary["review_verdict_pass"]
        and summary["worker_settlement"].get("state") == "completed"
        and len(set(profile_by_node.values())) >= 2
    )
    print(f"ASK->TAU NATIVE CANARY {'PASS' if ok else 'FAIL'}: {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--live" not in sys.argv:
        print("refusing to run: live provider calls; pass --live")
        raise SystemExit(2)
    raise SystemExit(main())
