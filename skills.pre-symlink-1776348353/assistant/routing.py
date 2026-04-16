"""Dual-tagger routing for Heart/Mind taxonomy architecture.

Heart and Mind are ORTHOGONAL dimensions — every input gets BOTH taggers,
regardless of scope.  Scope is used only to resolve legacy aliases and to
look up model registry configuration; it no longer gates which dimension
runs.

Rules:
  - ALL inputs → run BOTH mind-tagger (8 tactical tags) AND heart-tagger
    (6 emotional tags: anger/fear/joy/neutral/sadness/trust).
  - The text content, not the scope, determines which tags are emitted.
  - "tactical-tagger" is transparently rewritten to "mind-tagger" (legacy alias).

The scope→tagger mapping from the registry's ``preferred_scopes`` fields is
still read for configuration lookup, but no longer used to choose a single
tagger. Adding a new scope to a tagger registry entry still takes effect
without a code change — it now affects priority ordering within a dimension,
not which dimension runs.
"""

from __future__ import annotations

from typing import Any, Dict, List


#: Tasks that participate in Heart/Mind scope routing.
_TAXONOMY_TAGGER_TASKS = {"mind-tagger", "heart-tagger", "tactical-tagger", "bridge-tagger"}

#: Canonical alias for the renamed tactical tagger.
_LEGACY_ALIASES = {"tactical-tagger": "mind-tagger"}

#: The two required tagger tasks in canonical order.
DUAL_TAGGER_TASKS: List[str] = ["mind-tagger", "heart-tagger"]


def _build_scope_index(registry: Dict[str, Any]) -> Dict[str, str]:
    """Build {scope_token → task_name} from classifier preferred_scopes.

    Only indexes tasks that are taxonomy taggers. Reads the registry at
    call time so changes take effect without a process restart.
    """
    index: Dict[str, str] = {}
    for task_name, cfg in registry.get("classifiers", {}).items():
        if task_name not in _TAXONOMY_TAGGER_TASKS:
            continue
        for scope in cfg.get("preferred_scopes", []):
            index[scope.lower()] = task_name
    return index


def resolve_taxonomy_tagger(scope: str, task: str, registry: Dict[str, Any]) -> str:
    """Return the resolved single-tagger task name (legacy / bridge-tagger path).

    Most callers should use ``resolve_taxonomy_taggers`` (plural) instead,
    which always returns both mind and heart taggers.  This function is kept
    for backward compatibility with callers that only run one tagger at a time
    (e.g. bridge-tagger which is neither mind nor heart).

    Args:
        scope:    Persona/domain scope string from the caller (may be empty).
        task:     The originally requested task name (may be a legacy name
                  like "tactical-tagger").
        registry: Loaded model registry dict (passed in, not re-read here).

    Returns:
        Resolved task name.  For mind/heart tagger tasks, prefer
        ``resolve_taxonomy_taggers`` to get both dimensions.
    """
    effective_task = _LEGACY_ALIASES.get(task, task)

    # If the caller is asking for a bridge-tagger or other non-dimensional
    # task, return it directly — no dual-routing needed.
    if effective_task not in {"mind-tagger", "heart-tagger"}:
        return effective_task

    # For mind/heart tasks: caller explicitly chose a dimension — honour it.
    return effective_task


def resolve_taxonomy_taggers(scope: str, task: str, registry: Dict[str, Any]) -> List[str]:
    """Return the list of tagger tasks to run for the given input.

    Heart and Mind are orthogonal dimensions.  This function ALWAYS returns
    both ["mind-tagger", "heart-tagger"] for any taxonomy-related task so
    that every document is annotated along both dimensions.

    The ``scope`` argument is retained for API stability and future use
    (e.g. loading dimension-specific model checkpoints from the registry),
    but it no longer controls which dimensions run.

    Args:
        scope:    Persona/domain scope string from the caller (may be empty).
        task:     The originally requested task name.  If it is a non-taxonomy
                  task (e.g. "bridge-tagger" alone), only that task is returned.
        registry: Loaded model registry dict (passed in, not re-read here).

    Returns:
        Ordered list of task names to execute.  For taxonomy classification
        this is always ["mind-tagger", "heart-tagger"].
    """
    effective_task = _LEGACY_ALIASES.get(task, task)

    # Non-taxonomy tasks pass through unchanged.
    if effective_task and effective_task not in _TAXONOMY_TAGGER_TASKS:
        return [effective_task]

    # bridge-tagger is a separate dimension — return it alone if explicitly
    # requested, but include both mind+heart for everything else.
    if effective_task == "bridge-tagger":
        return ["bridge-tagger"]

    # Default: run both orthogonal dimensions.
    return list(DUAL_TAGGER_TASKS)
