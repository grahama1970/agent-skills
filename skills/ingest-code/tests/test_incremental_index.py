"""Incremental re-indexing must be fast AND honest.

The bugs worth guarding are the quiet ones: a cache that serves output from a
superseded extractor, and a pipeline that keeps answering questions about code
that was deleted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from incremental_index import (  # noqa: E402
    STATE_SCHEMA,
    IncrementalIndex,
    transform_version,
)


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


def test_first_run_processes_everything(state: Path) -> None:
    plan = IncrementalIndex(state, "v1").plan({"a": "h1", "b": "h2"})
    assert plan.added == ("a", "b")
    assert plan.unchanged == ()
    assert plan.is_full_reindex


def test_unchanged_entries_are_skipped_on_the_second_run(state: Path) -> None:
    idx = IncrementalIndex(state, "v1")
    idx.commit({"a": "h1", "b": "h2"})

    plan = IncrementalIndex(state, "v1").plan({"a": "h1", "b": "h2"})
    assert plan.unchanged == ("a", "b")
    assert plan.to_process == ()


def test_only_the_edited_entry_is_reprocessed(state: Path) -> None:
    idx = IncrementalIndex(state, "v1")
    idx.commit({"a": "h1", "b": "h2", "c": "h3"})

    plan = IncrementalIndex(state, "v1").plan({"a": "h1", "b": "CHANGED", "c": "h3"})
    assert plan.changed == ("b",)
    assert plan.unchanged == ("a", "c")
    assert plan.to_process == ("b",)


def test_a_changed_extractor_invalidates_byte_identical_content(state: Path) -> None:
    """The whole point of the code-hash half of the key.

    Content-only keying would report these as unchanged and serve output from
    the superseded extractor forever.
    """
    IncrementalIndex(state, "extractor-v1").commit({"a": "h1", "b": "h2"})

    plan = IncrementalIndex(state, "extractor-v2").plan({"a": "h1", "b": "h2"})
    assert plan.invalidated_by_transform
    assert plan.unchanged == ()
    assert plan.to_process == ("a", "b")


def test_deleted_source_entries_are_reported_for_pruning(state: Path) -> None:
    """Correctness, not speed: stale knowledge answers questions wrongly."""
    IncrementalIndex(state, "v1").commit({"kept": "h1", "removed": "h2"})

    plan = IncrementalIndex(state, "v1").plan({"kept": "h1"})
    assert plan.deleted == ("removed",)
    assert plan.unchanged == ("kept",)


def test_deletions_survive_a_transform_bump(state: Path) -> None:
    """A deleted symbol must still be pruned in the run that reprocesses all."""
    IncrementalIndex(state, "v1").commit({"kept": "h1", "removed": "h2"})

    plan = IncrementalIndex(state, "v2").plan({"kept": "h1"})
    assert plan.invalidated_by_transform
    assert plan.deleted == ("removed",), "a full re-index must not lose the delete set"


def test_a_corrupt_state_degrades_to_a_full_reindex(state: Path) -> None:
    state.write_text("{not json", encoding="utf-8")
    plan = IncrementalIndex(state, "v1").plan({"a": "h1"})
    assert plan.added == ("a",)
    assert plan.deleted == ()


def test_a_foreign_schema_is_not_trusted(state: Path) -> None:
    state.write_text(json.dumps({"schema": "something.else", "entries": {"a": "h1"}}), encoding="utf-8")
    plan = IncrementalIndex(state, "v1").plan({"a": "h1"})
    assert plan.added == ("a",), "an unrecognized state file must not be read as our own"


def test_commit_is_atomic_and_round_trips(state: Path) -> None:
    idx = IncrementalIndex(state, "v1")
    idx.commit({"a": "h1"})
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["schema"] == STATE_SCHEMA
    assert payload["transform_version"] == "v1"
    assert payload["entries"] == {"a": "h1"}
    assert not list(state.parent.glob("*.tmp")), "no temp file may survive a commit"


def test_transform_version_tracks_extractor_source(tmp_path: Path) -> None:
    extractor = tmp_path / "extract.py"
    extractor.write_text("def parse(): return 1\n", encoding="utf-8")
    before = transform_version([extractor])

    extractor.write_text("def parse(): return 2\n", encoding="utf-8")
    after = transform_version([extractor])

    assert before != after, "editing the extractor must change the version"
    assert transform_version([extractor]) == after, "version must be stable for stable source"


def test_transform_version_survives_a_missing_source(tmp_path: Path) -> None:
    """A partially installed skill degrades, it does not crash the ingest."""
    version = transform_version([tmp_path / "absent.py"])
    assert len(version) == 16
