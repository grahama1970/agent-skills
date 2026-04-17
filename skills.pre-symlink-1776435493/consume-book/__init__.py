"""Consume-book - Shared utilities for book consumption."""

from .ingest_bridge import sync_from_ingest
from .search import search_books
from .notes import add_note, list_notes
from .position import save_position, get_position, get_reading_stats

__all__ = [
    "sync_from_ingest",
    "search_books",
    "add_note",
    "list_notes",
    "save_position",
    "get_position",
    "get_reading_stats",
]
