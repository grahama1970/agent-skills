"""Autonomous apply resolver: truthful auto-fill, honest queue, never guess."""

from __future__ import annotations

from monitor_opportunities.autonomous_apply import resolve_application, resolve_field

BANK = {
    "identity": {"name": "Graham Anderson", "email": "g@x.co", "phone": "1", "current_job_title": "Principal AI Architect"},
    "work_authorization": {"authorized_us": "Yes", "require_sponsorship": "No"},
    "eeo": {"veteran_status": "I am not a protected veteran"},
    "screening": {"salary_expectation": "PLACEHOLDER — fill", "how_did_you_hear": "LinkedIn"},
}


def _f(name, ftype="text", required=True):
    return {"name": name, "field_type": ftype, "required": required}


def test_identity_and_resume_auto_fill() -> None:
    assert resolve_field(_f("Email"), BANK, "/r.pdf")["disposition"] == "auto_fill"
    assert resolve_field(_f("Resume", "file"), BANK, "/r.pdf")["value"] == "/r.pdf"
    assert resolve_field(_f("Current Job Title"), BANK, None)["value"] == "Principal AI Architect"


def test_placeholder_is_queued_not_guessed() -> None:
    r = resolve_field(_f("Salary expectation"), BANK, None)
    assert r["disposition"] == "queue" and r["value"] is None  # never fabricated


def test_unmatched_is_queued() -> None:
    assert resolve_field(_f("What is your favorite algorithm?"), BANK, None)["disposition"] == "queue"


def test_auto_submittable_when_required_all_resolve() -> None:
    form = {"provider": "ashby", "site": "x", "fields": [
        _f("Full Name"), _f("Email"), _f("Resume", "file"),
        _f("How did you hear about us?", required=False),  # optional, resolves anyway
        _f("Twitter", required=False),  # optional, queued — does NOT block
    ]}
    r = resolve_application(form, "/r.pdf", BANK)
    assert r["auto_submittable"] is True
    assert r["required_queued"] == []


def test_not_auto_submittable_when_required_field_queued() -> None:
    form = {"provider": "ashby", "site": "x", "fields": [
        _f("Email"), _f("Salary expectation"),  # required + placeholder -> blocks
    ]}
    r = resolve_application(form, "/r.pdf", BANK)
    assert r["auto_submittable"] is False
    assert "Salary expectation" in r["required_queued"]
