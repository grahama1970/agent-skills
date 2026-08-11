"""ATS learned-form storage: real forms stored, stubs rejected (no network)."""

from __future__ import annotations

import json

import monitor_opportunities.ats_store as ats


def _capture(monkeypatch) -> list[dict]:
    docs: list[dict] = []
    monkeypatch.setattr(ats, "_store", lambda doc, memory_url=ats.MEMORY_URL: docs.append(doc) or True)
    return docs


def _form_file(tmp_path, provider="ashby", site="unstructured", posting="abc", n=16):
    form = {
        "provider": provider, "site": site, "posting_id": posting,
        "url": f"https://jobs.ashbyhq.com/{site}/{posting}",
        "fields": [{"name": f"f{i}", "field_type": "text", "required": True} for i in range(n)],
        "accepted_attachments": ["Resume"],
    }
    p = tmp_path / "form.json"
    p.write_text(json.dumps(form), encoding="utf-8")
    return p


def test_real_form_stored(monkeypatch, tmp_path) -> None:
    docs = _capture(monkeypatch)
    fp = _form_file(tmp_path, n=16)
    res = ats.store_learned_form("cand:1", {"status": "OK", "field_count": 16, "form_path": str(fp)})
    assert res["stored"] is True
    assert res["key"] == "ashby-unstructured-abc"
    assert docs[0]["field_count"] == 16
    assert docs[0]["candidate_id"] == "cand:1"
    assert docs[0]["form_schema_digest"]


def test_stub_form_rejected(monkeypatch, tmp_path) -> None:
    # A 1-field capture (LinkedIn view page, not the real ATS) must NOT be stored.
    docs = _capture(monkeypatch)
    res = ats.store_learned_form("cand:2", {"status": "OK", "field_count": 1, "form_path": "x"})
    assert res["stored"] is False
    assert "stub" in res["reason"]
    assert docs == []


def test_failed_capture_not_stored(monkeypatch) -> None:
    _capture(monkeypatch)
    assert ats.store_learned_form("c", {"status": "FAILED"})["stored"] is False
    assert ats.store_learned_form("c", {"status": "DEFERRED"})["stored"] is False
