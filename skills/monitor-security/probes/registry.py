"""Probe framework for monitor-security.

Defines ProbeResult dataclass, ProbeStatus enum, and the probe registry
that maps probe names to their implementation functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from loguru import logger


class ProbeStatus(str, Enum):
    """Probe outcome status."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    FIXED = "fixed"


@dataclass
class ProbeResult:
    """Result from a single probe execution."""
    probe_id: str
    name: str
    tier: int
    status: ProbeStatus
    message: str
    details: dict = field(default_factory=dict)
    auto_fixable: bool = False
    fix_applied: bool = False


# --- Probe registry ---

_REGISTRY: dict[str, dict] = {}


def register_probe(
    probe_id: str,
    name: str,
    tier: int,
    auto_fixable: bool = False,
) -> Callable:
    """Decorator to register a probe function.

    The decorated function must accept (autofix: bool) and return ProbeResult.
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = {
            "probe_id": probe_id,
            "name": name,
            "tier": tier,
            "auto_fixable": auto_fixable,
            "fn": fn,
        }
        return fn
    return decorator


def get_probes(
    tier: int = 0,
    probe_name: str = "",
) -> list[dict]:
    """Get probes filtered by tier and/or name."""
    probes = list(_REGISTRY.values())
    if tier > 0:
        probes = [p for p in probes if p["tier"] == tier]
    if probe_name:
        probes = [p for p in probes if p["name"] == probe_name]
    probes.sort(key=lambda p: p["probe_id"])
    return probes


def run_probes(
    tier: int = 0,
    probe_name: str = "",
    autofix: bool = False,
) -> list[ProbeResult]:
    """Execute probes and collect results."""
    # Import tier modules to trigger registration
    from probes import (  # noqa: F401
        tier0_deterministic,
        tier0_threat_intel,
        tier1_owasp,
        tier2_docker_selfhack,
        tier3_cascade,
    )

    selected = get_probes(tier=tier, probe_name=probe_name)
    if not selected:
        logger.warning("No probes matched tier={} probe={}", tier, probe_name)
        return []

    logger.info("Running {} probe(s)", len(selected))
    results: list[ProbeResult] = []

    for entry in selected:
        probe_id = entry["probe_id"]
        name = entry["name"]
        fn = entry["fn"]
        try:
            logger.info("[{}] Running {}", probe_id, name)
            result = fn(autofix=autofix)
            results.append(result)
            logger.info("[{}] {} -> {}", probe_id, name, result.status.value)
        except Exception as e:
            logger.error("[{}] {} crashed: {}", probe_id, name, e)
            results.append(ProbeResult(
                probe_id=probe_id,
                name=name,
                tier=entry["tier"],
                status=ProbeStatus.FAIL,
                message=f"Probe crashed: {e}",
                details={"error": str(e)},
            ))

    return results
