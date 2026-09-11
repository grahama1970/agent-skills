"""Capability-aware seat routing (WebGPT design, consumed by project-watchdog).

A fallback is a list of ROUTE ids, not model strings: a model name does not tell
you whether the executor has a writable repo workspace. Each route declares
capabilities (repo_workspace_author / review / chat); a route is eligible for a
seat only when its capabilities superset-cover the seat's required capabilities.
That invariant is validated at load AND at resolve, fail-closed, so a
repair_creator fallback to a non-authoring transport is structurally impossible,
not merely discouraged.

The repair_creator deliberately has NO fallback (only the codex workspace
transport can author) and parks on a codex outage; reviewers and closure
auditors are non-codex-first so review work never burns the scarce authoring
transport. Seat ROUTING lives here; transport mechanics stay internal to
SciLLM/Tau; per-project intent stays in registry/projects.json. The
authoritative home for this policy is Tau (tau/config/seat-routing.yaml); this
project-watchdog copy is the consumable seam that the codex-quota noise lives in
and can be moved to Tau without changing the contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config as _config

CONFIG_FILE = "seat-routing.json"
SCHEMA = "project_watchdog.seat_routing.v1"


class SeatRoutingError(ValueError):
    """A seat-routing config or resolve violated the capability invariant."""


def default_config_path() -> Path:
    return _config.SKILL_DIR / "config" / CONFIG_FILE


def load(path: Path | None = None) -> dict[str, Any]:
    cfg = json.loads((path or default_config_path()).read_text())
    validate(cfg)
    return cfg


def _route_caps(cfg: dict[str, Any], route_id: str) -> set[str]:
    route = cfg["routes"].get(route_id)
    if route is None:
        raise SeatRoutingError(f"seat profile references unknown route {route_id!r}")
    return set(route.get("capabilities") or [])


def validate(cfg: dict[str, Any]) -> None:
    """Fail closed unless every listed fallback route can do the seat's job."""
    if cfg.get("version") != SCHEMA:
        raise SeatRoutingError(f"unknown seat-routing schema {cfg.get('version')!r}")
    routes = cfg.get("routes")
    profiles = cfg.get("seat_profiles")
    if not isinstance(routes, dict) or not routes:
        raise SeatRoutingError("seat-routing config has no routes")
    if not isinstance(profiles, dict) or not profiles:
        raise SeatRoutingError("seat-routing config has no seat_profiles")
    for name, profile in profiles.items():
        required = set(profile.get("requires") or [])
        listed = profile.get("routes") or []
        if not listed:
            raise SeatRoutingError(f"seat profile {name!r} lists no routes")
        for route_id in listed:
            caps = _route_caps(cfg, route_id)
            missing = required - caps
            if missing:
                raise SeatRoutingError(
                    f"seat profile {name!r} route {route_id!r} cannot do the seat's job: "
                    f"missing capabilities {sorted(missing)}"
                )
        if profile.get("when_unavailable") not in {"park_on_quota", "fail_closed"}:
            raise SeatRoutingError(
                f"seat profile {name!r} has invalid when_unavailable "
                f"{profile.get('when_unavailable')!r}"
            )


def resolve(profile_name: str, cfg: dict[str, Any] | None = None, *,
            codex_out: bool = False) -> dict[str, Any]:
    """Ordered eligible routes for a seat right now.

    When ``codex_out`` is set, routes whose executor is the codex CLI are
    dropped (the authoring transport is in a quota/rate outage). If no eligible
    route remains, the seat's ``when_unavailable`` decides: ``park_on_quota``
    parks the lane (the creator case -- no alternate authoring transport), while
    ``fail_closed`` is a hard failure the caller must surface.
    """
    cfg = cfg or load()
    profile = cfg["seat_profiles"].get(profile_name)
    if profile is None:
        raise SeatRoutingError(f"unknown seat profile {profile_name!r}")
    required = set(profile.get("requires") or [])
    eligible: list[str] = []
    for route_id in profile["routes"]:
        route = cfg["routes"][route_id]
        if not required <= set(route.get("capabilities") or []):
            continue  # defensive: validate() already guarantees this
        if codex_out and route.get("executor") == "codex_cli":
            continue
        eligible.append(route_id)
    if eligible:
        return {"profile": profile_name, "action": "dispatch", "routes": eligible,
                "model": cfg["routes"][eligible[0]]["model"], "codex_out": codex_out}
    action = "park" if profile.get("when_unavailable") == "park_on_quota" else "fail_closed"
    return {"profile": profile_name, "action": action, "routes": [],
            "reason": f"no eligible route (codex_out={codex_out})", "codex_out": codex_out}
