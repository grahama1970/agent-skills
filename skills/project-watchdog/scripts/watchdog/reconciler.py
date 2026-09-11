"""Fleet reconciler: one disposition per nonterminal object (#1649).

Recovery was exceptional: each retained-operation class (unsettled Tau run,
crash-before-scheduler, native-close outbox, orphan lease) needed a bespoke
recognizer, and a new residue class minted *_unclassified and looped instead of
reconciling.

This maps EVERY nonterminal fleet object to exactly one disposition from a
closed set, so there is no residue to mint an unclassified code for:

  resume_machine_work      re-dispatch / continue the machine work
  settle_native_lifecycle  settle the native ticket/lease/outbox/tau close
  wait_on_dependency       a known blocker (wait edge) not yet landed
  human_only_blocker       canonical human-only hold (also the safe default for
                           a genuinely unknown nonterminal object -- park for a
                           human, never loop on an unclassified code)

``drained`` is the mechanical done predicate: no runnable agent-work issue, no
unsettled machine-actionable journal, no orphan lease, no terminal Tau run
awaiting proof or close, no stranded owned bytes. A human-only blocker does not
prevent drain -- it is parked for a human, not machine-actionable.

State is a plain snapshot the caller assembles from journals, leases, Tau run
state, native issue state, and owned snapshots vs current main bytes:
  issues:      [{number, runnable, requires_human_input}]
  journals:    [{id, settled, retryable, lease_released}]
  leases:      [{issue, orphan}]
  tau_runs:    [{id, terminal, awaiting_proof, awaiting_close}]
  owned_bytes: [{issue, path, remote_identical, has_wait_edge}]
"""
from __future__ import annotations

from typing import Any

DISPOSITIONS = ("resume_machine_work", "settle_native_lifecycle",
                "wait_on_dependency", "human_only_blocker")


def reconcile(state: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, str]] = []

    def add(obj: str, disposition: str) -> None:
        assert disposition in DISPOSITIONS, disposition
        items.append({"object": obj, "disposition": disposition})

    for j in state.get("journals", []):
        if j.get("settled"):
            continue
        add(f"journal:{j['id']}",
            "resume_machine_work" if (j.get("retryable") and j.get("lease_released"))
            else "settle_native_lifecycle")
    for lease in state.get("leases", []):
        if lease.get("orphan"):
            add(f"lease:{lease['issue']}", "settle_native_lifecycle")
    for t in state.get("tau_runs", []):
        if not t.get("terminal"):
            continue
        if t.get("awaiting_close"):
            add(f"tau:{t['id']}", "settle_native_lifecycle")
        elif t.get("awaiting_proof"):
            add(f"tau:{t['id']}", "resume_machine_work")
    for o in state.get("owned_bytes", []):
        if o.get("remote_identical"):
            continue
        add(f"owned:{o['issue']}:{o['path']}",
            "wait_on_dependency" if o.get("has_wait_edge") else "resume_machine_work")
    for i in state.get("issues", []):
        if i.get("requires_human_input"):
            add(f"issue:{i['number']}", "human_only_blocker")
        elif i.get("runnable"):
            add(f"issue:{i['number']}", "resume_machine_work")

    return {
        "schema": "project_watchdog.fleet_reconcile.v1",
        "dispositions": sorted(items, key=lambda x: x["object"]),
        "unclassified": 0,
        "drained": drained(state),
        "counts": {d: sum(1 for x in items if x["disposition"] == d) for d in DISPOSITIONS},
    }


def drained(state: dict[str, Any]) -> bool:
    if any(not j.get("settled") for j in state.get("journals", [])):
        return False
    if any(l.get("orphan") for l in state.get("leases", [])):
        return False
    if any(t.get("terminal") and (t.get("awaiting_proof") or t.get("awaiting_close"))
           for t in state.get("tau_runs", [])):
        return False
    if any(not o.get("remote_identical") for o in state.get("owned_bytes", [])):
        return False
    if any(i.get("runnable") for i in state.get("issues", [])):
        return False
    return True
