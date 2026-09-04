"""Post-detection pixel redaction for Watch tracker frames.

The compositor consumes explicit target decisions. It never creates or mutates
accepted identity. Receipts claim only that pixels were redacted; they do not
claim that a person or object can no longer be re-identified.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

from jsonschema import Draft202012Validator


BlurSource = Literal["accepted", "suggested", "manual-track"]
BlurMode = Literal["face", "upper-person", "person"]
BlurStyle = Literal["gaussian", "pixelate", "solid"]
BBox = tuple[int, int, int, int]

TARGET_SCHEMA_VERSION = "watch.anonymization_targets.v1"
FRAME_RECEIPT_SCHEMA_VERSION = "watch.anonymization_frame_receipt.v1"
DEFAULT_TARGET_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "watch_anonymization_targets.schema.json"
)


class AnonymizationConfigError(ValueError):
    """Raised when a redaction policy is ambiguous or unsafe to execute."""


class FaceLocalizer(Protocol):
    @property
    def provenance(self) -> dict[str, Any]: ...

    def locate(self, frame: Any, person_bbox: BBox) -> tuple[BBox | None, str | None]: ...


@dataclass(frozen=True)
class AnonymizationTarget:
    decision_id: str
    track_id: str
    source: BlurSource
    stream_id: str
    asset_uid: str
    segment_id: str
    valid_from_seconds: float
    valid_until_seconds: float | None = None
    character_name: str | None = None
    detected_class: str | None = None
    confidence: float | None = None
    basis_ref: str | None = None

    def active_at(
        self,
        stream_id: str,
        asset_uid: str,
        segment_id: str,
        media_time_seconds: float,
    ) -> bool:
        return (
            self.stream_id == stream_id
            and self.asset_uid == asset_uid
            and self.segment_id == segment_id
            and media_time_seconds >= self.valid_from_seconds
            and (
                self.valid_until_seconds is None
                or media_time_seconds < self.valid_until_seconds
            )
        )


@dataclass(frozen=True)
class AnonymizationConfig:
    source: BlurSource
    mode: BlurMode = "upper-person"
    style: BlurStyle = "gaussian"
    strength: int = 31
    hold_ms: int = 750
    character_name: str | None = None
    allow_suggested_export: bool = False

    def validate(self, *, permanent_output: bool = False) -> None:
        if self.source not in {"accepted", "suggested", "manual-track"}:
            raise AnonymizationConfigError(f"unsupported blur source: {self.source}")
        if self.mode not in {"face", "upper-person", "person"}:
            raise AnonymizationConfigError(f"unsupported blur mode: {self.mode}")
        if self.style not in {"gaussian", "pixelate", "solid"}:
            raise AnonymizationConfigError(f"unsupported blur style: {self.style}")
        if isinstance(self.strength, bool) or not isinstance(self.strength, int):
            raise AnonymizationConfigError("--blur-strength must be an integer")
        if self.strength < 3:
            raise AnonymizationConfigError("--blur-strength must be at least 3")
        if isinstance(self.hold_ms, bool) or not isinstance(self.hold_ms, int):
            raise AnonymizationConfigError("--blur-hold-ms must be an integer")
        if not 0 <= self.hold_ms <= 5_000:
            raise AnonymizationConfigError("--blur-hold-ms must be between 0 and 5000")
        if self.source in {"accepted", "suggested"} and not _text(self.character_name):
            raise AnonymizationConfigError(
                "--blur-character is required for accepted or suggested targets"
            )
        if permanent_output and self.source == "suggested" and not self.allow_suggested_export:
            raise AnonymizationConfigError(
                "suggested identity may redact a live preview, but permanent output "
                "requires --allow-suggested-export"
            )


@dataclass
class _TrackState:
    target: AnonymizationTarget
    bbox: BBox
    roi: BBox
    last_seen_seconds: float
    detected_class: str


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _arg_or_default(args: Any, name: str, default: Any) -> Any:
    value = getattr(args, name, None)
    return default if value is None else value


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _frame_sha256(frame: Any) -> str:
    header = f"{tuple(frame.shape)}:{frame.dtype}:".encode()
    return _sha256(header + frame.tobytes(order="C"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bbox(value: Iterable[Any], shape: tuple[int, ...]) -> BBox | None:
    values = list(value)
    if len(values) != 4 or len(shape) < 2:
        return None
    height, width = int(shape[0]), int(shape[1])
    try:
        x1, y1, x2, y2 = (int(round(float(item))) for item in values)
    except (TypeError, ValueError):
        return None
    result = (
        max(0, min(width, x1)),
        max(0, min(height, y1)),
        max(0, min(width, x2)),
        max(0, min(height, y2)),
    )
    return result if result[2] > result[0] and result[3] > result[1] else None


def _expanded(
    bbox: BBox,
    shape: tuple[int, ...],
    *,
    scale_x: float,
    scale_y: float,
) -> BBox | None:
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half_w, half_h = (x2 - x1) * scale_x / 2, (y2 - y1) * scale_y / 2
    return _bbox((cx - half_w, cy - half_h, cx + half_w, cy + half_h), shape)


def _upper_person(bbox: BBox, shape: tuple[int, ...]) -> BBox | None:
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    return _bbox(
        (x1 - 0.08 * width, y1 - 0.03 * height, x2 + 0.08 * width, y1 + 0.45 * height),
        shape,
    )


def _full_box(bbox: BBox, shape: tuple[int, ...]) -> BBox | None:
    return _expanded(bbox, shape, scale_x=1.04, scale_y=1.04)


def _odd_kernel(requested: int, ceiling: int) -> int:
    result = min(max(3, requested), ceiling)
    return result - 1 if result % 2 == 0 else result


def _redact(frame: Any, roi_bbox: BBox, *, style: BlurStyle, strength: int) -> str:
    import cv2
    import numpy as np

    x1, y1, x2, y2 = roi_bbox
    roi = frame[y1:y2, x1:x2]
    height, width = roi.shape[:2]
    if not width or not height:
        raise ValueError("cannot redact an empty ROI")

    if style == "solid" or min(width, height) < 3:
        frame[y1:y2, x1:x2] = np.mean(roi, axis=(0, 1)).astype(roi.dtype)
        return "solid"
    if style == "pixelate":
        divisor = max(2, strength)
        tiny = cv2.resize(
            roi,
            (max(1, width // divisor), max(1, height // divisor)),
            interpolation=cv2.INTER_AREA,
        )
        frame[y1:y2, x1:x2] = cv2.resize(
            tiny, (width, height), interpolation=cv2.INTER_NEAREST
        )
        return "pixelate"

    kernel = _odd_kernel(strength, min(width, height))
    if kernel < 3:
        frame[y1:y2, x1:x2] = np.mean(roi, axis=(0, 1)).astype(roi.dtype)
        return "solid"
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kernel, kernel), 0)
    return "gaussian"


def _target_from_dict(value: dict[str, Any]) -> AnonymizationTarget:
    source = value["source"]
    start = float(value["valid_from_seconds"])
    end = value.get("valid_until_seconds")
    end = None if end is None else float(end)
    if start < 0 or (end is not None and end <= start):
        raise AnonymizationConfigError("invalid anonymization target time range")
    confidence = value.get("confidence")
    confidence = None if confidence is None else float(confidence)
    if confidence is not None and not 0 <= confidence <= 1:
        raise AnonymizationConfigError("target confidence must be between 0 and 1")
    return AnonymizationTarget(
        decision_id=str(value["decision_id"]),
        track_id=str(value["track_id"]),
        source=source,
        stream_id=str(value["stream_id"]),
        asset_uid=str(value["asset_uid"]),
        segment_id=str(value["segment_id"]),
        valid_from_seconds=start,
        valid_until_seconds=end,
        character_name=_text(value.get("character_name")),
        detected_class=_text(value.get("detected_class")),
        confidence=confidence,
        basis_ref=_text(value.get("basis_ref")),
    )


def load_target_manifest(
    path: Path,
    *,
    schema_path: Path = DEFAULT_TARGET_SCHEMA,
) -> tuple[list[AnonymizationTarget], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    targets = [_target_from_dict(item) for item in payload["targets"]]
    return targets, _sha256(_stable_json(payload).encode())


def accepted_targets_from_yolo_receipt(
    receipt_path: Path,
    *,
    stream_id: str,
    asset_uid: str,
    segment_id: str,
    character_name: str,
) -> tuple[list[AnonymizationTarget], str]:
    """Project timed human accept/reset events into asset-bound redaction intervals."""

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AnonymizationConfigError("YOLO label receipt must be a JSON object")
    if payload.get("schema") != "watch.yolo_track_labels.v1":
        raise AnonymizationConfigError(f"unexpected YOLO receipt schema: {receipt_path}")
    receipt_asset_uid = _text(payload.get("asset_uid"))
    if receipt_asset_uid != asset_uid:
        raise AnonymizationConfigError(
            "YOLO label receipt asset_uid does not match --asset-uid: "
            f"{receipt_asset_uid!r} != {asset_uid!r}"
        )
    receipt_row_index = payload.get("row_index")
    if (
        not isinstance(receipt_row_index, int)
        or isinstance(receipt_row_index, bool)
        or receipt_row_index < 0
    ):
        raise AnonymizationConfigError(
            "YOLO label receipt row_index must be a nonnegative integer"
        )
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise AnonymizationConfigError("YOLO receipt events must be an array")
    evidence_hash = _sha256(_stable_json(payload).encode())

    events: list[tuple[dict[str, Any], int]] = []
    for index, event in enumerate(raw_events):
        if not isinstance(event, dict):
            raise AnonymizationConfigError(f"YOLO receipt event {index} must be an object")
        event_asset_uid = _text(event.get("asset_uid"))
        if event_asset_uid != asset_uid:
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} is not bound to asset_uid {asset_uid!r}"
            )
        event_row_index = event.get("row_index")
        if (
            not isinstance(event_row_index, int)
            or isinstance(event_row_index, bool)
            or event_row_index != receipt_row_index
        ):
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} row_index does not match the receipt"
            )
        action = event.get("action")
        if action not in {"accept", "reject", "reset", "reject_box", "reset_box"}:
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} has unsupported action: {action!r}"
            )
        sequence = event.get("sequence")
        if sequence is not None and (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence < 1
        ):
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} sequence must be a positive integer"
            )
        event_time = event.get("time_seconds")
        if event_time is None:
            # Legacy labels without an event time cannot authorize a bounded export.
            continue
        if not _is_finite_number(event_time) or float(event_time) < 0:
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} time_seconds must be null or nonnegative"
            )
        if _text(event.get("track_id")) is None:
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} track_id must be nonempty"
            )
        confidence = event.get("confidence")
        if confidence is not None and (
            not _is_finite_number(confidence) or not 0 <= float(confidence) <= 1
        ):
            raise AnonymizationConfigError(
                f"YOLO receipt event {index} confidence must be between 0 and 1"
            )
        events.append((event, index))

    def sort_key(pair: tuple[dict[str, Any], int]) -> tuple[float, int, int]:
        event, index = pair
        sequence = event.get("sequence")
        sequence_key = int(sequence) if isinstance(sequence, int) else index
        return (float(event["time_seconds"]), sequence_key, index)

    events.sort(key=sort_key)

    requested = character_name.strip().casefold()
    active: dict[str, tuple[dict[str, Any], float]] = {}
    targets: list[AnonymizationTarget] = []

    def close(track_id: str, end: float | None) -> None:
        opened = active.pop(track_id, None)
        if opened is None:
            return
        event, start = opened
        if end is not None and end <= start:
            return
        event_id = _text(event.get("id")) or _sha256(_stable_json(event).encode())[:24]
        targets.append(
            AnonymizationTarget(
                decision_id=f"anon_accept_{event_id}",
                track_id=track_id,
                source="accepted",
                stream_id=stream_id,
                asset_uid=asset_uid,
                segment_id=segment_id,
                valid_from_seconds=start,
                valid_until_seconds=end,
                character_name=_text(event.get("character_name")),
                confidence=(
                    float(event["confidence"])
                    if _is_finite_number(event.get("confidence"))
                    else None
                ),
                basis_ref=(
                    "watch.yolo_track_labels.v1:"
                    f"sha256:{evidence_hash}#event={event_id}"
                ),
            )
        )

    for event, _index in events:
        track_id = _text(event.get("track_id"))
        if track_id is None:
            continue
        timestamp = float(event["time_seconds"])
        action = event.get("action")
        if action in {"reject", "reset", "reject_box", "reset_box"}:
            close(track_id, timestamp)
        elif action == "accept":
            close(track_id, timestamp)
            name = _text(event.get("character_name"))
            if name and name.casefold() == requested:
                active[track_id] = (event, timestamp)

    for track_id in sorted(active):
        close(track_id, None)
    return targets, evidence_hash


def manual_track_targets(
    track_ids: Iterable[str],
    *,
    stream_id: str,
    asset_uid: str,
    segment_id: str,
    valid_from_seconds: float,
    character_name: str | None,
) -> list[AnonymizationTarget]:
    result = []
    for raw in track_ids:
        track_id = str(raw).strip()
        if not track_id:
            continue
        track_id = track_id if track_id.startswith("track_") else f"track_{track_id}"
        seed = _stable_json(
            [
                stream_id,
                asset_uid,
                segment_id,
                track_id,
                valid_from_seconds,
                character_name,
            ]
        )
        result.append(
            AnonymizationTarget(
                decision_id=f"anon_manual_{_sha256(seed.encode())[:20]}",
                track_id=track_id,
                source="manual-track",
                stream_id=stream_id,
                asset_uid=asset_uid,
                segment_id=segment_id,
                valid_from_seconds=float(valid_from_seconds),
                character_name=_text(character_name),
                basis_ref="cli:--blur-track",
            )
        )
    return result


def _target_scope(target: AnonymizationTarget) -> tuple[str, str, str]:
    return (target.stream_id, target.asset_uid, target.segment_id)


def _validate_target(target: AnonymizationTarget) -> None:
    for field_name in (
        "decision_id",
        "track_id",
        "stream_id",
        "asset_uid",
        "segment_id",
    ):
        if not _text(getattr(target, field_name)):
            raise AnonymizationConfigError(f"target {field_name} must be nonempty")
    if not target.track_id.startswith("track_"):
        raise AnonymizationConfigError("target track_id must start with 'track_'")
    suffix = target.track_id.removeprefix("track_")
    if not suffix or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in suffix
    ):
        raise AnonymizationConfigError(
            "target track_id contains unsupported characters"
        )
    if target.source not in {"accepted", "suggested", "manual-track"}:
        raise AnonymizationConfigError(f"invalid target source: {target.source}")
    if (
        not _is_finite_number(target.valid_from_seconds)
        or float(target.valid_from_seconds) < 0
    ):
        raise AnonymizationConfigError("target valid_from_seconds must be nonnegative")
    if target.valid_until_seconds is not None and (
        not _is_finite_number(target.valid_until_seconds)
        or float(target.valid_until_seconds) <= float(target.valid_from_seconds)
    ):
        raise AnonymizationConfigError(
            "target valid_until_seconds must be finite and greater than its start"
        )
    if target.confidence is not None and (
        not _is_finite_number(target.confidence)
        or not 0 <= float(target.confidence) <= 1
    ):
        raise AnonymizationConfigError("target confidence must be between 0 and 1")


def _targets_overlap(a: AnonymizationTarget, b: AnonymizationTarget) -> bool:
    if a.track_id != b.track_id or _target_scope(a) != _target_scope(b):
        return False
    if (
        a.detected_class is not None
        and b.detected_class is not None
        and a.detected_class != b.detected_class
    ):
        return False
    a_end = math.inf if a.valid_until_seconds is None else a.valid_until_seconds
    b_end = math.inf if b.valid_until_seconds is None else b.valid_until_seconds
    return max(a.valid_from_seconds, b.valid_from_seconds) < min(a_end, b_end)


def select_targets(
    targets: Iterable[AnonymizationTarget],
    config: AnonymizationConfig,
    *,
    expected_scope: tuple[str, str, str] | None = None,
) -> tuple[AnonymizationTarget, ...]:
    requested = _text(config.character_name)
    candidates = tuple(targets)
    for target in candidates:
        _validate_target(target)
    selected = tuple(
        target
        for target in candidates
        if target.source == config.source
        and (expected_scope is None or _target_scope(target) == expected_scope)
        and (
            requested is None
            or (
                target.character_name is not None
                and target.character_name.casefold() == requested.casefold()
            )
        )
    )
    if not selected:
        raise AnonymizationConfigError(
            "anonymization policy selected no targets for the requested "
            "stream/asset/segment; refusing a false-green export"
        )
    scopes = {_target_scope(target) for target in selected}
    if len(scopes) != 1:
        raise AnonymizationConfigError(
            "one anonymization session cannot span multiple stream/asset/segment scopes"
        )
    decision_ids: set[str] = set()
    for index, current in enumerate(selected):
        if current.decision_id in decision_ids:
            raise AnonymizationConfigError(
                f"duplicate anonymization decision_id: {current.decision_id}"
            )
        decision_ids.add(current.decision_id)
        for previous in selected[:index]:
            if _targets_overlap(previous, current):
                raise AnonymizationConfigError(
                    "overlapping anonymization decisions are ambiguous for "
                    f"{current.track_id}: {previous.decision_id}, {current.decision_id}"
                )
    return selected


class AnonymizationEngine:
    """Stateful compositor with bounded dropout hold and decision retirement."""

    def __init__(
        self,
        *,
        config: AnonymizationConfig,
        targets: Iterable[AnonymizationTarget],
        face_localizer: FaceLocalizer | None = None,
        target_evidence_sha256: str | None = None,
        expected_scope: tuple[str, str, str] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.targets = select_targets(
            targets, config, expected_scope=expected_scope
        )
        self.scope = _target_scope(self.targets[0])
        self.face_localizer = face_localizer
        self.target_evidence_sha256 = target_evidence_sha256
        self._states: dict[tuple[str, str], _TrackState] = {}
        self._retired: set[str] = set()
        self._last_times: dict[str, float] = {}

    def _matches(
        self,
        *,
        track_id: str,
        detected_class: str,
        stream_id: str,
        asset_uid: str,
        segment_id: str,
        timestamp: float,
    ) -> list[AnonymizationTarget]:
        return sorted(
            (
                target
                for target in self.targets
                if target.track_id == track_id
                and target.active_at(
                    stream_id, asset_uid, segment_id, timestamp
                )
                and (
                    target.detected_class is None
                    or target.detected_class == detected_class
                )
            ),
            key=lambda target: (target.valid_from_seconds, target.decision_id),
            reverse=True,
        )

    def _retire(self, key: tuple[str, str]) -> None:
        state = self._states.pop(key, None)
        if state:
            self._retired.add(state.target.decision_id)

    def _roi(
        self,
        frame: Any,
        bbox: BBox,
        detected_class: str,
    ) -> tuple[BBox | None, str, str | None]:
        if self.config.mode == "person":
            return _full_box(bbox, frame.shape), "full_track_box", None
        if detected_class != "person":
            return (
                _full_box(bbox, frame.shape),
                "full_track_box",
                f"{self.config.mode}_requires_person_class",
            )
        if self.config.mode == "upper-person":
            return _upper_person(bbox, frame.shape), "upper_person", None
        if self.face_localizer:
            try:
                face, reason = self.face_localizer.locate(frame, bbox)
            except Exception as exc:  # localizer failure must not expose the target
                return (
                    _upper_person(bbox, frame.shape),
                    "upper_person_fallback",
                    f"face_localizer_error:{type(exc).__name__}",
                )
            face_bbox = _bbox(face, frame.shape) if face is not None else None
            if face_bbox is not None:
                face_cx = (face_bbox[0] + face_bbox[2]) / 2
                face_cy = (face_bbox[1] + face_bbox[3]) / 2
                face_belongs_to_target = (
                    bbox[0] <= face_cx <= bbox[2]
                    and bbox[1] <= face_cy <= bbox[3]
                )
                if face_belongs_to_target:
                    expanded = _expanded(
                        face_bbox, frame.shape, scale_x=1.6, scale_y=1.6
                    )
                    if expanded is not None:
                        return expanded, "face_detector", None
            fallback_reason = reason or (
                "face_not_detected"
                if face is None
                else "face_bbox_invalid"
                if face_bbox is None
                else "face_outside_target_person"
            )
            return (
                _upper_person(bbox, frame.shape),
                "upper_person_fallback",
                fallback_reason,
            )
        return (
            _upper_person(bbox, frame.shape),
            "upper_person_fallback",
            "face_localizer_unconfigured",
        )

    def apply(
        self,
        frame: Any,
        *,
        tracks: Iterable[dict[str, Any]],
        stream_id: str,
        asset_uid: str,
        segment_id: str,
        frame_index: int,
        media_time_seconds: float,
    ) -> tuple[Any, dict[str, Any]]:
        timestamp = float(media_time_seconds)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("media_time_seconds must be nonnegative and finite")
        requested_scope = (stream_id, asset_uid, segment_id)
        if requested_scope != self.scope:
            raise AnonymizationConfigError(
                "frame scope does not match the selected anonymization targets: "
                f"{requested_scope!r} != {self.scope!r}"
            )
        if timestamp < self._last_times.get(segment_id, timestamp):
            raise ValueError("anonymization frames must be processed in source-time order")
        self._last_times[segment_id] = timestamp

        rendered = frame.copy()
        applications: list[dict[str, Any]] = []
        non_applications: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for track in tracks:
            track_id = _text(track.get("track_id"))
            if track_id is None:
                continue
            detected_class = _text(track.get("detected_class")) or "unknown"
            key = (segment_id, track_id)
            if key in seen:
                raise ValueError(f"duplicate track_id in frame: {track_id}")
            seen.add(key)
            matches = self._matches(
                track_id=track_id,
                detected_class=detected_class,
                stream_id=stream_id,
                asset_uid=asset_uid,
                segment_id=segment_id,
                timestamp=timestamp,
            )
            target = matches[0] if matches else None
            state = self._states.get(key)
            if target is None:
                self._retire(key)
                continue
            if state and state.target.decision_id != target.decision_id:
                self._retire(key)
                state = None
            if state is None and target.decision_id in self._retired:
                non_applications.append(
                    _non_application(target, "decision_retired_after_track_gap")
                )
                continue

            bbox = _bbox(track.get("bbox_xyxy", []), frame.shape)
            if bbox is None:
                if (
                    state is not None
                    and timestamp - state.last_seen_seconds <= self.config.hold_ms / 1000
                ):
                    method = _redact(
                        rendered,
                        state.roi,
                        style=self.config.style,
                        strength=self.config.strength,
                    )
                    applications.append(
                        _application(
                            state.target,
                            state.bbox,
                            state.roi,
                            self.config.mode,
                            method,
                            "held_last_roi",
                            "current_track_bbox_invalid",
                            True,
                        )
                    )
                else:
                    if state is not None:
                        self._retire(key)
                    non_applications.append(
                        _non_application(target, "current_track_bbox_invalid")
                    )
                continue
            roi, localizer, fallback = self._roi(rendered, bbox, detected_class)
            if roi is None:
                non_applications.append(_non_application(target, "redaction_roi_invalid"))
                continue
            method = _redact(
                rendered, roi, style=self.config.style, strength=self.config.strength
            )
            self._states[key] = _TrackState(target, bbox, roi, timestamp, detected_class)
            applications.append(
                _application(
                    target,
                    bbox,
                    roi,
                    self.config.mode,
                    method,
                    localizer,
                    fallback,
                    False,
                )
            )

        for key, state in list(self._states.items()):
            if key in seen:
                continue
            if key[0] != segment_id or not state.target.active_at(
                stream_id, asset_uid, segment_id, timestamp
            ):
                self._retire(key)
                continue
            if timestamp - state.last_seen_seconds > self.config.hold_ms / 1000:
                self._retire(key)
                non_applications.append(
                    _non_application(state.target, "track_stale_decision_retired")
                )
                continue
            method = _redact(
                rendered,
                state.roi,
                style=self.config.style,
                strength=self.config.strength,
            )
            applications.append(
                _application(
                    state.target,
                    state.bbox,
                    state.roi,
                    self.config.mode,
                    method,
                    "held_last_roi",
                    None,
                    True,
                )
            )

        if self.face_localizer is None:
            face_provenance = {"localizer": "none", "network_used": False}
        else:
            try:
                face_provenance = self.face_localizer.provenance
            except Exception as exc:  # receipts must survive optional provenance bugs
                face_provenance = {
                    "localizer": "provenance_unavailable",
                    "network_used": False,
                    "error_type": type(exc).__name__,
                }

        input_hash = _frame_sha256(frame)
        receipt = {
            "schema": FRAME_RECEIPT_SCHEMA_VERSION,
            "stream_id": stream_id,
            "asset_uid": asset_uid,
            "segment_id": segment_id,
            "frame_index": int(frame_index),
            "media_time_seconds": timestamp,
            "policy": {
                "source": self.config.source,
                "character_name": self.config.character_name,
                "mode": self.config.mode,
                "style": self.config.style,
                "strength": self.config.strength,
                "hold_ms": self.config.hold_ms,
                "allow_suggested_export": self.config.allow_suggested_export,
                "target_evidence_sha256": self.target_evidence_sha256,
                "face_localizer": face_provenance,
            },
            "anonymization_applied": bool(applications),
            "applications": applications,
            "non_applications": non_applications,
            "identity_mutated": False,
            "deidentification_claimed": False,
            "input_frame_sha256": input_hash,
            "output_frame_sha256": _frame_sha256(rendered),
            "emitted_at": _utc_now(),
        }
        return rendered, receipt


def _application(
    target: AnonymizationTarget,
    bbox: BBox,
    roi: BBox,
    mode: BlurMode,
    method: str,
    localizer: str,
    fallback: str | None,
    held: bool,
) -> dict[str, Any]:
    return {
        "decision_id": target.decision_id,
        "track_id": target.track_id,
        "source": target.source,
        "character_name": target.character_name,
        "confidence": target.confidence,
        "basis_ref": target.basis_ref,
        "input_bbox_xyxy": list(bbox),
        "roi_xyxy": list(roi),
        "requested_mode": mode,
        "applied_method": method,
        "localizer": localizer,
        "fallback_reason": fallback,
        "held_from_last_observation": held,
    }


def _non_application(target: AnonymizationTarget, reason: str) -> dict[str, Any]:
    return {
        "track_id": target.track_id,
        "decision_id": target.decision_id,
        "source": target.source,
        "reason": reason,
    }


def _resolved_path(value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.isdigit() or "://" in text:
        return None
    return Path(text).expanduser().resolve(strict=False)


def _validate_redaction_paths(
    args: Any,
    *,
    receipt_path: Path,
    label_receipt: Any,
    target_manifest: Any,
) -> None:
    source_path = _resolved_path(getattr(args, "source", None))
    output_path = _resolved_path(getattr(args, "output_video", None))
    receipt_resolved = receipt_path.expanduser().resolve(strict=False)
    label_path = _resolved_path(label_receipt)
    manifest_path = _resolved_path(target_manifest)

    inputs = {
        "source": source_path,
        "label receipt": label_path,
        "target manifest": manifest_path,
    }
    outputs = {
        "output video": output_path,
        "anonymization receipt": receipt_resolved,
    }
    for output_name, output in outputs.items():
        if output is None:
            continue
        for input_name, input_path in inputs.items():
            if input_path is not None and output == input_path:
                raise AnonymizationConfigError(
                    f"{output_name} must not overwrite the {input_name}: {output}"
                )
    if output_path is not None and output_path == receipt_resolved:
        raise AnonymizationConfigError(
            "--output-video and --anonymization-receipt must be different paths"
        )


def session_from_args(args: Any) -> "AnonymizationSession":
    """Build a session from the live tracker argparse namespace."""

    source = getattr(args, "blur_source", None)
    related_used = any(
        (
            getattr(args, "blur_character", None),
            getattr(args, "blur_target_manifest", None),
            getattr(args, "blur_label_receipt", None),
            tuple(getattr(args, "blur_track", []) or []),
            getattr(args, "anonymization_receipt", None),
            getattr(args, "allow_suggested_export", False),
        )
    ) or any(
        getattr(args, option, None) is not None
        for option in (
            "blur_mode",
            "blur_style",
            "blur_strength",
            "blur_hold_ms",
        )
    )
    if source is None:
        if related_used:
            raise AnonymizationConfigError(
                "--blur-source is required when any anonymization option is used"
            )
        return AnonymizationSession(engine=None, receipt_path=None)

    start_seconds = getattr(args, "start_seconds", None)
    if not _is_finite_number(start_seconds) or float(start_seconds) < 0:
        raise AnonymizationConfigError(
            "--start-seconds must be nonnegative and finite for anonymization"
        )
    sample_fps = getattr(args, "sample_fps", None)
    if not _is_finite_number(sample_fps) or float(sample_fps) <= 0:
        raise AnonymizationConfigError(
            "--sample-fps must be greater than zero for anonymization"
        )
    scope_values = []
    for option_name in ("stream_id", "asset_uid", "segment_id"):
        value = _text(getattr(args, option_name, None))
        if value is None:
            raise AnonymizationConfigError(
                f"--{option_name.replace('_', '-')} must be nonempty for anonymization"
            )
        scope_values.append(value)
    run_scope = tuple(scope_values)

    config = AnonymizationConfig(
        source=source,
        mode=_arg_or_default(args, "blur_mode", "upper-person"),
        style=_arg_or_default(args, "blur_style", "gaussian"),
        strength=int(_arg_or_default(args, "blur_strength", 31)),
        hold_ms=int(_arg_or_default(args, "blur_hold_ms", 750)),
        character_name=_text(getattr(args, "blur_character", None)),
        allow_suggested_export=bool(
            getattr(args, "allow_suggested_export", False)
        ),
    )
    permanent_output = bool(getattr(args, "output_video", None))
    config.validate(permanent_output=permanent_output)
    if permanent_output:
        minimum_hold_ms = math.ceil(1000.0 / float(sample_fps))
        if config.hold_ms < minimum_hold_ms:
            raise AnonymizationConfigError(
                "--blur-hold-ms must cover at least one detector sample interval "
                f"for --output-video ({minimum_hold_ms}ms at {float(sample_fps):g} fps)"
            )

    target_manifest = getattr(args, "blur_target_manifest", None)
    label_receipt = getattr(args, "blur_label_receipt", None)
    manual_tracks = tuple(getattr(args, "blur_track", []) or [])
    if source == "accepted":
        if not label_receipt or target_manifest or manual_tracks:
            raise AnonymizationConfigError(
                "accepted blur requires --blur-label-receipt and cannot trust "
                "an unverified target manifest or manual-track input as accepted identity"
            )
        targets, evidence_hash = accepted_targets_from_yolo_receipt(
            Path(label_receipt),
            stream_id=run_scope[0],
            asset_uid=run_scope[1],
            segment_id=run_scope[2],
            character_name=str(config.character_name),
        )
    elif source == "suggested":
        if not target_manifest or label_receipt or manual_tracks:
            raise AnonymizationConfigError(
                "suggested blur requires --blur-target-manifest and cannot use "
                "accepted-label or manual-track inputs"
            )
        targets, evidence_hash = load_target_manifest(Path(target_manifest))
    else:
        if not manual_tracks or target_manifest or label_receipt:
            raise AnonymizationConfigError(
                "manual-track blur requires one or more --blur-track values and "
                "cannot use accepted/suggested target inputs"
            )
        targets = manual_track_targets(
            manual_tracks,
            stream_id=run_scope[0],
            asset_uid=run_scope[1],
            segment_id=run_scope[2],
            valid_from_seconds=float(args.start_seconds),
            character_name=config.character_name,
        )
        evidence_hash = _sha256(_stable_json(target_manifest_payload(targets)).encode())

    receipt_path = getattr(args, "anonymization_receipt", None)
    if receipt_path is None:
        receipt_path = Path(args.out_dir) / "watch_anonymization_receipts.jsonl"
    receipt_path = Path(receipt_path)
    _validate_redaction_paths(
        args,
        receipt_path=receipt_path,
        label_receipt=label_receipt,
        target_manifest=target_manifest,
    )
    engine = AnonymizationEngine(
        config=config,
        targets=targets,
        target_evidence_sha256=evidence_hash,
        expected_scope=(run_scope[0], run_scope[1], run_scope[2]),
    )
    return AnonymizationSession(engine=engine, receipt_path=receipt_path)


def anonymization_config_summary(args: Any) -> dict[str, Any]:
    source = getattr(args, "blur_source", None)
    if source is None:
        return {
            "enabled": False,
            "identity_mutated": False,
            "deidentification_claimed": False,
        }
    receipt_path = getattr(args, "anonymization_receipt", None)
    if receipt_path is None:
        receipt_path = Path(args.out_dir) / "watch_anonymization_receipts.jsonl"
    return {
        "enabled": True,
        "source": source,
        "character_name": getattr(args, "blur_character", None),
        "mode": _arg_or_default(args, "blur_mode", "upper-person"),
        "style": _arg_or_default(args, "blur_style", "gaussian"),
        "strength": int(_arg_or_default(args, "blur_strength", 31)),
        "hold_ms": int(_arg_or_default(args, "blur_hold_ms", 750)),
        "receipt_path": str(receipt_path),
        "identity_mutated": False,
        "deidentification_claimed": False,
    }


class AnonymizationSession:
    def __init__(
        self,
        *,
        engine: AnonymizationEngine | None,
        receipt_path: Path | None,
    ) -> None:
        self.engine = engine
        self.receipt_path = receipt_path
        self._handle: Any = None

    @property
    def enabled(self) -> bool:
        return self.engine is not None

    def __enter__(self) -> "AnonymizationSession":
        if self.enabled:
            assert self.receipt_path is not None
            self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.receipt_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            self._handle = os.fdopen(descriptor, "w", encoding="utf-8")
        return self

    def __exit__(self, *_args: Any) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None

    def process(self, frame: Any, **kwargs: Any) -> tuple[Any, dict[str, Any] | None]:
        if self.engine is None:
            return frame, None
        if self._handle is None:
            raise RuntimeError("anonymization session must be entered before processing")
        rendered, receipt = self.engine.apply(frame, **kwargs)
        self._handle.write(_stable_json(receipt) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        return rendered, receipt


def anonymization_message_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if receipt is None:
        return {
            "enabled": False,
            "anonymization_applied": False,
            "identity_mutated": False,
            "deidentification_claimed": False,
        }
    return {
        "enabled": True,
        "receipt_schema": receipt["schema"],
        "anonymization_applied": receipt["anonymization_applied"],
        "application_count": len(receipt["applications"]),
        "non_application_count": len(receipt["non_applications"]),
        "identity_mutated": False,
        "deidentification_claimed": False,
        "output_frame_sha256": receipt["output_frame_sha256"],
    }


def target_manifest_payload(
    targets: Iterable[AnonymizationTarget],
) -> dict[str, Any]:
    return {
        "schema": TARGET_SCHEMA_VERSION,
        "targets": [asdict(target) for target in targets],
    }
