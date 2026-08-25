#!/usr/bin/env python3
"""Guard: an UNCERTAIN probe must not drop a browser seat from a multi-seat run.

Operator report 2026-08-25: a 5-seat compete (webgpt/webclaude/webgemini/
webkimi/webgrok) silently dropped webgemini to a claude-opus-5-high API
substitute because the uncertainty-keep in selection was gated on
single_explicit_seat. Live receipt: removed_handlers ['webgemini'],
failure_code browser_provider_probe_timeout, availability DEGRADED /
provider_limited False. This exercises the REAL _select_available_browser_handlers
with that exact synthetic availability report and asserts the seat is kept.
"""
import sys
from ask import tau_dag_cli as t
from ask.tau_dag import TauDagCompileInput


def main() -> int:
    inp = TauDagCompileInput(
        request="x", repo="local/agent-skills", target="t", immutable_goal="g",
        solver_models=(), reviewer_model="", criteria=(),
        handlers=("webgpt", "webclaude", "webgemini", "webkimi", "webgrok"),
        workflow_mode="compete",
    )

    def prov(**kw):
        d = {"provider_limited": False}
        d.update(kw)
        return d

    report = {"live": True, "providers": {
        "webgpt": prov(), "webclaude": prov(), "webkimi": prov(), "webgrok": prov(),
        "webgemini": prov(
            probe_degraded=True, failure_code="browser_provider_probe_timeout",
            provider_probe_recovery_packet={
                "auto_retry_allowed": False,
                "auto_retry_blocked_reason": "provider_probe_uncertain_requires_readback"}),
    }}
    sel = t._select_available_browser_handlers(inp, report, browser_tab_lifecycle="fresh-temporary")
    active = sel.get("active_handlers") or []
    removed = sel.get("removed_handlers") or []
    print("active_handlers:", active)
    print("removed_handlers:", removed)
    kept = "webgemini" in active and "webgemini" not in removed
    # A CONFIRMED limit MUST still remove (guard against over-keeping): flip the
    # same seat to provider_limited True and assert it IS removed.
    report["providers"]["webgemini"] = prov(provider_limited=True)
    sel2 = t._select_available_browser_handlers(inp, report, browser_tab_lifecycle="fresh-temporary")
    confirmed_removed = "webgemini" in (sel2.get("removed_handlers") or [])
    print("confirmed_limit_removed:", confirmed_removed)
    if kept and confirmed_removed:
        print("UNCERTAIN_SEAT_KEPT_CONFIRMED_SEAT_REMOVED")
        return 0
    print("SELECTION_GUARD_FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
