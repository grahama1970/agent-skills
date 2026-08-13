"""Route inventory for /ask agentic dispatch seams (agent-skills#1220).

Classifies every module under ``src/ask`` into the four route classes from
ticket #1220's architecture invariant:

- ``local_non_agentic``: no model/subagent call; may remain direct. Modules
  that run health probes or config readbacks are marked ``probe_only``.
- ``tau_native_agent``: compiles to / executes under Tau agent nodes.
- ``tau_opaque_compat``: browser/legacy provider runtime that must be wrapped
  as an explicitly bounded Tau compatibility node.
- ``deprecated_direct_agent_path``: direct model/subagent call that must be
  migrated behind Tau (grahama1970/tau#310) or fail closed.

The inventory is the migration ledger: ``tests/test_route_inventory.py``
scans the source tree for real dispatch call sites and fails if any module
that issues provider/browser/model calls is missing from this table, or if a
``local_non_agentic`` entry issues such calls without a ``probe_only``
justification. Closure of #1220 requires every ``deprecated_direct_agent_path``
entry to migrate to ``tau_native_agent`` or ``tau_opaque_compat``; that final
step is blocked on tau#308/310 and scillm#27/28.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LOCAL_NON_AGENTIC = "local_non_agentic"
TAU_NATIVE_AGENT = "tau_native_agent"
TAU_OPAQUE_COMPAT = "tau_opaque_compat"
DEPRECATED_DIRECT = "deprecated_direct_agent_path"

ROUTE_CLASSES = frozenset({LOCAL_NON_AGENTIC, TAU_NATIVE_AGENT, TAU_OPAQUE_COMPAT, DEPRECATED_DIRECT})


@dataclass(frozen=True)
class RouteEntry:
    route_class: str
    notes: str
    probe_only: bool = False
    migration_target: str = field(default="")


# Keyed by path relative to src/ask, e.g. "kimi_runtime.py", "delegate/resolver.py".
INVENTORY: dict[str, RouteEntry] = {
    # --- Tau-native compile/submit surface -------------------------------
    "tau_dag.py": RouteEntry(TAU_NATIVE_AGENT, "Compiles and submits tau.dag_contract.v1 bundles; Tau owns execution."),
    "tau_dag_cli.py": RouteEntry(TAU_NATIVE_AGENT, "CLI wrapper over tau_dag compile/submit/status."),
    # Sending a prompt into another agent's Herdr pane IS agentic dispatch that
    # does not pass through Tau, so it is a bounded compat runtime rather than
    # a local module excused as probe-only: it sends, it does not merely observe.
    "herdr_cli.py": RouteEntry(
        TAU_OPAQUE_COMPAT,
        "Delivers a prompt to a human-owned Herdr pane through monitor-herdr's transport.",
        migration_target="tau#310 compat node: Herdr seat as a DAG node, blocked on a pane capture lane",
    ),
    "herdr_target.py": RouteEntry(
        LOCAL_NON_AGENTIC,
        "Resolves a name to a Herdr pane and samples pane state to decide addressability.",
        probe_only=True,
    ),
    "ask_dag.py": RouteEntry(TAU_NATIVE_AGENT, "Natural-language DAG inference feeding tau_dag compilation."),
    # --- Browser / legacy provider runtimes (opaque compat) --------------
    "kimi_runtime.py": RouteEntry(TAU_OPAQUE_COMPAT, "surf kimi.submit browser handler.", migration_target="tau#310 compat node"),
    "gemini_runtime.py": RouteEntry(TAU_OPAQUE_COMPAT, "Gemini browser/CLI handler.", migration_target="tau#310 compat node"),
    "perplexity_runtime.py": RouteEntry(TAU_OPAQUE_COMPAT, "Perplexity browser handler.", migration_target="tau#310 compat node"),
    "cursor_browser_runtime.py": RouteEntry(TAU_OPAQUE_COMPAT, "Cursor browser automation runtime.", migration_target="tau#310 compat node"),
    "cursor_browser_project.py": RouteEntry(TAU_OPAQUE_COMPAT, "Cursor browser project workflows.", migration_target="tau#310 compat node"),
    "cursor_browser_project_cli.py": RouteEntry(TAU_OPAQUE_COMPAT, "CLI for cursor browser project workflows.", migration_target="tau#310 compat node"),
    "oracle_adapters.py": RouteEntry(TAU_OPAQUE_COMPAT, "Browser/CLI oracle adapters (webgpt/webclaude/webkimi).", migration_target="tau#310 compat node"),
    "browser_review_runtime.py": RouteEntry(TAU_OPAQUE_COMPAT, "Browser-backed review runtime.", migration_target="tau#310 compat node"),
    "image_generation.py": RouteEntry(TAU_OPAQUE_COMPAT, "Image generation via external provider runtime.", migration_target="tau#310 compat node"),
    "kimi_capacity.py": RouteEntry(TAU_OPAQUE_COMPAT, "Kimi capacity probing tied to browser runtime.", migration_target="tau#310 compat node"),
    # --- Direct model/subagent paths that must migrate -------------------
    "ask.py": RouteEntry(DEPRECATED_DIRECT, "Entry point; spawns visible tmux subagents directly. Deferred: visible-agent projection belongs to tau#309/#1221.", migration_target="tau#310 + #1221 projection"),
    "ask_intent.py": RouteEntry(
        TAU_NATIVE_AGENT,
        "Intent classification runs through ask.tau_harness.run_single_tau_agent; "
        "the direct SciLLM POST survives only behind ASK_DIRECT_INTENT_COMPAT=1.",
    ),
    "tau_harness.py": RouteEntry(
        TAU_NATIVE_AGENT,
        "Shared single-agent Tau-native execution seam; the migration target for "
        "every deprecated_direct_agent_path entry.",
    ),
    "ask_oracle.py": RouteEntry(TAU_OPAQUE_COMPAT, "Oracle orchestration over browser compat adapters; no direct model call of its own.", migration_target="tau#310 compat node"),
    "argue.py": RouteEntry(DEPRECATED_DIRECT, "Deferred: uses SciLLM source-grounding/json_object the Tau transport does not expose yet.", migration_target="tau transport grounding support"),
    "consult.py": RouteEntry(
        TAU_NATIVE_AGENT,
        "Persona consult runs through ask.tau_harness.run_chat_via_tau with a "
        "profile-owned model; direct POST only behind ASK_DIRECT_SCILLM_COMPAT=1.",
    ),
    "deep_review.py": RouteEntry(DEPRECATED_DIRECT, "Deferred: grounded review dispatch pending Tau transport grounding.", migration_target="tau transport grounding support"),
    "parallel_review.py": RouteEntry(DEPRECATED_DIRECT, "Deferred: grounding/response_format semantics pending Tau transport support.", migration_target="tau transport grounding support"),
    "scillm_agents.py": RouteEntry(DEPRECATED_DIRECT, "Standing Codex app-server workers; belongs behind the opencode-serve-compat profile as a Tau compat node.", migration_target="tau#310 opencode-serve-compat"),
    "scillm_runtime.py": RouteEntry(LOCAL_NON_AGENTIC, "Observability metadata helpers; only httpx.get readback, no completion calls.", probe_only=True),
    "extract_store.py": RouteEntry(
        LOCAL_NON_AGENTIC,
        "Delegates to /doc2qra and /memory skills; its one urlopen is a bounded "
        "Memory-service /learn write on :8601, not a model/agent dispatch.",
        probe_only=True,
    ),
    "hybrid.py": RouteEntry(LOCAL_NON_AGENTIC, "Two-phase Memory recall composition; no model call."),
    "os_query.py": RouteEntry(LOCAL_NON_AGENTIC, "OS metadata answers over recall; subprocess import is unused."),
    "delegate/resolver.py": RouteEntry(DEPRECATED_DIRECT, "Coding-delegate resolution; belongs behind opencode-serve-compat.", migration_target="tau#310 opencode-serve-compat"),
    "delegate/registry.py": RouteEntry(DEPRECATED_DIRECT, "Coding-delegate registry; migrates with delegate/resolver.", migration_target="tau#310 opencode-serve-compat"),
    # --- Local, probe-only, or deterministic modules ---------------------
    "ask_config.py": RouteEntry(LOCAL_NON_AGENTIC, "Config load plus JSON health probes.", probe_only=True),
    "config_cli.py": RouteEntry(LOCAL_NON_AGENTIC, "Config CLI; runs readiness probes.", probe_only=True),
    "doctor.py": RouteEntry(LOCAL_NON_AGENTIC, "Health/live checks; readback only.", probe_only=True),
    "preflight.py": RouteEntry(LOCAL_NON_AGENTIC, "Deterministic preflight checks.", probe_only=True),
    "setup_bootstrap.py": RouteEntry(LOCAL_NON_AGENTIC, "Setup/bootstrap probes.", probe_only=True),
    "status.py": RouteEntry(LOCAL_NON_AGENTIC, "Status readback.", probe_only=True),
}

_CALL_PRIMITIVE = re.compile(r"subprocess\.(run|Popen|check_\w+)|httpx\.(post|stream|Client|AsyncClient)|urllib\.request\.urlopen")
_PROVIDER_TERM = re.compile(r"surf|kimi|webgpt|gemini|perplexity|opencode|codex|scillm|chat/completions|localhost:4001", re.IGNORECASE)


def scan_dispatch_modules(src_dir: Path) -> set[str]:
    """Return relative paths of modules that issue provider/browser/model calls.

    A module is flagged when it contains both a real call primitive
    (subprocess/httpx/urlopen) and a provider/browser term. This is the
    deterministic ground truth the inventory test checks INVENTORY against.
    """
    flagged: set[str] = set()
    for path in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _CALL_PRIMITIVE.search(text) and _PROVIDER_TERM.search(text):
            flagged.add(str(path.relative_to(src_dir)))
    return flagged


def classify(module: str) -> RouteEntry:
    """Classification for a module path relative to src/ask; unlisted modules are local."""
    return INVENTORY.get(module, RouteEntry(LOCAL_NON_AGENTIC, "Not in inventory: no known dispatch seam."))
