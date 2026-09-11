"""Validate every registered project's repair seat pair before a lease (#1652).

Invalid seat rotations only failed at dispatch time: setting
opencode-go/deepseek-v4-flash as creator landed fine, then every tick raised
SeatIndependenceError. This validates the registry up front so a seat change
that breaks the contract fails an eval before any lease is burned.

The seat contract already lives in config.assert_cross_provider_seats (creator
authoring-capable, reviewer code-capable and not a browser/oc- seat, providers
differ, not codex-exec). This wraps it over the whole registry and adds a
transport-resolvability check (the resolved execution handler must map without
error). Live provider reachability is out of scope for this deterministic eval.
"""
from __future__ import annotations

from typing import Any

from . import config


def validate_pair(creator: str, reviewer: str) -> str | None:
    """Return an error string if the seat pair violates the contract, else None."""
    try:
        config.assert_cross_provider_seats(creator, reviewer)
    except config.SeatIndependenceError as exc:
        return str(exc)
    # The resolved transport must map without error (unknown handler == unreachable).
    try:
        from .handlers import repair_execution_handlers
        repair_execution_handlers(creator, reviewer)
    except Exception as exc:  # noqa: BLE001
        return f"transport not resolvable: {exc}"
    return None


def validate_registry(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the creator/reviewer pair of every project. [] means all valid."""
    failures: list[dict[str, Any]] = []
    for p in projects:
        creator = p.get("repair_creator")
        reviewer = p.get("repair_reviewer")
        if not creator or not reviewer:
            # A project without a repair lane is not a seat-matrix violation.
            continue
        err = validate_pair(str(creator), str(reviewer))
        if err:
            failures.append({"project_id": p.get("project_id"),
                             "creator": creator, "reviewer": reviewer, "error": err})
    return failures
