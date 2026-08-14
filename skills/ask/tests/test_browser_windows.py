"""A window Ask opened and did not record is one nothing will ever reclaim.

These guard the ownership gap measured on 2026-08-14: 9 provider windows open,
none named by any of 351 lifecycle receipts, and the ledger empty at 0 bytes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# `ask` is already importable here (conftest owns the path); inserting src/
# again reorders resolution for every later test module in the session and
# broke five unrelated tau_dag tests when this file ran first.
from ask import browser_windows


@pytest.fixture(autouse=True)
def _ledger(tmp_path, monkeypatch):
    monkeypatch.setenv(browser_windows.REGISTRY_ENV, str(tmp_path / "browser-windows.jsonl"))
    return tmp_path / "browser-windows.jsonl"


def test_a_registered_window_is_readable_back(_ledger) -> None:
    assert browser_windows.register(["100"], mode="fresh-temporary", source="test") == ["100"]
    entries = browser_windows.load()
    assert [e["window_id"] for e in entries] == ["100"]
    assert entries[0]["pid"] == os.getpid()


def test_registering_nothing_writes_nothing(_ledger) -> None:
    assert browser_windows.register([], mode="fresh-temporary") == []
    assert browser_windows.load() == []


def test_duplicate_ids_are_recorded_once(_ledger) -> None:
    assert browser_windows.register(["7", "7", ""], mode="fresh-temporary") == ["7"]


def test_a_torn_append_does_not_lose_the_whole_ledger(_ledger) -> None:
    """Append-only exists so a killed writer costs one entry, not the file."""
    browser_windows.register(["1"], mode="fresh-temporary")
    with _ledger.open("a", encoding="utf-8") as handle:
        handle.write('{"window_id": "2", "pi')  # killed mid-write
    browser_windows.register(["3"], mode="fresh-temporary")
    assert {e["window_id"] for e in browser_windows.load()} == {"1", "3"}


def test_deregistering_removes_only_the_named_window(_ledger) -> None:
    browser_windows.register(["1", "2"], mode="fresh-temporary")
    browser_windows.deregister({"1"})
    assert [e["window_id"] for e in browser_windows.load()] == ["2"]


def test_a_live_owner_protects_its_window(_ledger) -> None:
    """A concurrent roundtable must never have its seats closed out from under it."""
    browser_windows.register(["1"], mode="fresh-temporary")
    assert browser_windows.reclaimable(now=1e12) == []


def test_a_dead_owner_past_its_ttl_is_reclaimable(_ledger, monkeypatch) -> None:
    browser_windows.register(["1"], mode="fresh-temporary")
    monkeypatch.setattr(browser_windows, "pid_alive", lambda pid: False)
    assert [e["window_id"] for e in browser_windows.reclaimable(now=1e12)] == ["1"]


def test_a_dead_owner_inside_its_ttl_is_kept(_ledger, monkeypatch) -> None:
    """A run that died mid-flight may hold output that exists only in-tab."""
    browser_windows.register(["1"], mode="fresh-temporary")
    monkeypatch.setattr(browser_windows, "pid_alive", lambda pid: False)
    assert browser_windows.reclaimable() == []


def test_pending_recovery_is_an_obligation_with_a_clock() -> None:
    """28 of 351 receipts kept windows for a recovery nobody ever performed."""
    assert browser_windows.ttl_for_mode("pending-recovery") > browser_windows.ttl_for_mode("fresh-keep")
    assert browser_windows.ttl_for_mode("pending-recovery") < float("inf")


def test_an_unknown_mode_gets_the_shortest_ttl() -> None:
    assert browser_windows.ttl_for_mode("nonsense") == browser_windows.FRESH_TEMPORARY_TTL_SECONDS


def test_a_permission_error_counts_the_owner_as_alive(monkeypatch) -> None:
    """Guessing 'dead' on someone else's pid would close a live run's window."""
    def _raise(pid, sig):
        raise PermissionError

    monkeypatch.setattr(os, "kill", _raise)
    assert browser_windows.pid_alive(1) is True


def test_a_missing_pid_counts_as_dead(monkeypatch) -> None:
    def _raise(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", _raise)
    assert browser_windows.pid_alive(999999) is False


def _fake_surf(monkeypatch, payload, returncode: int = 0):
    class _Proc:
        def __init__(self):
            self.returncode = returncode
            self.stdout = json.dumps(payload) if not isinstance(payload, str) else payload

    monkeypatch.setattr(browser_windows.subprocess, "run", lambda *a, **k: _Proc())


def test_a_tab_resolves_to_the_window_that_holds_it(monkeypatch) -> None:
    """The worker only ever learns a tab id; ownership needs the window."""
    _fake_surf(monkeypatch, [{"id": 42, "windowId": 900}, {"id": 43, "windowId": 901}])
    assert browser_windows.window_ids_for_tabs(["42"], surf_run=Path("/x/run.sh")) == {"42": "900"}


def test_a_failed_tab_list_claims_nothing(monkeypatch) -> None:
    _fake_surf(monkeypatch, [], returncode=1)
    assert browser_windows.window_ids_for_tabs(["42"], surf_run=Path("/x/run.sh")) == {}


def test_unparseable_tab_list_output_claims_nothing(monkeypatch) -> None:
    _fake_surf(monkeypatch, "not json")
    assert browser_windows.window_ids_for_tabs(["42"], surf_run=Path("/x/run.sh")) == {}


def test_register_tabs_claims_the_resolved_window(_ledger, monkeypatch) -> None:
    _fake_surf(monkeypatch, [{"id": 42, "windowId": 900}])
    claimed = browser_windows.register_tabs(
        ["42"], surf_run=Path("/x/run.sh"), source="tau_roundtable_worker"
    )
    assert claimed == ["900"]
    assert browser_windows.load()[0]["source"] == "tau_roundtable_worker"
