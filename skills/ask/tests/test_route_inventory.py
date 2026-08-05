"""Route inventory test for agent-skills#1220.

Proves the no-bypass boundary at inventory level: every module that issues a
real provider/browser/model call is classified, and nothing classified as
local_non_agentic makes such calls without an explicit probe_only readback
justification. Migration of deprecated_direct_agent_path entries behind Tau
is blocked on tau#308/310 + scillm#27/28; this test is the ledger that keeps
the seam list honest in the meantime.
"""

from __future__ import annotations

from pathlib import Path

from ask.route_inventory import (
    DEPRECATED_DIRECT,
    INVENTORY,
    LOCAL_NON_AGENTIC,
    ROUTE_CLASSES,
    TAU_NATIVE_AGENT,
    classify,
    scan_dispatch_modules,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "ask"


def test_all_inventory_classes_valid() -> None:
    for module, entry in INVENTORY.items():
        assert entry.route_class in ROUTE_CLASSES, f"{module}: bad class {entry.route_class!r}"
        assert entry.notes.strip(), f"{module}: notes required"


def test_inventory_paths_exist() -> None:
    missing = [m for m in INVENTORY if not (SRC / m).is_file()]
    assert not missing, f"inventory references nonexistent modules: {missing}"


def test_every_dispatch_module_is_classified() -> None:
    flagged = scan_dispatch_modules(SRC)
    unclassified = sorted(m for m in flagged if m not in INVENTORY)
    assert not unclassified, (
        "modules issue provider/browser/model calls but are not in the #1220 "
        f"route inventory: {unclassified}"
    )


def test_local_non_agentic_modules_do_not_dispatch() -> None:
    flagged = scan_dispatch_modules(SRC)
    violations = [
        m
        for m, e in INVENTORY.items()
        if e.route_class == LOCAL_NON_AGENTIC and m in flagged and not e.probe_only
    ]
    assert not violations, (
        f"local_non_agentic modules issue agentic calls without probe_only justification: {violations}"
    )


def test_deprecated_paths_name_migration_target() -> None:
    missing = [
        m for m, e in INVENTORY.items() if e.route_class == DEPRECATED_DIRECT and not e.migration_target
    ]
    assert not missing, f"deprecated direct paths without migration target: {missing}"


def test_tau_native_surface_present() -> None:
    native = [m for m, e in INVENTORY.items() if e.route_class == TAU_NATIVE_AGENT]
    assert "tau_dag.py" in native and "tau_dag_cli.py" in native


def test_classify_defaults_unlisted_to_local() -> None:
    entry = classify("does_not_exist.py")
    assert entry.route_class == LOCAL_NON_AGENTIC


# --- Migration ratchet (#1220) -------------------------------------------
# The deprecated set may only shrink. Migrating a module means moving it to
# tau_native_agent (via ask.tau_harness) or tau_opaque_compat and DELETING it
# from this frozen list; adding a new name here is a policy violation.
FROZEN_DEPRECATED = {
    "ask.py",
    "ask_oracle.py",
    "argue.py",
    "consult.py",
    "deep_review.py",
    "parallel_review.py",
    "scillm_agents.py",
    "scillm_runtime.py",
    "extract_store.py",
    "hybrid.py",
    "os_query.py",
    "delegate/resolver.py",
    "delegate/registry.py",
}


def test_deprecated_set_only_shrinks() -> None:
    current = {m for m, e in INVENTORY.items() if e.route_class == DEPRECATED_DIRECT}
    grown = current - FROZEN_DEPRECATED
    assert not grown, f"new deprecated direct-agent paths are forbidden (#1220): {sorted(grown)}"


def test_migrated_intent_path_is_tau_native() -> None:
    assert INVENTORY["ask_intent.py"].route_class == TAU_NATIVE_AGENT
    assert INVENTORY["tau_harness.py"].route_class == TAU_NATIVE_AGENT
