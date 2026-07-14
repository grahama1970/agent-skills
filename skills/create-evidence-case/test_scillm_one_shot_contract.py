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
                        "content": '{"decision":"answer","answer":"CM0028 applies to detect firmware changes.","clarifying_question":"","citations":["CM0028"]}'
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
        lambda _answer: {
            "resolved_entities": [
                {"canonical_id": "CM0028"},
                {"canonical_id": "MID-001"},
                {"canonical_id": "Detect"},
            ]
        },
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

    assert answer.splitlines()[0] == "CM0028 applies to detect firmware changes."
    assert "[CM0028]" in answer
    assert "MID-001" not in answer
    assert "[Detect]" not in answer
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
                        "content": '{"decision":"answer","answer":"CM0020 mitigates DE-0001.","clarifying_question":"","citations":[null,"CM0020","DE-0001"]}'
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

    assert answer.splitlines()[0] == "CM0020 mitigates DE-0001."
    assert "[CM0020]" in answer
    assert "[DE-0001]" in answer


def test_scillm_render_fails_closed_after_transport_errors(monkeypatch):
    def fail_post(*_args, **_kwargs):
        raise RuntimeError("transport unavailable")

    monkeypatch.setattr("runner.httpx.post", fail_post)

    answer = EvidenceCaseRunner()._scillm_render(
        question="How does CM0020 address DE-0001?",
        verdict_state="satisfied",
        resolved=[],
        unresolved=[],
        external=[],
        extraction_glossary=[],
        qra_items=[],
        steps=[],
    )

    assert answer == "LLM render failed: transport unavailable"


def test_assertion_semantic_decision_requires_closed_grounded_contract(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": (
                    '{"schema":"sparta.assertion_semantic_decision.v1",'
                    '"assertion_id":"F36B-MAP-test",'
                    '"assertion_claim_sha256":"sha256:test",'
                    '"decision":"SUPPORTS",'
                    '"decision_reason":"The recalled item directly supports the assertion.",'
                    '"evidence_refs":["qra-1"],'
                    '"supported_claim_refs":["F36B-MAP-test"],'
                    '"contradicted_claim_refs":[],"clarification_question":null}'
                )}}]
            }

    def post(*args, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("runner.httpx.post", post)
    result = EvidenceCaseRunner()._scillm_assertion_decision(
        assertion_id="F36B-MAP-test",
        assertion_claim_sha256="sha256:test",
        claim_text="Does the exact mapping support the engineering obligation?",
        resolved=[],
        qra_items=[{"_key": "qra-1", "question": "Q", "answer": "A"}],
        steps=[],
    )

    assert result["decision"] == "SUPPORTS"
    assert result["renderer_terminal_state"] == "completed"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["model"] == "gemini-flash"


def test_assertion_semantic_decision_marks_validation_exhaustion_runtime_failure(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"decision":"SUPPORTS"}'}}]}

    monkeypatch.setattr("runner.httpx.post", lambda *args, **kwargs: Response())
    result = EvidenceCaseRunner()._scillm_assertion_decision(
        assertion_id="F36B-MAP-test",
        assertion_claim_sha256="sha256:test",
        claim_text="Does the exact mapping support the engineering obligation?",
        resolved=[],
        qra_items=[],
        steps=[],
    )

    assert result["decision"] is None
    assert result["renderer_terminal_state"] == "validation_exhausted"


def test_memory_persistence_client_uses_current_http_daemon(monkeypatch):
    monkeypatch.setattr(storage._thread_local, "memory_http", None, raising=False)
    client = storage._get_memory_http()
    try:
        assert str(client.base_url) == "http://127.0.0.1:8601"
    finally:
        client.close()
        monkeypatch.setattr(storage._thread_local, "memory_http", None, raising=False)
