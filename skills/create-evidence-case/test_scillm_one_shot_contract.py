from __future__ import annotations

import runner
import storage
from runner import EvidenceCaseRunner


def test_scillm_render_uses_caller_attributed_gemini_one_shot(monkeypatch):
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{
                    "message": {
                        "content": '{"answer":"CM0028 applies.","citations":["CM0028"]}'
                    }
                }]
            }

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(runner.httpx, "post", fake_post)
    monkeypatch.setattr(
        runner,
        "collect_entities",
        lambda _answer: {"resolved_entities": [{"canonical_id": "CM0028"}]},
    )

    answer = EvidenceCaseRunner()._scillm_render(
        question="What protects firmware?",
        verdict_state="satisfied",
        resolved=[],
        unresolved=[],
        external=None,
        extraction_glossary=[{"id": "CM0028", "name": "Firmware Protection"}],
        qra_items=[],
        steps=[],
    )

    assert answer == "CM0028 applies."
    assert captured["headers"]["X-Caller-Skill"] == "create-evidence-case"
    assert captured["json"]["model"] == "gemini-flash"
    assert "max_tokens" not in captured["json"]
    assert not captured["json"]["model"].startswith("qra-")


def test_scillm_render_ignores_nullable_citation_ids(monkeypatch):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{
                    "message": {
                        "content": '{"answer":"CM0020 mitigates DE-0001.","citations":[null,"CM0020","DE-0001"]}'
                    }
                }]
            }

    monkeypatch.setattr(runner.httpx, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        runner,
        "collect_entities",
        lambda _answer: {
            "resolved_entities": [
                {"canonical_id": None},
                {"canonical_id": "CM0020"},
                {"canonical_id": "DE-0001"},
            ]
        },
    )

    answer = EvidenceCaseRunner()._scillm_render(
        question="How does CM0020 mitigate DE-0001?",
        verdict_state="satisfied",
        resolved=[],
        unresolved=[],
        external=None,
        extraction_glossary=[
            {"id": "CM0020", "name": "Threat modeling"},
            {"id": "DE-0001", "name": "Disable Fault Management"},
        ],
        qra_items=[{"control_id": None, "question": "legacy", "answer": "legacy"}],
        steps=[],
    )

    assert answer == "CM0020 mitigates DE-0001."


def test_memory_persistence_client_uses_current_http_daemon(monkeypatch):
    monkeypatch.setattr(storage._thread_local, "memory_http", None, raising=False)
    client = storage._get_memory_http()
    try:
        assert str(client.base_url) == "http://127.0.0.1:8601"
    finally:
        client.close()
        monkeypatch.setattr(storage._thread_local, "memory_http", None, raising=False)
