"""Pure-logic tests for live ATS form capture (no surf/network).

Prove the provider parsing, field-type mapping, and DOM->neutral-form mapping
that feed application_plan.inspect_ats_form, so the capture is verified without
a live browser.
"""

from __future__ import annotations

import pytest

from monitor_opportunities.browser_capture import (
    BrowserCaptureError,
    _ats_field_type,
    _ats_provider_from_url,
    _generic_form_from_dom,
)


def test_provider_parse_greenhouse() -> None:
    p, site, pid = _ats_provider_from_url("https://boards.greenhouse.io/acme/jobs/123456")
    assert (p, site, pid) == ("greenhouse", "acme", "123456")


def test_provider_parse_ashby_and_lever() -> None:
    assert _ats_provider_from_url("https://jobs.ashbyhq.com/reducto/abc-uuid")[0] == "ashby"
    assert _ats_provider_from_url("https://jobs.lever.co/fleet/def-uuid")[0] == "lever"


def test_provider_parse_unknown() -> None:
    p, site, _ = _ats_provider_from_url("https://careers.example.com/apply/9")
    assert p == "unknown"
    assert site == "careers.example.com"


def test_field_type_sensitive_and_kinds() -> None:
    assert _ats_field_type("Are you legally authorized to work?", "select", "", True) == "work_authorization"
    assert _ats_field_type("Gender", "select", "", True) == "self_identification"
    assert _ats_field_type("Resume/CV", "input", "file", False) == "file"
    assert _ats_field_type("Cover letter", "textarea", "", False) == "free_text"
    assert _ats_field_type("Preferred location", "select", "", True) == "choice"
    assert _ats_field_type("Email", "input", "email", False) == "email"
    assert _ats_field_type("First name", "input", "text", False) == "text"


def test_generic_form_from_dom_shape() -> None:
    rows = [
        {"tag": "input", "type": "text", "id": "first_name", "label": "First name", "required": True},
        {"tag": "input", "type": "file", "id": "resume", "label": "Resume/CV *", "required": True},
        {"tag": "textarea", "type": "", "id": "q1", "label": "Why here?", "required": False},
        {"tag": "select", "type": "", "id": "auth", "label": "Work authorization", "required": True, "options": ["Yes", "No"]},
        {"tag": "input", "type": "text", "id": "dupe", "label": "First name", "required": True},  # dedup
    ]
    form = _generic_form_from_dom("greenhouse", "acme", "123", "https://x/apply", rows)
    assert form["provider"] == "greenhouse"
    names = [f["name"] for f in form["fields"]]
    assert names == ["First name", "Resume/CV", "Why here?", "Work authorization"]  # trimmed + deduped
    assert "Resume/CV" in form["accepted_attachments"]
    auth = next(f for f in form["fields"] if f["name"] == "Work authorization")
    assert auth["field_type"] == "work_authorization"
    assert auth["required"] is True


def test_generic_form_from_dom_empty_raises() -> None:
    with pytest.raises(BrowserCaptureError):
        _generic_form_from_dom("unknown", "x", "1", "u", [{"tag": "input", "label": ""}])
