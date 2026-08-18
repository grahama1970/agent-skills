#!/usr/bin/env python3
"""Live Herdr topology proof for ops-herdr.

Inputs: a running Herdr server on this machine (``herdr status``).
Outputs: a JSON report on stdout and a receipt under ``outputs/``.
Failure modes: exits 1 when Herdr disagrees with the contract this skill builds
against, exits 2 when Herdr is unreachable.

This exists because ``sanity.sh`` compiles modules and checks ``--help``, which is
exactly the class of test that let the pre-0.8 ``agent start``/``agent send``/
``agent wait`` argv rot undetected. Every assertion below is a readback of what
Herdr actually did, never the exit code of the command that asked for it.

Agent startup is opt-in (``--with-agent KIND``) because attaching a real provider
consumes a session; the topology and move paths need no agent to be proven.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "scripts"))

from ops_herdr_core import (  # noqa: E402
    AGENT_KINDS,
    HerdrContractError,
    check_protocol,
    layout_pane_ids,
    create_tab,
    create_workspace,
    ensure_dir,
    move_pane,
    pane_layout,
    run_herdr,
    split_pane,
    utc_stamp,
    write_json,
)

LABEL_PREFIX = "ops-herdr-live-eval"


def fail(checks: list[dict[str, Any]], name: str, detail: str) -> None:
    """Record a failed assertion without aborting the cleanup path."""
    checks.append({"check": name, "ok": False, "detail": detail})


def ok(checks: list[dict[str, Any]], name: str, detail: str = "") -> None:
    """Record a passed assertion."""
    checks.append({"check": name, "ok": True, "detail": detail})


def close_workspace(workspace_id: str, herdr_bin: str, session: str | None) -> None:
    """Close a workspace this eval created, ignoring an already-closed workspace."""
    run_herdr(["workspace", "close", workspace_id], herdr_bin=herdr_bin, session=session, check=False)


def run_eval(*, herdr_bin: str, session: str | None, with_agent: str | None) -> dict[str, Any]:
    """Build a real Herdr topology, move a live pane, and read every step back."""
    checks: list[dict[str, Any]] = []
    created: list[str] = []
    cwd = Path.cwd()
    stamp = utc_stamp()

    protocol = check_protocol(herdr_bin=herdr_bin, session=session)
    if not protocol["ok"]:
        return {"status": "BLOCKED", "reason": "protocol", "protocol": protocol, "checks": checks}
    ok(checks, "protocol", f"protocol {protocol['protocol']} >= {protocol['minimum']}")

    try:
        topology = create_workspace(
            label=f"{LABEL_PREFIX}-{stamp}-disposable",
            cwd=cwd, session=session, herdr_bin=herdr_bin, env_values=[], dry_run=False,
        )
        created.append(topology.workspace_id)

        # 1. workspace create must return workspace, root tab, AND root pane.
        for field, value in (
            ("workspace_id", topology.workspace_id),
            ("root_tab_id", topology.root_tab_id),
            ("root_pane_id", topology.root_pane_id),
        ):
            if value:
                ok(checks, f"workspace_create.{field}", value)
            else:
                fail(checks, f"workspace_create.{field}", "empty")
        if topology.root_tab_id.startswith(topology.workspace_id):
            ok(checks, "workspace_create.ids_qualified", f"{topology.root_tab_id} under {topology.workspace_id}")
        else:
            fail(checks, "workspace_create.ids_qualified", f"{topology.root_tab_id} not under {topology.workspace_id}")

        # 2. tab create must also return its root pane.
        tab = create_tab(
            workspace_id=topology.workspace_id, label="agents", cwd=cwd,
            session=session, herdr_bin=herdr_bin, env_values=["OPS_HERDR_EVAL=1"], dry_run=False,
        )
        ok(checks, "tab_create.tab_id", tab.tab_id) if tab.tab_id else fail(checks, "tab_create.tab_id", "empty")
        ok(checks, "tab_create.root_pane_id", tab.root_pane_id) if tab.root_pane_id else fail(checks, "tab_create.root_pane_id", "empty")

        # 3. splits must return the NEW pane id, and the layout must show them.
        right = split_pane(pane_id=tab.root_pane_id, direction="right", cwd=cwd, session=session, herdr_bin=herdr_bin)
        down = split_pane(pane_id=right, direction="down", cwd=cwd, session=session, herdr_bin=herdr_bin)
        distinct = len({tab.root_pane_id, right, down})
        if distinct == 3:
            ok(checks, "pane_split.distinct_ids", f"{tab.root_pane_id}, {right}, {down}")
        else:
            fail(checks, "pane_split.distinct_ids", f"expected 3 distinct panes, got {distinct}")

        layout = pane_layout(pane_id=tab.root_pane_id, session=session, herdr_bin=herdr_bin)
        leaves = layout_pane_ids(layout)
        if sorted(leaves) == sorted([tab.root_pane_id, right, down]):
            ok(checks, "pane_layout.leaves", f"{len(leaves)} leaves match the panes we created")
        else:
            fail(checks, "pane_layout.leaves", f"expected {[tab.root_pane_id, right, down]}, layout reported {leaves}")
        if layout.get("tab_id") == tab.tab_id:
            ok(checks, "pane_layout.tab_id", tab.tab_id)
        else:
            fail(checks, "pane_layout.tab_id", f"expected {tab.tab_id}, got {layout.get('tab_id')}")

        # 4. a cross-workspace move must preserve the terminal and report the id map.
        before = run_herdr(["pane", "get", down], herdr_bin=herdr_bin, session=session).parsed
        before_terminal = (before or {}).get("result", {}).get("pane", {}).get("terminal_id")
        move = move_pane(
            pane_id=down, new_workspace=True,
            label=f"{LABEL_PREFIX}-moved-{stamp}-disposable", tab_label="agents",
            session=session, herdr_bin=herdr_bin,
        )
        if move.created_workspace_id:
            created.append(move.created_workspace_id)
        if move.previous_pane_id == down:
            ok(checks, "pane_move.previous_pane_id", down)
        else:
            fail(checks, "pane_move.previous_pane_id", f"expected {down}, got {move.previous_pane_id}")
        if move.pane_id and move.pane_id != down:
            ok(checks, "pane_move.new_pane_id", move.pane_id)
        else:
            fail(checks, "pane_move.new_pane_id", f"pane id did not change: {move.pane_id}")
        if before_terminal and move.terminal_id == before_terminal:
            ok(checks, "pane_move.terminal_preserved", move.terminal_id)
        else:
            fail(checks, "pane_move.terminal_preserved", f"{before_terminal} -> {move.terminal_id}")
        if move.id_map() == {down: move.pane_id}:
            ok(checks, "pane_move.id_map", json.dumps(move.id_map()))
        else:
            fail(checks, "pane_move.id_map", json.dumps(move.id_map()))

        # 5. the old pane id must still resolve, which is what makes reconciliation safe.
        alias = run_herdr(["pane", "get", down], herdr_bin=herdr_bin, session=session, check=False)
        if alias.returncode == 0:
            ok(checks, "pane_move.old_id_alias", f"{down} still resolves")
        else:
            fail(checks, "pane_move.old_id_alias", f"{down} no longer resolves (exit {alias.returncode})")

        # 6. optional: attach a real agent to a real pane on the 0.8 contract.
        if with_agent:
            if with_agent not in AGENT_KINDS:
                fail(checks, "agent_start.kind", f"{with_agent} not in Herdr's kind enum")
            else:
                started = run_herdr(
                    ["agent", "start", f"eval-{stamp}", "--kind", with_agent, "--pane", right, "--timeout", "60000"],
                    herdr_bin=herdr_bin, session=session, check=False,
                )
                if started.returncode != 0:
                    fail(checks, "agent_start.exit", f"exit {started.returncode}: {started.stderr.strip()[:200]}")
                else:
                    listing = run_herdr(["agent", "list"], herdr_bin=herdr_bin, session=session).parsed
                    agents = (listing or {}).get("result", {}).get("agents", [])
                    match = [a for a in agents if a.get("pane_id") == right]
                    if match and match[0].get("agent") == with_agent:
                        ok(checks, "agent_start.readback", f"{with_agent} live on {right}")
                    else:
                        fail(checks, "agent_start.readback", f"no {with_agent} agent found on {right}")
    except HerdrContractError as exc:
        fail(checks, "herdr_contract", str(exc))
    except Exception as exc:  # noqa: BLE001 - the eval must always reach cleanup.
        fail(checks, "unexpected_error", repr(exc))
    finally:
        for workspace_id in created:
            close_workspace(workspace_id, herdr_bin, session)

    remaining = run_herdr(["workspace", "list"], herdr_bin=herdr_bin, session=session, check=False).parsed
    leftovers = [
        w.get("label")
        for w in ((remaining or {}).get("result", {}) or {}).get("workspaces", [])
        if str(w.get("label", "")).startswith(LABEL_PREFIX)
    ]
    if leftovers:
        fail(checks, "cleanup", f"eval workspaces left behind: {leftovers}")
    else:
        ok(checks, "cleanup", "no eval workspaces remain")

    failures = [c for c in checks if not c["ok"]]
    return {
        "status": "PASS" if not failures else "FAIL",
        "protocol": protocol,
        "with_agent": with_agent,
        "checks": checks,
        "failures": failures,
        "created_workspaces": created,
    }


def main() -> int:
    """Run the live topology eval and emit a JSON report plus a receipt."""
    parser = argparse.ArgumentParser(description="Live Herdr topology proof for ops-herdr.")
    parser.add_argument("--herdr-bin", default="herdr")
    parser.add_argument("--session", default=None)
    parser.add_argument("--with-agent", default=None, help="Also start this Herdr agent kind (consumes a provider session).")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    status = run_herdr(["status"], herdr_bin=args.herdr_bin, session=args.session, check=False)
    if status.returncode != 0:
        print(json.dumps({"status": "BLOCKED", "reason": "herdr_unreachable"}, indent=2))
        return 2

    report = run_eval(herdr_bin=args.herdr_bin, session=args.session, with_agent=args.with_agent)
    report["created_at"] = utc_stamp()
    out = Path(args.output) if args.output else SCRIPT_DIR.parent / "outputs" / f"live-space-e2e-{report['created_at']}.json"
    write_json(ensure_dir(out.parent) / out.name, report)
    report["report_path"] = str(out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
