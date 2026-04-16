"""Consume Movie - Search and extract from ingested movies."""

from .search import search_subtitles
from .clips import extract_clip
from .notes import add_note, list_notes
from .list import list_movies
from .ingest_bridge import sync_from_ingest

__all__ = [
    "search_subtitles",
    "extract_clip", 
    "add_note",
    "list_notes",
    "list_movies",
    "sync_from_ingest"
]