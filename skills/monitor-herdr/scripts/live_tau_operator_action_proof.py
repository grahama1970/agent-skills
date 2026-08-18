"""Live #1221 part-2 proof: real Tau journal → operator action → real receipt.

Proof boundary, stated precisely: the Tau runtime, journal, projection
functions, and ``apply_operator_action`` are all REAL. Only the model turn is
stubbed, using tau's own ``FakeProvider`` — the operator-action contract is
journal-level, so a live provider call would add cost without adding proof.

The run is projected BEFORE settlement so the node is still live and Tau
actually permits operator actions, which is the realistic case: an operator
acts on a running node, not a finished one.

What this proves end to end:
- monitor-herdr composes a request Tau accepts;
- Tau's own applier decides the outcome and moves its journal;
- monitor-herdr validates the receipt against the request it sent;
- typed outcomes (applied / queued_for_next_turn / unsupported) round-trip;
- a stale request is refused by Tau's optimistic-concurrency check.
"""

from __future__ import annotations

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


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERDR_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = _load("tau_projection_client")
operator = _load("tau_operator_actions")


def main() -> int:
    import asyncio

    from tau_agent import AssistantMessage
    from tau_ai import FakeProvider, ProviderResponseEndEvent, ProviderResponseStartEvent
    from tau_coding.dag_runtime.agent_node import AgentNodeRun, ToolPolicy
    from tau_coding.dag_runtime.agent_projection import apply_operator_action, project_agent_node, project_run
    from tau_coding.dag_runtime.model import canonical_sha256

    run_id = f"herdr-operator-action-proof-{int(time.time())}"
    out_dir = HERDR_ROOT / "receipts" / "tau-operator-actions" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    goal_hash = canonical_sha256({"ticket": "agent-skills#1221", "run_id": run_id})

    work_order = {
        "schema": "tau.agent_node.v1",
        "run_id": run_id,
        "node_id": "backend",
        "attempt_id": f"{run_id}:backend:1",
        "attempt": 1,
        "goal_hash": goal_hash,
        "plan_sha256": "sha256:" + "0" * 64,
        "model": "fake",
        "harness": "tau_native_agent_loop",
        "role": "backend",
        "required_evidence": [],
        "transport_profile_selection": {
            "selected_profile": {"profile_id": "claude-model-turn", "provider": "anthropic-oauth"}
        },
    }
    stream = [
        ProviderResponseStartEvent(model="fake"),
        ProviderResponseEndEvent(message=AssistantMessage(content="herdr-operator-action-live"), finish_reason="stop"),
    ]
    run = AgentNodeRun(
        work_order=work_order,
        policy=ToolPolicy(goal_hash=goal_hash, allowed_tools=()),
        provider=FakeProvider([stream]),
        tools=[],
    )
    asyncio.run(run.run("Reply with exactly: herdr-operator-action-live"))

    # Project the LIVE node (pre-settlement) so Tau still permits actions.
    node_projection = project_agent_node(run)
    run_projection = project_run(
        run_id=run_id, dag_id=f"dag-{run_id}", goal_hash=goal_hash, node_projections=[node_projection]
    )
    projection_path = out_dir / "run-projection.json"
    projection_path.write_text(json.dumps(run_projection, indent=2), encoding="utf-8")

    state_dir = out_dir / "state"
    state = client.attach(client.load_run_projection(projection_path), state_dir)
    permitted = state["cards"][0]["permitted_operator_actions"]

    # Use the client's REAL default submitter, so the proof covers its Tau
    # import, its error wrapping, and its refusal codes — not a bespoke stub.
    submit = operator.tau_submitter
    results: list[dict[str, Any]] = []

    def act(action: str, *, instruction: str | None = None) -> dict[str, Any]:
        """Submit one action against the CURRENT journal head and re-attach."""
        current = client.attach(
            _reproject(projection_path, run_id, goal_hash, project_agent_node(run), project_run),
            state_dir,
        )
        result = operator.submit_action(
            state=current,
            node_id="backend",
            action=action,
            actor="human_operator",
            instruction=instruction,
            submitter=submit,
            run=run,
        )
        results.append(result)
        return result

    steer = act("add_next_turn_instruction", instruction="Also record the operator instruction.")
    pause = act("pause")
    review = act("request_independent_review")

    # Negative path: a request built against a stale journal seq must be refused
    # by Tau itself, not silently retried and never by typing into a terminal.
    stale_state = json.loads(json.dumps(state))
    stale_state["cards"][0]["journal_seq"] = 0
    stale_state["cards"][0]["permitted_operator_actions"] = permitted
    stale_refused = None
    try:
        operator.submit_action(
            state=stale_state, node_id="backend", action="cancel",
            actor="human_operator", submitter=submit, run=run,
        )
    except operator.OperatorActionError as exc:
        stale_refused = exc.code

    cancel = act("cancel")

    summary = {
        "schema": "monitor_herdr.tau_operator_action_live_proof.v1",
        "ticket": "agent-skills#1221",
        "run_id": run_id,
        "proof_boundary": {
            "tau_runtime_journal_and_applier": "real",
            "model_turn": "tau FakeProvider (operator actions are journal-level)",
            "receipts_validated_by": "monitor-herdr tau_operator_actions.validate_action_receipt",
        },
        "permitted_operator_actions": permitted,
        "outcomes": {r["action"]: r["outcome"] for r in results},
        "journal_changed": {r["action"]: r["journal_changed"] for r in results},
        "receipt_sha256": {r["action"]: r["receipt_sha256"] for r in results},
        "stale_request_refused_with": stale_refused,
        "terminal_fallback_attempted": False,
        "paths": {"projection": str(projection_path), "state": str(state_dir / f"{run_id}.json")},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for result in results:
        (out_dir / f"action-{result['action']}-receipt.json").write_text(
            json.dumps(result["receipt"], indent=2), encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))

    ok = (
        steer["outcome"] == "queued_for_next_turn"
        and pause["outcome"] == "unsupported"
        and review["outcome"] == "applied"
        and cancel["outcome"] == "applied"
        and cancel["journal_changed"] is True
        and stale_refused == "operator_action_stale_journal_seq"
    )
    print(f"HERDR TAU-OPERATOR-ACTION LIVE PROOF {'PASS' if ok else 'FAIL'}: {out_dir}")
    return 0 if ok else 1


def _reproject(projection_path: Path, run_id: str, goal_hash: str, node_projection: Any, project_run: Any) -> dict[str, Any]:
    """Rewrite the projection from the current journal head and reload it."""
    payload = project_run(
        run_id=run_id, dag_id=f"dag-{run_id}", goal_hash=goal_hash, node_projections=[node_projection]
    )
    projection_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return client.load_run_projection(projection_path)


if __name__ == "__main__":
    raise SystemExit(main())
