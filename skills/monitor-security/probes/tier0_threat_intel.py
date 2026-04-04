"""Tier 0.5 — Threat Intelligence probes (hourly, automated).

P08: threat-intel-ingest
P09: threat-intel-crossref
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger

import config
from probes import register_probe, ProbeResult, ProbeStatus


@register_probe("P08", "threat-intel-ingest", tier=1, auto_fixable=False)
def probe_threat_intel_ingest(autofix: bool = False) -> ProbeResult:
    """Check that hourly threat intel ingestion is running and recent."""
    digest_path = config.THREAT_INTEL_DIGEST

    if not digest_path.exists():
        return ProbeResult(
            probe_id="P08", name="threat-intel-ingest", tier=1,
            status=ProbeStatus.WARN,
            message="No threat intel digest found (run 'threat-intel' first)",
            details={"digest_path": str(digest_path)},
        )

    try:
        data = json.loads(digest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P08", name="threat-intel-ingest", tier=1,
            status=ProbeStatus.FAIL,
            message=f"Failed to parse digest: {e}",
        )

    last_updated = data.get("last_updated", "")
    total_runs = data.get("total_runs", 0)

    # Check freshness (should be updated within last 2 hours)
    if last_updated:
        try:
            ts = time.mktime(time.strptime(last_updated, "%Y-%m-%dT%H:%M:%S"))
            age_hours = (time.time() - ts) / 3600
        except ValueError:
            age_hours = 999

        if age_hours > 2:
            return ProbeResult(
                probe_id="P08", name="threat-intel-ingest", tier=1,
                status=ProbeStatus.WARN,
                message=f"Threat intel digest is {age_hours:.1f}h old (expected < 2h)",
                details={"last_updated": last_updated, "total_runs": total_runs, "age_hours": round(age_hours, 1)},
            )

    latest_run = data.get("latest_run", {})
    cf_status = latest_run.get("consume_feed", {}).get("status", "unknown")
    sb_status = latest_run.get("social_bridge", {}).get("status", "unknown")

    if cf_status == "error" or sb_status == "error":
        return ProbeResult(
            probe_id="P08", name="threat-intel-ingest", tier=1,
            status=ProbeStatus.WARN,
            message=f"Threat intel had errors (feed={cf_status}, social={sb_status})",
            details={"latest_run": latest_run},
        )

    return ProbeResult(
        probe_id="P08", name="threat-intel-ingest", tier=1,
        status=ProbeStatus.PASS,
        message=f"Threat intel active ({total_runs} runs, last: {last_updated})",
        details={"total_runs": total_runs, "last_updated": last_updated},
    )


@register_probe("P09", "threat-intel-crossref", tier=1, auto_fixable=False)
def probe_threat_intel_crossref(autofix: bool = False) -> ProbeResult:
    """Cross-reference accumulated CVEs against embry-os dependency manifests."""
    digest_path = config.THREAT_INTEL_DIGEST

    if not digest_path.exists():
        return ProbeResult(
            probe_id="P09", name="threat-intel-crossref", tier=1,
            status=ProbeStatus.SKIP,
            message="No threat intel digest available",
        )

    try:
        data = json.loads(digest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ProbeResult(
            probe_id="P09", name="threat-intel-crossref", tier=1,
            status=ProbeStatus.FAIL,
            message="Failed to read threat intel digest",
        )

    matches = data.get("matches", [])
    crossref = data.get("latest_run", {}).get("crossref", {})

    if not matches:
        return ProbeResult(
            probe_id="P09", name="threat-intel-crossref", tier=1,
            status=ProbeStatus.PASS,
            message="No CVEs match embry-os dependencies",
            details={
                "python_deps": crossref.get("python_deps", 0),
                "node_deps": crossref.get("node_deps", 0),
            },
        )

    # Separate by severity
    critical = [m for m in matches if m.get("severity") == "critical"]
    high = [m for m in matches if m.get("severity") == "high"]

    if critical:
        status = ProbeStatus.FAIL
        msg = f"{len(critical)} CRITICAL + {len(high)} HIGH CVEs match dependencies"
    elif high:
        status = ProbeStatus.WARN
        msg = f"{len(high)} HIGH CVEs match dependencies"
    else:
        status = ProbeStatus.WARN
        msg = f"{len(matches)} CVEs match dependencies"

    return ProbeResult(
        probe_id="P09", name="threat-intel-crossref", tier=1,
        status=status,
        message=msg,
        details={
            "total_matches": len(matches),
            "critical": len(critical),
            "high": len(high),
            "affected_deps": list(set(m.get("matched_dependency", "") for m in matches)),
        },
    )
