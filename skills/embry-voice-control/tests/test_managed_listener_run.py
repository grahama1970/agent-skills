"""Managed-listener run-dir allocation: fresh ledger per invocation.

These are pure-logic tests (no live audio, no journal) covering the state-leak
fix: every runner invocation must receive a never-before-used run dir so a
stale cycle ledger from a previous or failed run can never pre-consume the new
invocation's target cycles.  Existing run dirs must never be resumed, moved, or
deleted, so segment WAVs referenced by already-stored receipts keep their
recorded absolute paths.
"""

from __future__ import annotations

from pathlib import Path

from embry_voice_control.audio_e2e.runner import (
    _managed_listener_run_dir_is_fresh,
    _select_managed_listener_run,
)


def _populate(run_dir: Path) -> None:
    """Simulate a listener that persisted a ledger + segment WAV in run_dir."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(
        '{"schema":"realtimestt.physical_hot_mic_listener_state.v1",'
        '"target_cycles":2,"completed_cycles":[{"cycle":1}]}',
        encoding="utf-8",
    )
    segments = run_dir / "segments"
    segments.mkdir(exist_ok=True)
    (segments / "cycle-01.wav").write_bytes(b"RIFFfake")


def test_fresh_campaign_uses_base_dir_with_pending_target(tmp_path: Path) -> None:
    run_dir, target = _select_managed_listener_run(
        campaign_dir=tmp_path,
        pending_turn_count=2,
    )
    assert run_dir == tmp_path / "managed-listener"
    assert target == 2


def test_empty_base_dir_is_treated_as_fresh(tmp_path: Path) -> None:
    (tmp_path / "managed-listener").mkdir()
    run_dir, target = _select_managed_listener_run(
        campaign_dir=tmp_path,
        pending_turn_count=3,
    )
    assert run_dir == tmp_path / "managed-listener"
    assert target == 3


def test_stale_ledger_never_consumes_target_cycles(tmp_path: Path) -> None:
    # A prior/failed run left a ledger (completed_cycles) in the base dir.
    _populate(tmp_path / "managed-listener")

    run_dir, target = _select_managed_listener_run(
        campaign_dir=tmp_path,
        pending_turn_count=2,
    )
    # A brand-new, non-existent dir is chosen -> the listener starts from an
    # empty ledger, so target == pending turns for THIS invocation, never the
    # stale target inherited from the previous run.
    assert run_dir == tmp_path / "managed-listener-run-001"
    assert not run_dir.exists()
    assert target == 2

    # The stale run dir (and its segment WAVs) are left exactly in place so
    # already-stored receipts keep resolving their recorded absolute paths.
    assert (tmp_path / "managed-listener" / "state.json").is_file()
    assert (tmp_path / "managed-listener" / "segments" / "cycle-01.wav").is_file()


def test_each_invocation_gets_a_new_dir(tmp_path: Path) -> None:
    chosen: list[Path] = []
    for _ in range(4):
        run_dir, target = _select_managed_listener_run(
            campaign_dir=tmp_path,
            pending_turn_count=1,
        )
        assert target == 1
        # Every allocation must be fresh and distinct from earlier ones.
        assert _managed_listener_run_dir_is_fresh(run_dir)
        assert run_dir not in chosen
        chosen.append(run_dir)
        # Simulate the listener persisting state into the chosen dir.
        _populate(run_dir)

    assert chosen == [
        tmp_path / "managed-listener",
        tmp_path / "managed-listener-run-001",
        tmp_path / "managed-listener-run-002",
        tmp_path / "managed-listener-run-003",
    ]


def test_run_dir_freshness_predicate(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert _managed_listener_run_dir_is_fresh(missing) is True

    empty = tmp_path / "empty"
    empty.mkdir()
    assert _managed_listener_run_dir_is_fresh(empty) is True

    populated = tmp_path / "populated"
    _populate(populated)
    assert _managed_listener_run_dir_is_fresh(populated) is False
