"""Read-only SQLite KV access with WAL-safe copies."""
from __future__ import annotations

import contextlib
import pathlib
import shutil
import sqlite3
import tempfile
from typing import Any, Iterator, Optional, Sequence, Tuple

from ccopy.errors import CursorCopyError
from ccopy.utils import parse_json_value

@contextlib.contextmanager
def copied_sqlite_db(db_path: pathlib.Path) -> Iterator[pathlib.Path]:
    """Copy SQLite db + WAL companions to a temp dir and yield copied path.

    SQLite WAL mode means newest committed rows may live in the `-wal` file. A
    simple read of only state.vscdb can be stale, so copy the trio before opening.
    """
    if not db_path.exists():
        raise CursorCopyError(f"database not found: {db_path}")
    with tempfile.TemporaryDirectory(prefix="cursor-copy-db-") as td:
        tmp_dir = pathlib.Path(td)
        tmp_db = tmp_dir / db_path.name
        shutil.copy2(db_path, tmp_db)
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, tmp_dir / sidecar.name)
        yield tmp_db


class KVDB:
    def __init__(self, db_path: pathlib.Path):
        self.original_path = db_path
        self._tmp_ctx = copied_sqlite_db(db_path)
        self.db_path = self._tmp_ctx.__enter__()
        self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self._tables = self._get_tables()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.conn.close()
        with contextlib.suppress(Exception):
            self._tmp_ctx.__exit__(None, None, None)

    def __enter__(self) -> "KVDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _get_tables(self) -> set[str]:
        rows = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {str(r[0]) for r in rows}

    def has_table(self, table: str) -> bool:
        return table in self._tables

    def get_raw(self, key: str, tables: Sequence[str] = ("cursorDiskKV", "ItemTable")) -> Optional[Any]:
        for table in tables:
            if table not in self._tables:
                continue
            row = self.conn.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
            if row is not None:
                return row[0]
        return None

    def get_json(self, key: str, tables: Sequence[str] = ("cursorDiskKV", "ItemTable")) -> Any:
        return parse_json_value(self.get_raw(key, tables=tables))

    def iter_key_prefix(self, prefix: str, table: str = "cursorDiskKV") -> Iterator[Tuple[str, Any]]:
        if table not in self._tables:
            return
        for row in self.conn.execute(
            f"SELECT key, value FROM {table} WHERE key LIKE ? ORDER BY rowid ASC", (prefix + "%",)
        ):
            yield str(row[0]), row[1]

    def iter_item_keys_like(self, pattern: str, table: str = "ItemTable") -> Iterator[Tuple[str, Any]]:
        if table not in self._tables:
            return
        for row in self.conn.execute(
            f"SELECT key, value FROM {table} WHERE key LIKE ? ORDER BY key ASC", (pattern,)
        ):
            yield str(row[0]), row[1]

