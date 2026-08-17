"""Tests for REST state transitions."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from live_evidence.api import create_app
from live_evidence.config import AppSettings


def make_settings(tmp_path: Path) -> AppSettings:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "name: api-test\nwatch_terms: [agent]\nproject_aliases: {}\n",
        encoding="utf-8",
    )
    return AppSettings(
        skill_root=tmp_path,
        data_dir=tmp_path / "data",
        profile_path=profile_path,
        repo_roots=[],
        memory_url="http://127.0.0.1:9",
        request_timeout_s=0.2,
        subprocess_timeout_s=0.5,
    )


def test_session_state_transitions(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        initial = client.get("/api/state")
        assert initial.status_code == 200
        assert initial.json()["session"]["status"] == "idle"

        blocked = client.post("/api/session/start", json={"consent_confirmed": False})
        assert blocked.status_code == 200
        assert blocked.json()["session"]["status"] == "idle"
        assert blocked.json()["session"]["consent_confirmed"] is False

        started = client.post("/api/session/start", json={"consent_confirmed": True})
        assert started.status_code == 200
        assert started.json()["session"]["status"] == "listening"
        assert started.json()["session"]["consent_confirmed"] is True

        paused = client.post("/api/session/pause")
        assert paused.status_code == 200
        assert paused.json()["session"]["status"] == "paused"

        resumed = client.post("/api/session/start", json={"consent_confirmed": True})
        assert resumed.status_code == 200
        assert resumed.json()["session"]["status"] == "listening"

        stopped = client.post("/api/session/stop")
        assert stopped.status_code == 200
        assert stopped.json()["session"]["status"] == "stopped"


def test_action_registration_degrades_without_memory(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/actions/register",
            json={
                "actions": [
                    {
                        "element_id": "live-evidence:test:action",
                        "app": "live-evidence",
                        "action": "LIVE_EVIDENCE_TEST_ACTION",
                        "label": "Test action",
                        "description": "Verify action registration boundary",
                    }
                ]
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] in {"ok", "degraded"}


def test_stopped_session_archives_transcript_without_retrieval(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()
        client.post("/api/session/stop").raise_for_status()
        transcript = client.post(
            "/api/transcript",
            json={
                "schema": "live_evidence.transcript_event.v1",
                "speaker": "interviewer",
                "kind": "final",
                "source": "api",
                "text": "How do you prevent an agent from drifting during a long workflow?",
            },
        )
        assert transcript.status_code == 202
        time.sleep(0.25)
        state = client.get("/api/state")
        assert state.status_code == 200
        payload = state.json()
        assert payload["session"]["status"] == "stopped"
        assert len(payload["transcript"]) == 1
        assert payload["cards"] == []
        assert payload["current_thread"] == "Waiting for the conversation"
