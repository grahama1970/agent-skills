"""Transcript indexing for consume-youtube."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

TOKEN_RE = re.compile(r"[a-z0-9']+")


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


def _index_segment_terms(
    index: dict[str, list[dict[str, object]]],
    video_id: str,
    start: float,
    text: str,
    max_occurrences_per_term: int,
) -> None:
    tokens = TOKEN_RE.findall(text.lower())
    for token in tokens:
        entries = index.setdefault(token, [])
        if len(entries) >= max_occurrences_per_term:
            continue
        entries.append({
            "video_id": video_id,
            "start": start,
            "text": text,
        })


def build_index(
    channel: str,
    ingest_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    max_occurrences_per_term: int = 200,
) -> Path:
    """Build a lightweight inverted index for a channel."""
    ingest_root = _detect_ingest_root(ingest_root)
    if not ingest_root:
        raise FileNotFoundError("Ingest root not found")

    channel_dir = ingest_root / channel
    if not channel_dir.exists():
        raise FileNotFoundError(f"Channel directory not found: {channel_dir}")

    if not output_dir:
        output_dir = Path.home() / ".pi" / "consume-youtube" / "indices"
    output_dir.mkdir(parents=True, exist_ok=True)

    index: dict[str, list[dict[str, object]]] = {}
    transcript_files = [
        path for path in channel_dir.glob("*.json")
        if not path.name.startswith(".")
    ]

    for transcript_path in transcript_files:
        try:
            data = json.loads(transcript_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        video_id = meta.get("video_id", transcript_path.stem)
        transcript = data.get("transcript", []) if isinstance(data, dict) else []

        for segment in transcript:
            text = str(segment.get("text", ""))
            if not text:
                continue
            start = float(segment.get("start", 0))
            _index_segment_terms(index, video_id, start, text, max_occurrences_per_term)

    payload = {
        "channel": channel,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "terms": index,
    }

    output_path = output_dir / f"{channel}.json"
    output_path.write_text(json.dumps(payload), encoding="utf-8")
    return output_path


def main() -> None:
    """CLI entry point for indexing."""
    import argparse

    parser = argparse.ArgumentParser(description="Build a transcript index for a channel")
    parser.add_argument("--channel", required=True, help="Channel name")
    parser.add_argument("--ingest-root", help="Ingest root directory")
    parser.add_argument("--output-dir", help="Output directory for indices")
    parser.add_argument("--max-occurrences", type=int, default=200, help="Max occurrences per term")

    args = parser.parse_args()

    ingest_root = Path(args.ingest_root) if args.ingest_root else None
    output_dir = Path(args.output_dir) if args.output_dir else None

    index_path = build_index(
        channel=args.channel,
        ingest_root=ingest_root,
        output_dir=output_dir,
        max_occurrences_per_term=args.max_occurrences,
    )

    console.print(f"[green]Index written: {index_path}[/green]")


if __name__ == "__main__":
    main()
