"""CLI for monitor-contacts: the commands run.sh and SKILL.md already document.

Every command reports honestly: a memory-service outage or an empty store is
stated as such, never rendered as "no changes".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from loguru import logger

from .freshness import detect_changes, stale_contacts
from .relationship_graph import reconnect_signals_from_observations
from .store import COLLECTION, DEFAULT_MEMORY_URL, count, load, save

app = typer.Typer(name="monitor-contacts", help="Contact freshness monitoring.",
                  no_args_is_help=True)


def _all_keys(memory_url: str) -> list[str]:
    """Keys are only discoverable by exact read, so callers pass observed
    contacts; a full scan is not available through the memory service."""
    return []


@app.command()
def status(memory_url: str = typer.Option(DEFAULT_MEMORY_URL, "--memory-url"),
           json_output: bool = typer.Option(True, "--json/--no-json")) -> None:
    """Service and store status."""
    n = count(memory_url)
    payload = {
        "schema": "monitor_contacts.status.v1",
        "collection": COLLECTION,
        "memory_url": memory_url,
        "memory_reachable": n >= 0,
        "contacts_stored": None if n < 0 else n,
        "note": ("memory service unreachable; contact count unknown"
                 if n < 0 else "store reachable"),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True) if json_output
               else f"contacts: {payload['contacts_stored']}")


@app.command()
def report(memory_url: str = typer.Option(DEFAULT_MEMORY_URL, "--memory-url"),
           stale_days: int = typer.Option(30, "--stale-days")) -> None:
    """Freshness report over the stored contacts."""
    n = count(memory_url)
    typer.echo(json.dumps({
        "schema": "monitor_contacts.report.v1",
        "collection": COLLECTION,
        "contacts_stored": None if n < 0 else n,
        "stale_days": stale_days,
        "note": ("The memory service exposes no scan endpoint, so a freshness "
                 "sweep runs over contacts supplied by a cycle (see `cycle "
                 "--input`), not over the whole collection."),
    }, indent=2, sort_keys=True))


@app.command()
def cycle(
    input_file: str = typer.Option(..., "--input",
                                   help="JSON list of observed contacts "
                                        "({name, org, role} each)."),
    memory_url: str = typer.Option(DEFAULT_MEMORY_URL, "--memory-url"),
    research_limit: int = typer.Option(5, "--research-limit"),
    commit: bool = typer.Option(False, "--commit",
                                help="Persist observations. Off by default."),
) -> None:
    """One monitoring cycle: load stored, diff, research, optionally persist."""
    from .store import contact_key

    observed = json.loads(open(input_file, encoding="utf-8").read())
    for c in observed:
        c.setdefault("_key", contact_key(str(c.get("name") or "")))
        c.setdefault("observed_at", datetime.now(UTC).isoformat())
    stored = load([str(c["_key"]) for c in observed], memory_url)
    changes = detect_changes(stored, observed, research_limit=research_limit)
    stale = stale_contacts(list(stored.values()))
    saved = save(observed, memory_url) if commit else 0
    typer.echo(json.dumps({
        "schema": "monitor_contacts.cycle.v1",
        "observed": len(observed),
        "had_prior": len(stored),
        "changes": changes,
        "stale_contacts": stale,
        "persisted": saved,
        "committed": commit,
        "first_run_note": (None if stored else
                           "no prior records for these contacts: stored-vs-observed "
                           "diffs begin next cycle; public-signal changes still apply"),
    }, indent=2, sort_keys=True))


@app.command()
def changes(memory_url: str = typer.Option(DEFAULT_MEMORY_URL, "--memory-url"),
            since: str = typer.Option("30d", "--since")) -> None:
    """Recent changes. Requires a cycle to have run; reports honestly if not."""
    typer.echo(json.dumps({
        "schema": "monitor_contacts.changes.v1",
        "since": since,
        "changes": [],
        "note": ("Change history is emitted per cycle. Run `cycle --input <file> "
                 "--commit` on a fresh observation set; this command does not "
                 "invent history it does not have."),
    }, indent=2, sort_keys=True))


@app.command("relationship-graph")
def relationship_graph(
    input_file: Path = typer.Option(..., "--input", exists=True, dir_okay=False),
    source_id: str = typer.Option("monitor-contacts:observations", "--source-id"),
) -> None:
    """Export local-only reconnect relationship signals for consumers."""
    observations = json.loads(input_file.read_text(encoding="utf-8"))
    if not isinstance(observations, list):
        raise typer.BadParameter("--input must be a JSON list of contact observations")
    signals = reconnect_signals_from_observations(observations, source_id=source_id)
    typer.echo(json.dumps({
        "schema": "monitor_contacts.relationship_graph.v1",
        "source_id": source_id,
        "observed": len(observations),
        "relationship_signals": signals,
        "external_effects": False,
        "note": "Human-decision records only; no email, LinkedIn, Meetup, or ATS effect is authorized.",
    }, indent=2, sort_keys=True))


@app.command()
def monitor(interval: str = typer.Option("weekly", "--interval")) -> None:
    """Foreground monitoring is delegated to /scheduler rather than a daemon."""
    logger.info("monitor-contacts does not run its own daemon")
    typer.echo(json.dumps({
        "schema": "monitor_contacts.monitor.v1",
        "status": "DELEGATED",
        "interval": interval,
        "note": ("Scheduling belongs to /scheduler. Register a job that runs "
                 "`monitor-contacts cycle --input <observations> --commit` "
                 "instead of running a second long-lived daemon."),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
