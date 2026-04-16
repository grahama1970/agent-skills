"""Tier 1: P27 taxonomy-evolution probe.

Track taxonomy tag usage trends, surface new/deprecated tag candidates.
Extracted from tier1_data.py to keep probe files under 800 LOC.

Inputs: ArangoDB via db.get_db().
Outputs: ProbeResult with tag distribution and drift analysis.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe

# Canonical taxonomy tags — the source of truth
CANONICAL_BRIDGES = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
CANONICAL_TACTICAL = {"Detect", "Harden", "Model", "Isolate", "Restore", "Evade", "Exploit", "Persist"}
CANONICAL_DIMENSIONAL = {
    "Fix", "Optimization", "Refactor", "Hardening", "Debug",
    "Architecture", "Migration", "Attack", "Defend", "Mitigate",
    "Audit", "Compliance",
}

# Thresholds
_EVOLUTION_RARE_THRESHOLD = 5
_EVOLUTION_EMERGING_THRESHOLD = 10
_EVOLUTION_STATE_FILE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/agents/shared/monitor-memory/taxonomy_evolution.jsonl"


def _get_db():
    from db import get_db
    return get_db()


@register_probe("P27", "taxonomy-evolution", tier=1, auto_fixable=False)
def probe_taxonomy_evolution(autofix: bool = False) -> ProbeResult:
    """Track taxonomy tag usage trends, surface new/deprecated tag candidates."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P27", name="taxonomy-evolution", tier=1,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    try:
        rows = list(db.aql.execute("""
            FOR l IN lessons
                FILTER l.taxonomy != null
                RETURN {
                    bridges: l.taxonomy.bridge_attributes || l.bridge_attributes || [],
                    tactical: l.taxonomy.tactical_tags || [],
                    dimensional: l.taxonomy.dimensional_tags || []
                }
        """))
    except Exception as e:
        return ProbeResult(
            probe_id="P27", name="taxonomy-evolution", tier=1,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)},
        )

    if not rows:
        return ProbeResult(
            probe_id="P27", name="taxonomy-evolution", tier=1,
            status=ProbeStatus.SKIP, message="No lessons with taxonomy data",
            details={},
        )

    bridge_counts: dict[str, int] = {}
    tactical_counts: dict[str, int] = {}
    dimensional_counts: dict[str, int] = {}

    for row in rows:
        for tag in (row.get("bridges") or []):
            bridge_counts[tag] = bridge_counts.get(tag, 0) + 1
        for tag in (row.get("tactical") or []):
            tactical_counts[tag] = tactical_counts.get(tag, 0) + 1
        for tag in (row.get("dimensional") or []):
            dimensional_counts[tag] = dimensional_counts.get(tag, 0) + 1

    rare_bridges = [t for t in CANONICAL_BRIDGES if bridge_counts.get(t, 0) < _EVOLUTION_RARE_THRESHOLD]
    rare_tactical = [t for t in CANONICAL_TACTICAL if tactical_counts.get(t, 0) < _EVOLUTION_RARE_THRESHOLD]
    rare_dimensional = [t for t in CANONICAL_DIMENSIONAL if dimensional_counts.get(t, 0) < _EVOLUTION_RARE_THRESHOLD]

    emerging_bridges = {
        t: c for t, c in bridge_counts.items()
        if t not in CANONICAL_BRIDGES and c >= _EVOLUTION_EMERGING_THRESHOLD
    }
    emerging_tactical = {
        t: c for t, c in tactical_counts.items()
        if t not in CANONICAL_TACTICAL and c >= _EVOLUTION_EMERGING_THRESHOLD
    }
    emerging_dimensional = {
        t: c for t, c in dimensional_counts.items()
        if t not in CANONICAL_DIMENSIONAL and c >= _EVOLUTION_EMERGING_THRESHOLD
    }

    snapshot = {
        "timestamp": int(time.time()),
        "total_lessons": len(rows),
        "bridge_counts": dict(sorted(bridge_counts.items(), key=lambda x: -x[1])),
        "tactical_counts": dict(sorted(tactical_counts.items(), key=lambda x: -x[1])),
        "dimensional_counts": dict(sorted(dimensional_counts.items(), key=lambda x: -x[1])),
        "rare_canonical": {
            "bridges": rare_bridges, "tactical": rare_tactical, "dimensional": rare_dimensional,
        },
        "emerging_non_canonical": {
            "bridges": emerging_bridges, "tactical": emerging_tactical, "dimensional": emerging_dimensional,
        },
    }
    try:
        _EVOLUTION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_EVOLUTION_STATE_FILE, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
    except Exception as e:
        logger.warning("P27: failed to write evolution snapshot: {}", e)

    total_emerging = len(emerging_bridges) + len(emerging_tactical) + len(emerging_dimensional)
    total_rare = len(rare_bridges) + len(rare_tactical) + len(rare_dimensional)

    issues = []
    if total_emerging > 0:
        issues.append(f"{total_emerging} emerging non-canonical tags need /assess review")
    if total_rare > 0:
        issues.append(f"{total_rare} canonical tags rarely used (deprecation candidates)")

    if total_emerging > 5:
        status = ProbeStatus.WARN
    elif total_emerging > 0 or total_rare > 3:
        status = ProbeStatus.WARN
    else:
        status = ProbeStatus.PASS

    message = "; ".join(issues) if issues else "Taxonomy tags healthy — all canonical tags active, no emerging drift"

    return ProbeResult(
        probe_id="P27", name="taxonomy-evolution", tier=1,
        status=status,
        message=message,
        details={
            "total_lessons_with_taxonomy": len(rows),
            "bridge_distribution": dict(sorted(bridge_counts.items(), key=lambda x: -x[1])[:10]),
            "tactical_distribution": dict(sorted(tactical_counts.items(), key=lambda x: -x[1])[:10]),
            "rare_canonical": {
                "bridges": rare_bridges, "tactical": rare_tactical, "dimensional": rare_dimensional,
            },
            "emerging_candidates": {
                "bridges": dict(sorted(emerging_bridges.items(), key=lambda x: -x[1])[:5]),
                "tactical": dict(sorted(emerging_tactical.items(), key=lambda x: -x[1])[:5]),
                "dimensional": dict(sorted(emerging_dimensional.items(), key=lambda x: -x[1])[:5]),
            },
            "snapshot_file": str(_EVOLUTION_STATE_FILE),
        },
    )
