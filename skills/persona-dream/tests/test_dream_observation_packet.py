from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_dream_observation_packet as checker  # noqa: E402
import write_dream_observation_packet as writer  # noqa: E402


RUN_ID = "pipeline-complete"
REVISION_ID = "rev_idea_f3f9c48d5cc2"
ACTIVATION_ID = "activation-f316f5e66ba900751235c2ee3cd27da3"
REQUEST_SHA = "sha256:" + "f" * 64
REQUEST_ID = "019f6bef-0c0f-7921-8a5e-a1f12890fb75"
ENDPOINT = "fal-ai/kling-video/v3/standard/image-to-video"
DURATION = 10.041667


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def provider_fixture(tmp_path: Path) -> dict[str, Path]:
    run_root = tmp_path / RUN_ID
    revision_root = run_root / ".persona-dream" / "revisions" / REVISION_ID
    provider_root = revision_root / "phase_11_submit_return" / "provider_return" / REQUEST_SHA.removeprefix("sha256:")
    watch_root = provider_root / "watch-codex-vision"
    frames_root = watch_root / "frames"
    video = provider_root / "provider_return.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"provider-return-video")
    video_sha = writer.sha256_file(video)

    request_path = revision_root / "phase_11_submit_return" / "canonical" / "phase11_live_request.v1.json"
    request = {
        "schema": "persona_dream.phase11_live_request.v1",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "activation_transaction_id": ACTIVATION_ID,
        "request_body_sha256": REQUEST_SHA,
        "endpoint": ENDPOINT,
        "provider_request_body": {
            "multi_prompt": [{"duration": "2", "prompt": "fixture"}],
            "start_image_url": "https://example.invalid/start.png",
            "duration": "10",
            "generate_audio": False,
            "elements": [],
            "shot_type": "customize",
            "negative_prompt": "blur",
            "cfg_scale": 0.5,
        },
    }
    write_json(request_path, request)

    download_path = provider_root / "phase11_download_ffprobe_receipt.v1.json"
    download = {
        "schema": "persona_dream.phase11_download_ffprobe_receipt.v1",
        "status": "PASS_PHASE11_PROVIDER_RETURN_DOWNLOADED",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "activation_transaction_id": ACTIVATION_ID,
        "request_body_sha256": REQUEST_SHA,
        "request_id": REQUEST_ID,
        "endpoint": ENDPOINT,
        "download_relative_path": video.relative_to(run_root).as_posix(),
        "downloaded_sha256": video_sha,
        "size_bytes": video.stat().st_size,
        "source_url": "https://v3b.fal.media/files/output.mp4",
        "content_type": "video/mp4",
        "ffprobe": {
            "format": {
                "duration": str(DURATION),
                "size": str(video.stat().st_size),
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            }
        },
        "actual_provider_call_attempts": 1,
    }
    write_json(download_path, download)

    envelope_path = provider_root / "phase11_provider_return_envelope.v1.json"
    envelope = {
        "schema": "persona_dream.phase11_provider_return_envelope.v1",
        "status": "PASS_PHASE11_PROVIDER_RETURN_RECEIVED",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "source_revision_id": "rev_repair_a8b93ffeca8f",
        "activation_transaction_id": ACTIVATION_ID,
        "request_body_sha256": REQUEST_SHA,
        "request_id": REQUEST_ID,
        "endpoint": ENDPOINT,
        "video_url": download["source_url"],
        "download_receipt_relative_path": download_path.relative_to(run_root).as_posix(),
        "download_receipt_sha256": writer.sha256_file(download_path),
        "downloaded_mp4_sha256": video_sha,
        "provider_result_sha256": "sha256:" + "a" * 64,
        "provider_live": True,
        "submitted": True,
        "watch_started": False,
        "actual_provider_call_attempts": 1,
    }
    write_json(envelope_path, envelope)

    manifest_frames = []
    report_frames = []
    descriptions = []
    scene_elements = []
    receipt_frames = []
    for index in range(writer.EXPECTED_PROVIDER_FRAME_COUNT):
        timestamp = round(index * 0.84, 2)
        frame_path = frames_root / f"frame_{index + 1:04d}.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_bytes(f"frame-{index}".encode())
        external_path = Path("/home/fixture/.local/share/agent-skills/watch-frames/providerreturn") / frame_path.name
        description = f"Observed visual frame {index + 1}."
        manifest_frames.append({"index": index, "timestamp_seconds": timestamp, "path": str(frame_path)})
        report_frames.append({"index": index, "timestamp_seconds": timestamp, "path": str(external_path), "source": "uniform-fallback"})
        descriptions.append({
            "index": index,
            "timestamp": timestamp,
            "path": str(external_path),
            "description": description,
            "source": "scillm:gpt-5.5",
            "status": "described",
            "requested_model": "codex-vision",
            "served_model": "gpt-5.5",
            "provider": "scillm",
        })
        scene_elements.append({
            "index": index,
            "visual_description": description,
            "sound": "Sound not transcribed; audio not analyzed",
        })
        receipt_frames.append({
            "index": index,
            "timestamp": timestamp,
            "path": str(external_path),
            "status": "described",
            "attempts": [{
                "provider": "scillm",
                "requested_model": "codex-vision",
                "served_model": "gpt-5.5",
                "status": "described",
                "http_status": 200,
                "error_type": None,
                "error": None,
            }],
        })

    frames_path = write_json(watch_root / "frames_manifest.json", {
        "source": str(video),
        "sampling_mode": "uniform-fallback",
        "frame_count": writer.EXPECTED_PROVIDER_FRAME_COUNT,
        "max_frames": writer.EXPECTED_PROVIDER_FRAME_COUNT,
        "resolution": 768,
        "duration_seconds": DURATION,
        "frames": manifest_frames,
    })
    visual_receipt = {
        "schema": "watch.visual_description_receipt.v1",
        "status": "described",
        "mocked": False,
        "live": True,
        "requested_model": "codex-vision",
        "fallback_models": [],
        "frame_count": writer.EXPECTED_PROVIDER_FRAME_COUNT,
        "described_count": writer.EXPECTED_PROVIDER_FRAME_COUNT,
        "gate": {"status": "passed", "reason": None},
        "frames": receipt_frames,
    }
    visual_path = write_json(watch_root / "visual_description_receipt.json", visual_receipt)
    report_path = write_json(watch_root / "report.json", {
        "watch_report": {
            "source": str(video),
            "title": "provider_return",
            "duration_seconds": DURATION,
            "duration_formatted": "10s",
            "sampling_mode": "uniform-fallback",
            "frame_count": writer.EXPECTED_PROVIDER_FRAME_COUNT,
            "metadata": {"width": 1280, "height": 720, "codec": "h264"},
            "gaps": ["missing_transcript"],
            "visual_description": descriptions,
        },
        "frames": report_frames,
        "visual_descriptions": descriptions,
        "scene_elements": scene_elements,
        "visual_description_receipt": visual_receipt,
    })
    return {
        "run_root": run_root,
        "provider_root": provider_root,
        "watch_root": watch_root,
        "video": video,
        "request": request_path,
        "download": download_path,
        "envelope": envelope_path,
        "frames": frames_path,
        "report": report_path,
        "visual": visual_path,
    }


def build_provider(paths: dict[str, Path]) -> dict[str, Any]:
    return writer.build_packet(
        paths["watch_root"],
        paths["video"],
        "dream-provider-return",
        REVISION_ID,
        "provider_return",
        run_root=paths["run_root"],
        provider_return_envelope=paths["envelope"],
        download_ffprobe_receipt=paths["download"],
        canonical_request=paths["request"],
        visual_description_receipt=paths["visual"],
    )


@pytest.fixture(autouse=True)
def fixed_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "video_duration", lambda _path: DURATION)


def test_valid_provider_return_binds_exact_lineage_and_live_visual_evidence(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    packet = build_provider(paths)
    assert writer.validate_packet(packet) == []
    assert packet["status"] == "PASS_DREAM_OBSERVATION_CONTRACT_PROVIDER_RETURN"
    assert packet["run_id"] == RUN_ID
    assert packet["revision_id"] == REVISION_ID
    assert packet["activation_transaction_id"] == ACTIVATION_ID
    assert packet["request_body_sha256"] == REQUEST_SHA
    assert packet["request_id"] == REQUEST_ID
    assert packet["actual_provider_call_attempts"] == 1
    assert packet["provider_returned"] is True
    assert packet["persona_watched_provider_dream"] is True
    assert packet["fixture_backed"] is False
    assert packet["watch_evidence"]["frame_count"] == 12
    assert packet["watch_evidence"]["described_count"] == 12
    assert packet["watch_evidence"]["served_models"] == ["gpt-5.5"]
    assert len(packet["frame_evidence"]) == 12
    assert len(packet["visual_facts"]) == 12
    assert packet["transcript_facts"] == []
    assert packet["audible_facts"] == []
    assert packet["audio_strategy"] == {
        "generate_audio": False,
        "transcript_present": False,
        "missing_audio_is_expected": True,
    }
    assert packet["psychological_interpretation_performed"] is False


def test_wrong_mp4_hash_is_rejected(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    download = read_json(paths["download"])
    download["downloaded_sha256"] = "sha256:" + "0" * 64
    write_json(paths["download"], download)
    envelope = read_json(paths["envelope"])
    envelope["download_receipt_sha256"] = writer.sha256_file(paths["download"])
    write_json(paths["envelope"], envelope)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_MP4_HASH"


def test_wrong_request_id_is_rejected(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    download = read_json(paths["download"])
    download["request_id"] = "wrong-request-id"
    write_json(paths["download"], download)
    envelope = read_json(paths["envelope"])
    envelope["download_receipt_sha256"] = writer.sha256_file(paths["download"])
    write_json(paths["envelope"], envelope)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_REQUEST_ID"


def test_wrong_request_hash_is_rejected(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    request = read_json(paths["request"])
    request["request_body_sha256"] = "sha256:" + "1" * 64
    write_json(paths["request"], request)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_REQUEST_BODY_SHA256"


def test_wrong_revision_is_rejected(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    envelope = read_json(paths["envelope"])
    envelope["revision_id"] = "rev-wrong"
    write_json(paths["envelope"], envelope)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_REVISION_ID"


@pytest.mark.parametrize("failure", ["missing_description", "failed_gate"])
def test_missing_or_failed_visual_description_evidence_is_rejected(tmp_path: Path, failure: str) -> None:
    paths = provider_fixture(tmp_path)
    if failure == "missing_description":
        report = read_json(paths["report"])
        report["visual_descriptions"][3]["description"] = ""
        report["scene_elements"][3]["visual_description"] = ""
        write_json(paths["report"], report)
        expected = "BLOCKED_DREAM_OBSERVATION_VISUAL_DESCRIPTION"
    else:
        receipt = read_json(paths["visual"])
        receipt["gate"] = {"status": "failed", "reason": "fixture"}
        write_json(paths["visual"], receipt)
        report = read_json(paths["report"])
        report["visual_description_receipt"] = receipt
        write_json(paths["report"], report)
        expected = "BLOCKED_DREAM_OBSERVATION_VISUAL_GATE"
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == expected


def test_frame_path_escape_is_rejected(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    escaped = paths["provider_root"] / "escaped-frame.jpg"
    escaped.write_bytes(b"escape")
    manifest = read_json(paths["frames"])
    manifest["frames"][0]["path"] = str(escaped)
    write_json(paths["frames"], manifest)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_FRAME_PATH_ESCAPE"


def test_silent_video_gap_requires_generate_audio_false(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    packet = build_provider(paths)
    assert "transcript_absent_expected_generate_audio_false" in packet["coverage_gaps"]
    request = read_json(paths["request"])
    request["provider_request_body"]["generate_audio"] = True
    write_json(paths["request"], request)
    with pytest.raises(writer.ObservationBlocked) as blocked:
        build_provider(paths)
    assert blocked.value.code == "BLOCKED_DREAM_OBSERVATION_TRANSCRIPT_REQUIRED_FOR_AUDIO_REQUEST"


def test_fixture_packet_behavior_is_preserved(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"video")
    write_json(watch_root / "frames_manifest.json", {"frames": [{"path": str(frame)}]})
    write_json(watch_root / "transcript.json", {"segments": [{"text": "Kai waits.", "start": 0, "duration": 1}]})
    write_json(watch_root / "report.json", {"visual_descriptions": [], "scene_elements": []})
    packet = writer.build_packet(watch_root, video, "dream-1", "rev-1", "fixture_video")
    assert writer.validate_packet(packet) == []
    assert packet["status"] == "PASS_DREAM_OBSERVATION_CONTRACT_FIXTURE"
    assert packet["provider_returned"] is False
    assert packet["persona_watched_provider_dream"] is False
    assert packet["actual_provider_call_attempts"] == 0
    assert packet["visual_facts"] == []
    assert "visual_descriptions_missing" in packet["coverage_gaps"]
    assert packet["psychological_interpretation_performed"] is False


def test_checker_independently_rehashes_every_frame_reference(tmp_path: Path) -> None:
    paths = provider_fixture(tmp_path)
    packet = build_provider(paths)
    assert checker.check_packet(packet, paths["run_root"]) == []
    first_frame = paths["watch_root"] / "frames" / "frame_0001.jpg"
    first_frame.write_bytes(b"tampered")
    errors = checker.check_packet(packet, paths["run_root"])
    assert any("frame_evidence[0]: sha256 mismatch" in error for error in errors)
