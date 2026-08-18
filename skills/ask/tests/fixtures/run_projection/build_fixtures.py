#!/usr/bin/env python3
"""Materialize the cross-mode projection fixtures (#1401 required proof 1).

The fixtures are committed files, not generated at test time, so a reviewer can
read exactly what each mode is asserted against. This script regenerates them
byte-identically; run it when a mode's real artifact shape changes.

Shapes are taken from the live corpus at
``/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs`` (1695 runs),
not invented: real DAG nodes carry ``agent`` with no separate ``handler`` field,
``request.json`` carries ``workflow_mode``/``dag_template``/``topology``, and a
node's terminal state lives in ``node-artifacts/<id>/node-receipt.json``.

Each mode deliberately encodes one hard case rather than a happy path, because
the projection exists to make absence and non-settlement visible.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent

GOAL = {
    "goal_id": "ask-fixture",
    "goal_version": 1,
    "immutable_goal": "fixture goal",
    "goal_hash": "sha256:fixture",
}


def _node(node_id: str) -> dict:
    """A DAG node in the real shape: agent set, no separate handler field."""
    return {"id": node_id, "agent": node_id, "executor": "local"}


def _receipt(*, ok: bool, status: str, failure_code: str = "", provider_live: bool = False) -> dict:
    receipt = {"ok": ok, "status": status, "provider_live": provider_live}
    if failure_code:
        receipt["failure_code"] = failure_code
    return receipt


# mode -> (request fields, node ids, per-node artifacts, execution-status)
MODES: dict[str, dict] = {
    # One handler that settled cleanly: the baseline every other mode deviates from.
    "one_handler": {
        "request": {"workflow_mode": "", "dag_template": "", "topology": "sequential"},
        "nodes": ["handler-webgpt", "join"],
        "artifacts": {
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False, "provider_live": True},
    },
    # Required proof 5: a partially successful roundtable must enumerate EVERY
    # seat with its exact terminal cause -- including the seat that produced
    # nothing at all.
    "roundtable_partial": {
        "request": {"workflow_mode": "roundtable", "dag_template": "roundtable", "topology": "concurrent"},
        "nodes": ["handler-webgpt", "handler-webclaude", "handler-webkimi", "join"],
        "artifacts": {
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "handler-webclaude": {
                "node-receipt.json": _receipt(
                    ok=False, status="NEEDS_ATTENTION", failure_code="browser_provider_rate_limited"
                )
            },
            # No artifacts at all: the seat that silently vanished.
            "join": {"node-receipt.json": _receipt(ok=False, status="DEGRADED", failure_code="degraded_join")},
        },
        "execution": {"status": "DEGRADED", "ok": False, "live": True, "mocked": False},
    },
    "compete": {
        "request": {"workflow_mode": "compete", "dag_template": "compete", "topology": "concurrent"},
        "nodes": ["handler-webgpt", "handler-webclaude", "join"],
        "artifacts": {
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "handler-webclaude": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    "creator_reviewer": {
        "request": {"workflow_mode": "roundtable", "dag_template": "creator-reviewer", "topology": "sequential"},
        "nodes": ["handler-webgpt", "reviewer-webclaude", "join"],
        "artifacts": {
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "reviewer-webclaude": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    "argue": {
        "request": {"workflow_mode": "roundtable", "dag_template": "argue", "topology": "sequential"},
        "nodes": ["handler-for", "handler-against", "join"],
        "artifacts": {
            "handler-for": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "handler-against": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    "deep_review": {
        "request": {"workflow_mode": "roundtable", "dag_template": "deep-review", "topology": "concurrent"},
        "nodes": ["reviewer-correctness", "reviewer-tests", "join"],
        "artifacts": {
            "reviewer-correctness": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "reviewer-tests": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    "team_plan": {
        "request": {"workflow_mode": "roundtable", "dag_template": "team-plan", "topology": "sequential"},
        "nodes": ["planner", "handler-webgpt", "join"],
        "artifacts": {
            "planner": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    # Required proof 9: a provider answered and the process exited zero, but
    # nothing admitted the output. This must NOT project as success.
    "natural_ask_dag": {
        "request": {"workflow_mode": "", "dag_template": "", "topology": "sequential"},
        "nodes": ["handler-webgpt", "join"],
        "artifacts": {
            "handler-webgpt": {
                "response.md": "A confident, favorable-looking provider answer.",
                "response.raw.md": "raw provider text",
            },
            "join": {},
        },
        "execution": {"status": "NEEDS_ATTENTION", "ok": False, "live": True, "mocked": False},
    },
    # Mixed targets: a browser seat, a model seat, and a Herdr session seat.
    "mixed_targets": {
        "request": {"workflow_mode": "roundtable", "dag_template": "roundtable", "topology": "concurrent"},
        "nodes": ["handler-webgpt", "handler-gpt-5.5-high", "handler-session-memory", "join"],
        "artifacts": {
            "handler-webgpt": {"node-receipt.json": _receipt(ok=True, status="PASS", provider_live=True)},
            "handler-gpt-5.5-high": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "handler-session-memory": {"node-receipt.json": _receipt(ok=True, status="PASS")},
            "join": {"node-receipt.json": _receipt(ok=True, status="PASS")},
        },
        "execution": {"status": "PASS", "ok": True, "live": True, "mocked": False},
    },
    # Required proof 6: a run blocked in preflight keeps request, goal, plan and
    # failure detail even though provider execution never began.
    "local_non_agentic_blocked": {
        "request": {"workflow_mode": "", "dag_template": "single-call", "topology": "sequential"},
        "nodes": ["handler-webgpt", "join"],
        "artifacts": {},
        "execution": {
            "status": "NEEDS_ATTENTION",
            "ok": False,
            "live": True,
            "mocked": False,
            "provider_live": False,
            "no_tau_execution": True,
            "failure_code": "browser_provider_probe_timeout",
            "removed_seats": ["webgpt"],
        },
    },
}


def build(root: Path = HERE) -> list[Path]:
    written: list[Path] = []
    for mode, spec in MODES.items():
        run = root / mode
        if run.is_dir():
            shutil.rmtree(run)
        run.mkdir(parents=True)

        request = {
            "schema": "ask.tau_dag_request.v1",
            "request": f"{mode} fixture request",
            "repo": "local/agent-skills",
            "target": f"fixture-{mode}",
            "immutable_goal": GOAL["immutable_goal"],
            "goal": GOAL,
            **spec["request"],
        }
        (run / "request.json").write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
        (run / "dag.json").write_text(
            json.dumps(
                {"schema": "tau.dag_contract.v1", "goal": GOAL, "nodes": [_node(n) for n in spec["nodes"]]},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (run / "compile-status.json").write_text(
            json.dumps({"schema": "ask.tau_dag_bundle.v1", "status": "READY"}, indent=2, sort_keys=True) + "\n"
        )
        if spec.get("execution") is not None:
            (run / "execution-status.json").write_text(
                json.dumps(spec["execution"], indent=2, sort_keys=True) + "\n"
            )
        for node_id, files in spec["artifacts"].items():
            node_dir = run / "node-artifacts" / node_id
            node_dir.mkdir(parents=True, exist_ok=True)
            for name, payload in files.items():
                text = (
                    json.dumps(payload, indent=2, sort_keys=True) + "\n"
                    if isinstance(payload, dict)
                    else str(payload)
                )
                (node_dir / name).write_text(text)
        written.append(run)
    return written


if __name__ == "__main__":
    for path in build():
        print(f"wrote {path}")
