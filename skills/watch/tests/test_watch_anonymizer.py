"""Regression tests for Watch post-detection pixel redaction."""
from __future__ import annotations

import base64
import json
import types
from pathlib import Path

import cv2
import numpy as np
import pytest
import sys
from jsonschema import Draft202012Validator

WATCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WATCH_DIR))

from scripts.watch_anonymizer import (
    AnonymizationConfig,
    AnonymizationConfigError,
    AnonymizationEngine,
    AnonymizationSession,
    AnonymizationTarget,
    accepted_targets_from_yolo_receipt,
    load_target_manifest,
    session_from_args,
    target_manifest_payload,
)
from scripts.live_ultralytics_tracking import iter_track_events, iter_track_frames


def checkerboard(height: int = 120, width: int = 160) -> np.ndarray:
    yy, xx = np.indices((height, width))
    pattern = ((xx // 2 + yy // 2) % 2 * 255).astype(np.uint8)
    return np.repeat(pattern[:, :, None], 3, axis=2)


def target(
    *,
    decision_id: str = "decision_1",
    track_id: str = "track_1",
    source: str = "accepted",
    start: float = 0.0,
    end: float | None = None,
    character: str | None = "Willie",
) -> AnonymizationTarget:
    return AnonymizationTarget(
        decision_id=decision_id,
        track_id=track_id,
        source=source,  # type: ignore[arg-type]
        stream_id="stream_1",
        asset_uid="asset_1",
        segment_id="segment_1",
        valid_from_seconds=start,
        valid_until_seconds=end,
        character_name=character,
        basis_ref="fixture#decision",
    )


def track(track_id: str = "track_1", bbox=(30, 20, 110, 110), detected_class="person"):
    return {
        "track_id": track_id,
        "bbox_xyxy": list(bbox),
        "detected_class": detected_class,
    }


def apply(
    engine: AnonymizationEngine,
    frame: np.ndarray,
    *,
    tracks,
    timestamp: float,
    frame_index: int = 0,
):
    return engine.apply(
        frame,
        tracks=tracks,
        stream_id="stream_1",
        asset_uid="asset_1",
        segment_id="segment_1",
        frame_index=frame_index,
        media_time_seconds=timestamp,
    )


def mask_outside(shape: tuple[int, ...], roi: list[int]) -> np.ndarray:
    mask = np.ones(shape[:2], dtype=bool)
    x1, y1, x2, y2 = roi
    mask[y1:y2, x1:x2] = False
    return mask


def laplacian_variance(image: np.ndarray) -> float:
    return float(cv2.Laplacian(image, cv2.CV_64F).var())


def test_accepted_willie_track_blurs_pixels_and_preserves_outside_roi():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
            strength=31,
        ),
        targets=[target()],
    )

    rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)
    application = receipt["applications"][0]
    roi = application["roi_xyxy"]
    x1, y1, x2, y2 = roi

    assert receipt["anonymization_applied"] is True
    assert receipt["identity_mutated"] is False
    assert receipt["deidentification_claimed"] is False
    assert receipt["input_frame_sha256"] != receipt["output_frame_sha256"]
    assert np.array_equal(frame[mask_outside(frame.shape, roi)], rendered[mask_outside(frame.shape, roi)])
    assert laplacian_variance(rendered[y1:y2, x1:x2]) < laplacian_variance(frame[y1:y2, x1:x2])


def test_suggested_willie_is_redaction_target_not_accepted_identity():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="suggested",
            character_name="Willie",
            mode="upper-person",
        ),
        targets=[target(source="suggested")],
    )

    _rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)

    assert receipt["applications"][0]["source"] == "suggested"
    assert receipt["identity_mutated"] is False
    assert "identity_accepted" not in json.dumps(receipt)
    assert "accept" not in receipt["applications"][0]


def test_non_target_track_is_byte_identical():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target(track_id="track_1")],
    )

    rendered, receipt = apply(
        engine,
        frame,
        tracks=[track(track_id="track_2")],
        timestamp=1.0,
    )

    assert np.array_equal(frame, rendered)
    assert receipt["applications"] == []
    assert receipt["input_frame_sha256"] == receipt["output_frame_sha256"]


class MissingFaceLocalizer:
    @property
    def provenance(self):
        return {"localizer": "fixture_missing_face", "network_used": False}

    def locate(self, _frame, _person_bbox):
        return None, "face_not_detected"


def test_face_miss_falls_back_to_upper_person_instead_of_leaving_target_clear():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="face",
        ),
        targets=[target()],
        face_localizer=MissingFaceLocalizer(),
    )

    rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)
    application = receipt["applications"][0]

    assert application["localizer"] == "upper_person_fallback"
    assert application["fallback_reason"] == "face_not_detected"
    assert not np.array_equal(frame, rendered)


def test_face_mode_without_model_also_falls_back_fail_safe():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="face",
        ),
        targets=[target()],
    )

    _rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)

    assert receipt["applications"][0]["localizer"] == "upper_person_fallback"
    assert receipt["applications"][0]["fallback_reason"] == "face_localizer_unconfigured"


def test_non_person_target_uses_full_track_box_in_face_mode():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="manual-track",
            character_name=None,
            mode="face",
        ),
        targets=[target(source="manual-track", character=None)],
    )

    _rendered, receipt = apply(
        engine,
        frame,
        tracks=[track(detected_class="object")],
        timestamp=1.0,
    )

    assert receipt["applications"][0]["localizer"] == "full_track_box"
    assert receipt["applications"][0]["fallback_reason"] == "face_requires_person_class"


def test_reset_boundary_stops_redaction_at_the_event_timestamp():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target(end=5.0)],
    )

    before_stop, before_receipt = apply(engine, frame, tracks=[track()], timestamp=4.99)
    at_stop, stop_receipt = apply(
        engine,
        frame,
        tracks=[track()],
        timestamp=5.0,
        frame_index=1,
    )

    assert before_receipt["anonymization_applied"] is True
    assert not np.array_equal(before_stop, frame)
    assert stop_receipt["anonymization_applied"] is False
    assert np.array_equal(at_stop, frame)


def test_dropout_is_held_then_reused_track_id_requires_new_decision():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
            hold_ms=750,
        ),
        targets=[target()],
    )

    _rendered, first = apply(engine, frame, tracks=[track()], timestamp=0.0)
    _held, held = apply(engine, frame, tracks=[], timestamp=0.5, frame_index=1)
    stale_frame, stale = apply(engine, frame, tracks=[], timestamp=0.8, frame_index=2)
    reused_frame, reused = apply(
        engine,
        frame,
        tracks=[track()],
        timestamp=0.9,
        frame_index=3,
    )

    assert first["applications"][0]["held_from_last_observation"] is False
    assert held["applications"][0]["held_from_last_observation"] is True
    assert stale["non_applications"][0]["reason"] == "track_stale_decision_retired"
    assert np.array_equal(stale_frame, frame)
    assert reused["non_applications"][0]["reason"] == "decision_retired_after_track_gap"
    assert np.array_equal(reused_frame, frame)


def test_new_decision_can_redact_reused_track_id_after_gap():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
            hold_ms=100,
        ),
        targets=[
            target(decision_id="old", end=0.1),
            target(decision_id="new", start=1.0),
        ],
    )

    apply(engine, frame, tracks=[track()], timestamp=0.0)
    apply(engine, frame, tracks=[], timestamp=0.2, frame_index=1)
    rendered, receipt = apply(
        engine,
        frame,
        tracks=[track()],
        timestamp=1.0,
        frame_index=2,
    )

    assert receipt["applications"][0]["decision_id"] == "new"
    assert not np.array_equal(rendered, frame)


def test_pixelate_mode_reduces_detail():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="manual-track",
            mode="person",
            style="pixelate",
            strength=12,
        ),
        targets=[target(source="manual-track", character=None)],
    )

    rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)
    x1, y1, x2, y2 = receipt["applications"][0]["roi_xyxy"]

    assert receipt["applications"][0]["applied_method"] == "pixelate"
    assert laplacian_variance(rendered[y1:y2, x1:x2]) < laplacian_variance(frame[y1:y2, x1:x2])


def test_suggested_permanent_export_requires_explicit_opt_in():
    config = AnonymizationConfig(
        source="suggested",
        character_name="Willie",
    )

    with pytest.raises(AnonymizationConfigError, match="allow-suggested-export"):
        config.validate(permanent_output=True)

    AnonymizationConfig(
        source="suggested",
        character_name="Willie",
        allow_suggested_export=True,
    ).validate(permanent_output=True)


def test_yolo_receipt_projection_closes_and_reopens_segments(tmp_path: Path):
    receipt_path = tmp_path / "labels.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "watch.yolo_track_labels.v1",
                "asset_uid": "asset_1",
                "row_index": 1,
                "events": [
                    {
                        "id": "accept_1",
                        "sequence": 1,
                        "action": "accept",
                        "asset_uid": "asset_1",
                        "row_index": 1,
                        "track_id": "track_1",
                        "time_seconds": 1.0,
                        "character_name": "Willie",
                    },
                    {
                        "id": "reset_1",
                        "sequence": 2,
                        "action": "reset_box",
                        "asset_uid": "asset_1",
                        "row_index": 1,
                        "track_id": "track_1",
                        "time_seconds": 2.0,
                    },
                    {
                        "id": "accept_2",
                        "sequence": 3,
                        "action": "accept",
                        "asset_uid": "asset_1",
                        "row_index": 1,
                        "track_id": "track_1",
                        "time_seconds": 3.0,
                        "character_name": "Willie",
                    },
                ],
            }
        )
    )

    targets, receipt_hash = accepted_targets_from_yolo_receipt(
        receipt_path,
        stream_id="stream_1",
        asset_uid="asset_1",
        segment_id="segment_1",
        character_name="Willie",
    )

    assert len(targets) == 2
    assert (targets[0].valid_from_seconds, targets[0].valid_until_seconds) == (1.0, 2.0)
    assert (targets[1].valid_from_seconds, targets[1].valid_until_seconds) == (3.0, None)
    assert targets[0].decision_id != targets[1].decision_id
    assert len(receipt_hash) == 64


def test_untimed_legacy_label_is_not_used_for_export(tmp_path: Path):
    receipt_path = tmp_path / "legacy.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "watch.yolo_track_labels.v1",
                "asset_uid": "asset_1",
                "row_index": 1,
                "labels": {"track_1": {"characterName": "Willie"}},
                "events": [],
            }
        )
    )

    targets, _receipt_hash = accepted_targets_from_yolo_receipt(
        receipt_path,
        stream_id="stream_1",
        asset_uid="asset_1",
        segment_id="segment_1",
        character_name="Willie",
    )

    assert targets == []




def test_accepted_source_rejects_unverified_target_manifest(tmp_path: Path):
    manifest = tmp_path / "accepted-targets.json"
    manifest.write_text(json.dumps(target_manifest_payload([target()])))
    args = live_args(tmp_path, tmp_path / "unused.mp4")
    args.blur_source = "accepted"
    args.blur_label_receipt = None
    args.blur_target_manifest = manifest
    args.blur_track = []

    with pytest.raises(AnonymizationConfigError, match="cannot trust"):
        session_from_args(args)

def test_target_and_receipt_schemas_validate(tmp_path: Path):
    target_schema_path = WATCH_DIR / "docs" / "architecture" / "watch_anonymization_targets.schema.json"
    receipt_schema_path = WATCH_DIR / "docs" / "architecture" / "watch_anonymization_receipt.schema.json"
    target_manifest_path = tmp_path / "targets.json"
    target_manifest_path.write_text(json.dumps(target_manifest_payload([target()])))

    targets, digest = load_target_manifest(
        target_manifest_path,
        schema_path=target_schema_path,
    )
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=targets,
        target_evidence_sha256=digest,
    )
    _rendered, receipt = apply(engine, checkerboard(), tracks=[track()], timestamp=1.0)

    Draft202012Validator(
        json.loads(receipt_schema_path.read_text())
    ).validate(receipt)


def test_committed_example_target_manifest_validates():
    target_schema_path = WATCH_DIR / "docs" / "architecture" / "watch_anonymization_targets.schema.json"
    example_path = (
        WATCH_DIR
        / "docs"
        / "architecture"
        / "fixtures"
        / "watch_anonymization_targets.example.json"
    )

    targets, digest = load_target_manifest(
        example_path,
        schema_path=target_schema_path,
    )

    assert targets[0].source == "suggested"
    assert targets[0].character_name == "Willie"
    assert len(digest) == 64


def test_session_writes_one_receipt_per_processed_frame(tmp_path: Path):
    receipt_path = tmp_path / "receipts.jsonl"
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target()],
    )
    with AnonymizationSession(engine=engine, receipt_path=receipt_path) as session:
        session.process(
            checkerboard(),
            tracks=[track()],
            stream_id="stream_1",
            asset_uid="asset_1",
            segment_id="segment_1",
            frame_index=0,
            media_time_seconds=1.0,
        )

    records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["schema"] == "watch.anonymization_frame_receipt.v1"


class FakeBoxes:
    def __init__(self):
        self.xyxy = np.array([[30.0, 20.0, 110.0, 110.0]])
        self.id = np.array([1.0])
        self.conf = np.array([0.95])

    def __len__(self):
        return 1


class FakeResult:
    boxes = FakeBoxes()


class FakeYOLO:
    def __init__(self, _model):
        pass

    def track(self, _frame, **_kwargs):
        return [FakeResult()]


def write_test_video(
    path: Path,
    *,
    frame_count: int = 3,
    fps: float = 5.0,
) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (160, 120),
    )
    assert writer.isOpened()
    for _ in range(frame_count):
        writer.write(checkerboard())
    writer.release()


def live_args(
    tmp_path: Path,
    source: Path,
    *,
    output_video: Path | None = None,
    sample_fps: float = 5.0,
):
    from argparse import Namespace

    return Namespace(
        source=str(source),
        sample_fps=sample_fps,
        model="fake.pt",
        tracker="bytetrack.yaml",
        conf=0.25,
        iou=0.5,
        imgsz=640,
        device=None,
        no_class_filter=False,
        class_id=0,
        detected_class="person",
        attach_domain_candidate=False,
        candidate_name=None,
        candidate_actor_name=None,
        candidate_entity_id=None,
        start_seconds=0.0,
        stream_id="stream_1",
        asset_uid="asset_1",
        segment_id="segment_1",
        jpeg_quality=100,
        pace_realtime=False,
        output_video=output_video,
        display=False,
        max_events=10,
        out_dir=tmp_path,
        blur_source="manual-track",
        blur_character="Willie",
        blur_target_manifest=None,
        blur_label_receipt=None,
        blur_track=["1"],
        blur_mode="person",
        blur_style="gaussian",
        blur_strength=31,
        blur_hold_ms=750,
        allow_suggested_export=False,
        anonymization_receipt=tmp_path / "anonymization.jsonl",
    )


def first_video_frame(path: Path) -> np.ndarray:
    capture = cv2.VideoCapture(str(path))
    ok, frame = capture.read()
    capture.release()
    assert ok
    return frame


def test_frame_stream_encodes_redacted_pixels_not_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.mp4"
    write_test_video(source)
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    args = live_args(tmp_path, source)

    generator = iter_track_frames(args)
    message = next(generator)
    generator.close()

    encoded = np.frombuffer(base64.b64decode(message["jpeg"]), dtype=np.uint8)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    original = first_video_frame(source)
    x1, y1, x2, y2 = [30, 20, 110, 110]

    assert message["anonymization"]["anonymization_applied"] is True
    assert laplacian_variance(decoded[y1 + 5:y2 - 5, x1 + 5:x2 - 5]) < (
        laplacian_variance(original[y1 + 5:y2 - 5, x1 + 5:x2 - 5]) * 0.25
    )
    receipts = [json.loads(line) for line in args.anonymization_receipt.read_text().splitlines()]
    assert len(receipts) == 1
    assert receipts[0]["identity_mutated"] is False


def test_output_video_contains_redacted_pixels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.mp4"
    output = tmp_path / "redacted.mp4"
    write_test_video(source)
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    args = live_args(tmp_path, source, output_video=output)

    events = list(iter_track_events(args))

    assert events
    assert output.is_file() and output.stat().st_size > 0
    original = first_video_frame(source)
    redacted = first_video_frame(output)
    assert laplacian_variance(redacted[30:100, 40:100]) < (
        laplacian_variance(original[30:100, 40:100]) * 0.35
    )
    assert len(args.anonymization_receipt.read_text().splitlines()) == 3


def video_frame_count(path: Path) -> int:
    capture = cv2.VideoCapture(str(path))
    count = 0
    while True:
        ok, _frame = capture.read()
        if not ok:
            break
        count += 1
    capture.release()
    return count


def test_output_video_redacts_every_source_frame_between_detector_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source_10fps.mp4"
    output = tmp_path / "redacted_10fps.mp4"
    write_test_video(source, frame_count=6, fps=10.0)
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    args = live_args(tmp_path, source, output_video=output, sample_fps=2.0)

    events = list(iter_track_events(args))

    assert len(events) == 2
    assert video_frame_count(source) == 6
    assert video_frame_count(output) == 6
    receipts = [
        json.loads(line)
        for line in args.anonymization_receipt.read_text().splitlines()
    ]
    assert len(receipts) == 6
    assert receipts[0]["applications"][0]["held_from_last_observation"] is False
    assert all(
        receipt["anonymization_applied"]
        for receipt in receipts
    )
    assert any(
        application["held_from_last_observation"]
        for receipt in receipts[1:]
        for application in receipt["applications"]
    )

def test_output_video_finishes_source_after_event_budget_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source_budget.mp4"
    output = tmp_path / "redacted_budget.mp4"
    write_test_video(source, frame_count=6, fps=10.0)
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    args = live_args(tmp_path, source, output_video=output, sample_fps=2.0)
    args.max_events = 1

    events = list(iter_track_events(args))

    assert len(events) == 1
    assert video_frame_count(output) == video_frame_count(source) == 6
    receipts = [
        json.loads(line)
        for line in args.anonymization_receipt.read_text().splitlines()
    ]
    assert len(receipts) == 6



class FoundFaceLocalizer:
    @property
    def provenance(self):
        return {
            "localizer": "fixture_found_face",
            "network_used": False,
        }

    def locate(self, _frame, _person_bbox):
        return (50, 30, 70, 50), None


class ExplodingFaceLocalizer:
    @property
    def provenance(self):
        return {
            "localizer": "fixture_exploding_face",
            "network_used": False,
        }

    def locate(self, _frame, _person_bbox):
        raise RuntimeError("fixture localizer failure")


def test_face_detection_roi_is_expanded_before_redaction():
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="face",
        ),
        targets=[target()],
        face_localizer=FoundFaceLocalizer(),
    )

    _rendered, receipt = apply(
        engine,
        checkerboard(),
        tracks=[track()],
        timestamp=1.0,
    )

    application = receipt["applications"][0]
    assert application["localizer"] == "face_detector"
    assert application["roi_xyxy"] == [44, 24, 76, 56]


def test_face_localizer_error_falls_back_instead_of_exposing_target():
    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="face",
        ),
        targets=[target()],
        face_localizer=ExplodingFaceLocalizer(),
    )

    rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)

    application = receipt["applications"][0]
    assert application["localizer"] == "upper_person_fallback"
    assert application["fallback_reason"] == "face_localizer_error:RuntimeError"
    assert not np.array_equal(rendered, frame)


def test_frame_scope_must_match_target_scope():
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target()],
    )

    with pytest.raises(AnonymizationConfigError, match="frame scope"):
        engine.apply(
            checkerboard(),
            tracks=[track()],
            stream_id="stream_1",
            asset_uid="different_asset",
            segment_id="segment_1",
            frame_index=0,
            media_time_seconds=1.0,
        )


def test_overlapping_decisions_for_one_track_fail_closed():
    with pytest.raises(AnonymizationConfigError, match="overlapping"):
        AnonymizationEngine(
            config=AnonymizationConfig(
                source="accepted",
                character_name="Willie",
                mode="person",
            ),
            targets=[
                target(decision_id="decision_a", start=0.0, end=2.0),
                target(decision_id="decision_b", start=1.0, end=3.0),
            ],
        )


def test_duplicate_track_observation_in_one_frame_fails_closed():
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target()],
    )

    with pytest.raises(ValueError, match="duplicate track_id"):
        apply(
            engine,
            checkerboard(),
            tracks=[track(), track(bbox=(40, 20, 120, 110))],
            timestamp=1.0,
        )


def test_accepted_receipt_must_match_asset_and_event_scope(tmp_path: Path):
    receipt_path = tmp_path / "labels.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "watch.yolo_track_labels.v1",
                "asset_uid": "other_asset",
                "row_index": 1,
                "events": [],
            }
        )
    )

    with pytest.raises(AnonymizationConfigError, match="asset_uid"):
        accepted_targets_from_yolo_receipt(
            receipt_path,
            stream_id="stream_1",
            asset_uid="asset_1",
            segment_id="segment_1",
            character_name="Willie",
        )


def test_suggested_manifest_for_other_asset_fails_before_source_open(
    tmp_path: Path,
):
    manifest_path = tmp_path / "suggested.json"
    other_scope = AnonymizationTarget(
        decision_id="suggested_other_asset",
        track_id="track_1",
        source="suggested",
        stream_id="stream_1",
        asset_uid="other_asset",
        segment_id="segment_1",
        valid_from_seconds=0.0,
        character_name="Willie",
    )
    manifest_path.write_text(json.dumps(target_manifest_payload([other_scope])))
    args = live_args(tmp_path, tmp_path / "source-not-opened.mp4")
    args.blur_source = "suggested"
    args.blur_character = "Willie"
    args.blur_target_manifest = manifest_path
    args.blur_label_receipt = None
    args.blur_track = []

    with pytest.raises(AnonymizationConfigError, match="selected no targets"):
        session_from_args(args)


def test_anonymization_suboption_without_source_fails_closed(tmp_path: Path):
    args = live_args(tmp_path, tmp_path / "source-not-opened.mp4")
    args.blur_source = None
    args.blur_character = None
    args.blur_target_manifest = None
    args.blur_label_receipt = None
    args.blur_track = []
    args.anonymization_receipt = None
    args.blur_mode = "person"
    args.blur_style = None
    args.blur_strength = None
    args.blur_hold_ms = None

    with pytest.raises(AnonymizationConfigError, match="--blur-source"):
        session_from_args(args)


def test_redaction_outputs_cannot_overwrite_source_or_evidence(tmp_path: Path):
    source = tmp_path / "source.mp4"
    args = live_args(tmp_path, source, output_video=source)

    with pytest.raises(AnonymizationConfigError, match="must not overwrite the source"):
        session_from_args(args)


def test_receipt_file_is_created_exclusively(tmp_path: Path):
    receipt_path = tmp_path / "receipts.jsonl"
    receipt_path.write_text("existing-proof\n")
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="person",
        ),
        targets=[target()],
    )

    with pytest.raises(FileExistsError):
        with AnonymizationSession(engine=engine, receipt_path=receipt_path):
            pass

    assert receipt_path.read_text() == "existing-proof\n"


class CapturingWriter:
    def __init__(self):
        self.frames: list[np.ndarray] = []
        self.released = False

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


def test_redaction_video_writer_receives_the_receipted_compositor_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from scripts import live_ultralytics_tracking as live_tracker
    from scripts.watch_anonymizer import _frame_sha256

    source = tmp_path / "source_writer_capture.mp4"
    write_test_video(source, frame_count=2, fps=5.0)
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    writer = CapturingWriter()
    monkeypatch.setattr(
        live_tracker,
        "_writer_for",
        lambda _cv2, _writer, _path, _fps, _frame: writer,
    )
    args = live_args(
        tmp_path,
        source,
        output_video=tmp_path / "captured-redaction.mp4",
    )

    events = list(live_tracker.iter_track_events(args))

    assert events
    assert writer.released is True
    receipts = [
        json.loads(line)
        for line in args.anonymization_receipt.read_text().splitlines()
    ]
    assert len(writer.frames) == len(receipts) == 2
    assert _frame_sha256(writer.frames[0]) == receipts[0]["output_frame_sha256"]


def test_accepted_receipt_rejects_unknown_timed_action(tmp_path: Path):
    receipt = {
        "schema": "watch.yolo_track_labels.v1",
        "asset_uid": "asset_1",
        "row_index": 3,
        "events": [
            {
                "id": "future_action",
                "action": "pause_identity",
                "asset_uid": "asset_1",
                "row_index": 3,
                "track_id": "track_1",
                "time_seconds": 1.0,
            }
        ],
    }
    path = tmp_path / "unknown-action.json"
    path.write_text(json.dumps(receipt))

    with pytest.raises(AnonymizationConfigError, match="unsupported action"):
        accepted_targets_from_yolo_receipt(
            path,
            stream_id="stream_1",
            asset_uid="asset_1",
            segment_id="segment_1",
            character_name="Willie",
        )


@pytest.mark.parametrize("bad_time", [True, -1.0, float("nan"), "1.0"])
def test_accepted_receipt_rejects_malformed_timed_event(
    tmp_path: Path,
    bad_time,
):
    receipt = {
        "schema": "watch.yolo_track_labels.v1",
        "asset_uid": "asset_1",
        "row_index": 3,
        "events": [
            {
                "id": "bad_time",
                "action": "accept",
                "asset_uid": "asset_1",
                "row_index": 3,
                "track_id": "track_1",
                "time_seconds": bad_time,
                "character_name": "Willie",
            }
        ],
    }
    path = tmp_path / "bad-time.json"
    path.write_text(json.dumps(receipt))

    with pytest.raises(AnonymizationConfigError, match="time_seconds"):
        accepted_targets_from_yolo_receipt(
            path,
            stream_id="stream_1",
            asset_uid="asset_1",
            segment_id="segment_1",
            character_name="Willie",
        )


def test_face_outside_target_person_falls_back_to_upper_person():
    class WrongPersonFaceLocalizer:
        @property
        def provenance(self):
            return {"localizer": "fixture", "network_used": False}

        def locate(self, _frame, _person_bbox):
            return (0, 0, 20, 20), None

    frame = checkerboard()
    engine = AnonymizationEngine(
        config=AnonymizationConfig(
            source="accepted",
            character_name="Willie",
            mode="face",
        ),
        targets=[target()],
        face_localizer=WrongPersonFaceLocalizer(),
    )

    _rendered, receipt = apply(engine, frame, tracks=[track()], timestamp=1.0)

    application = receipt["applications"][0]
    assert application["localizer"] == "upper_person_fallback"
    assert application["fallback_reason"] == "face_outside_target_person"
    assert application["roi_xyxy"][0] > 0


def test_effective_detector_interval_guards_permanent_redaction_export(
    tmp_path: Path,
):
    from scripts.live_ultralytics_tracking import _validate_redaction_output_cadence

    args = live_args(
        tmp_path,
        tmp_path / "source.mp4",
        output_video=tmp_path / "redacted.mp4",
        sample_fps=8.0,
    )
    args.blur_hold_ms = 125
    session = session_from_args(args)

    # 30fps / stride 4 is an effective 133.3ms detector interval, even though
    # the requested 8fps interval is only 125ms.
    with pytest.raises(AnonymizationConfigError, match="effective detector interval"):
        _validate_redaction_output_cadence(
            session,
            args=args,
            source_fps=30.0,
            frame_stride=4,
        )


def test_anonymization_rejects_empty_scope_before_media_open(tmp_path: Path):
    args = live_args(tmp_path, tmp_path / "source-not-opened.mp4")
    args.segment_id = ""

    with pytest.raises(AnonymizationConfigError, match="--segment-id"):
        session_from_args(args)
