"""Live #1221 proof: real Tau agent run → tau#309 projection → Herdr attach.

Runs one live Tau-native agent node over SciLLM transport, derives the
authoritative ``tau.agent_projection.v1`` / ``tau.run_projection.v1`` with
tau's OWN projection functions (journal-derived, never pane/transport state),
writes them to disk, attaches via the monitor-herdr projection client, and
reads the resulting workspace state back. Refuses without ``--live``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERDR_ROOT = Path(__file__).resolve().parent.parent
TAU_SRC = Path(os.environ.get("TAU_REPO", str(Path.home() / "workspace/experiments/tau"))) / "src"
sys.path.insert(0, str(TAU_SRC))

import importlib.util

_cspec = importlib.util.spec_from_file_location(
    "tau_projection_client", HERDR_ROOT / "scripts" / "tau_projection_client.py"
)
client = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(client)


def main() -> int:
    import asyncio

    from tau_agent.tools import AgentTool  # noqa: F401 (import proves tau env)
    from tau_ai.scillm_transport import ScillmTransportProvider
    from tau_coding.dag_runtime.agent_node import AgentNodeRun, ToolPolicy
    from tau_coding.dag_runtime.agent_projection import project_agent_node, project_run
    from tau_coding.dag_runtime.model import canonical_sha256

    run_id = f"herdr-projection-proof-{int(time.time())}"
    out_dir = HERDR_ROOT / "receipts" / "tau-projection" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    goal_hash = canonical_sha256({"ticket": "agent-skills#1221", "run_id": run_id})

    work_order = {
        "schema": "tau.agent_node.v1",
        "run_id": run_id,
        "node_id": "probe",
        "attempt_id": f"{run_id}:probe:1",
        "attempt": 1,
        "goal_hash": goal_hash,
        "plan_sha256": "sha256:" + "0" * 64,
        "model": "profile:codex-model-turn",
        "harness": "tau_native_agent_loop",
        "role": "backend",
        "required_evidence": [],
        "transport_profile_selection": {
            "selected_profile": {"id": "codex-model-turn", "model": "gpt-5.5", "provider": "codex-oauth"}
        },
    }
    provider = ScillmTransportProvider(
        base_url=os.environ.get("SCILLM_BASE_URL", "http://localhost:4001"),
        api_key=os.environ["SCILLM_MASTER_KEY"],
        profile_id="codex-model-turn",
        correlation={"tau_run_id": run_id, "node_id": "probe", "attempt": 1, "goal_hash": goal_hash},
        required_capabilities=["streaming"],
        timeout_seconds=120,
    )
    run = AgentNodeRun(
        work_order=work_order,
        policy=ToolPolicy(goal_hash=goal_hash, allowed_tools=(), allowed_paths=(), max_tool_calls=0),
        provider=provider,
        tools=[],
        max_turns=2,
    )
    asyncio.run(run.run("Reply with exactly: herdr-projection-live"))
    settlement = run.settle()

    node_projection = project_agent_node(run, settlement=settlement)
    run_projection = project_run(
        run_id=run_id,
        dag_id=f"dag-{run_id}",
        goal_hash=goal_hash,
        node_projections=[node_projection],
    )
    projection_path = out_dir / "run-projection.json"
    projection_path.write_text(json.dumps(run_projection, indent=2), encoding="utf-8")

    state = client.attach(client.load_run_projection(projection_path), out_dir / "state")
    readback = client.status(run_id, out_dir / "state")
    summary = {
        "schema": "monitor_herdr.tau_projection_live_proof.v1",
        "ticket": "agent-skills#1221",
        "run_id": run_id,
        "settlement_state": settlement["state"],
        "node_lifecycle": node_projection["lifecycle"],
        "projection_sha256": node_projection["sha256"],
        "workspace": state["workspace"],
        "cards": readback["cards"],
        "all_terminal": readback["all_terminal"],
        "paths": {"projection": str(projection_path), "state": str(out_dir / "state" / f"{run_id}.json")},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    ok = (
        settlement["state"] == "completed"
        and readback["all_terminal"]
        and (state["cards"][0]["transport_profile"] or {}).get("id") == "codex-model-turn"
    )
    print(f"HERDR TAU-PROJECTION LIVE PROOF {'PASS' if ok else 'FAIL'}: {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--live" not in sys.argv:
        print("refusing to run: live provider calls; pass --live")
        raise SystemExit(2)
    raise SystemExit(main())
