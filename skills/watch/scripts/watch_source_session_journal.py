"""Immutable source-session journal for Watch live tracking (gate P0A).

One acquisition run = one source session = one append-only journal file. The
tracker adapter is the only append writer; consumers are read-only validators.
The journal is source-derived acquisition evidence and is never mutated;
corrections happen downstream as overlays and evidence cases.

Integrity contract (fail-closed on read):
- line 1 is a session header binding source identity (uri + sha256), clock
  mode, declared fps, frame stride, model, tracker config, conf, imgsz;
- every record carries a sha256 checksum over its canonical JSON;
- event sequences are contiguous and monotonically increasing from 1;
- clock values must be recomputable from the header's declared clock
  (``declared_frame_offset`` mode) — decoded-PTS mode records the decoded
  value explicitly and the two modes never mix;
- a finalize record closes the session; a journal without one (or with a
  truncated final line) is rejected.

Deterministic identity: ``event_id`` names one journal position
(schema|session|sequence). ``observation_id`` names one bounded track window
(schema|session|track|first_seq|last_seq|window clock). Mutable evidence
(bboxes, confidences, candidate labels) lives only in the canonical evidence
digest so that divergent evidence at the same natural position keeps the same
ID and collides on digest instead of silently forking records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

WATCH_NAMESPACE_UUID = uuid.UUID("7a17ce7d-9dbf-5e8a-bc40-8ef36138c84d")
JOURNAL_SCHEMA = "watch.source_session_journal.v1"
CLOCK_MODES = ("declared_frame_offset", "decoded_pts")
CLOCK_EPSILON_SECONDS = 0.02


class JournalValidationError(ValueError):
    """Raised when a journal fails fail-closed validation."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_checksum(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return sha256_hex(canonical_json(body))


def source_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def event_id(session_id: str, sequence: int) -> str:
    return str(uuid.uuid5(WATCH_NAMESPACE_UUID, f"{JOURNAL_SCHEMA}|{session_id}|{sequence}"))


def observation_id(
    session_id: str,
    track_id: str,
    first_sequence: int,
    last_sequence: int,
    window_start: float,
    window_end: float,
) -> str:
    name = (
        f"{JOURNAL_SCHEMA}|{session_id}|{track_id}|{first_sequence}|{last_sequence}"
        f"|{window_start:.3f}|{window_end:.3f}"
    )
    return str(uuid.uuid5(WATCH_NAMESPACE_UUID, name))


class JournalWriter:
    """Sole append writer for a source-session journal (tracker boundary only)."""

    def __init__(
        self,
        path: Path,
        *,
        source_uri: str,
        source_sha256_value: str,
        source_hash_mode: str,
        clock_mode: str,
        declared_fps: float,
        clock_start_seconds: float,
        frame_stride: int,
        sample_fps: float,
        model: str,
        tracker_config: str,
        conf: float,
        imgsz: int,
        producer: str,
        crop_manifest_path: str | None = None,
    ) -> None:
        if clock_mode not in CLOCK_MODES:
            raise ValueError(f"clock_mode must be one of {CLOCK_MODES}")
        self.path = path
        self._sequence = 0
        self._finalized = False
        self._chain = hashlib.sha256()
        started_at = datetime.now(timezone.utc).isoformat()
        session_seed = canonical_json(
            {
                "source_sha256": source_sha256_value,
                "clock_mode": clock_mode,
                "declared_fps": declared_fps,
                "frame_stride": frame_stride,
                "model": model,
                "tracker_config": tracker_config,
                "conf": conf,
                "imgsz": imgsz,
                "started_at": started_at,
            }
        )
        self.session_id = str(uuid.uuid5(WATCH_NAMESPACE_UUID, f"{JOURNAL_SCHEMA}|session|{session_seed}"))
        header: dict[str, Any] = {
            "record_type": "session_header",
            "schema_version": JOURNAL_SCHEMA,
            "source_session_id": self.session_id,
            "source_uri": source_uri,
            "source_sha256": source_sha256_value,
            "source_hash_mode": source_hash_mode,
            "clock_mode": clock_mode,
            "declared_fps": declared_fps,
            "clock_start_seconds": clock_start_seconds,
            "frame_stride": frame_stride,
            "sample_fps": sample_fps,
            "model": model,
            "tracker_config": tracker_config,
            "conf": conf,
            "imgsz": imgsz,
            "producer": producer,
            "crop_manifest_path": crop_manifest_path,
            "started_at": started_at,
        }
        self._header = header
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8")
        self._write_record(header)

    @property
    def header(self) -> dict[str, Any]:
        return dict(self._header)

    def append_event(
        self,
        event: dict[str, Any],
        *,
        source_frame_index: int,
        media_time_seconds: float,
        decoded_pts_seconds: float | None = None,
        frame_digest: str | None = None,
    ) -> dict[str, Any]:
        if self._finalized:
            raise RuntimeError("journal already finalized")
        self._sequence += 1
        clock: dict[str, Any] = {
            "mode": self._header["clock_mode"],
            "source_frame_index": source_frame_index,
            "media_time_seconds": round(media_time_seconds, 3),
        }
        if self._header["clock_mode"] == "decoded_pts":
            if decoded_pts_seconds is None:
                raise ValueError("decoded_pts clock mode requires decoded_pts_seconds")
            clock["decoded_pts_seconds"] = round(decoded_pts_seconds, 6)
        record: dict[str, Any] = {
            "record_type": "event",
            "sequence": self._sequence,
            "event_id": event_id(self.session_id, self._sequence),
            "clock": clock,
            "event": event,
            "frame_digest": frame_digest,
            "evidence_digest": sha256_hex(
                canonical_json(
                    {
                        "source_sha256": self._header["source_sha256"],
                        "clock": clock,
                        "track_id": event.get("track_id"),
                        "bbox_xyxy": event.get("bbox_xyxy"),
                        "detected_class": event.get("detected_class"),
                        "candidate_entities": event.get("candidate_entities"),
                        "status": event.get("status"),
                        "frame_digest": frame_digest,
                    }
                )
            ),
        }
        self._write_record(record)
        return record

    def finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._write_record(
            {
                "record_type": "finalize",
                "event_count": self._sequence,
                "chain_sha256": self._chain.hexdigest(),
                "finalized_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._handle.close()

    def _write_record(self, record: dict[str, Any]) -> None:
        record = dict(record)
        record["record_sha256"] = record_checksum(record)
        if record["record_type"] != "finalize":
            self._chain.update(record["record_sha256"].encode("ascii"))
        self._handle.write(canonical_json(record) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())


def read_journal(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Read and validate a finalized journal. Fail closed on any defect."""
    raw = Path(path).read_text(encoding="utf-8")
    if not raw:
        raise JournalValidationError("journal is empty")
    if not raw.endswith("\n"):
        raise JournalValidationError("journal ends with a truncated record")
    records = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise JournalValidationError(f"blank journal line {line_number}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalValidationError(f"unparseable journal line {line_number}: {exc}") from exc
        if record_checksum(record) != record.get("record_sha256"):
            raise JournalValidationError(f"record checksum mismatch at line {line_number}")
        records.append(record)

    header = records[0]
    if header.get("record_type") != "session_header":
        raise JournalValidationError("first record is not a session header")
    if header.get("schema_version") != JOURNAL_SCHEMA:
        raise JournalValidationError(f"unsupported journal schema: {header.get('schema_version')}")
    if header.get("clock_mode") not in CLOCK_MODES:
        raise JournalValidationError(f"invalid clock_mode: {header.get('clock_mode')}")

    if records[-1].get("record_type") != "finalize":
        raise JournalValidationError("journal is not finalized")
    finalize = records[-1]

    events = records[1:-1]
    chain = hashlib.sha256()
    chain.update(header["record_sha256"].encode("ascii"))
    session_id = header["source_session_id"]
    declared_fps = float(header["declared_fps"])
    clock_start = float(header["clock_start_seconds"])
    for index, record in enumerate(events, start=1):
        if record.get("record_type") != "event":
            raise JournalValidationError(f"unexpected record type at event position {index}")
        if record.get("sequence") != index:
            raise JournalValidationError(
                f"non-contiguous sequence at position {index}: {record.get('sequence')}"
            )
        if record.get("event_id") != event_id(session_id, index):
            raise JournalValidationError(f"event_id mismatch at sequence {index}")
        clock = record.get("clock") or {}
        if clock.get("mode") != header["clock_mode"]:
            raise JournalValidationError(f"mixed clock modes at sequence {index}")
        if header["clock_mode"] == "declared_frame_offset":
            expected = clock_start + (
                float(clock["source_frame_index"]) / declared_fps if declared_fps > 0 else 0.0
            )
            if abs(float(clock["media_time_seconds"]) - expected) > CLOCK_EPSILON_SECONDS:
                raise JournalValidationError(
                    f"clock inconsistency at sequence {index}: media_time "
                    f"{clock['media_time_seconds']} != declared offset {expected:.3f}"
                )
        else:
            if "decoded_pts_seconds" not in clock:
                raise JournalValidationError(f"missing decoded PTS at sequence {index}")
        chain.update(record["record_sha256"].encode("ascii"))

    if finalize.get("event_count") != len(events):
        raise JournalValidationError(
            f"finalize event_count {finalize.get('event_count')} != {len(events)} events"
        )
    if finalize.get("chain_sha256") != chain.hexdigest():
        raise JournalValidationError("finalize chain hash mismatch — journal was altered")
    return header, events, finalize


def build_observation_plan(
    header: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Deterministic, side-effect-free bounded-observation plan from a journal."""
    session_id = header["source_session_id"]
    by_track: dict[str, list[dict[str, Any]]] = {}
    for record in events:
        by_track.setdefault(record["event"]["track_id"], []).append(record)

    observations = []
    for track_id in sorted(by_track):
        track_events = by_track[track_id]
        first_seq = track_events[0]["sequence"]
        last_seq = track_events[-1]["sequence"]
        times = [float(r["clock"]["media_time_seconds"]) for r in track_events]
        window_start, window_end = min(times), max(times)
        obs_id = observation_id(session_id, track_id, first_seq, last_seq, window_start, window_end)
        evidence_digest = sha256_hex(
            canonical_json(
                {
                    "source_sha256": header["source_sha256"],
                    "clock_mode": header["clock_mode"],
                    "events": [
                        {
                            "sequence": r["sequence"],
                            "clock": r["clock"],
                            "bbox_xyxy": r["event"].get("bbox_xyxy"),
                            "candidate_entities": r["event"].get("candidate_entities"),
                            "status": r["event"].get("status"),
                            "frame_digest": r.get("frame_digest"),
                        }
                        for r in track_events
                    ],
                }
            )
        )
        observations.append(
            {
                "observation_id": obs_id,
                "source_session_id": session_id,
                "track_id": track_id,
                "first_event_sequence": first_seq,
                "last_event_sequence": last_seq,
                "event_ids": [r["event_id"] for r in track_events],
                "event_count": len(track_events),
                "window_start_seconds": window_start,
                "window_end_seconds": window_end,
                "clock_mode": header["clock_mode"],
                "evidence_digest": evidence_digest,
                "asset_uid": track_events[0]["event"].get("asset_uid"),
                "stream_id": track_events[0]["event"].get("stream_id"),
                "segment_id": track_events[0]["event"].get("segment_id"),
            }
        )

    canonical_set = sha256_hex(
        canonical_json([[o["observation_id"], o["evidence_digest"]] for o in observations])
    )
    return {
        "schema_version": "watch.source_session_observation_plan.v1",
        "source_session_id": session_id,
        "source_sha256": header["source_sha256"],
        "clock_mode": header["clock_mode"],
        "observation_count": len(observations),
        "observations": observations,
        "canonical_set_sha256": canonical_set,
    }


def iter_journal_paths(directory: Path) -> Iterator[Path]:
    yield from sorted(directory.glob("*.journal.jsonl"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Fail-closed journal validation + observation plan")
    validate.add_argument("journal", type=Path)
    validate.add_argument("--plan-out", type=Path, help="Write the observation plan JSON here")
    args = parser.parse_args()

    if args.command == "validate":
        try:
            header, events, finalize = read_journal(args.journal)
        except JournalValidationError as exc:
            print(f"JOURNAL_REJECTED: {exc}")
            return 2
        plan = build_observation_plan(header, events)
        if args.plan_out:
            args.plan_out.parent.mkdir(parents=True, exist_ok=True)
            args.plan_out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"JOURNAL_OK session={header['source_session_id']} events={len(events)} "
            f"observations={plan['observation_count']} canonical={plan['canonical_set_sha256'][:16]}"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
