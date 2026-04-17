"""Manual auto-fix dispatcher for monitor-memory.

Allows running a specific probe's auto-fix action via `./run.sh fix <name>`.

Inputs: probe name string.
Outputs: runs the probe with autofix=True, reports result.
"""
from __future__ import annotations

from loguru import logger

from probes import ProbeStatus, run_probes
from reporter import report_results


def run_fix(probe_name: str) -> None:
    """Run a specific probe with autofix enabled and report."""
    logger.info("Manual fix requested for probe: {}", probe_name)

    results = run_probes(tier=0, probe_name=probe_name, autofix=True)

    if not results:
        logger.error("Probe '{}' not found in registry", probe_name)
        raise SystemExit(1)

    result = results[0]
    report_results(results, json_output=False)

    if not result.auto_fixable:
        logger.warning("Probe '{}' is not auto-fixable", probe_name)
    elif result.fix_applied:
        logger.info("Fix applied successfully for '{}'", probe_name)
    elif result.status == ProbeStatus.PASS:
        logger.info("Probe '{}' is already passing, no fix needed", probe_name)
    else:
        logger.error("Fix was attempted but did not resolve '{}'", probe_name)
