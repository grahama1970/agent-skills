from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import qra  # noqa: E402


def _frame(tmp_path: Path) -> list[dict]:
    image = tmp_path / "frame_0001.jpg"
    image.write_bytes(b"fake image bytes")
    return [{"index": 0, "timestamp_seconds": 1.25, "path": str(image)}]


def test_scillm_completion_uses_configured_base_and_key(monkeypatch):
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "model": "served-vlm",
                "choices": [{"message": {"content": "A configured proxy response."}}],
            }

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(qra, "WATCH_SCILLM_API_BASE", "http://watch-scillm.test/")
    monkeypatch.setattr(qra, "WATCH_SCILLM_PROXY_KEY", "watch-test-key")
    monkeypatch.setattr(qra.httpx, "post", fake_post)

    result = qra._scillm_chat_completion(
        [{"role": "user", "content": "describe"}],
        model="configured-vlm",
        timeout=7,
    )

    assert result["status"] == "described"
    assert result["served_model"] == "served-vlm"
    assert calls == [
        {
            "url": "http://watch-scillm.test/v1/chat/completions",
            "json": {
                "model": "configured-vlm",
                "messages": [{"role": "user", "content": "describe"}],
                "temperature": 0.3,
                "stream": False,
            },
            "headers": {
                "Authorization": "Bearer watch-test-key",
                "X-Caller-Skill": "watch",
            },
            "timeout": 7,
        }
    ]


def test_visual_description_explicit_model_override(monkeypatch, tmp_path):
    attempts: list[str] = []

    def fake_attempt(_messages, model):
        attempts.append(model)
        return {
            "provider": "scillm",
            "requested_model": model,
            "served_model": "served-explicit-vlm",
            "status": "described",
            "http_status": 200,
            "error_type": None,
            "error": None,
            "content": "A visible subject is standing in a warmly lit room.",
        }

    monkeypatch.setattr(qra, "_visual_model_attempt", fake_attempt)

    descriptions, receipt = qra.describe_scene_images_with_receipt(
        _frame(tmp_path),
        "Fixture",
        model="explicit-vlm",
    )

    assert attempts == ["explicit-vlm"]
    assert receipt["requested_model"] == "explicit-vlm"
    assert receipt["gate"]["status"] == "passed"
    assert descriptions[0]["requested_model"] == "explicit-vlm"
    assert descriptions[0]["served_model"] == "served-explicit-vlm"


def test_visual_description_default_model_discovery(monkeypatch, tmp_path):
    attempts: list[str] = []

    def fake_attempt(_messages, model):
        attempts.append(model)
        return {
            "provider": "scillm",
            "requested_model": model,
            "served_model": model,
            "status": "described",
            "http_status": 200,
            "error_type": None,
            "error": None,
            "content": "The frame shows a person near a table.",
        }

    monkeypatch.setattr(qra, "WATCH_VISUAL_DESCRIPTION_MODEL", "default-vlm")
    monkeypatch.setattr(qra, "WATCH_VISUAL_DESCRIPTION_FALLBACK_MODELS", "")
    monkeypatch.setattr(qra, "_visual_model_attempt", fake_attempt)

    descriptions, receipt = qra.describe_scene_images_with_receipt(_frame(tmp_path), "Fixture")

    assert attempts == ["default-vlm"]
    assert receipt["requested_model"] == "default-vlm"
    assert descriptions[0]["served_model"] == "default-vlm"


def test_visual_description_unsupported_model_fallback(monkeypatch, tmp_path):
    attempts: list[str] = []

    def fake_attempt(_messages, model):
        attempts.append(model)
        if model == "unsupported-vlm":
            return {
                "provider": "scillm",
                "requested_model": model,
                "served_model": None,
                "status": "failed",
                "http_status": 400,
                "error_type": "http_error",
                "error": "unsupported image model",
                "content": "",
            }
        return {
            "provider": "scillm",
            "requested_model": model,
            "served_model": "fallback-vlm",
            "status": "described",
            "http_status": 200,
            "error_type": None,
            "error": None,
            "content": "A frame-derived visual description was produced.",
        }

    monkeypatch.setattr(qra, "_visual_model_attempt", fake_attempt)

    descriptions, receipt = qra.describe_scene_images_with_receipt(
        _frame(tmp_path),
        "Fixture",
        model="unsupported-vlm",
        fallback_models="fallback-vlm",
    )

    assert attempts == ["unsupported-vlm", "fallback-vlm"]
    assert receipt["gate"]["status"] == "passed"
    assert receipt["frames"][0]["attempts"][0]["http_status"] == 400
    assert descriptions[0]["served_model"] == "fallback-vlm"


def test_visual_description_all_models_failed_receipt(monkeypatch, tmp_path):
    def fake_attempt(_messages, model):
        return {
            "provider": "scillm",
            "requested_model": model,
            "served_model": None,
            "status": "failed",
            "http_status": 400,
            "error_type": "http_error",
            "error": "unsupported image model",
            "content": "",
        }

    monkeypatch.setattr(qra, "_visual_model_attempt", fake_attempt)

    descriptions, receipt = qra.describe_scene_images_with_receipt(
        _frame(tmp_path),
        "Fixture",
        model="bad-primary",
        fallback_models="bad-fallback",
    )

    assert descriptions == []
    assert receipt["status"] == "all_models_failed"
    assert receipt["gate"]["status"] == "failed"
    assert receipt["gate"]["reason"] == "no_frame_descriptions"
    assert receipt["frames"][0]["attempts"][0]["requested_model"] == "bad-primary"
    assert receipt["frames"][0]["attempts"][1]["requested_model"] == "bad-fallback"
