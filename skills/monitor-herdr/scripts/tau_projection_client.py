"""Tau-run projection client for monitor-herdr (agent-skills#1221, tau#309).

Consumes ``tau.run_projection.v1`` / ``tau.agent_projection.v1`` and projects
them into one Herdr workspace state per run: one card per visible Tau agent
node. Herdr state is a RENDERING — the Tau journal stays authoritative; a
pane badge, process exit, or transport status can never override it.

Fail-closed rules (ticket negative paths):
- unknown run / missing projection file → typed error, no state written;
- schema or sha256 mismatch → refused;
- goal mismatch against an existing attached workspace → refused;
- stale projection (lower journal_seq than stored) → refused, state kept;
- reattach is idempotent: same projection → byte-identical state, retries
  update the card in place, terminal nodes are marked, never duplicated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

RUN_PROJECTION_SCHEMA = "tau.run_projection.v1"
AGENT_PROJECTION_SCHEMA = "tau.agent_projection.v1"
TERMINAL_LIFECYCLES = ("completed", "failed", "cancelled", "blocked")
STATE_SCHEMA = "monitor_herdr.tau_workspace_state.v1"


class ProjectionError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code + (f": {detail}" if detail else ""))
        self.code = code


def _canonical_sha256(payload: dict[str, Any]) -> str:
    # Byte-parity with tau_coding.dag_runtime.model.canonical_sha256.
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def load_run_projection(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProjectionError("unknown_run", str(path))
    try:
        projection = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ProjectionError("projection_unreadable", str(exc)) from exc
    if projection.get("schema") != RUN_PROJECTION_SCHEMA:
        raise ProjectionError("projection_schema_invalid", str(projection.get("schema")))
    for node in projection.get("nodes", []):
        if node.get("schema") != AGENT_PROJECTION_SCHEMA:
            raise ProjectionError("node_projection_schema_invalid", str(node.get("node_id")))
        claimed = node.get("sha256")
        body = {k: v for k, v in node.items() if k != "sha256"}
        if claimed and _canonical_sha256(body) != claimed:
            raise ProjectionError("node_projection_sha_mismatch", str(node.get("node_id")))
    return projection


def _card(node: dict[str, Any]) -> dict[str, Any]:
    lifecycle = str(node.get("lifecycle", "selected"))
    return {
        "node_id": node["node_id"],
        "label": f"{node.get('role') or 'agent'}/{node['node_id']}",
        "role": node.get("role"),
        "attempt": node.get("attempt"),
        "goal_hash": node.get("goal_hash"),
        "harness": node.get("harness", "tau_native_agent_loop"),
        "transport_profile": node.get("transport_profile"),
        "lifecycle": lifecycle,
        "terminal": lifecycle in TERMINAL_LIFECYCLES,
        "turns": node.get("turns", 0),
        "journal_seq": node.get("journal_seq", 0),
        "current_blocker": node.get("current_blocker"),
        "permitted_operator_actions": list(node.get("permitted_operator_actions", [])),
        "evidence_kinds": list(node.get("evidence_kinds", [])),
        "projection_only": True,
    }


def attach(projection: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    """Create or idempotently update the workspace state for a run."""
    run_id = str(projection["run_id"])
    state_path = state_dir / f"{run_id}.json"
    new_seq = sum(int(n.get("journal_seq", 0)) for n in projection.get("nodes", []))
    if state_path.is_file():
        stored = json.loads(state_path.read_text(encoding="utf-8"))
        if stored.get("goal_hash") != projection.get("goal_hash"):
            raise ProjectionError("goal_mismatch", run_id)
        if int(stored.get("journal_seq_total", 0)) > new_seq:
            raise ProjectionError("stale_projection", f"stored={stored.get('journal_seq_total')} new={new_seq}")
    cards: dict[str, dict[str, Any]] = {}
    for node in projection.get("nodes", []):
        cards[str(node["node_id"])] = _card(node)  # reattach replaces by node_id — no duplicates
    state = {
        "schema": STATE_SCHEMA,
        "workspace": f"tau-run:{run_id}",
        "run_id": run_id,
        "dag_id": projection.get("dag_id"),
        "goal_hash": projection.get("goal_hash"),
        "journal_seq_total": new_seq,
        "cards": [cards[k] for k in sorted(cards)],
        "proof_boundary": {
            "herdr_state_is_projection_only": True,
            "tau_journal_is_authoritative": True,
        },
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def status(run_id: str, state_dir: Path) -> dict[str, Any]:
    state_path = state_dir / f"{run_id}.json"
    if not state_path.is_file():
        raise ProjectionError("unknown_run", run_id)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return {
        "schema": "monitor_herdr.tau_status.v1",
        "run_id": run_id,
        "workspace": state["workspace"],
        "cards": [
            {k: c[k] for k in ("label", "lifecycle", "terminal", "transport_profile", "current_blocker", "permitted_operator_actions")}
            for c in state["cards"]
        ],
        "all_terminal": all(c["terminal"] for c in state["cards"]) if state["cards"] else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tau-run projection client")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_attach = sub.add_parser("attach-tau-run")
    p_attach.add_argument("--projection", required=True, type=Path)
    p_attach.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/monitor-herdr/tau-runs")
    p_status = sub.add_parser("tau-status")
    p_status.add_argument("--run-id", required=True)
    p_status.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/monitor-herdr/tau-runs")
    args = parser.parse_args()
    try:
        if args.cmd == "attach-tau-run":
            out = attach(load_run_projection(args.projection), args.state_dir)
        else:
            out = status(args.run_id, args.state_dir)
    except ProjectionError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc)}))
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
