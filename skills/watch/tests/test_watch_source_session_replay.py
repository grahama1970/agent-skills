"""P0A/P0B: source-session journal integrity, determinism, and fail-closed replay."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

WATCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WATCH_DIR / "scripts"))

from watch_source_session_journal import (  # noqa: E402
    JournalValidationError,
    JournalWriter,
    build_observation_plan,
    canonical_json,
    event_id,
    read_journal,
    record_checksum,
)

REPLAY = WATCH_DIR / "scripts" / "replay_source_session_journal.py"


def make_event(track: str, media_time: float) -> dict:
    return {
        "event_type": "track_update",
        "schema_version": "watch.live_track_update.v1",
        "stream_id": "watch_stream_p0_test",
        "asset_uid": "p0_test_asset",
        "segment_id": "seg_p0",
        "media_time_seconds": media_time,
        "track_id": track,
        "bbox_xyxy": [10, 10, 50, 90],
        "detected_class": "person",
        "candidate_entities": [],
        "status": "PROVISIONAL",
        "emitted_at": "2026-07-18T00:00:00Z",
    }


def write_journal(path: Path, fps: float = 10.0, events: int = 6) -> None:
    writer = JournalWriter(
        path,
        source_uri="file:///tmp/p0-test.mp4",
        source_sha256_value="a" * 64,
        source_hash_mode="sha256_full",
        clock_mode="declared_frame_offset",
        declared_fps=fps,
        clock_start_seconds=0.0,
        frame_stride=2,
        sample_fps=5.0,
        model="yolo11n.pt",
        tracker_config="bytetrack.yaml",
        conf=0.25,
        imgsz=640,
        producer="test",
    )
    for index in range(events):
        frame = index * 2
        track = "track_1" if index % 2 == 0 else "track_2"
        writer.append_event(
            make_event(track, frame / fps),
            source_frame_index=frame,
            media_time_seconds=frame / fps,
        )
    writer.finalize()


def rewrite_consistent(path: Path, mutate) -> None:
    """Tamper with a journal while recomputing all checksums and the chain.

    Simulates an adversary or bug that keeps the journal internally
    consistent — only semantic validation or digest comparison can catch it.
    """
    records = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(records)
    chain = hashlib.sha256()
    out = []
    for record in records:
        record.pop("record_sha256", None)
        record["record_sha256"] = record_checksum(record)
        if record["record_type"] != "finalize":
            chain.update(record["record_sha256"].encode("ascii"))
        out.append(record)
    finalize = out[-1]
    assert finalize["record_type"] == "finalize"
    finalize["chain_sha256"] = chain.hexdigest()
    finalize.pop("record_sha256", None)
    finalize["record_sha256"] = record_checksum(finalize)
    path.write_text("\n".join(canonical_json(r) for r in out) + "\n")


def test_round_trip_and_deterministic_plan(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    header, events, finalize = read_journal(journal)
    assert finalize["event_count"] == 6
    assert events[0]["event_id"] == event_id(header["source_session_id"], 1)

    plan_a = build_observation_plan(header, events)
    plan_b = build_observation_plan(*read_journal(journal)[:2])
    assert plan_a == plan_b
    assert plan_a["observation_count"] == 2
    assert plan_a["canonical_set_sha256"] == plan_b["canonical_set_sha256"]


def test_truncated_final_record_fails_closed(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    raw = journal.read_text()
    journal.write_text(raw[:-20])
    with pytest.raises(JournalValidationError, match="truncated"):
        read_journal(journal)


def test_missing_finalize_fails_closed(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    lines = journal.read_text().splitlines()
    journal.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(JournalValidationError, match="not finalized"):
        read_journal(journal)


def test_checksum_tamper_fails_closed(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    lines = journal.read_text().splitlines()
    record = json.loads(lines[2])
    record["event"]["bbox_xyxy"] = [0, 0, 1, 1]
    lines[2] = canonical_json(record)
    journal.write_text("\n".join(lines) + "\n")
    with pytest.raises(JournalValidationError, match="checksum mismatch"):
        read_journal(journal)


def test_dropped_record_fails_closed(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)

    def drop_event_two(records: list) -> None:
        del records[2]
        records[-1]["event_count"] = 5

    rewrite_consistent(journal, drop_event_two)
    with pytest.raises(JournalValidationError, match="non-contiguous sequence"):
        read_journal(journal)


def test_consistent_clock_tamper_fails_closed(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)

    def shift_clock(records: list) -> None:
        records[3]["clock"]["media_time_seconds"] += 1.0

    rewrite_consistent(journal, shift_clock)
    with pytest.raises(JournalValidationError, match="clock inconsistency"):
        read_journal(journal)


def test_divergent_evidence_same_id_different_digest(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    original = build_observation_plan(*read_journal(journal)[:2])

    def swap_bbox(records: list) -> None:
        records[1]["event"]["bbox_xyxy"] = [99, 99, 199, 299]
        records[1]["evidence_digest"] = "0" * 64

    rewrite_consistent(journal, swap_bbox)
    tampered = build_observation_plan(*read_journal(journal)[:2])

    original_by_id = {o["observation_id"]: o for o in original["observations"]}
    tampered_by_id = {o["observation_id"]: o for o in tampered["observations"]}
    assert set(original_by_id) == set(tampered_by_id), "same natural position must keep the same ID"
    diverged = [
        oid
        for oid in original_by_id
        if original_by_id[oid]["evidence_digest"] != tampered_by_id[oid]["evidence_digest"]
    ]
    assert diverged, "divergent evidence must collide on digest"
    assert original["canonical_set_sha256"] != tampered["canonical_set_sha256"]


def test_replay_rejects_tampered_journal_before_any_write(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    raw = journal.read_text()
    journal.write_text(raw[:-20])
    receipt = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPLAY),
            "--journal",
            str(journal),
            "--receipt-out",
            str(receipt),
            "--embedding-url",
            "http://127.0.0.1:1",
            "--qdrant-url",
            "http://127.0.0.1:1",
            "--memory-url",
            "http://127.0.0.1:1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "JOURNAL_REJECTED" in result.stdout
    assert not receipt.exists()


def test_replay_refuses_production_collections(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    result = subprocess.run(
        [
            sys.executable,
            str(REPLAY),
            "--journal",
            str(journal),
            "--memory-collection",
            "watch_content",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert "REFUSED_PRODUCTION_COLLECTION" in result.stdout


def test_plan_only_mode_has_no_side_effects(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    result = subprocess.run(
        [
            sys.executable,
            str(REPLAY),
            "--journal",
            str(journal),
            "--plan-only",
            "--embedding-url",
            "http://127.0.0.1:1",
            "--qdrant-url",
            "http://127.0.0.1:1",
            "--memory-url",
            "http://127.0.0.1:1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PLAN_OK" in result.stdout


def test_lenient_reader_salvages_crashed_journal(tmp_path: Path) -> None:
    from watch_source_session_journal import read_journal_lenient

    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    lines = journal.read_text().splitlines()
    # Simulate a producer killed mid-append: drop finalize, truncate last event.
    crashed = "\n".join(lines[:-2]) + "\n" + lines[-2][:30]
    journal.write_text(crashed)

    with pytest.raises(JournalValidationError):
        read_journal(journal)
    header, events, salvage = read_journal_lenient(journal)
    assert salvage["finalized"] is False
    assert salvage["salvaged_event_count"] == 5
    assert len(events) == 5
    assert salvage["dropped"], "truncated tail must be reported"
    assert header["source_session_id"]


def test_chained_session_header_records_predecessor(tmp_path: Path) -> None:
    first = tmp_path / "s1.journal.jsonl"
    write_journal(first)
    first_header = read_journal(first)[0]

    writer = JournalWriter(
        tmp_path / "s2.journal.jsonl",
        source_uri="file:///tmp/p0-test.mp4",
        source_sha256_value="a" * 64,
        source_hash_mode="sha256_full",
        clock_mode="declared_frame_offset",
        declared_fps=10.0,
        clock_start_seconds=0.0,
        frame_stride=2,
        sample_fps=5.0,
        model="yolo11n.pt",
        tracker_config="bytetrack.yaml",
        conf=0.25,
        imgsz=640,
        producer="test",
        previous_session_id=first_header["source_session_id"],
        chain_reason="producer_death_supervised_restart",
    )
    writer.append_event(make_event("track_1", 0.0), source_frame_index=0, media_time_seconds=0.0)
    writer.finalize()

    second_header = read_journal(tmp_path / "s2.journal.jsonl")[0]
    assert second_header["previous_session_id"] == first_header["source_session_id"]
    assert second_header["source_session_id"] != first_header["source_session_id"]
    assert "producer_death" in second_header["chain_reason"]


def test_outbox_records_failures_and_drains_idempotently(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    outbox_path = Path(str(journal) + ".outbox.json")

    dead = [
        sys.executable, str(REPLAY),
        "--journal", str(journal),
        "--max-attempts", "1",
        "--retry-delay-seconds", "0",
        "--embedding-url", "http://127.0.0.1:1",
        "--qdrant-url", "http://127.0.0.1:1",
        "--memory-url", "http://127.0.0.1:1",
    ]
    result = subprocess.run(dead, capture_output=True, text=True)
    assert result.returncode == 5, result.stdout + result.stderr
    assert "OUTBOX_PENDING" in result.stdout
    outbox = json.loads(outbox_path.read_text())
    assert outbox and all(v["status"] == "FAILED_RETRYABLE" for v in outbox.values())

    # A later drain against still-dead sinks keeps entries retryable and
    # increments attempts without corrupting the outbox.
    result = subprocess.run(dead + ["--drain"], capture_output=True, text=True)
    assert result.returncode == 5
    drained = json.loads(outbox_path.read_text())
    assert all(v["attempts"] >= 2 for v in drained.values())


def test_salvage_replay_flags_provenance_in_plan_only(tmp_path: Path) -> None:
    journal = tmp_path / "session.journal.jsonl"
    write_journal(journal)
    lines = journal.read_text().splitlines()
    journal.write_text("\n".join(lines[:-1]) + "\n")  # drop finalize

    strict = subprocess.run(
        [sys.executable, str(REPLAY), "--journal", str(journal), "--plan-only"],
        capture_output=True, text=True,
    )
    assert strict.returncode == 2
    assert "JOURNAL_REJECTED" in strict.stdout

    salvage = subprocess.run(
        [sys.executable, str(REPLAY), "--journal", str(journal), "--plan-only", "--allow-unfinalized"],
        capture_output=True, text=True,
    )
    assert salvage.returncode == 0, salvage.stdout + salvage.stderr
    assert "PLAN_OK" in salvage.stdout
