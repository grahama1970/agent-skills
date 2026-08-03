"""Compatibility wrapper for canonical ingest-code Tree-sitter symbol scanning."""

from __future__ import annotations

from pathlib import Path

from code_memory_client import CodeMemoryClient
from ingest_code import _scan_treesitter_symbol_records_for_directory


def treesitter_scan_dir(directory: str, scope: str) -> int:
    """Run the canonical ingest-code Tree-sitter scan and store symbols."""
    root = Path(directory).resolve()
    records = _scan_treesitter_symbol_records_for_directory(root, root, scope)
    return CodeMemoryClient().upsert_code_symbols(records).stored
