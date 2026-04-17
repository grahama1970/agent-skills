"""Tier 2: Persona Lifecycle probes (report only).

P05 journal-completeness  — Check if all personas journaled today
P06 dream-completeness    — Check dream output for Horus & Embry
P07 content-scan          — Check monitor-personas ran in last 24h
P14 scope-growth          — Count new lessons per scope in last 24h
P15 feed-freshness        — Check consume-feed state recency
P16 episodic-health       — Check monitor-episodic-archiver health

Inputs: ArangoDB, filesystem state files.
Outputs: ProbeResult per probe.
"""
from __future__ import annotations
import os

import json
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe


def _get_db():
    """Lazy import to avoid crashing if ArangoDB is unreachable at import time."""
    from db import get_db
    return get_db()


# ── P05: journal-completeness ────────────────────────────────────────────────


@register_probe("P05", "journal-completeness", tier=2)
def probe_journal_completeness(autofix: bool = False) -> ProbeResult:
    """Check if all personas have journaled today."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P05", name="journal-completeness", tier=2,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    if not db.has_collection("persona_journals"):
        return ProbeResult(
            probe_id="P05", name="journal-completeness", tier=2,
            status=ProbeStatus.SKIP,
            message="persona_journals collection does not exist",
            details={},
        )

    today = date.today().isoformat()
    aql = """
    FOR p IN @personas
      LET has_journal = LENGTH(
        FOR j IN persona_journals
          FILTER j.persona == p AND j.date == @today
          LIMIT 1
          RETURN 1
      ) > 0
      RETURN {persona: p, journaled_today: has_journal}
    """
    try:
        rows = list(db.aql.execute(aql, bind_vars={
            "personas": config.PERSONAS_JOURNAL,
            "today": today,
        }))
    except Exception as e:
        return ProbeResult(
            probe_id="P05", name="journal-completeness", tier=2,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)},
        )

    missing = [r["persona"] for r in rows if not r.get("journaled_today")]
    journaled = [r["persona"] for r in rows if r.get("journaled_today")]

    status = ProbeStatus.PASS if not missing else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P05", name="journal-completeness", tier=2,
        status=status,
        message=f"{len(journaled)}/{len(config.PERSONAS_JOURNAL)} journaled today"
              + (f", missing: {', '.join(missing)}" if missing else ""),
        details={"journaled": journaled, "missing": missing, "date": today},
    )


# ── P06: dream-completeness ─────────────────────────────────────────────────


@register_probe("P06", "dream-completeness", tier=2)
def probe_dream_completeness(autofix: bool = False) -> ProbeResult:
    """Check dream output for Horus and Embry."""
    today = date.today().isoformat()
    results = {}

    for persona in config.PERSONAS_DREAM:
        dream_dir = config.MEMORY_PROJECT_PATH / "persona" / "dreams" / today
        manifest = dream_dir / "manifest.yaml"
        results[persona] = manifest.exists()

    missing = [p for p, ok in results.items() if not ok]

    status = ProbeStatus.PASS if not missing else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P06", name="dream-completeness", tier=2,
        status=status,
        message=f"{len(results) - len(missing)}/{len(results)} dreamed today"
              + (f", missing: {', '.join(missing)}" if missing else ""),
        details={"results": results, "date": today},
    )


# ── P07: content-scan ────────────────────────────────────────────────────────


@register_probe("P07", "content-scan", tier=2)
def probe_content_scan(autofix: bool = False) -> ProbeResult:
    """Check monitor-personas state files for recent activity."""
    state_dir = Path.home() / ".pi/monitor-personas"
    if not state_dir.exists():
        return ProbeResult(
            probe_id="P07", name="content-scan", tier=2,
            status=ProbeStatus.SKIP,
            message="monitor-personas state directory not found",
            details={"state_dir": str(state_dir)},
        )

    state_files = list(state_dir.glob("state_*.json"))
    if not state_files:
        # Try the main state file
        main_state = state_dir / "state.json"
        if main_state.exists():
            state_files = [main_state]

    if not state_files:
        return ProbeResult(
            probe_id="P07", name="content-scan", tier=2,
            status=ProbeStatus.WARN,
            message="No state files found in monitor-personas",
            details={"state_dir": str(state_dir)},
        )

    stale_files = []
    fresh_files = []
    now = time.time()
    threshold = 24 * 3600

    for sf in state_files:
        try:
            data = json.loads(sf.read_text())
            last_run = data.get("last_run") or data.get("last_updated", "")
            if last_run:
                dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                if age_s > threshold:
                    stale_files.append(sf.name)
                else:
                    fresh_files.append(sf.name)
            else:
                # Check file mtime as fallback
                if (now - sf.stat().st_mtime) > threshold:
                    stale_files.append(sf.name)
                else:
                    fresh_files.append(sf.name)
        except (json.JSONDecodeError, OSError, ValueError):
            stale_files.append(sf.name)

    status = ProbeStatus.PASS if not stale_files else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P07", name="content-scan", tier=2,
        status=status,
        message=f"{len(fresh_files)} fresh, {len(stale_files)} stale state files",
        details={"fresh": fresh_files, "stale": stale_files},
    )


# ── P14: scope-growth ────────────────────────────────────────────────────────


@register_probe("P14", "scope-growth", tier=2)
def probe_scope_growth(autofix: bool = False) -> ProbeResult:
    """Count new lessons per scope in last 24 hours."""
    try:
        db = _get_db()
    except Exception as e:
        return ProbeResult(
            probe_id="P14", name="scope-growth", tier=2,
            status=ProbeStatus.SKIP, message=f"ArangoDB unreachable: {e}",
            details={"error": str(e)},
        )

    yesterday = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    ).isoformat()

    aql = """
    FOR l IN lessons
      FILTER l.created_at >= @yesterday
      COLLECT scope = l.scope WITH COUNT INTO cnt
      SORT cnt DESC
      RETURN {scope, count: cnt}
    """
    try:
        rows = list(db.aql.execute(aql, bind_vars={"yesterday": yesterday}))
    except Exception as e:
        return ProbeResult(
            probe_id="P14", name="scope-growth", tier=2,
            status=ProbeStatus.FAIL, message=f"AQL query failed: {e}",
            details={"error": str(e)},
        )

    total_new = sum(r["count"] for r in rows)

    # Pure metric — always PASS
    return ProbeResult(
        probe_id="P14", name="scope-growth", tier=2,
        status=ProbeStatus.PASS,
        message=f"{total_new} new lessons today across {len(rows)} scope(s)",
        details={"scopes": rows, "total_new": total_new},
    )


# ── P15: feed-freshness ─────────────────────────────────────────────────────


@register_probe("P15", "feed-freshness", tier=2)
def probe_feed_freshness(autofix: bool = False) -> ProbeResult:
    """Check consume-feed state for feed recency."""
    state_file = Path.home() / ".pi/consume-feed/state.json"
    if not state_file.exists():
        return ProbeResult(
            probe_id="P15", name="feed-freshness", tier=2,
            status=ProbeStatus.SKIP,
            message="consume-feed state not found",
            details={"state_file": str(state_file)},
        )

    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P15", name="feed-freshness", tier=2,
            status=ProbeStatus.FAIL, message=f"Failed to read feed state: {e}",
            details={"error": str(e)},
        )

    feeds = data.get("feeds", {})
    if not feeds:
        return ProbeResult(
            probe_id="P15", name="feed-freshness", tier=2,
            status=ProbeStatus.WARN,
            message="No feeds tracked in state",
            details={},
        )

    stale = []
    fresh = []
    threshold = 24 * 3600

    for name, info in feeds.items():
        last_fetched = info.get("last_fetched", "")
        if last_fetched:
            try:
                dt = datetime.fromisoformat(last_fetched.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                if age_s > threshold:
                    stale.append(name)
                else:
                    fresh.append(name)
            except ValueError:
                stale.append(name)
        else:
            stale.append(name)

    status = ProbeStatus.PASS if not stale else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P15", name="feed-freshness", tier=2,
        status=status,
        message=f"{len(fresh)} fresh, {len(stale)} stale feeds",
        details={"fresh": fresh, "stale": stale},
    )


# ── P16: episodic-health ─────────────────────────────────────────────────────


@register_probe("P16", "episodic-health", tier=2)
def probe_episodic_health(autofix: bool = False) -> ProbeResult:
    """Check monitor-episodic-archiver health."""
    archiver_sh = config.PROJECT_ROOT / ".pi/skills/monitor-episodic-archiver/run.sh"
    if not archiver_sh.exists():
        return ProbeResult(
            probe_id="P16", name="episodic-health", tier=2,
            status=ProbeStatus.SKIP,
            message="monitor-episodic-archiver not found",
            details={},
        )

    try:
        result = subprocess.run(
            [str(archiver_sh), "check", "--json"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return ProbeResult(
            probe_id="P16", name="episodic-health", tier=2,
            status=ProbeStatus.FAIL,
            message=f"Episodic archiver check failed: {e}",
            details={"error": str(e)},
        )

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}

    health = data.get("health", "unknown")
    status_map = {
        "healthy": ProbeStatus.PASS,
        "warning": ProbeStatus.WARN,
        "critical": ProbeStatus.FAIL,
    }
    status = status_map.get(health, ProbeStatus.WARN)

    return ProbeResult(
        probe_id="P16", name="episodic-health", tier=2,
        status=status,
        message=f"Episodic archiver: {health}",
        details=data,
    )
