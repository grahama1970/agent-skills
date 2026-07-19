"""Run YOLO + ByteTrack and emit Watch live-track JSONL events.

This adapter is the first real-ML boundary after the deterministic frame
harness. It streams Ultralytics tracking results into the existing
``watch.live_track_update.v1`` contract. Domain/movie candidates are opt-in and
remain provisional; detector output alone is never scene truth.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_MANIFEST = DEFAULT_ARCH_DIR / "watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json"
DEFAULT_SCHEMA = DEFAULT_ARCH_DIR / "watch_track_observations.schema.json"
DEFAULT_OUT_DIR = DEFAULT_ARCH_DIR / "generated" / "bad_santa_marcus_0248_yolo_bytetrack"
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "yolo11n.pt"

PERSON_CLASS_ID = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Video/stream source. Defaults to manifest clip path.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--tracker", default="bytetrack.yaml")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0,
        help=(
            "Target event sampling rate for Watch tracking checks. "
            "The tracker may process video internally, but emitted Watch "
            "events are time-mapped at this cadence."
        ),
    )
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--attach-domain-candidate", action="store_true")
    parser.add_argument("--stdout-jsonl", action="store_true", help="Emit each Watch track event as JSONL on stdout for SSE bridge use.")
    parser.add_argument("--stream-id", help="Override manifest stream_id for live per-clip tracking.")
    parser.add_argument("--asset-uid", help="Override manifest asset_uid for live per-clip tracking.")
    parser.add_argument("--segment-id", help="Override manifest segment_id for live per-clip tracking.")
    parser.add_argument("--start-seconds", type=float, help="Override manifest time_range.start_seconds for live per-clip tracking.")
    parser.add_argument("--candidate-name", help="Optional provisional character/entity name to attach to emitted events.")
    parser.add_argument("--candidate-actor-name", help="Optional actor name for the provisional candidate.")
    parser.add_argument("--candidate-entity-id", help="Optional entity id for the provisional candidate.")
    parser.add_argument(
        "--journal",
        type=Path,
        help=(
            "Write an immutable source-session journal (P0A) to this path. "
            "Each event is appended and fsynced as it is emitted; the tracker "
            "is the only append writer."
        ),
    )
    parser.add_argument(
        "--previous-journal",
        type=Path,
        help=(
            "Chain this session to a prior (possibly crashed/unfinalized) "
            "session journal. Starts a NEW session; track ids never carry "
            "identity across the chain boundary."
        ),
    )
    parser.add_argument(
        "--chain-reason",
        default="producer_restart",
        help="Recorded chain reason when --previous-journal is set.",
    )
    args = parser.parse_args()

    manifest = _read_json(args.manifest)
    observation = _observation_with_overrides(
        manifest["collections"]["watch_track_observations"][0],
        stream_id=args.stream_id,
        asset_uid=args.asset_uid,
        segment_id=args.segment_id,
        start_seconds=args.start_seconds,
        candidate_name=args.candidate_name,
        candidate_actor_name=args.candidate_actor_name,
        candidate_entity_id=args.candidate_entity_id,
    )
    source = args.source or observation["evidence_basis"]["clip_refs"][0]["path"]
    if not _source_exists(source) and not _looks_like_stream(source):
        raise FileNotFoundError(f"source does not exist: {source}")
    fps = _source_fps(source)
    frame_stride = _frame_stride(fps=fps, sample_fps=args.sample_fps)

    journal_writer = None
    if args.journal:
        from watch_source_session_journal import JournalWriter, read_journal_lenient, source_sha256

        previous_session_id = None
        chain_reason = None
        if args.previous_journal:
            previous_header, _events, salvage = read_journal_lenient(args.previous_journal)
            previous_session_id = previous_header["source_session_id"]
            chain_reason = (
                f"{args.chain_reason}"
                f" (previous finalized={salvage['finalized']},"
                f" salvaged_events={salvage['salvaged_event_count']})"
            )

        is_stream = _looks_like_stream(source)
        journal_writer = JournalWriter(
            args.journal,
            source_uri=str(source),
            source_sha256_value="" if is_stream else source_sha256(source),
            source_hash_mode="uri_only" if is_stream else "sha256_full",
            clock_mode="declared_frame_offset",
            declared_fps=fps,
            clock_start_seconds=float(observation["time_range"]["start_seconds"]),
            frame_stride=frame_stride,
            sample_fps=args.sample_fps,
            model=str(args.model),
            tracker_config=args.tracker,
            conf=args.conf,
            imgsz=args.imgsz,
            producer="track_yolo_bytetrack.py",
            previous_session_id=previous_session_id,
            chain_reason=chain_reason,
        )

    events: list[dict[str, Any]] = []
    for event, source_frame_index in _track_source(
        source=source,
        observation=observation,
        model_name=args.model,
        tracker=args.tracker,
        conf=args.conf,
        imgsz=args.imgsz,
        fps=fps,
        frame_stride=frame_stride,
        max_events=args.max_events,
        attach_domain_candidate=args.attach_domain_candidate,
    ):
        if journal_writer is not None:
            journal_writer.append_event(
                event,
                source_frame_index=source_frame_index,
                media_time_seconds=float(event["media_time_seconds"]),
            )
        if args.stdout_jsonl:
            # Emit incrementally so SSE consumers see events as they happen;
            # schema validation still runs over the full set afterwards.
            print(json.dumps(event, sort_keys=True), flush=True)
        events.append(event)
    if journal_writer is not None:
        journal_writer.finalize()
    if not events:
        raise RuntimeError("YOLO/ByteTrack produced no track events")
    _validate_events(events, args.schema)

    if args.stdout_jsonl:
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    events_path = args.out_dir / "watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl"
    events_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": "watch.yolo_bytetrack_event_log_summary.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "source": source,
        "source_fps": fps,
        "model": args.model,
        "tracker": args.tracker,
        "conf": args.conf,
        "imgsz": args.imgsz,
        "sample_fps": args.sample_fps,
        "frame_stride": frame_stride,
        "event_log": _display_path(events_path),
        "event_count": len(events),
        "track_ids": sorted({event["track_id"] for event in events}),
        "time_bounds_seconds": {
            "start": min(event["media_time_seconds"] for event in events),
            "end": max(event["media_time_seconds"] for event in events),
        },
        "domain_candidates_attached": args.attach_domain_candidate,
        "claim_boundary": (
            "YOLO/ByteTrack events prove detector/tracker output only. Character "
            "identity remains provisional until Watch evidence, re-identification, "
            "or human review supports it. This command does not write memory."
        ),
    }
    _write_json(args.out_dir / "summary.json", summary)

    print("yolo_bytetrack_events_ok", len(events))
    print("track_ids", summary["track_ids"])
    print("source_fps", fps)
    print("event_log", events_path)
    return 0


def _observation_with_overrides(
    observation: dict[str, Any],
    *,
    stream_id: str | None,
    asset_uid: str | None,
    segment_id: str | None,
    start_seconds: float | None,
    candidate_name: str | None,
    candidate_actor_name: str | None,
    candidate_entity_id: str | None,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(observation))
    if stream_id:
        updated["stream_id"] = stream_id
    if asset_uid:
        updated["asset_uid"] = asset_uid
    if segment_id:
        updated["segment_id"] = segment_id
    if start_seconds is not None:
        duration = float(updated["time_range"].get("end_seconds", 0)) - float(updated["time_range"].get("start_seconds", 0))
        updated["time_range"]["start_seconds"] = start_seconds
        updated["time_range"]["end_seconds"] = start_seconds + max(duration, 0)
    if candidate_name:
        candidate = dict(updated.get("candidate_entity") or {})
        safe_name = candidate_name.lower().replace(" ", "_")
        candidate.update({
            "entity_id": candidate_entity_id or f"movie_domain_entities/{safe_name}_provisional",
            "name": candidate_name,
            "kind": candidate.get("kind") or "CHARACTER",
            "actor_name": candidate_actor_name,
            "confidence": float(candidate.get("confidence", 0.5)),
            "status": "CANDIDATE",
            "basis": candidate.get("basis") or ["watch_modal_query_context"],
        })
        if not candidate_actor_name:
            candidate.pop("actor_name", None)
        updated["candidate_entity"] = candidate
    return updated


def _track_source(
    *,
    source: str,
    observation: dict[str, Any],
    model_name: str,
    tracker: str,
    conf: float,
    imgsz: int,
    fps: float,
    frame_stride: int,
    max_events: int,
    attach_domain_candidate: bool,
) -> Iterable[tuple[dict[str, Any], int]]:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "ultralytics is required for live YOLO/ByteTrack tracking. "
            "Install the Watch tracking extra before running this adapter."
        ) from exc

    model = YOLO(model_name)
    results = model.track(
        source=source,
        stream=True,
        tracker=tracker,
        conf=conf,
        imgsz=imgsz,
        classes=[PERSON_CLASS_ID],
        vid_stride=frame_stride,
        verbose=False,
    )
    return _events_from_results(
        results,
        observation=observation,
        fps=fps,
        frame_stride=frame_stride,
        max_events=max_events,
        attach_domain_candidate=attach_domain_candidate,
    )


def _events_from_results(
    results: Iterable[Any],
    *,
    observation: dict[str, Any],
    fps: float,
    frame_stride: int,
    max_events: int,
    attach_domain_candidate: bool,
) -> Iterable[tuple[dict[str, Any], int]]:
    start_seconds = float(observation["time_range"]["start_seconds"])
    emitted_base = _utc_now()
    event_count = 0
    last_event_for_track: dict[str, tuple[dict[str, Any], int]] = {}
    for emitted_frame_index, result in enumerate(results):
        source_frame_index = emitted_frame_index * max(1, frame_stride)
        boxes = getattr(result, "boxes", None)
        if boxes is None or getattr(boxes, "id", None) is None:
            continue
        ids = _tolist(boxes.id)
        xyxy_values = _tolist(boxes.xyxy)
        cls_values = _tolist(getattr(boxes, "cls", []))
        conf_values = _tolist(getattr(boxes, "conf", []))
        for box_index, track_id_value in enumerate(ids):
            class_id = int(cls_values[box_index]) if box_index < len(cls_values) else PERSON_CLASS_ID
            if class_id != PERSON_CLASS_ID:
                continue
            event_count += 1
            track_id = f"track_{_normalize_track_id(track_id_value)}"
            confidence = float(conf_values[box_index]) if box_index < len(conf_values) else 0.0
            media_time = round(start_seconds + (source_frame_index / fps if fps > 0 else 0.0), 2)
            event = {
                "event_type": "track_update",
                "schema_version": "watch.live_track_update.v1",
                "stream_id": observation["stream_id"],
                "asset_uid": observation["asset_uid"],
                "segment_id": observation["segment_id"],
                "media_time_seconds": media_time,
                "track_id": track_id,
                "bbox_xyxy": _bbox(xyxy_values[box_index]),
                "detected_class": "person",
                "candidate_entities": _candidate_entities(
                    observation,
                    confidence=confidence,
                    attach_domain_candidate=attach_domain_candidate,
                ),
                "status": "PROVISIONAL",
                "emitted_at": (emitted_base + timedelta(seconds=(source_frame_index / fps if fps > 0 else 0.0))).isoformat().replace("+00:00", "Z"),
            }
            last_event_for_track[track_id] = (event, source_frame_index)
            yield event, source_frame_index
            if event_count >= max_events:
                return
    for event, frame_index in last_event_for_track.values():
        boundary = dict(event)
        boundary["status"] = "BOUNDARY_CANDIDATE"
        boundary["emitted_at"] = _utc_now().isoformat().replace("+00:00", "Z")
        yield boundary, frame_index


def _candidate_entities(
    observation: dict[str, Any],
    *,
    confidence: float,
    attach_domain_candidate: bool,
) -> list[dict[str, Any]]:
    if not attach_domain_candidate:
        return []
    candidate = observation.get("candidate_entity")
    if not candidate:
        return []
    return [
        {
            "entity_id": candidate["entity_id"],
            "name": candidate["name"],
            "kind": candidate["kind"],
            "actor_name": candidate.get("actor_name"),
            "confidence": min(float(candidate.get("confidence", 0.0)), confidence),
            "status": "PROVISIONAL",
            "basis": ["movie_domain_memory", "person_reid_embedding"],
        }
    ]


def _tolist(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return value if isinstance(value, list) else list(value)


def _bbox(value: Any) -> list[int]:
    values = [int(round(float(item))) for item in value]
    if len(values) != 4:
        raise ValueError(f"expected bbox with four values, got {values}")
    x1, y1, x2, y2 = values
    return [max(0, x1), max(0, y1), max(0, x2), max(0, y2)]


def _normalize_track_id(value: Any) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric).replace(".", "_")


def _source_fps(source: str) -> float:
    if _looks_like_stream(source):
        return 30.0
    if shutil.which("ffprobe") is None:
        return 30.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            source,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return 30.0
    try:
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        for key in ("avg_frame_rate", "r_frame_rate"):
            fps = _parse_rate(stream.get(key))
            if fps > 0:
                return fps
    except Exception:
        return 30.0
    return 30.0


def _parse_rate(value: Any) -> float:
    if not value:
        return 0.0
    text = str(value)
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
    return float(text)


def _frame_stride(*, fps: float, sample_fps: float) -> int:
    if sample_fps <= 0:
        raise ValueError("--sample-fps must be greater than zero")
    if fps <= 0:
        return 1
    return max(1, round(fps / sample_fps))


def _validate_events(events: list[dict[str, Any]], schema_path: Path) -> None:
    schema = _read_json(schema_path)
    event_schema = dict(schema["$defs"]["live_track_update_event"])
    event_schema["$defs"] = schema["$defs"]
    validator = Draft202012Validator(event_schema)
    for index, event in enumerate(events, start=1):
        errors = sorted(validator.iter_errors(event), key=lambda error: error.path)
        if errors:
            details = "; ".join(
                f"{list(error.path)}: {error.message}" for error in errors
            )
            raise ValueError(f"event {index} failed schema validation: {details}")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _looks_like_stream(value: str) -> bool:
    return "://" in value or value.startswith("/dev/")


def _source_exists(value: str) -> bool:
    return Path(value).exists()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


if __name__ == "__main__":
    raise SystemExit(main())
