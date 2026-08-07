#!/usr/bin/env python3
"""Build the "How proof works" explainer from ONE real Tau execution.

Emits site/proof-explainer.json: six stages — goal, bounded context,
constrained execution, captured evidence, deterministic judgment, receipt —
each resolved to a real immutable artifact in the run directory, with the
exact field excerpt, the source SHA-256, a transition invariant, and explicit
proves / does-not-prove boundaries.

Nothing here is authored prose about the run: every value is read from the
artifacts of the roundtable that designed this site. If any required field is
missing, generation FAILS (the site must not ship a fabricated proof chain).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN = Path(
    "/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/"
    "ask-tau-roundtable-round-2-webgpt-webcla-ce79c8ef960c"
)


class MissingEvidence(Exception):
    """A required field or artifact is absent — fail closed, do not fabricate."""


def sha16(path: Path) -> str:
    if not path.exists():
        raise MissingEvidence(f"missing artifact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load(path: Path) -> dict:
    if not path.exists():
        raise MissingEvidence(f"missing artifact: {path}")
    return json.loads(path.read_text())


def need(d: dict, *keys: str):
    """Fetch a nested field; raise MissingEvidence if any hop is absent."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise MissingEvidence(f"missing field: {'.'.join(keys)}")
        cur = cur[k]
    return cur


def rel(path: Path) -> str:
    return path.name


def build() -> dict:
    dag_path = RUN / "dag.json"
    cmd_path = RUN / "command-specs/handler-webclaude/tau-dispatch-command.json"
    recv_path = RUN / "node-artifacts/handler-webclaude/node-receipt.json"
    join_path = RUN / "node-artifacts/join/node-receipt.json"
    es_path = RUN / "execution-status.json"

    dag = load(dag_path)
    cmd = load(cmd_path)
    recv = load(recv_path)
    join = load(join_path)
    es = load(es_path)

    goal_hash = need(dag, "goal", "goal_hash")
    immutable_goal = need(dag, "goal", "immutable_goal")
    limits = need(dag, "limits")
    fail_closed = need(dag, "fail_closed_on")
    required_evidence = need(dag, "required_evidence")

    stages = [
        {
            "n": 1,
            "name": "Goal",
            "desc": "The objective is fixed and hashed before anything runs. "
            "Every later step is checked against this exact hash.",
            "artifact": rel(dag_path),
            "digest": sha16(dag_path),
            "excerpt": {
                "immutable_goal": immutable_goal[:180]
                + ("…" if len(immutable_goal) > 180 else ""),
                "goal_hash": goal_hash,
            },
            "invariant": "goal_hash is frozen; any drift trips "
            "goal_hash_mismatch and the run fails closed.",
            "proves": "The work was pinned to one stated objective, "
            "identified by a content hash.",
            "not": "That the objective itself is the right thing to build.",
        },
        {
            "n": 2,
            "name": "Bounded context",
            "desc": "Limits, required evidence, and fail-closed conditions are "
            "declared up front — the agent operates inside a fence.",
            "artifact": rel(dag_path),
            "digest": sha16(dag_path),
            "excerpt": {
                "limits": limits,
                "required_evidence": required_evidence,
                "fail_closed_on": f"{len(fail_closed)} conditions incl. "
                + ", ".join(fail_closed[:3]),
            },
            "invariant": "Missing any required-evidence artifact aborts the "
            "run rather than reporting success.",
            "proves": "Permissions, timeouts, and stop conditions existed "
            "before the agent acted.",
            "not": "That the chosen bounds are sufficient for every risk.",
        },
        {
            "n": 3,
            "name": "Constrained execution",
            "desc": "The exact command Tau dispatched, with its side-effect "
            "declaration, recorded verbatim.",
            "artifact": rel(cmd_path),
            "digest": sha16(cmd_path),
            "excerpt": {
                "mutates": need(cmd, "mutates"),
                "compile_only": need(cmd, "compile_only"),
                "requires_network": need(cmd, "requires_network"),
                "timeout_s": need(cmd, "timeout_s"),
            },
            "invariant": "mutates:false is a declared contract — a write "
            "would contradict the receipt and fail review.",
            "proves": "What ran, whether it could mutate state, and its "
            "timeout — captured, not narrated.",
            "not": "That the reviewer's output is semantically correct.",
        },
        {
            "n": 4,
            "name": "Captured evidence",
            "desc": "The handler receipt records that a real provider answered "
            "live — not a mock, not a claim.",
            "artifact": rel(recv_path),
            "digest": sha16(recv_path),
            "excerpt": {
                "handler": need(recv, "handler"),
                "live": need(recv, "live"),
                "mocked": need(recv, "mocked"),
                "browser_model_preference": need(recv, "browser_model_preference"),
                "created_at": need(recv, "created_at"),
            },
            "invariant": "live:true with mocked:false is required; a mocked "
            "lane cannot satisfy the evidence gate.",
            "proves": "A real model produced this seat's response, on the "
            "record, at a stamped time.",
            "not": "That the response's content is right — only that it "
            "genuinely occurred.",
        },
        {
            "n": 5,
            "name": "Deterministic judgment",
            "desc": "A join gate — not a model — counts usable seats and "
            "emits a PASS/FAIL verdict against a typed schema.",
            "artifact": rel(join_path),
            "digest": sha16(join_path),
            "excerpt": {
                "schema": need(join, "schema"),
                "status": need(join, "status"),
                "topology": need(join, "topology"),
                "usable_response_count": need(join, "usable_response_count"),
                "failed_seat_count": need(join, "failed_seat_count"),
            },
            "invariant": "The verdict is computed from seat receipts; it "
            "cannot be set by a model asserting success.",
            "proves": "A deterministic gate ran and recorded how many seats "
            "actually returned usable work.",
            "not": "That the panel's collective judgment is correct.",
        },
        {
            "n": 6,
            "name": "Receipt",
            "desc": "The top-level receipt carries its own explicit boundary — "
            "what it proves and, just as loudly, what it does not.",
            "artifact": rel(es_path),
            "digest": sha16(es_path),
            "excerpt": {
                "status": need(es, "status"),
                "live": need(es, "live"),
                "mocked": need(es, "mocked"),
                "proves": need(es, "proof_scope", "proves")[0],
                "does_not_prove": need(es, "proof_scope", "does_not_prove")[0],
            },
            "invariant": "The receipt states its own does-not-prove list; the "
            "claim can never exceed the evidence.",
            "proves": "The run reached a typed terminal state with a scoped, "
            "self-limiting proof statement.",
            "not": "That PASS means the design advice was good — only that "
            "the process is accountable.",
        },
    ]

    return {
        "run": RUN.name,
        "goal_hash": goal_hash,
        "nodes": len(need(dag, "nodes")),
        "stages": stages,
    }


def main() -> None:
    try:
        data = build()
    except MissingEvidence as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise SystemExit(1)
    out = REPO / "site/proof-explainer.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"proof-explainer: {len(data['stages'])} stages from {data['run']}")


if __name__ == "__main__":
    main()
