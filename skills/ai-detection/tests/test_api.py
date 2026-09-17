"""Nonmocked ASGI and SQLite sanity checks; separate live Chromium proof is in test_browser."""
import pytest
from fastapi.testclient import TestClient

from ai_detection.api import create_app
from ai_detection.contracts import EvidenceExport, Policy
from ai_detection.verify import verify_export
from tests.helpers import edit


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "http.sqlite3"), base_url="http://localhost") as instance:
        yield instance


def test_http_session_roundtrip(client):
    assert client.get("/api/health").json()["efficacy"] == "NOT_ESTABLISHED"
    response = client.post("/api/sessions", json={"consent": True, "language": "python"})
    assert response.status_code == 201
    data = response.json()
    base = f"/api/sessions/{data['session_id']}"
    auth = {"Authorization": f"Bearer {data['token']}"}
    event, source = edit("", "def answer():\n    return '🧪'\n")
    assert client.post(base + "/events", headers=auth, json=event.model_dump()).status_code == 200
    result = client.post(base + "/submit", headers=auth, json={"revision": 1, "source_sha256": event.after_sha256})
    assert result.status_code == 200
    assert result.json()["automatic_penalty"] is False
    exported = client.get(base + "/export", headers=auth)
    assert data["token"] not in exported.text
    assert verify_export(EvidenceExport.model_validate(exported.json()))["status"] == "PASS"
    assert client.delete(base, headers=auth).json()["deleted"] is True
    assert client.get(base + "/export", headers=auth).status_code == 401


@pytest.mark.parametrize("payload", [{"consent": False}, {"consent": "true"}, {"consent": 1},
                                       {"consent": True, "trusted": True}])
def test_api_consent_validation(client, payload):
    result = client.post("/api/sessions", json=payload)
    assert result.status_code == 422
    assert result.json()["validation_errors"]


def test_error_does_not_echo_sensitive_unknown_value(client):
    sensitive = "confidential-source-and-token-should-not-echo"
    response = client.post("/api/sessions", json={"consent": True, "secret": sensitive})
    assert response.status_code == 422
    assert sensitive not in response.text


def test_request_boundaries_and_security_headers(client):
    assert client.post("/api/sessions", json={"consent": True},
                       headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "unrelated.example"}).status_code == 400
    assert client.post("/api/sessions", content='{"consent":true,"consent":false}',
                       headers={"Content-Type": "application/json"}).status_code == 400
    assert client.post("/api/sessions", content="x" * 800000,
                       headers={"Content-Type": "application/json"}).status_code == 413
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/sessions/unknown/export").status_code == 401


def test_session_capacity(tmp_path):
    with TestClient(create_app(tmp_path / "one.sqlite3", Policy(max_sessions=1)), base_url="http://localhost") as client:
        assert client.post("/api/sessions", json={"consent": True}).status_code == 201
        assert client.post("/api/sessions", json={"consent": True}).status_code == 429
