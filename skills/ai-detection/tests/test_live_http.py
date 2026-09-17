"""Live server end-to-end proof over real sockets, independent of unavailable browser transport."""
import hashlib

import httpx

from ai_detection.contracts import EvidenceExport
from ai_detection.io import atomic_json
from ai_detection.verify import verify_export
from tests.helpers import edit
from tests.test_browser import real_server


def test_real_http_transport(tmp_path, evidence_dir):
    with real_server(tmp_path, evidence_dir) as base, httpx.Client(timeout=5, trust_env=False) as client:
        opened = client.post(base + "/api/sessions", json={"consent": True, "language": "python"})
        opened.raise_for_status()
        identity = opened.json()
        session_url = base + "/api/sessions/" + identity["session_id"]
        auth = {"Authorization": "Bearer " + identity["token"]}
        event, source = edit("", "def greeting():\n    return 'Hello 🧪 雪'\n")
        received = client.post(session_url + "/events", headers=auth, json=event.model_dump())
        received.raise_for_status()
        assert received.json()["event"]["after_sha256"] == hashlib.sha256(source.encode()).hexdigest()
        submitted = client.post(session_url + "/submit", headers=auth,
                               json={"revision": 1, "source_sha256": event.after_sha256})
        submitted.raise_for_status()
        exported = client.get(session_url + "/export", headers=auth)
        exported.raise_for_status()
        data = EvidenceExport.model_validate(exported.json())
        assert data.source == source
        result = verify_export(data)
        assert result["status"] == "PASS"
        deleted = client.delete(session_url, headers=auth)
        deleted.raise_for_status()
        assert deleted.json()["deleted"] is True
        assert client.get(session_url + "/export", headers=auth).status_code == 401
        atomic_json(evidence_dir / "http-readback.json", {
            "schema_version": "ai_detection.live_http_proof.v1", "status": "PASS",
            "transport": "real_loopback_http", "independent_readback": result,
            "delete_readback": "unauthorized_after_delete", "browser_exercised": False,
            "real_human_detection": "NOT_ESTABLISHED"})
