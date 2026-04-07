"""
Ingest MIDI fragments into ArangoDB (consume_midi collection) via the
/memory learn Unix socket endpoint.

Usage:
    # Store a single fragment directly:
    uv run --project . python ingest.py \
        --source-song "Wish You Were Here" --artist "Pink Floyd" \
        --key "G major" --bpm 63 --instrument guitar \
        --heart "Fragility,Resilience"

    # Bulk-ingest from a stem directory (expects *.mid / *.json files):
    uv run --project . python ingest.py \
        --stem-dir /data/stems/wish-you-were-here \
        --source-song "Wish You Were Here" --artist "Pink Floyd"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger

app = typer.Typer(
    name="consume-midi-ingest",
    help="Store MIDI fragments with key, BPM, instrument, and heart tags into memory.",
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


def _learn_fragment(fragment: dict) -> bool:
    """
    POST a MIDI fragment to /learn on the memory daemon.

    The fragment is serialised as the `solution` field; the `problem` string
    is a human-readable description for search recall.

    Returns True on success, False on failure (with warning log).
    """
    source = fragment.get("source_song", "unknown")
    artist = fragment.get("artist", "")
    instrument = fragment.get("instrument", "unknown")
    key = fragment.get("key", "")
    bpm = fragment.get("bpm", "")

    problem = (
        f"MIDI fragment: {artist} - {source} | {instrument} | key {key} bpm {bpm}"
        if artist
        else f"MIDI fragment: {source} | {instrument} | key {key} bpm {bpm}"
    )

    heart_tags: list[str] = fragment.get("heart", [])
    tags = ["consume_midi", instrument] + heart_tags

    payload = {
        "problem": problem[:240],
        "solution": json.dumps(fragment),
        "scope": "operational",
        "tags": tags,
    }

    try:
        with _get_memory_client() as client:
            resp = client.post("/learn", json=payload)
            resp.raise_for_status()
            data = resp.json()
        ok = data.get("stored", data.get("ok", False))
        if ok:
            logger.info("Stored fragment: {}", problem[:80])
        else:
            logger.warning("Memory learn returned ok=false for: {}", problem[:80])
        return bool(ok)
    except FileNotFoundError:
        logger.warning(
            "Memory socket not found at {} — is embry-memory running?", _MEMORY_SOCKET
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning("Memory learn HTTP error: {}", exc)
        return False
    except Exception as exc:
        logger.warning("Memory learn failed: {}", exc)
        return False


def _load_stem_dir(
    stem_dir: Path,
    source_song: str,
    artist: str,
) -> list[dict]:
    """
    Scan *stem_dir* for MIDI fragment JSON files and return a list of fragment dicts.

    Expected JSON schema per file:
      {
        "instrument": "bass",
        "key": "D minor",
        "bpm": 85,
        "heart": ["anger", "sadness"],
        "notes": [...]          # piano-roll-spec note events
      }
    Missing fields are filled from CLI arguments where possible.
    """
    fragments: list[dict] = []
    json_files = list(stem_dir.glob("*.json"))
    if not json_files:
        logger.warning("No *.json files found in {}", stem_dir)
        return fragments

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping {}: {}", jf.name, exc)
            continue

        # Merge CLI-level metadata as defaults
        data.setdefault("source_song", source_song)
        data.setdefault("artist", artist)
        data.setdefault("instrument", jf.stem)  # filename as fallback instrument name
        data.setdefault("key", "")
        data.setdefault("bpm", None)
        data.setdefault("heart", [])
        data.setdefault("notes", [])
        fragments.append(data)

    logger.info("Loaded {} fragments from {}", len(fragments), stem_dir)
    return fragments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    source_song: str = typer.Option(
        ...,
        "--source-song",
        help="Title of the reference song this MIDI came from.",
    ),
    artist: str = typer.Option(
        "",
        "--artist",
        help="Artist name for the reference song.",
    ),
    stem_dir: Optional[Path] = typer.Option(
        None,
        "--stem-dir",
        exists=False,
        help="Directory containing per-stem MIDI fragment JSON files.",
    ),
    key: Optional[str] = typer.Option(
        None,
        "--key",
        help="Musical key of the fragment, e.g. 'D minor'.",
    ),
    bpm: Optional[int] = typer.Option(
        None,
        "--bpm",
        help="Tempo (BPM) of the fragment.",
    ),
    instrument: Optional[str] = typer.Option(
        None,
        "--instrument",
        help="Instrument name, e.g. 'bass', 'drums', 'piano'.",
    ),
    heart: Optional[str] = typer.Option(
        None,
        "--heart",
        help="Comma-separated HMT heart taxonomy tags, e.g. 'anger,sadness'.",
    ),
    notes_json: Optional[str] = typer.Option(
        None,
        "--notes",
        help="Piano-roll note events as a JSON array string.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug logging.",
    ),
) -> None:
    """Store MIDI fragments (key, BPM, instrument, heart tags) into the memory library."""
    if not verbose:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    heart_tags: list[str] = (
        [t.strip() for t in heart.split(",") if t.strip()] if heart else []
    )

    # -----------------------------------------------------------------------
    # Build fragment list
    # -----------------------------------------------------------------------
    fragments: list[dict] = []

    if stem_dir:
        if not stem_dir.is_dir():
            typer.echo(f"Error: --stem-dir '{stem_dir}' is not a directory.", err=True)
            raise typer.Exit(code=1)
        fragments = _load_stem_dir(stem_dir, source_song, artist)

        # Apply CLI overrides to each fragment
        for frag in fragments:
            if key:
                frag["key"] = key
            if bpm is not None:
                frag["bpm"] = bpm
            if instrument:
                frag["instrument"] = instrument
            if heart_tags:
                frag["heart"] = list(set(frag.get("heart", []) + heart_tags))
    else:
        # Single inline fragment from CLI flags
        notes: list = []
        if notes_json:
            try:
                notes = json.loads(notes_json)
            except json.JSONDecodeError as exc:
                typer.echo(f"Error: --notes is not valid JSON: {exc}", err=True)
                raise typer.Exit(code=1)

        fragments = [
            {
                "source_song": source_song,
                "artist": artist,
                "key": key or "",
                "bpm": bpm,
                "instrument": instrument or "",
                "heart": heart_tags,
                "notes": notes,
            }
        ]

    if not fragments:
        typer.echo("Nothing to ingest.")
        raise typer.Exit(code=0)

    # -----------------------------------------------------------------------
    # Ingest each fragment
    # -----------------------------------------------------------------------
    stored = 0
    failed = 0
    for frag in fragments:
        if _learn_fragment(frag):
            stored += 1
        else:
            failed += 1

    typer.echo(
        f"Ingest complete: {stored} stored, {failed} failed "
        f"(total {len(fragments)} fragments)."
    )
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
