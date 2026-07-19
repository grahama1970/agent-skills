"""Deterministic tests for the v2 observation packet: schema, psychology filter,
assembly logic, vertex-consistency mapping, and the validator. No live calls."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_observation_packet_v2 as bld  # noqa: E402
import validate_dream_observation_packet_v2 as val  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas/dream_observation_packet.v2.schema.json").read_text())


def _sha_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- #
# 1. schema self-validity                                                      #
# --------------------------------------------------------------------------- #
def test_schema_is_valid_draft202012():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_schema_forbids_psychology_in_description_and_pins_flag():
    assert "FORBIDDEN" in SCHEMA["description"].upper() or "forbidden" in SCHEMA["description"]
    assert SCHEMA["properties"]["psychological_interpretation_performed"] == {"const": False}


# --------------------------------------------------------------------------- #
# 2. deterministic psychology filter                                           #
# --------------------------------------------------------------------------- #
def test_psychology_hit_flags_emotion_terms():
    assert bld.psychology_hit("a man who looks happy") == "happy"
    assert bld.psychology_hit("she seems anxious about it") == "anxious"
    assert bld.psychology_hit("two surfers on boards") is None
    # perceptual hedges are NOT psychology
    assert bld.psychology_hit("the face appears blurry and distant") is None


def test_filter_phrase_list_strips_only_offending_phrases():
    kept, rej = bld.filter_phrase_list(
        ["two people on surfboards", "a person who feels calm", "ocean water"],
        frame_index=6, field="visible_entities",
    )
    assert kept == ["two people on surfboards", "ocean water"]
    assert len(rej) == 1
    assert rej[0]["term"] in {"feels", "calm"}
    assert rej[0]["frame_index"] == 6
    assert rej[0]["field"] == "visible_entities"


def test_filter_summary_blanks_psychological_summary():
    txt, rej = bld.filter_summary("The surfer looks joyful in the water.", frame_index=3)
    assert txt == ""
    assert rej and rej[0]["term"] == "joyful"
    clean, none = bld.filter_summary("Two people are on surfboards in the ocean.", frame_index=3)
    assert clean.startswith("Two people") and none == []


# --------------------------------------------------------------------------- #
# 3. assembly logic + schema conformance                                       #
# --------------------------------------------------------------------------- #
def _minimal_inputs():
    v1 = {
        "schema": "persona_dream.watch_gauntlet_observation_packet.v1",
        "status": "DEGRADED_WATCH_GAUNTLET_OBSERVATION",
        "run_id": "pipeline-complete",
        "revision_id": "rev_successor_943b01ecd9a3",
        "source_revision_id": "rev_upstream_bf3b05d47fb8",
        "source_video": "provider_return.mp4",
        "source_video_sha256": "sha256:" + "5" * 64,
        "source_video_size_bytes": 16843175,
        "duration_seconds": 10.041667,
        "perception": {"sampling_mode": "uniform-fallback", "requested_mode": "scene-change"},
        "frame_evidence": [
            {"index": 6, "timestamp_seconds": 5.02, "path": "watch/frames_bound/frame_0006.jpg",
             "sha256": "sha256:" + "a" * 64, "size_bytes": 19577,
             "in_identity_window": True, "in_speaker_window": True},
        ],
        "step_hooks": {"step_38_visible_speaker_lipsync": {
            "speaker": "Kai", "spoken_interval_seconds": [5.0, 8.08], "speaker_visibility_frames": []}},
    }
    vertices = [
        {"_key": "coverage_gap_00", "observation_type": "coverage_gap", "statement": "entities unavailable"},
        {"_key": "frame_0006", "observation_type": "frame", "statement": "Frame 6 ... entities=unavailable"},
        {"_key": "frame_0007", "observation_type": "frame", "statement": "Frame 7 ... entities=unavailable"},
        {"_key": "frame_0008", "observation_type": "frame", "statement": "Frame 8 ... entities=unavailable"},
        {"_key": "frame_0009", "observation_type": "frame", "statement": "Frame 9 ... entities=unavailable"},
        {"_key": "identity_temporal_continuity_review", "observation_type": "renderer_continuity_review",
         "statement": "verdict INDETERMINATE"},
        {"_key": "visible_speaker_lipsync_window", "observation_type": "speaker_visibility",
         "statement": "saying: None"},
    ]
    return {
        "v1_packet": v1,
        "v1_packet_sha256": "sha256:" + "e" * 64,
        "v1_packet_rel_path": "reports/x/watch_gauntlet/59b9ff3155d6/dream_observation_packet.v1.json",
        "return_id": "97688ec5",
        "muxed_video": "m.mp4", "muxed_video_sha256": "sha256:" + "b" * 64, "muxed_video_size_bytes": 100,
        "request_id": None, "request_body_sha256": None,
        "provider_lineage": {"module_status": "PRESENT", "endpoint": None, "request_hash": None,
                             "downloaded_mp4_sha256": "sha256:" + "5" * 64,
                             "provider_return_envelope": None, "download_receipt": None},
        "scene_cuts": {"module_status": "NOT_APPLICABLE", "method": "watch", "cuts": []},
        "transcript": {"module_status": "PRESENT", "engine": "whisper:large-v3-turbo",
                       "source_video": "m.mp4", "source_video_sha256": "sha256:" + "b" * 64,
                       "authoritative_forced_alignment": None,
                       "segments": [{"start_seconds": 4.74, "end_seconds": 7.86,
                                     "text": "If we paddle now, we're cutting across the line up.",
                                     "speaker": "Kai", "source": "authoritative_forced_alignment_receipt"}]},
        "nonverbal_audio": {"module_status": "PRESENT", "events": []},
        "vlm_frames": [{"index": 6, "timestamp_seconds": 5.02, "people_count": 7,
                        "visible_entities": ["two people on surfboards", "ocean water"],
                        "actions": ["a person raises one hand"], "absences": ["no boats visible"],
                        "summary": "Two people on surfboards in the ocean.",
                        "tau_receipt_sha256": "sha256:" + "c" * 64, "http_status": 200}],
        "vlm_rejections": [],
        "vlm_prompt_sha256": "sha256:" + "d" * 64,
        "vlm_module_status": "PRESENT",
        "absences": {"module_status": "PRESENT",
                     "items": [{"statement": "no boats visible", "scope": "per_frame", "evidence_refs": ["frame_0006"]}]},
        "identity_evidence": {"module_status": "PRESENT", "authority": "embedding_cosine",
                              "model": "insightface:buffalo_l:w600k_r50", "threshold": 0.421,
                              "references": [{"name": "Embry", "path": "/ref.png", "sha256": "sha256:" + "f" * 64}],
                              "summary": {"embry_identity_verdict": "DRIFT_OR_FAIL"},
                              "per_frame": [{"frame": "frame_0006.jpg", "entity": "Embry",
                                             "best_cosine": 0.31, "verdict": "FAIL", "status": "FAIL"}],
                              "adjudications": [{"panel_id": "step36_kai_frame_0011", "verdict": "PASS",
                                                 "summary": "distant man", "prompt_sha256": None,
                                                 "receipt_content_sha256": None, "http_status": 200}]},
        "speaker_visibility": {"module_status": "PRESENT", "speaker": "Kai",
                               "spoken_interval_seconds": [5.0, 8.08],
                               "transcript_line_at_interval": "If we paddle now...",
                               "readable_speaking_mouth_present": False,
                               "lipsync_rule_applicability": "INAPPLICABLE_BY_COMPOSITION",
                               "speaker_visibility_frames": [], "adjudication": None},
        "continuity_adjudications": {"module_status": "PRESENT", "verdict": "PASS_POST_KLING_CONTINUITY_REVIEW",
                                     "subgates": {}, "receipt_refs": []},
        "coverage_gaps": [{"code": "lipsync_inapplicable_by_composition", "statement": "no readable mouth"}],
        "acceptance_context": {"module_status": "PRESENT", "gate_summary": {"agent_level_gauntlet": "ACCEPTED"},
                               "human_subjective_acceptance": "NOT_CLAIMED_REMAINS_HUMAN", "receipt_refs": []},
        "vertices": vertices,
        "tau_receipts": [{"route": "tau:persona-dream-panel-reviewer", "purpose": "per-frame-visible-entities",
                          "model": "gpt-5.5", "api_key_source": "docker:scillm-proxy:SCILLM_MASTER_KEY",
                          "prompt_sha256": "sha256:" + "d" * 64, "content_sha256": "sha256:" + "c" * 64,
                          "http_status": 200, "live_call_performed": True, "frame_index": 6}],
        "degradations": [],
        "claims": {"proves": ["x"], "does_not_prove": ["y"]},
        "generated_at": "2026-07-19T15:00:00+00:00",
        "live": True, "mocked": False,
    }


def test_assemble_packet_is_schema_valid_and_accepted():
    packet = bld.assemble_packet(_minimal_inputs())
    jsonschema.Draft202012Validator(SCHEMA).validate(packet)
    assert packet["packet_status"] == "ACCEPTED"
    assert packet["psychological_interpretation_performed"] is False
    assert packet["supersedes"]["prior_packet_sha256"] == "sha256:" + "e" * 64
    assert packet["sampled_frames"]["frame_count"] == 1


def test_assemble_packet_degraded_when_vlm_fails():
    inputs = _minimal_inputs()
    inputs["vlm_module_status"] = "DEGRADED"
    inputs["vlm_frames"] = []
    inputs["degradations"] = [{"module": "visible_entities_per_frame", "code": "vlm_route_unavailable",
                               "blocker": "route failed after 2 attempts"}]
    packet = bld.assemble_packet(inputs)
    jsonschema.Draft202012Validator(SCHEMA).validate(packet)
    assert packet["packet_status"] == "DEGRADED"
    assert packet["degradations"][0]["code"] == "vlm_route_unavailable"


# --------------------------------------------------------------------------- #
# 4. vertex-consistency mapping                                                #
# --------------------------------------------------------------------------- #
def test_vertex_consistency_maps_all_seven_additive():
    packet = bld.assemble_packet(_minimal_inputs())
    vc = packet["vertex_consistency"]
    assert vc["module_status"] == "PRESENT"
    ids = [v["vertex_id"] for v in vc["vertices"]]
    assert ids == bld.EXPECTED_VERTEX_IDS
    # with VLM present + transcript line, all 7 are additive-enrichment (no bare CONSISTENT/CONTRADICTION)
    outcomes = {v["outcome"] for v in vc["vertices"]}
    assert outcomes == {"CONSISTENT_WITH_ADDITIVE_ENRICHMENT"}
    assert all("CONTRADICTION" != v["outcome"] for v in vc["vertices"])


def test_vertex_consistency_no_contradiction_and_notes_present():
    packet = bld.assemble_packet(_minimal_inputs())
    for v in packet["vertex_consistency"]["vertices"]:
        assert v["represented_in_modules"], v["vertex_id"]
        assert v["delta_note"]


# --------------------------------------------------------------------------- #
# 5. validator catches leaks / bad hashes                                      #
# --------------------------------------------------------------------------- #
def test_validator_passes_clean_packet(tmp_path):
    inputs = _minimal_inputs()
    # write a real frame file matching its sha
    frame_bytes = b"jpegdata-6"
    frame_dir = tmp_path / "watch/frames_bound"
    frame_dir.mkdir(parents=True)
    (frame_dir / "frame_0006.jpg").write_bytes(frame_bytes)
    inputs["v1_packet"]["frame_evidence"][0]["path"] = "watch/frames_bound/frame_0006.jpg"
    inputs["v1_packet"]["frame_evidence"][0]["sha256"] = _sha_bytes(frame_bytes)
    inputs["v1_packet"]["frame_evidence"][0]["size_bytes"] = len(frame_bytes)
    packet = bld.assemble_packet(inputs)
    ppath = tmp_path / "packet.json"
    ppath.write_text(json.dumps(packet), encoding="utf-8")
    ok, report = val.validate(ppath, tmp_path)
    assert ok, report["errors"]
    assert report["frames_rehashed"] == 1


def test_validator_flags_psychology_leak(tmp_path):
    inputs = _minimal_inputs()
    # inject a leaked psychological phrase directly (bypassing the filter)
    inputs["vlm_frames"][0]["visible_entities"].append("a joyful surfer")
    packet = bld.assemble_packet(inputs)
    ppath = tmp_path / "packet.json"
    ppath.write_text(json.dumps(packet), encoding="utf-8")
    ok, report = val.validate(ppath, tmp_path)
    assert not ok
    assert any("psychology leak" in e for e in report["errors"])


def test_validator_flags_frame_hash_mismatch(tmp_path):
    inputs = _minimal_inputs()
    frame_dir = tmp_path / "watch/frames_bound"
    frame_dir.mkdir(parents=True)
    (frame_dir / "frame_0006.jpg").write_bytes(b"different-bytes")
    inputs["v1_packet"]["frame_evidence"][0]["path"] = "watch/frames_bound/frame_0006.jpg"
    packet = bld.assemble_packet(inputs)  # keeps sha aaaa...
    ppath = tmp_path / "packet.json"
    ppath.write_text(json.dumps(packet), encoding="utf-8")
    ok, report = val.validate(ppath, tmp_path)
    assert not ok
    assert any("sha256 mismatch" in e for e in report["errors"])
