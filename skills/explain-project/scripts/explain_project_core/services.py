"""Ambient skill-service liveness probes for the cockpit.

These are informational probes of sibling skill surfaces
($debugger bridge files, $live-evidence HTTP API, $surf tab
transport). They are separate from the revision-fenced cockpit
proof state and never claim adapter receipt semantics.

Every probe fails closed: unreachable, unconfigured, or stale
surfaces report OFFLINE / NOT_CONFIGURED, never READY.
"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import time
from collections.abc import Callable

import httpx

from .models import (
    ServiceHealth,
)

CACHE_TTL_SECONDS = 8.0

_cache: dict[tuple[str, str], tuple[float, ServiceHealth]] = {}


def _cached(
    key: str,
    fingerprint: str,
    build: Callable[[], ServiceHealth],
) -> ServiceHealth:
    entry = _cache.get((key, fingerprint))
    now = time.monotonic()
    if entry is not None and now - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]
    health = build()
    _cache[(key, fingerprint)] = (now, health)
    return health


def probe_debugger(repo: Path | None) -> ServiceHealth:
    """Freshness of the most recent VS Code debugger-bridge status."""
    fingerprint = str(repo or "none")

    def build() -> ServiceHealth:
        if repo is None:
            return ServiceHealth(
                service="debugger",
                status="NOT_CONFIGURED",
                detail="no --repo bound to cockpit",
            )

        bridge_dir = repo / ".vscode" / "debugger-bridge"
        candidates: list[Path] = []
        if bridge_dir.is_dir():
            # status files = debug sessions; request.json /
            # processed-ids.json = any live bridge request (e.g.
            # `open --bridge` selections). Bridge liveness is the
            # newest of all three.
            candidates = [
                bridge_dir / "request.json",
                bridge_dir / "processed-ids.json",
                *bridge_dir.glob("status.*.json"),
            ]
        newest = max(
            (p.stat().st_mtime for p in candidates if p.is_file()),
            default=None,
        )

        if newest is None:
            return ServiceHealth(
                service="debugger",
                status="NOT_CONFIGURED",
                detail="no bridge artifacts in --repo",
            )

        age = time.time() - newest
        if age > 900:
            return ServiceHealth(
                service="debugger",
                status="DEGRADED",
                detail=f"bridge idle {int(age // 60)}m",
            )

        return ServiceHealth(
            service="debugger",
            status="ONLINE",
            detail=f"bridge answered {int(age)}s ago",
        )

    return _cached("debugger", fingerprint, build)


def probe_live_evidence(
    url: str | None,
) -> ServiceHealth:
    """Reachability of the live-evidence local HTTP API."""
    base = url or os.environ.get(
        "EXPLAIN_PROJECT_LIVE_EVIDENCE_URL",
        "http://127.0.0.1:8799",
    )

    def build() -> ServiceHealth:
        try:
            response = httpx.get(
                f"{base.rstrip('/')}/api/health",
                timeout=1.5,
            )
        except httpx.HTTPError:
            return ServiceHealth(
                service="live_evidence",
                status="OFFLINE",
                detail=f"no listener at {base}",
            )

        if response.status_code != 200:
            return ServiceHealth(
                service="live_evidence",
                status="DEGRADED",
                detail=(
                    f"/api/health returned "
                    f"{response.status_code}"
                ),
            )

        phase = "reachable"
        try:
            snapshot = httpx.get(
                f"{base.rstrip('/')}/api/state",
                timeout=1.5,
            )
            if snapshot.status_code == 200:
                value = snapshot.json()
                if isinstance(value, dict):
                    session_value = value.get("session")
                    if isinstance(session_value, dict):
                        phase = str(
                            session_value.get("status")
                            or "reachable",
                        )
        except httpx.HTTPError:
            pass

        return ServiceHealth(
            service="live_evidence",
            status="ONLINE",
            detail=f"session phase: {phase}",
        )

    return _cached("live_evidence", base, build)


def _surf_runner() -> Path | None:
    override = os.environ.get(
        "EXPLAIN_PROJECT_SURF_RUNNER",
    )
    if override:
        path = Path(override)
        return path if path.is_file() else None

    default = (
        Path(__file__).resolve()
        .parents[3]
        / "surf"
        / "run.sh"
    )
    return default if default.is_file() else None


def probe_surf(tab_id: str | None) -> ServiceHealth:
    """Surf transport reachability plus optional tab-id binding."""
    fingerprint = tab_id or "none"

    def build() -> ServiceHealth:
        runner = _surf_runner()
        if runner is None:
            return ServiceHealth(
                service="surf",
                status="NOT_CONFIGURED",
                detail="skills/surf/run.sh not found",
            )

        try:
            completed = subprocess.run(
                ["bash", str(runner), "tab.list", "--json"],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except (subprocess.TimeoutExpired, OSError):
            return ServiceHealth(
                service="surf",
                status="OFFLINE",
                detail="tab.list timed out or failed",
            )

        if completed.returncode != 0:
            return ServiceHealth(
                service="surf",
                status="OFFLINE",
                detail=(
                    "tab.list exit "
                    f"{completed.returncode}"
                ),
            )

        try:
            import json

            tabs = json.loads(completed.stdout)
        except ValueError:
            return ServiceHealth(
                service="surf",
                status="DEGRADED",
                detail="tab.list output not JSON",
            )

        if not tab_id:
            count = len(tabs) if isinstance(tabs, list) else 0
            return ServiceHealth(
                service="surf",
                status="ONLINE",
                detail=f"transport up; {count} tabs; no tab bound",
            )

        match = next(
            (
                tab
                for tab in tabs
                if isinstance(tab, dict)
                and str(tab.get("id")) == tab_id
            ),
            None,
        ) if isinstance(tabs, list) else None

        if match is None:
            return ServiceHealth(
                service="surf",
                status="DEGRADED",
                detail=f"transport up; tab {tab_id} not open",
            )

        return ServiceHealth(
            service="surf",
            status="ONLINE",
            detail=(
                f"tab {tab_id} · "
                f"{str(match.get('title', ''))[:48]}"
            ),
        )

    return _cached("surf", fingerprint, build)


def probe_services(
    repo: Path | None,
    live_evidence_url: str | None = None,
    surf_tab_id: str | None = None,
) -> list[ServiceHealth]:
    return [
        probe_live_evidence(live_evidence_url),
        probe_debugger(repo),
        probe_surf(surf_tab_id),
    ]
