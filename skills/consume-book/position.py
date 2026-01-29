"""Reading position tracking for consume-book."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


@dataclass
class ReadingPosition:
    book_id: str
    last_position: int
    last_updated: str
    total_chars_read: int
    time_spent_sec: float

    def to_dict(self) -> dict[str, object]:
        return {
            "book_id": self.book_id,
            "last_position": self.last_position,
            "last_updated": self.last_updated,
            "total_chars_read": self.total_chars_read,
            "time_spent_sec": self.time_spent_sec,
        }


def _load_positions(path: Path) -> dict[str, ReadingPosition]:
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    positions: dict[str, ReadingPosition] = {}
    for book_id, entry in data.get("books", {}).items():
        positions[book_id] = ReadingPosition(
            book_id=book_id,
            last_position=int(entry.get("last_position", 0)),
            last_updated=str(entry.get("last_updated", "")),
            total_chars_read=int(entry.get("total_chars_read", 0)),
            time_spent_sec=float(entry.get("time_spent_sec", 0)),
        )
    return positions


def _save_positions(path: Path, positions: dict[str, ReadingPosition]) -> None:
    payload = {
        "books": {book_id: pos.to_dict() for book_id, pos in positions.items()}
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_position(
    book_id: str,
    char_position: int,
    time_spent_sec: Optional[float] = None,
    registry_path: Optional[Path] = None,
) -> ReadingPosition:
    """Save a reading position for a book."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-book" / "bookmarks.json"

    positions = _load_positions(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    current = positions.get(book_id)

    if current:
        total_chars = current.total_chars_read + max(0, char_position - current.last_position)
        time_spent = current.time_spent_sec + (time_spent_sec or 0)
    else:
        total_chars = max(0, char_position)
        time_spent = time_spent_sec or 0

    updated = ReadingPosition(
        book_id=book_id,
        last_position=char_position,
        last_updated=now,
        total_chars_read=total_chars,
        time_spent_sec=time_spent,
    )

    positions[book_id] = updated
    _save_positions(registry_path, positions)
    return updated


def get_position(book_id: str, registry_path: Optional[Path] = None) -> Optional[ReadingPosition]:
    """Get the last saved position for a book."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-book" / "bookmarks.json"

    positions = _load_positions(registry_path)
    return positions.get(book_id)


def get_reading_stats(book_id: str, registry_path: Optional[Path] = None) -> dict[str, object]:
    """Return reading stats for a book."""
    position = get_position(book_id, registry_path)
    if not position:
        return {}

    return position.to_dict()


def _format_position_output(position: ReadingPosition) -> str:
    return (
        f"Book: {position.book_id}\n"
        f"Last position: {position.last_position}\n"
        f"Total chars read: {position.total_chars_read}\n"
        f"Time spent (sec): {position.time_spent_sec}\n"
        f"Last updated: {position.last_updated}"
    )


def main() -> None:
    """CLI entry point for position tracking."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage book reading positions")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    save_parser = subparsers.add_parser("save", help="Save reading position")
    save_parser.add_argument("--book", required=True, help="Book ID")
    save_parser.add_argument("--char-position", type=int, required=True, help="Character position")
    save_parser.add_argument("--time-spent", type=float, help="Time spent in seconds")

    resume_parser = subparsers.add_parser("resume", help="Show last saved position")
    resume_parser.add_argument("--book", required=True, help="Book ID")
    resume_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "save":
        position = save_position(
            book_id=args.book,
            char_position=args.char_position,
            time_spent_sec=args.time_spent,
        )
        console.print(f"[green]Position saved[/green]\n{_format_position_output(position)}")
    elif args.command == "resume":
        position = get_position(args.book)
        if not position:
            console.print("[yellow]No saved position[/yellow]")
            return
        if args.json:
            print(json.dumps(position.to_dict(), indent=2))
        else:
            console.print(_format_position_output(position))
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
