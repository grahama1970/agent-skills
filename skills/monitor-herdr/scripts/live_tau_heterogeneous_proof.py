"""Live #1221 proofs 4 and 5: heterogeneous Tau run + live operator action.

Requirement 4: a live non-mocked heterogeneous Tau run appears in ONE Herdr
workspace with at least two distinct model profiles and follows Tau state
through settlement.
Requirement 5: at least one live operator action is submitted through Tau and
read back from the resulting Tau receipt/projection.

Provider boundary: Tau owns SciLLM. This script never reads a SciLLM key from
the operator or the environment directly — it calls Tau's own resolver, the
same one Tau's other provider lanes use, and Tau's own transport class. The
project agent consumes Tau receipts, never raw SciLLM responses.

Both model turns are REAL provider calls over two distinct transport profiles.
Nothing here is stubbed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Load .env before any os.environ lookup below; without it these proofs work only
# when launched from a parent that already loaded it and read nothing standalone.
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True) or None, override=False)
except Exception:  # noqa: BLE001 - dotenv is optional, never fatal.
    pass

HERDR_ROOT = Path(__file__).resolve().parent.parent
TAU_SRC = Path(os.environ.get("TAU_REPO", str(Path.home() / "workspace/experiments/tau"))) / "src"
sys.path.insert(0, str(TAU_SRC))

PROFILES = (
    {"node_id": "backend", "role": "backend", "profile_id": "claude-model-turn"},
    {"node_id": "frontend", "role": "frontend", "profile_id": "codex-model-turn"},
)


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERDR_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = _load("tau_projection_client")
operator = _load("tau_operator_actions")


def main() -> int:
    from tau_ai.scillm_transport import ScillmTransportProvider
    from tau_coding.battle_scillm import _resolve_api_key
    from tau_coding.dag_runtime.agent_node import AgentNodeRun, ToolPolicy
    from tau_coding.dag_runtime.agent_projection import project_agent_node, project_run
    from tau_coding.dag_runtime.model import canonical_sha256

    # Tau-owned credential resolution: env, then its proxy container, then dev
    # default. The operator supplies nothing.
    api_key, api_key_source, api_key_errors = _resolve_api_key()
    base_url = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")

    run_id = f"herdr-heterogeneous-proof-{int(time.time())}"
    out_dir = HERDR_ROOT / "receipts" / "tau-heterogeneous" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    goal_hash = canonical_sha256({"ticket": "agent-skills#1221", "run_id": run_id})
    state_dir = out_dir / "state"

    def build_run(spec: dict[str, str]) -> Any:
        work_order = {
            "schema": "tau.agent_node.v1",
            "run_id": run_id,
            "node_id": spec["node_id"],
            "attempt_id": f"{run_id}:{spec['node_id']}:1",
            "attempt": 1,
            "goal_hash": goal_hash,
            "plan_sha256": "sha256:" + "0" * 64,
            "model": f"profile:{spec['profile_id']}",
            "harness": "tau_native_agent_loop",
            "role": spec["role"],
            "required_evidence": [],
            "transport_profile_selection": {
                "selected_profile": {"profile_id": spec["profile_id"]}
            },
        }
        provider = ScillmTransportProvider(
            base_url=base_url,
            api_key=api_key,
            profile_id=spec["profile_id"],
            correlation={
                "tau_run_id": run_id,
                "node_id": spec["node_id"],
                "attempt": 1,
                "goal_hash": goal_hash,
            },
            timeout_seconds=180,
        )
        return AgentNodeRun(
            work_order=work_order,
            policy=ToolPolicy(goal_hash=goal_hash, allowed_tools=(), allowed_paths=(), max_tool_calls=0),
            provider=provider,
            tools=[],
            max_turns=2,
        )

    runs = {spec["node_id"]: build_run(spec) for spec in PROFILES}

    # --- requirement 5: a live operator action on a live (pre-settlement) node
    backend = runs["backend"]
    asyncio.run(backend.run("Reply with exactly: herdr-heterogeneous-backend"))

    live_projection = project_run(
        run_id=run_id, dag_id=f"dag-{run_id}", goal_hash=goal_hash,
        node_projections=[project_agent_node(backend)],
    )
    live_path = out_dir / "live-projection.json"
    live_path.write_text(json.dumps(live_projection, indent=2), encoding="utf-8")
    live_state = client.attach(client.load_run_projection(live_path), state_dir)

    action = operator.submit_action(
        state=live_state,
        node_id="backend",
        action="request_independent_review",
        actor="human_operator",
        submitter=operator.tau_submitter,
        run=backend,
    )
    (out_dir / "operator-action-receipt.json").write_text(
        json.dumps(action["receipt"], indent=2), encoding="utf-8"
    )

    # --- requirement 4: both profiles, one workspace, through settlement
    asyncio.run(runs["frontend"].run("Reply with exactly: herdr-heterogeneous-frontend"))

    node_projections = []
    settlements = {}
    for node_id, run in runs.items():
        settlement = run.settle()
        settlements[node_id] = settlement["state"]
        node_projections.append(project_agent_node(run, settlement=settlement))

    settled_projection = project_run(
        run_id=run_id, dag_id=f"dag-{run_id}", goal_hash=goal_hash, node_projections=node_projections
    )
    settled_path = out_dir / "run-projection.json"
    settled_path.write_text(json.dumps(settled_projection, indent=2), encoding="utf-8")

    state = client.attach(client.load_run_projection(settled_path), state_dir)
    readback = client.status(run_id, state_dir)

    def profile_id_of(card: dict[str, Any]) -> str:
        profile = card.get("transport_profile")
        if isinstance(profile, dict):
            return str(profile.get("profile_id") or profile.get("id") or "")
        return str(profile or "")

    observed_profiles = sorted({profile_id_of(c) for c in state["cards"]} - {""})

    summary = {
        "schema": "monitor_herdr.tau_heterogeneous_live_proof.v1",
        "ticket": "agent-skills#1221",
        "requirements": ["proof_4_heterogeneous_live_run", "proof_5_live_operator_action"],
        "run_id": run_id,
        "proof_boundary": {
            "model_turns": "live SciLLM provider calls via Tau transport",
            "scillm_credential_source": api_key_source,
            "scillm_credential_errors": api_key_errors,
            "tau_owns_provider_boundary": True,
        },
        "workspace": state["workspace"],
        "distinct_transport_profiles": observed_profiles,
        "node_count": len(state["cards"]),
        "settlement_states": settlements,
        "lifecycles": {c["node_id"]: c["lifecycle"] for c in state["cards"]},
        "all_terminal": readback["all_terminal"],
        "operator_action": {
            "action": action["action"],
            "outcome": action["outcome"],
            "journal_changed": action["journal_changed"],
            "receipt_sha256": action["receipt_sha256"],
        },
        "paths": {
            "run_projection": str(settled_path),
            "state": str(state_dir / f"{run_id}.json"),
            "operator_action_receipt": str(out_dir / "operator-action-receipt.json"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    ok = (
        len(observed_profiles) >= 2
        and len(state["cards"]) == 2
        and readback["all_terminal"]
        and all(v == "completed" for v in settlements.values())
        and action["outcome"] == "applied"
        and action["journal_changed"] is True
    )
    print(f"HERDR TAU-HETEROGENEOUS LIVE PROOF {'PASS' if ok else 'FAIL'}: {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--live" not in sys.argv:
        print("refusing to run: live provider calls; pass --live")
        raise SystemExit(2)
    raise SystemExit(main())
