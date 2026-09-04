"""Stream Ultralytics YOLO/ByteTrack observations as Watch live-track events.

This is the Watch Stage 1 tracker boundary: detect/track people frame-by-frame
from a video, webcam, RTSP, or similar stream and emit event-backed bounding
boxes immediately. It does not identify characters. Named identity belongs to a
separate verifier that consumes crops/references after this first-stage stream.

An optional post-detection compositor can redact explicitly targeted tracks
before frame JPEGs, display pixels, or output video are emitted. That compositor
does not alter Stage 1 observations or accepted identity.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

if __package__:
    from .watch_anonymizer import (
        AnonymizationConfigError,
        AnonymizationSession,
        anonymization_config_summary,
        anonymization_message_summary,
        session_from_args,
    )
else:
    from watch_anonymizer import (
        AnonymizationConfigError,
        AnonymizationSession,
        anonymization_config_summary,
        anonymization_message_summary,
        session_from_args,
    )


DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "watch_track_observations.schema.json"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "generated" / "watch_live_ultralytics_frame_loop"
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "yolo11n.pt"
PERSON_CLASS_ID = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="YOLO model path/name. Defaults to Watch yolo11n.pt.")
    parser.add_argument("--source", required=True, help="Camera index, video path, RTSP URL, or stream URL.")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Ultralytics tracker config.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--stream-id", default="watch_stream_live")
    parser.add_argument("--asset-uid", default="watch_asset")
    parser.add_argument("--segment-id", default="watch_segment")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--sample-fps", type=float, default=5.0, help="Detection cadence for emitted events.")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default=None)
    parser.add_argument("--class-id", type=int, default=PERSON_CLASS_ID, help="YOLO class id to keep. COCO person is 0.")
    parser.add_argument("--no-class-filter", action="store_true", help="Do not pass a classes filter to Ultralytics.")
    parser.add_argument("--detected-class", default="person", choices=["person", "vehicle", "drone", "object", "unknown"])
    parser.add_argument("--candidate-name", help="Optional provisional identity hint. It is not promoted by this script.")
    parser.add_argument("--candidate-actor-name", help="Optional actor/domain hint paired with --candidate-name.")
    parser.add_argument("--candidate-entity-id", help="Optional entity id paired with --candidate-name.")
    parser.add_argument("--attach-domain-candidate", action="store_true", help="Attach candidate_entities as PROVISIONAL only.")
    parser.add_argument("--stdout-jsonl", action="store_true", help="Print events as JSONL as each frame is processed.")
    parser.add_argument("--stdout-frame-jsonl", action="store_true", help="Print frame+box messages as JSONL for WebSocket canvas streaming.")
    parser.add_argument("--sse", action="store_true", help="Print events as SSE track_update frames.")
    parser.add_argument("--jpeg-quality", type=int, default=75, help="JPEG quality for --stdout-frame-jsonl frames.")
    parser.add_argument(
        "--output-video",
        type=Path,
        help=(
            "Optional annotated/redacted video-only output path. OpenCV writes "
            "video frames; source audio is not preserved by this backend slice."
        ),
    )
    parser.add_argument("--display", action="store_true", help="Open an OpenCV display window. Off by default for headless use.")
    parser.add_argument("--pace-realtime", action="store_true", help="Sleep between sampled frames to approximate source time.")

    anonymization = parser.add_argument_group("post-detection pixel redaction")
    anonymization.add_argument(
        "--blur-character",
        help="Character-name filter for accepted/suggested target decisions. This never accepts identity.",
    )
    anonymization.add_argument(
        "--blur-source",
        choices=["accepted", "suggested", "manual-track"],
        help="Authority lane used only to select redaction targets.",
    )
    anonymization.add_argument(
        "--blur-label-receipt",
        type=Path,
        help="Timed watch.yolo_track_labels.v1 receipt used to derive accepted target intervals.",
    )
    anonymization.add_argument(
        "--blur-target-manifest",
        type=Path,
        help="Explicit watch.anonymization_targets.v1 manifest, required for suggestion targets.",
    )
    anonymization.add_argument(
        "--blur-track",
        action="append",
        default=[],
        metavar="TRACK_ID",
        help="Explicit detector track to redact for --blur-source manual-track. Repeatable.",
    )
    anonymization.add_argument(
        "--blur-mode",
        choices=["face", "upper-person", "person"],
        default=None,
        help=(
            "ROI policy (default when enabled: upper-person). face falls back "
            "to upper-person unless a localizer is supplied."
        ),
    )
    anonymization.add_argument(
        "--blur-style",
        choices=["gaussian", "pixelate", "solid"],
        default=None,
        help="Pixel transform (default when enabled: gaussian).",
    )
    anonymization.add_argument(
        "--blur-strength",
        type=int,
        default=None,
        help="Transform strength (default when enabled: 31).",
    )
    anonymization.add_argument(
        "--blur-hold-ms",
        type=int,
        default=None,
        help="Bounded last-ROI hold in milliseconds (default when enabled: 750).",
    )
    anonymization.add_argument(
        "--allow-suggested-export",
        action="store_true",
        help="Explicitly allow tentative suggestions to drive permanent --output-video redaction.",
    )
    anonymization.add_argument(
        "--anonymization-receipt",
        type=Path,
        help="JSONL frame-receipt path. Defaults under --out-dir.",
    )
    args = parser.parse_args()

    if args.sample_fps <= 0:
        raise ValueError("--sample-fps must be greater than zero")
    if args.max_events <= 0:
        raise ValueError("--max-events must be greater than zero")

    if args.stdout_frame_jsonl:
        frames = []
        args.out_dir.mkdir(parents=True, exist_ok=True)
        frame_log_path = args.out_dir / "watch_live_ultralytics_frames.jsonl"
        with frame_log_path.open("w", encoding="utf-8") as frame_file:
            for frame_msg in iter_track_frames(args):
                frames.append(frame_msg)
                line = json.dumps(frame_msg, sort_keys=True)
                frame_file.write(line + "\n")
                frame_file.flush()
                print(line, flush=True)
                if len(frames) >= args.max_events:
                    break
        _write_json(args.out_dir / "summary.json", _frame_summary(args=args, frames=frames, frame_log_path=frame_log_path))
        if not frames:
            raise RuntimeError("Ultralytics frame-loop tracker produced no frame messages")
        return 0

    validator = _event_validator(args.schema)
    events: list[dict[str, Any]] = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    events_path = args.out_dir / "watch_live_ultralytics_events.jsonl"

    event_file = events_path.open("w", encoding="utf-8")
    try:
        for event in iter_track_events(args):
            validator.validate(event)
            events.append(event)
            line = json.dumps(event, sort_keys=True)
            event_file.write(line + "\n")
            event_file.flush()
            if args.stdout_jsonl:
                print(line, flush=True)
            if args.sse:
                print(f"event: track_update\ndata: {line}\n", flush=True)
            if len(events) >= args.max_events and not _complete_pixel_pass_requested(args):
                break
    finally:
        event_file.close()

    summary = _summary(args=args, events=events, events_path=events_path)
    _write_json(args.out_dir / "summary.json", summary)
    if not events:
        raise RuntimeError("Ultralytics frame-loop tracker produced no track events")
    if not args.stdout_jsonl and not args.sse:
        print("live_ultralytics_events_ok", len(events))
        print("event_log", events_path)
    return 0


def iter_track_events(args: argparse.Namespace) -> Iterable[dict[str, Any]]:
    anonymizer = session_from_args(args)
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "Watch live tracking requires ultralytics and opencv-python. "
            "Install the Watch tracking extra before running this script."
        ) from exc

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video source: {args.source}")

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if not source_fps or not math.isfinite(source_fps) or source_fps <= 0:
        source_fps = 30.0
    frame_stride = max(1, round(source_fps / args.sample_fps))
    _validate_redaction_output_cadence(
        anonymizer, args=args, source_fps=source_fps, frame_stride=frame_stride
    )
    model = YOLO(args.model)

    classes = None if args.no_class_filter else [args.class_id]
    track_kwargs: dict[str, Any] = {
        "persist": True,
        "tracker": args.tracker,
        "conf": args.conf,
        "iou": args.iou,
        "imgsz": args.imgsz,
        "classes": classes,
        "verbose": False,
    }
    if args.device:
        track_kwargs["device"] = args.device

    writer = None
    event_base = _utc_now()
    frame_index = -1
    emitted_count = 0
    candidate_entities = _candidate_entities(args)
    complete_pixel_pass = _complete_pixel_pass_requested(args)
    full_frame_output = bool(args.display or complete_pixel_pass)

    with anonymizer:
        try:
            while True:
                loop_start = time.perf_counter()
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                sampled = frame_index % frame_stride == 0
                if not sampled and not full_frame_output:
                    continue

                frame_seconds = frame_index / source_fps
                media_time = round(args.start_seconds + frame_seconds, 3)
                tracks: list[dict[str, Any]] = []
                if sampled:
                    result = model.track(frame, **track_kwargs)
                    boxes = result[0].boxes if result and result[0].boxes is not None else None
                    tracks = _tracks_from_boxes(
                        boxes,
                        detected_class=args.detected_class,
                        candidate_entities=candidate_entities,
                    )

                rendered, _receipt = anonymizer.process(
                    frame,
                    tracks=tracks,
                    stream_id=args.stream_id,
                    asset_uid=args.asset_uid,
                    segment_id=args.segment_id,
                    frame_index=frame_index,
                    media_time_seconds=media_time,
                )
                annotated = rendered.copy()
                frame_events: list[dict[str, Any]] = []
                for track in tracks:
                    if emitted_count >= args.max_events:
                        break
                    event = {
                        "event_type": "track_update",
                        "schema_version": "watch.live_track_update.v1",
                        "stream_id": args.stream_id,
                        "asset_uid": args.asset_uid,
                        "segment_id": args.segment_id,
                        "media_time_seconds": media_time,
                        "track_id": track["track_id"],
                        "bbox_xyxy": track["bbox_xyxy"],
                        "detected_class": track["detected_class"],
                        "candidate_entities": track["candidate_entities"],
                        "status": "PROVISIONAL",
                        "emitted_at": (
                            event_base + timedelta(seconds=frame_seconds)
                        ).isoformat().replace("+00:00", "Z"),
                    }
                    emitted_count += 1
                    frame_events.append(event)
                    _draw_box(
                        annotated,
                        bbox=track["bbox_xyxy"],
                        track_id=track["track_id"],
                        confidence=track["confidence"],
                    )

                if args.output_video:
                    # A redaction export writes the compositor output itself, not
                    # detector decorations added after the receipt hash. Operator
                    # display may still show boxes; non-redaction output preserves
                    # the historical annotated-video behavior.
                    video_frame = rendered if anonymizer.enabled else annotated
                    writer = _writer_for(
                        cv2, writer, args.output_video, source_fps, video_frame
                    )
                    writer.write(video_frame)
                if args.display:
                    cv2.imshow("Watch Ultralytics Stage 1 Tracking", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        return
                if args.pace_realtime:
                    interval = 1.0 / source_fps if full_frame_output else frame_stride / source_fps
                    elapsed = time.perf_counter() - loop_start
                    time.sleep(max(0.0, interval - elapsed))

                # Complete export/redaction passes continue to source EOF even after
                # the observation event budget is exhausted.
                yield from frame_events
                if emitted_count >= args.max_events and not complete_pixel_pass:
                    return
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            if args.display:
                cv2.destroyAllWindows()


def iter_track_frames(args: argparse.Namespace) -> Iterable[dict[str, Any]]:
    anonymizer = session_from_args(args)
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "Watch live tracking requires ultralytics and opencv-python. "
            "Install the Watch tracking extra before running this script."
        ) from exc

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video source: {args.source}")

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if not source_fps or not math.isfinite(source_fps) or source_fps <= 0:
        source_fps = 30.0
    frame_stride = max(1, round(source_fps / args.sample_fps))
    model = YOLO(args.model)
    classes = None if args.no_class_filter else [args.class_id]
    track_kwargs: dict[str, Any] = {
        "persist": True,
        "tracker": args.tracker,
        "conf": args.conf,
        "iou": args.iou,
        "imgsz": args.imgsz,
        "classes": classes,
        "verbose": False,
    }
    if args.device:
        track_kwargs["device"] = args.device

    frame_index = -1
    processed_index = 0
    candidate_entities = _candidate_entities(args)

    with anonymizer:
        try:
            while True:
                loop_start = time.perf_counter()
                ok, frame = cap.read()
                if not ok:
                    yield {"type": "end", "processed_frames": processed_index}
                    return
                frame_index += 1
                if frame_index % frame_stride != 0:
                    continue

                result = model.track(frame, **track_kwargs)
                frame_seconds = frame_index / source_fps
                media_time = round(args.start_seconds + frame_seconds, 3)
                boxes = result[0].boxes if result and result[0].boxes is not None else None
                tracks = _tracks_from_boxes(
                    boxes,
                    detected_class=args.detected_class,
                    candidate_entities=candidate_entities,
                )
                rendered, receipt = anonymizer.process(
                    frame,
                    tracks=tracks,
                    stream_id=args.stream_id,
                    asset_uid=args.asset_uid,
                    segment_id=args.segment_id,
                    frame_index=frame_index,
                    media_time_seconds=media_time,
                )
                height, width = rendered.shape[:2]
                yield {
                    "type": "frame",
                    "schema_version": "watch.tracker_canvas_frame.v1",
                    "stream_id": args.stream_id,
                    "asset_uid": args.asset_uid,
                    "segment_id": args.segment_id,
                    "media_time_seconds": media_time,
                    "frame_index": frame_index,
                    "processed_index": processed_index,
                    "source_fps": source_fps,
                    "sample_fps": args.sample_fps,
                    "width": width,
                    "height": height,
                    "tracks": tracks,
                    "anonymization": anonymization_message_summary(receipt),
                    "jpeg": _encode_jpeg(rendered, args.jpeg_quality),
                }
                processed_index += 1
                if args.pace_realtime:
                    elapsed = time.perf_counter() - loop_start
                    time.sleep(max(0.0, (1.0 / args.sample_fps) - elapsed))
        finally:
            cap.release()


def _complete_pixel_pass_requested(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "output_video", None) or getattr(args, "blur_source", None))


def _validate_redaction_output_cadence(
    anonymizer: AnonymizationSession,
    *,
    args: argparse.Namespace,
    source_fps: float,
    frame_stride: int,
) -> None:
    if not anonymizer.enabled or not getattr(args, "output_video", None):
        return
    assert anonymizer.engine is not None
    minimum_hold_ms = math.ceil(1000.0 * frame_stride / source_fps)
    if anonymizer.engine.config.hold_ms < minimum_hold_ms:
        raise AnonymizationConfigError(
            "--blur-hold-ms must cover the effective detector interval for "
            f"--output-video ({minimum_hold_ms}ms at source_fps={source_fps:g}, "
            f"frame_stride={frame_stride})"
        )


def _tracks_from_boxes(
    boxes: Any,
    *,
    detected_class: str,
    candidate_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if boxes is None or getattr(boxes, "id", None) is None or len(boxes) == 0:
        return []
    xyxy_values = _tolist(boxes.xyxy)
    ids = _tolist(boxes.id)
    conf_values = _tolist(boxes.conf)
    tracks = []
    for box_index, track_id_value in enumerate(ids):
        bbox = _bbox(xyxy_values[box_index])
        track_id = f"track_{_normalize_track_id(track_id_value)}"
        confidence = _maybe_conf(conf_values, box_index)
        tracks.append({
            "track_id": track_id,
            "label": f"Person {track_id.replace('track_', '#')}{f' {confidence:.2f}' if confidence is not None else ''}",
            "confidence": confidence,
            "detected_class": detected_class,
            "bbox_xyxy": bbox,
            "candidate_entities": candidate_entities,
            "identity_status": "IDENTITY_NOT_VERIFIED",
        })
    return tracks


def _encode_jpeg(frame: Any, jpeg_quality: int) -> str:
    import cv2

    quality = max(1, min(100, int(jpeg_quality)))
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("failed to encode frame as JPEG")
    return base64.b64encode(buffer).decode("ascii")


def parse_source(source: str) -> int | str:
    try:
        return int(source)
    except ValueError:
        return source


def _candidate_entities(args: argparse.Namespace) -> list[dict[str, Any]]:
    if not args.attach_domain_candidate or not args.candidate_name:
        return []
    safe_name = args.candidate_name.lower().replace(" ", "_")
    entity = {
        "entity_id": args.candidate_entity_id or f"movie_domain_entities/{safe_name}_provisional",
        "name": args.candidate_name,
        "kind": "CHARACTER",
        "confidence": 0.5,
        "status": "PROVISIONAL",
        "basis": ["movie_domain_memory"],
    }
    if args.candidate_actor_name:
        entity["actor_name"] = args.candidate_actor_name
    return [entity]


def _draw_box(frame: Any, *, bbox: list[int], track_id: str, confidence: float | None) -> None:
    import cv2

    x1, y1, x2, y2 = bbox
    color = color_for_id(track_id)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"{track_id.replace('track_', 'person #')}"
    if confidence is not None:
        label += f" {confidence:.2f}"
    cv2.putText(frame, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2, cv2.LINE_AA)


def color_for_id(track_id: str | int | None) -> tuple[int, int, int]:
    if track_id is None:
        return (3, 218, 198)
    text = str(track_id).replace("track_", "")
    try:
        value = int(float(text))
    except ValueError:
        value = sum(ord(char) for char in text)
    return (
        int((37 * value) % 255),
        int((17 * value) % 255),
        int((29 * value) % 255),
    )


def _writer_for(cv2: Any, writer: Any, output_path: Path, fps: float, frame: Any) -> Any:
    if writer is not None:
        return writer
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = frame.shape[:2]
    created = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not created.isOpened():
        raise RuntimeError(f"could not open output video writer: {output_path}")
    return created


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


def _maybe_conf(values: list[Any], index: int) -> float | None:
    if index >= len(values):
        return None
    return float(values[index])


def _event_validator(schema_path: Path) -> Draft202012Validator:
    schema = _read_json(schema_path)
    event_schema = dict(schema["$defs"]["live_track_update_event"])
    event_schema["$defs"] = schema["$defs"]
    return Draft202012Validator(event_schema)


def _summary(*, args: argparse.Namespace, events: list[dict[str, Any]], events_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "watch.live_ultralytics_frame_loop_summary.v1",
        "status": "EVENTS_WRITTEN" if events else "NO_TRACK_EVENTS",
        "stage": "STAGE_1_DETECT_AND_TRACK_ONLY",
        "source": args.source,
        "model": args.model,
        "tracker": args.tracker,
        "sample_fps": args.sample_fps,
        "event_log": _display_path(events_path),
        "event_count": len(events),
        "track_ids": sorted({event["track_id"] for event in events}),
        "time_bounds_seconds": {
            "start": min((event["media_time_seconds"] for event in events), default=None),
            "end": max((event["media_time_seconds"] for event in events), default=None),
        },
        "post_detection_redaction": anonymization_config_summary(args),
        "output_video_audio_preserved": (
            False if getattr(args, "output_video", None) else None
        ),
        "mocked": False,
        "live": True,
        "claim_boundary": (
            "This artifact proves frame-by-frame Ultralytics tracking event emission. "
            "When post-detection redaction is configured, its separate frame receipts prove only "
            "that selected pixels in processed frames were altered. Neither artifact proves named identity, "
            "anonymity, crop/reference similarity, Qdrant writes, Arango writes, or memory recall."
        ),
    }


def _frame_summary(*, args: argparse.Namespace, frames: list[dict[str, Any]], frame_log_path: Path) -> dict[str, Any]:
    track_ids = sorted({
        track["track_id"]
        for frame in frames
        if frame.get("type") == "frame"
        for track in frame.get("tracks", [])
    })
    frame_messages = [frame for frame in frames if frame.get("type") == "frame"]
    return {
        "schema_version": "watch.tracker_canvas_frame_summary.v1",
        "status": "FRAMES_WRITTEN" if frame_messages else "NO_TRACK_FRAMES",
        "stage": "STAGE_1_DETECT_AND_TRACK_CANVAS_STREAM",
        "source": args.source,
        "model": args.model,
        "tracker": args.tracker,
        "sample_fps": args.sample_fps,
        "frame_log": _display_path(frame_log_path),
        "frame_count": len(frame_messages),
        "message_count": len(frames),
        "track_ids": track_ids,
        "time_bounds_seconds": {
            "start": min((frame["media_time_seconds"] for frame in frame_messages), default=None),
            "end": max((frame["media_time_seconds"] for frame in frame_messages), default=None),
        },
        "post_detection_redaction": anonymization_config_summary(args),
        "output_video_audio_preserved": (
            False if getattr(args, "output_video", None) else None
        ),
        "mocked": False,
        "live": True,
        "claim_boundary": (
            "This artifact proves server-produced frame+track messages for canvas rendering. "
            "When post-detection redaction is configured, JPEG pixels are encoded from the "
            "redacted frame and a separate receipt records the applied ROI. This does not prove "
            "named identity, anonymity, crop/reference similarity, Qdrant writes, Arango writes, "
            "or memory recall."
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


if __name__ == "__main__":
    raise SystemExit(main())
