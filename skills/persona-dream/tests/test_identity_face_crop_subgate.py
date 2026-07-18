#!/usr/bin/env python3
"""Unit tests for the face-crop identity subgate (no live calls).

Covers the pure geometry/mapping/verdict helpers, real PIL cropping on a
generated fixture, and the full ``run_face_crop_subgate`` orchestration driven
by a fake ``post_fn`` that routes on prompt content.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "identity_face_crop_subgate", SCRIPTS / "identity_face_crop_subgate.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load()


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def test_normalize_bbox_passthrough_normalized():
    assert sg.normalize_bbox([0.1, 0.2, 0.5, 0.6], 1000, 800) == [0.1, 0.2, 0.5, 0.6]


def test_normalize_bbox_from_pixels():
    out = sg.normalize_bbox([100, 200, 500, 600], 1000, 800)
    assert out == [0.1, 0.25, 0.5, 0.75]


def test_normalize_bbox_orders_and_clamps():
    out = sg.normalize_bbox([0.9, 0.9, 0.1, 0.1], 100, 100)
    assert out == [0.1, 0.1, 0.9, 0.9]
    out2 = sg.normalize_bbox([-50, -50, 5000, 5000], 1000, 1000)
    assert out2 == [0.0, 0.0, 1.0, 1.0]


def test_normalize_bbox_bad_length():
    with pytest.raises(ValueError):
        sg.normalize_bbox([0.1, 0.2, 0.3], 10, 10)


def test_expand_bbox_and_clamp():
    out = sg.expand_bbox([0.4, 0.4, 0.6, 0.6], 0.5)
    assert out == pytest.approx([0.3, 0.3, 0.7, 0.7])
    edge = sg.expand_bbox([0.0, 0.0, 0.2, 0.2], 1.0)
    assert edge == pytest.approx([0.0, 0.0, 0.4, 0.4])


def test_bbox_to_pixels():
    assert sg.bbox_to_pixels([0.1, 0.2, 0.5, 0.6], 1000, 800) == (100, 160, 500, 480)
    # degenerate box gets a minimum 1px extent and is clamped to bounds
    px = sg.bbox_to_pixels([0.999, 0.999, 1.0, 1.0], 100, 100)
    assert px[2] <= 100 and px[3] <= 100 and px[2] > px[0] and px[3] > px[1]


# --------------------------------------------------------------------------- #
# Entity mapping
# --------------------------------------------------------------------------- #
def test_pick_entity_face_by_sex():
    faces = [
        {"bbox_norm": [0.0, 0.0, 0.1, 0.1], "apparent_sex": "male", "position": "right", "prominence": "foreground"},
        {"bbox_norm": [0.0, 0.0, 0.3, 0.3], "apparent_sex": "female", "position": "left", "prominence": "foreground"},
    ]
    assert sg.pick_entity_face(faces, "Embry")["apparent_sex"] == "female"
    assert sg.pick_entity_face(faces, "Kai")["apparent_sex"] == "male"


def test_pick_entity_face_position_fallback():
    faces = [
        {"bbox_norm": [0.0, 0.0, 0.2, 0.2], "apparent_sex": "unclear", "position": "left"},
        {"bbox_norm": [0.0, 0.0, 0.2, 0.2], "apparent_sex": "unclear", "position": "right"},
    ]
    assert sg.pick_entity_face(faces, "Embry")["position"] == "left"
    assert sg.pick_entity_face(faces, "Kai")["position"] == "right"


def test_pick_entity_face_largest_fallback():
    faces = [
        {"bbox_norm": [0.0, 0.0, 0.1, 0.1], "apparent_sex": "unclear", "position": "center"},
        {"bbox_norm": [0.0, 0.0, 0.4, 0.4], "apparent_sex": "unclear", "position": "center"},
    ]
    assert sg.pick_entity_face(faces, "Embry")["bbox_norm"] == [0.0, 0.0, 0.4, 0.4]


def test_pick_entity_face_empty():
    assert sg.pick_entity_face([], "Embry") is None


# --------------------------------------------------------------------------- #
# Verdict aggregation
# --------------------------------------------------------------------------- #
def test_subgate_verdict_all_pass():
    res = [{"entity": "Embry", "status": "PASS"}, {"entity": "Kai", "status": "PASS"}]
    v = sg.subgate_verdict(res)
    assert v["status"] == "PASS" and v["blocking_findings"] == []


def test_subgate_verdict_one_fail():
    res = [
        {"entity": "Embry", "status": "FAIL", "reason": "cooler undertone"},
        {"entity": "Kai", "status": "PASS"},
    ]
    v = sg.subgate_verdict(res)
    assert v["status"] == "FAIL"
    assert any("FAIL_FACE_CROP_IDENTITY_MISMATCH" in b and "Embry" in b for b in v["blocking_findings"])


def test_subgate_verdict_empty_fails():
    assert sg.subgate_verdict([])["status"] == "FAIL"


# --------------------------------------------------------------------------- #
# compare_face_crops verdict logic (fake post_fn, no crops needed)
# --------------------------------------------------------------------------- #
def _fake_post(content_json: dict):
    def _post(payload):
        return {"choices": [{"message": {"content": json.dumps(content_json)}}]}

    return _post


def test_compare_same_high_two_features_passes(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n")
    post = _fake_post({
        "verdict": "SAME",
        "confidence": "high",
        "matching_features": ["warm olive undertone + freckles", "rounded fuller jaw"],
        "divergences": [],
    })
    out = sg.compare_face_crops(p, p, entity="Embry", model="gpt-5.5", post_fn=post)
    assert out["status"] == "PASS"


def test_compare_different_fails(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n")
    post = _fake_post({
        "verdict": "DIFFERENT",
        "confidence": "high",
        "matching_features": ["brown hair"],
        "divergences": ["cooler paler undertone", "narrower face"],
    })
    out = sg.compare_face_crops(p, p, entity="Embry", model="gpt-5.5", post_fn=post)
    assert out["status"] == "FAIL"
    assert "cooler paler undertone" in out["reason"]


def test_compare_same_low_confidence_fails_closed(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n")
    post = _fake_post({
        "verdict": "SAME",
        "confidence": "low",
        "matching_features": ["a", "b"],
        "divergences": [],
    })
    out = sg.compare_face_crops(p, p, entity="Kai", model="gpt-5.5", post_fn=post)
    assert out["status"] == "FAIL" and "confidence" in out["reason"]


# --------------------------------------------------------------------------- #
# Real PIL crop
# --------------------------------------------------------------------------- #
def test_crop_and_upscale_real(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "src.png"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(src)
    out = sg.crop_and_upscale(src, [0.25, 0.25, 0.5, 0.5], tmp_path / "crop.png", margin=0.0, min_side=768)
    with Image.open(out) as im:
        assert max(im.size) >= 768  # upscaled


# --------------------------------------------------------------------------- #
# Full orchestration with a routing fake post_fn (no PIL, injected crop/size)
# --------------------------------------------------------------------------- #
def _routing_post(*, embry_verdict: str):
    """Fake vision endpoint that routes by prompt content."""

    def _post(payload):
        text = ""
        for msg in payload["messages"]:
            c = msg.get("content")
            if isinstance(c, list):
                for part in c:
                    if part.get("type") == "text":
                        text += part["text"] + "\n"
            elif isinstance(c, str):
                text += c + "\n"
        if "locate every" in text:  # frame face detection
            body = {"faces": [
                {"bbox": [0.1, 0.2, 0.3, 0.5], "apparent_sex": "female", "position": "left", "prominence": "foreground"},
                {"bbox": [0.6, 0.2, 0.8, 0.5], "apparent_sex": "male", "position": "right", "prominence": "foreground"},
            ]}
        elif "clearest" in text:  # reference face detection
            body = {"bbox": [0.05, 0.05, 0.25, 0.35]}
        else:  # face-to-face comparison
            body = {
                "verdict": "SAME",
                "confidence": "high",
                "matching_features": ["warm olive undertone", "rounded jaw"],
                "divergences": [],
            }
        return {"choices": [{"message": {"content": json.dumps(body)}}]}

    return _post


def test_run_subgate_pass(tmp_path, monkeypatch):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x")
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"y")

    crops = []

    def fake_crop(image_path, bbox_norm, out_path, **kw):
        Path(out_path).write_bytes(b"crop")
        crops.append(out_path)
        return Path(out_path)

    def fake_size(_p):
        return (1000, 800)

    res = sg.run_face_crop_subgate(
        frame_path=frame,
        references={"Embry": ref, "Kai": ref},
        required_entities=["Embry", "Kai"],
        model="gpt-5.5",
        post_fn=_routing_post(embry_verdict="SAME"),
        work_dir=tmp_path / "work",
        crop_fn=fake_crop,
        read_size=fake_size,
    )
    assert res["status"] == "PASS"
    assert len(res["entity_results"]) == 2
    assert all(r["status"] == "PASS" for r in res["entity_results"])


def test_run_subgate_fail_on_mismatch(tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x")
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"y")

    calls = {"compare": 0}

    def routing(payload):
        text = ""
        for msg in payload["messages"]:
            c = msg.get("content")
            if isinstance(c, list):
                for part in c:
                    if part.get("type") == "text":
                        text += part["text"] + "\n"
            elif isinstance(c, str):
                text += c + "\n"
        if "locate every" in text:
            body = {"faces": [
                {"bbox": [0.1, 0.2, 0.3, 0.5], "apparent_sex": "female", "position": "left", "prominence": "foreground"},
                {"bbox": [0.6, 0.2, 0.8, 0.5], "apparent_sex": "male", "position": "right", "prominence": "foreground"},
            ]}
        elif "clearest" in text:
            body = {"bbox": [0.05, 0.05, 0.25, 0.35]}
        else:
            calls["compare"] += 1
            # First compared entity (Embry) mismatches; second (Kai) matches.
            if calls["compare"] == 1:
                body = {"verdict": "DIFFERENT", "confidence": "high",
                        "matching_features": [], "divergences": ["cooler paler undertone", "narrower face"]}
            else:
                body = {"verdict": "SAME", "confidence": "high",
                        "matching_features": ["tan skin", "curly hair volume"], "divergences": []}
        return {"choices": [{"message": {"content": json.dumps(body)}}]}

    def fake_crop(image_path, bbox_norm, out_path, **kw):
        Path(out_path).write_bytes(b"crop")
        return Path(out_path)

    res = sg.run_face_crop_subgate(
        frame_path=frame,
        references={"Embry": ref, "Kai": ref},
        required_entities=["Embry", "Kai"],
        model="gpt-5.5",
        post_fn=routing,
        work_dir=tmp_path / "work",
        crop_fn=fake_crop,
        read_size=lambda _p: (1000, 800),
    )
    assert res["status"] == "FAIL"
    assert any("FAIL_FACE_CROP_IDENTITY_MISMATCH" in b and "Embry" in b for b in res["blocking_findings"])


def test_run_subgate_fail_closed_no_face(tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x")
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"y")

    def no_face_post(payload):
        text = json.dumps(payload)
        if "locate every" in text:
            body = {"faces": []}  # no candidate faces detected
        elif "clearest" in text:
            body = {"bbox": [0.05, 0.05, 0.25, 0.35]}
        else:
            body = {"verdict": "SAME", "confidence": "high", "matching_features": ["a", "b"], "divergences": []}
        return {"choices": [{"message": {"content": json.dumps(body)}}]}

    res = sg.run_face_crop_subgate(
        frame_path=frame,
        references={"Embry": ref, "Kai": ref},
        required_entities=["Embry", "Kai"],
        model="gpt-5.5",
        post_fn=no_face_post,
        work_dir=tmp_path / "work",
        crop_fn=lambda *a, **k: Path(a[2]),
        read_size=lambda _p: (1000, 800),
    )
    assert res["status"] == "FAIL"
    assert all(r["status"] == "FAIL" for r in res["entity_results"])
