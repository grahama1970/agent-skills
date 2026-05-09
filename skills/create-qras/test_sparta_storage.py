"""Focused storage safety tests for create-qras."""

from __future__ import annotations

import json

import generator


class _Response:
    status_code = 200
    text = "ok"

    def raise_for_status(self):
        return None


class _JsonEncodingClient:
    def __init__(self):
        self.payload = None

    def post(self, _path, *, json=None):
        json_module = __import__("json")
        json_module.dumps(json)
        self.payload = json
        return _Response()


def test_store_qra_breaks_circular_evidence_case_before_post(monkeypatch):
    monkeypatch.setattr(generator, "_get_embedding", lambda _text: [0.1, 0.2, 0.3])
    client = _JsonEncodingClient()
    qra = {
        "_key": "q1",
        "qra_type": "relationship",
        "question": "How does DE-0001 relate to CM0001?",
        "answer": "They share a fault-management context.",
        "reasoning": "The evidence case binds both controls.",
        "evidence_case": {},
    }
    qra["evidence_case"]["self"] = qra

    assert generator._store_qra(client, qra) is True

    document = client.payload["document"]
    assert client.payload["collection"] == "sparta_qra_relationship"
    assert document["evidence_case"]["self"] == "[Circular]"
    assert document["embedding"] == [0.1, 0.2, 0.3]
    assert "embedding" not in qra


def test_json_safe_copy_converts_non_json_values():
    copied = generator._json_safe_copy({"ids": {"CM0001", "CM0002"}, "raw": b"abc"})

    assert sorted(copied["ids"]) == ["CM0001", "CM0002"]
    assert copied["raw"] == "abc"
    json.dumps(copied)


def test_detect_framework_handles_cve_ids_as_nvd():
    assert generator._detect_framework("CVE-2025-11589") == "NVD"
