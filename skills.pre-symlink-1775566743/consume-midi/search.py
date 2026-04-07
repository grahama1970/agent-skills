"""
Search the MIDI fragment library stored in ArangoDB (consume_midi collection)
via the /memory recall Unix socket endpoint.

Usage:
    uv run --project . python search.py --key "D minor" --bpm 85 \
        --instrument bass --mood anger,sadness
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import httpx
import typer
from loguru import logger

app = typer.Typer(
    name="consume-midi-search",
    help="Search the MIDI fragment library by key, BPM, instrument, and mood.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Memory Unix socket transport
# ---------------------------------------------------------------------------

_MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)


def _get_memory_client() -> httpx.Client:
    """Return an httpx Client wired to the memory Unix socket."""
    transport = httpx.HTTPTransport(uds=_MEMORY_SOCKET)
    return httpx.Client(
        transport=transport,
        base_url="http://localhost",
        timeout=30.0,
    )


def _recall_midi_fragments(query: str, k: int = 20) -> list[dict]:
    """
    Call /recall on the memory daemon and return matching MIDI fragments.

    Gracefully returns an empty list if the socket is unavailable.
    """
    try:
        with _get_memory_client() as client:
            resp = client.post("/recall", json={"query": query, "k": k})
            resp.raise_for_status()
            data = resp.json()
    except FileNotFoundError:
        logger.warning("Memory socket not found at {} — is embry-memory running?", _MEMORY_SOCKET)
        return []
    except httpx.HTTPError as exc:
        logger.warning("Memory recall HTTP error: {}", exc)
        return []
    except Exception as exc:
        logger.warning("Memory recall failed: {}", exc)
        return []

    items: list[dict] = data.get("items", []) or data.get("results", [])
    # Filter to consume_midi tagged items only
    midi_items = []
    for item in items:
        tags = item.get("tags", [])
        if "consume_midi" in tags:
            midi_items.append(item)
    return midi_items


def _build_query(
    key: Optional[str],
    bpm: Optional[int],
    instrument: Optional[str],
    mood: Optional[str],
) -> str:
    """Assemble a free-text recall query from the provided filters."""
    parts = ["consume_midi MIDI fragment"]
    if key:
        parts.append(f"key {key}")
    if bpm is not None:
        parts.append(f"bpm {bpm}")
    if instrument:
        parts.append(f"instrument {instrument}")
    if mood:
        # mood can be comma-separated tags
        parts.append(f"mood {mood}")
    return " ".join(parts)


def _matches_filters(
    fragment: dict,
    key: Optional[str],
    bpm: Optional[int],
    instrument: Optional[str],
    mood_tags: list[str],
    bpm_tolerance: int,
) -> bool:
    """Post-filter a recalled fragment against the exact criteria."""
    solution_raw = fragment.get("solution", "{}")
    try:
        data = json.loads(solution_raw) if isinstance(solution_raw, str) else solution_raw
    except json.JSONDecodeError:
        data = {}

    if key and data.get("key", "").lower() != key.lower():
        return False

    if bpm is not None:
        frag_bpm = data.get("bpm")
        if frag_bpm is None:
            return False
        if abs(int(frag_bpm) - bpm) > bpm_tolerance:
            return False

    if instrument and data.get("instrument", "").lower() != instrument.lower():
        return False

    if mood_tags:
        frag_heart: list[str] = data.get("heart", [])
        frag_heart_lower = [t.lower() for t in frag_heart]
        if not any(m.lower() in frag_heart_lower for m in mood_tags):
            return False

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def search(
    key: Optional[str] = typer.Option(
        None,
        "--key",
        help="Musical key filter, e.g. 'D minor' or 'G major'.",
    ),
    bpm: Optional[int] = typer.Option(
        None,
        "--bpm",
        help="Target BPM (tempo). Matches within ±10 BPM by default.",
    ),
    instrument: Optional[str] = typer.Option(
        None,
        "--instrument",
        help="Instrument stem filter, e.g. 'bass', 'drums', 'piano'.",
    ),
    mood: Optional[str] = typer.Option(
        None,
        "--mood",
        help="Comma-separated HMT heart tags, e.g. 'anger,sadness'.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        help="Maximum number of results to return.",
    ),
    bpm_tolerance: int = typer.Option(
        10,
        "--bpm-tolerance",
        help="Allowed BPM deviation when filtering by --bpm.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON instead of formatted text.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug logging.",
    ),
) -> None:
    """Search the MIDI fragment library by key, BPM, instrument, and mood."""
    if not verbose:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    mood_tags: list[str] = [t.strip() for t in mood.split(",") if t.strip()] if mood else []

    query = _build_query(key, bpm, instrument, mood)
    logger.debug("Recall query: {}", query)

    raw_items = _recall_midi_fragments(query, k=limit * 5)
    logger.debug("Recalled {} candidate items from memory", len(raw_items))

    filtered = [
        item
        for item in raw_items
        if _matches_filters(item, key, bpm, instrument, mood_tags, bpm_tolerance)
    ][:limit]

    logger.debug("Filtered to {} matching MIDI fragments", len(filtered))

    if as_json:
        typer.echo(json.dumps(filtered, indent=2, default=str))
        return

    if not filtered:
        typer.echo("No MIDI fragments found matching the given filters.")
        return

    for idx, item in enumerate(filtered, start=1):
        solution_raw = item.get("solution", "{}")
        try:
            data = json.loads(solution_raw) if isinstance(solution_raw, str) else solution_raw
        except json.JSONDecodeError:
            data = {}

        typer.echo(f"[{idx}] {data.get('source_song', 'unknown')} — {data.get('instrument', '?')}")
        typer.echo(f"     Key: {data.get('key', '?')}  BPM: {data.get('bpm', '?')}")
        typer.echo(f"     Heart: {', '.join(data.get('heart', []))}")
        notes = data.get("notes", [])
        typer.echo(f"     Notes: {len(notes)} events")
        typer.echo("")


if __name__ == "__main__":
    app()
