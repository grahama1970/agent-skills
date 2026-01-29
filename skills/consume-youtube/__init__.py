"""Consume-youtube - Shared utilities for YouTube transcript consumption."""

from .ingest_bridge import sync_from_ingest
from .search import search_transcripts
from .notes import add_note, list_notes
from .indexer import build_index

__all__ = [
    "sync_from_ingest",
    "search_transcripts",
    "add_note",
    "list_notes",
    "build_index",
]
