#!/usr/bin/env python3
"""
Export trained RVC model metadata to /memory for Horus persona recall.

Enables queries like:
    "Do we have a voice model for Chelsea Wolfe?"
    "What oud models are available?"
    "List all trained vocalist models"

Usage:
    python sync_memory.py --models-root /mnt/storage12tb/media/music/rvc-models
    python sync_memory.py --export-file models_memory.jsonl
    python sync_memory.py --export-memory  # Direct to ArangoDB
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer


MODELS_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/music/rvc-models"


def scan_trained_models(models_root: Optional[Path] = None) -> List[dict]:
    """Scan all trained models and collect metadata."""
    root = models_root or MODELS_ROOT
    models = []

    for category in ["voice", "instrument"]:
        cat_dir = root / category
        if not cat_dir.exists():
            continue

        for model_dir in sorted(cat_dir.iterdir()):
            if not model_dir.is_dir():
                continue

            meta_path = model_dir / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            meta["_category"] = category
            meta["_path"] = str(model_dir)
            meta["_slug"] = model_dir.name

            # Check for inference model
            has_infer = any(model_dir.glob("*-infer.pth"))
            has_index = any(model_dir.glob("*.index"))
            meta["_ready"] = has_infer and has_index

            models.append(meta)

    return models


def format_model_for_memory(meta: dict) -> dict:
    """
    Format a trained model as a memory entry.

    The problem field is structured so semantic search on queries like
    "do we have a voice for Chelsea Wolfe" or "oud models" will match.
    """
    name = meta.get("artist", meta.get("name", meta.get("_slug", "unknown")))
    category = meta.get("_category", "unknown")
    subcategory = meta.get("subcategory", category)
    voice_type = meta.get("voice_type")
    genres = meta.get("genres", [])
    bridge_tags = meta.get("bridge_tags", [])
    ready = meta.get("_ready", False)
    path = meta.get("_path", "")

    # Problem: structured for semantic matching
    if subcategory and subcategory != category:
        problem = f"Trained voice model: {name} ({subcategory})"
    else:
        problem = f"Trained voice model: {name} ({category})"

    # Solution: rich details
    parts = [f"RVC voice model for {name}."]
    parts.append(f"Category: {category}.")

    if subcategory:
        parts.append(f"Type: {subcategory}.")
    if voice_type:
        parts.append(f"Voice type: {voice_type}.")
    if genres:
        parts.append(f"Genres: {', '.join(genres[:4])}.")
    if bridge_tags:
        parts.append(f"Bridge: {', '.join(bridge_tags)}.")

    status = "Ready for inference" if ready else "Training complete (needs export)"
    parts.append(f"Status: {status}.")

    if path:
        parts.append(f"Path: {path}")

    solution = " ".join(parts)

    # Tags
    memory_tags = ["trained_model", "voice_model", "rvc", category]
    memory_tags.append(name.lower().replace(" ", "_"))

    if subcategory:
        memory_tags.append(subcategory.replace("-", "_"))

    # Add instrument keywords for search
    instrument_keywords = {
        "guitarist": ["guitar", "guitar_player"],
        "bassist": ["bass", "bass_player"],
        "drummer": ["drums", "drummer"],
        "pianist": ["piano", "pianist"],
        "trumpeter": ["trumpet", "trumpet_player"],
        "saxophonist": ["saxophone", "sax_player"],
        "violinist": ["violin", "violinist"],
        "cellist": ["cello", "cellist"],
        "vocalist": ["vocals", "singer"],
        "oud-player": ["oud", "oud_player"],
        "percussionist": ["percussion", "percussionist"],
        "flutist": ["flute", "flute_player"],
    }
    for kw in instrument_keywords.get(subcategory, []):
        memory_tags.append(kw)

    for genre in genres[:3]:
        memory_tags.append(genre.replace(" ", "_").replace("-", "_"))
    for bridge in bridge_tags:
        memory_tags.append(bridge.lower())

    return {
        "problem": problem,
        "solution": solution,
        "category": "music",
        "tags": list(set(memory_tags)),
        "bridge_attributes": bridge_tags,
        "collection_tags": {"domain": "Music", "function": "Recall"},
    }


def format_library_summary(models: List[dict]) -> dict:
    """Create a library summary entry for high-level queries."""
    total = len(models)
    by_category = {}
    by_subcategory = {}

    for m in models:
        cat = m.get("_category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

        sub = m.get("subcategory", cat)
        by_subcategory[sub] = by_subcategory.get(sub, 0) + 1

    ready_count = sum(1 for m in models if m.get("_ready"))

    problem = "Voice model library summary — all trained RVC models"

    lines = [f"Total trained models: {total} ({ready_count} ready for inference)."]
    lines.append("")

    if by_category:
        lines.append("By category:")
        for cat, count in sorted(by_category.items()):
            lines.append(f"  {cat}: {count}")

    if by_subcategory:
        lines.append("")
        lines.append("By type:")
        for sub, count in sorted(by_subcategory.items(), key=lambda x: -x[1]):
            lines.append(f"  {sub}: {count}")

    lines.append("")
    lines.append("Artists:")
    for m in sorted(models, key=lambda x: x.get("artist", x.get("_slug", ""))):
        name = m.get("artist", m.get("_slug", "?"))
        sub = m.get("subcategory", "?")
        ready = "[ready]" if m.get("_ready") else "[needs export]"
        lines.append(f"  {name} ({sub}) {ready}")

    solution = "\n".join(lines)

    return {
        "problem": problem,
        "solution": solution,
        "category": "music",
        "tags": ["voice_model_library", "rvc", "trained_models", "library_summary"],
        "bridge_attributes": [],
        "collection_tags": {"domain": "Music", "function": "Recall"},
    }


def sync_models_to_memory(
    models_root: Optional[Path] = None,
    export_file: Optional[Path] = None,
    export_memory: bool = False,
) -> List[dict]:
    """
    Scan trained models and export to memory.

    Args:
        models_root: Root directory of RVC models.
        export_file: Write memory JSONL to this file.
        export_memory: Export directly to memory service.

    Returns:
        List of memory entries.
    """
    models = scan_trained_models(models_root)
    print(f"Found {len(models)} trained models", file=sys.stderr)

    entries = []
    for meta in models:
        entries.append(format_model_for_memory(meta))

    # Add library summary
    entries.append(format_library_summary(models))

    if export_file:
        export_file = Path(export_file)
        export_file.parent.mkdir(parents=True, exist_ok=True)
        with open(export_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        print(f"Wrote {len(entries)} memory entries to {export_file}", file=sys.stderr)

    if export_memory:
        _export_to_memory_service(entries)

    return entries


def _export_to_memory_service(entries: List[dict]) -> None:
    """Export entries to memory via MemoryClient."""
    try:
        skills_dir = Path(__file__).parent.parent
        sys.path.insert(0, str(skills_dir))
        from common.memory_client import MemoryClient, MemoryScope

        client = MemoryClient(scope=MemoryScope.HORUS_LORE, use_python_api=True)
        results = client.batch_learn(
            [
                {
                    "problem": e["problem"],
                    "solution": e["solution"],
                    "tags": e["tags"],
                }
                for e in entries
            ],
            concurrency=4,
        )
        success = sum(1 for r in results if r.success)
        print(f"Exported {success}/{len(entries)} entries to memory", file=sys.stderr)
    except Exception as e:
        print(f"Memory export failed: {e}", file=sys.stderr)


def main(
    models_root: str = typer.Option(
        str(MODELS_ROOT), help=f"Root directory of RVC models (default: {MODELS_ROOT})",
    ),
    export_file: Optional[str] = typer.Option(None, help="Write memory JSONL to this file"),
    export_memory: bool = typer.Option(False, help="Export directly to /memory service"),
    as_json: bool = typer.Option(False, "--json", help="Print entries as JSON to stdout"),
):
    """Export trained RVC model metadata to /memory."""
    entries = sync_models_to_memory(
        models_root=Path(models_root),
        export_file=Path(export_file) if export_file else None,
        export_memory=export_memory,
    )

    if as_json:
        print(json.dumps(entries, indent=2))
    else:
        print(f"\nSummary:")
        print(f"  Total entries: {len(entries)}")
        print(f"  Model entries: {len(entries) - 1}")
        print(f"  Library summary: 1")


if __name__ == "__main__":
    typer.run(main)

