"""Bridge to import transcripts from ingest-youtube."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from consume_common.registry import ContentRegistry

console = Console()

IGNORED_FILES = {".batch_state.json", ".metadata_cache.json", "enriched_batch.jsonl"}


def _detect_ingest_root(explicit_root: Optional[Path]) -> Optional[Path]:
    if explicit_root:
        return explicit_root

    candidates = [
        Path(__file__).resolve().parents[4] / "run" / "youtube-transcripts",
        Path.home() / "workspace" / "experiments" / "pi-mono" / "run" / "youtube-transcripts",
        Path.home() / "run" / "youtube-transcripts",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _load_metadata_cache(channel_dir: Path) -> dict[str, dict[str, str]]:
    cache_path = channel_dir / ".metadata_cache.json"
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def sync_from_ingest(
    ingest_root: Optional[Path] = None,
    registry_path: Optional[Path] = None
) -> int:
    """Import transcripts into consume-youtube registry.

    Args:
        ingest_root: Directory containing channel transcript folders
        registry_path: Override registry path

    Returns:
        Number of videos imported
    """
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-youtube" / "registry.json"

    ingest_root = _detect_ingest_root(ingest_root)
    if not ingest_root:
        console.print("[red]Ingest root not found[/red]")
        return 0

    if not ingest_root.exists():
        console.print(f"[red]Ingest root does not exist: {ingest_root}[/red]")
        return 0

    registry = ContentRegistry(registry_path)
    imported = 0

    existing_sources = {entry.get("source_path") for entry in registry.list_content("youtube")}

    channel_dirs = [d for d in ingest_root.iterdir() if d.is_dir()]
    console.print(f"[cyan]Found {len(channel_dirs)} channels[/cyan]")

    for channel_dir in channel_dirs:
        channel = channel_dir.name
        metadata_cache = _load_metadata_cache(channel_dir)
        transcript_files = [
            path for path in channel_dir.glob("*.json")
            if path.name not in IGNORED_FILES
        ]

        for transcript_path in transcript_files:
            if str(transcript_path) in existing_sources:
                continue

            try:
                data = json.loads(transcript_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                console.print(f"[yellow]Skipping invalid JSON: {transcript_path}[/yellow]")
                continue

            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            transcript = data.get("transcript", []) if isinstance(data, dict) else []
            video_id = meta.get("video_id", transcript_path.stem)
            metadata = metadata_cache.get(video_id, {})
            title = metadata.get("title") or video_id

            entry = {
                "type": "youtube",
                "title": title,
                "source_path": str(transcript_path),
                "metadata": {
                    "video_id": video_id,
                    "channel": channel,
                    "language": meta.get("language"),
                    "method": meta.get("method"),
                    "segment_count": len(transcript),
                },
            }

            content_id = registry.add_content(entry)
            imported += 1
            console.print(f"[green]Imported: {title} (ID: {content_id[:8]}...)[/green]")

    console.print(f"[green]Total imported: {imported} videos[/green]")
    return imported


def main() -> None:
    """CLI entry point for sync."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync YouTube transcripts from ingest-youtube")
    parser.add_argument("--ingest-root", help="Ingest root directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    ingest_root = Path(args.ingest_root) if args.ingest_root else None
    count = sync_from_ingest(ingest_root=ingest_root)

    if args.json:
        print(json.dumps({"imported": count}))


if __name__ == "__main__":
    main()
