#!/usr/bin/env python3
"""Incremental re-indexing: process only what changed, prune what disappeared.

Purpose
    Ingestion here is append-only and unconditional: every run re-extracts and
    re-embeds every symbol, and a symbol deleted from the codebase keeps its
    knowledge in memory forever. This module supplies the two pieces that fixes
    -- a memoization key that is honest about code changes, and a delete set.

    The key is ``(content_hash, transform_version)``, not ``content_hash``
    alone. A cache keyed only on content silently serves results produced by an
    older extractor: bump the AST walker or the CWE rules, and every unchanged
    file keeps its stale output forever. ``transform_version`` is derived by
    hashing the extractor's own source, so changing the code invalidates the
    cache without anyone remembering to bump a constant -- the failure mode of
    every hand-maintained version number.

    Deletions matter for correctness, not speed. An append-only pipeline keeps
    answering questions about functions that no longer exist; ``plan().deleted``
    is what lets a caller remove them.

Inputs
    A state file path, a transform version, and a mapping of stable entry key
    to current content hash.

Outputs
    ``IndexPlan`` partitioning keys into unchanged / added / changed / deleted,
    and a ``commit`` that persists the new state atomically.

Failure modes
    A missing, unreadable, or corrupt state file is treated as an empty state:
    the run degrades to a full re-index, which is correct but slow, and never
    fails the ingest. A state written by a different transform version
    invalidates every entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

STATE_SCHEMA = "ingest.incremental_state.v1"


def transform_version(sources: Iterable[Path], *, extra: str = "") -> str:
    """Derive a version string from the extractor's own source code.

    Hashing the code is what makes the cache honest under refactors. A manually
    bumped constant is forgotten exactly when it matters most -- the run where
    someone changed how symbols are parsed.

    Missing source files contribute their absence rather than raising: a
    partially installed skill should still produce a stable, distinct version
    rather than crash the ingest.
    """
    digest = hashlib.sha256()
    for path in sorted(sources, key=lambda p: str(p)):
        digest.update(str(Path(path).name).encode("utf-8"))
        try:
            digest.update(Path(path).read_bytes())
        except OSError:
            digest.update(b"\0missing\0")
    if extra:
        digest.update(extra.encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class IndexPlan:
    """What this run must do, partitioned by why."""

    unchanged: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    invalidated_by_transform: bool = False

    @property
    def to_process(self) -> tuple[str, ...]:
        """Entries needing extraction this run."""
        return self.added + self.changed

    @property
    def is_full_reindex(self) -> bool:
        return self.invalidated_by_transform or not self.unchanged

    def summary(self) -> dict[str, object]:
        return {
            "unchanged": len(self.unchanged),
            "added": len(self.added),
            "changed": len(self.changed),
            "deleted": len(self.deleted),
            "invalidated_by_transform": self.invalidated_by_transform,
        }


@dataclass
class IncrementalIndex:
    """Content-addressed state for one ingestion target.

    ``state_path`` holds the previous run's ``key -> content_hash`` map plus the
    transform version that produced it.
    """

    state_path: Path
    version: str
    _previous: dict[str, str] = field(default_factory=dict, init=False)
    _previous_version: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._previous, self._previous_version = self._load()

    def _load(self) -> tuple[dict[str, str], str]:
        try:
            payload = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt or absent state degrades to a full re-index. That is
            # slow but correct; failing the ingest instead would turn a cache
            # problem into an outage.
            return {}, ""
        if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
            return {}, ""
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            return {}, ""
        clean = {str(k): str(v) for k, v in entries.items() if isinstance(v, (str, int))}
        return clean, str(payload.get("transform_version") or "")

    def plan(self, current: Mapping[str, str]) -> IndexPlan:
        """Partition current entries against the previous run's state."""
        current_keys = {str(k): str(v) for k, v in current.items()}
        # A changed transform invalidates everything, including entries whose
        # content is byte-identical -- the whole point of the code-hash half.
        stale_transform = bool(self._previous) and self._previous_version != self.version
        previous = {} if stale_transform else self._previous

        unchanged: list[str] = []
        added: list[str] = []
        changed: list[str] = []
        for key, content_hash in current_keys.items():
            if key not in previous:
                added.append(key)
            elif previous[key] != content_hash:
                changed.append(key)
            else:
                unchanged.append(key)
        # Deleted is computed against the REAL previous state even when the
        # transform changed: those entries are gone from the source and must be
        # pruned regardless of why everything else is being reprocessed.
        deleted = [key for key in self._previous if key not in current_keys]
        return IndexPlan(
            unchanged=tuple(sorted(unchanged)),
            added=tuple(sorted(added)),
            changed=tuple(sorted(changed)),
            deleted=tuple(sorted(deleted)),
            invalidated_by_transform=stale_transform,
        )

    def commit(self, current: Mapping[str, str]) -> Path:
        """Persist the new state atomically.

        Written via a temp file and ``os.replace`` so an interrupted run leaves
        the previous state intact rather than a truncated one: a half-written
        state would silently mark real work as already done.
        """
        path = Path(self.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": STATE_SCHEMA,
            "transform_version": self.version,
            "entries": {str(k): str(v) for k, v in current.items()},
        }
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        )
        try:
            with handle as fh:
                json.dump(payload, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(handle.name, path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
        self._previous = dict(payload["entries"])
        self._previous_version = self.version
        return path
