"""Contact-change detection: role/org moves and project wins become vendor leads."""
from __future__ import annotations

from monitor_opportunities import contact_changes as cc


def test_contact_key_is_stable_across_org_moves() -> None:
    # The whole point is recognising the same person at a DIFFERENT company,
    # so org must not participate in the identity.
    assert cc.contact_key("Sumeet Vij") == cc.contact_key("  sumeet   vij ")
    assert cc.contact_key("Sumeet Vij", "Accenture") == cc.contact_key("Sumeet Vij", "Booz Allen")


def test_normalize_extracts_org_from_headline() -> None:
    rows = [{"name": "Colin Mackenzie", "current": "VP, AI Engineering at Multiverse"}]
    out = cc.normalize_contacts(rows, "actively_hiring")
    assert out[0]["org"] == "Multiverse"
    assert out[0]["role"].startswith("VP, AI Engineering")


def test_org_move_becomes_a_vendor_lead_carrying_the_warm_path() -> None:
    current = cc.normalize_contacts(
        [{"name": "Jane Roe", "current": "Head of AI at Lockheed Martin",
          "mutuals": "Chris Fregly is a mutual connection"}],
        "actively_hiring",
    )
    previous = {current[0]["_key"]: {**current[0], "org": "Gauss Labs",
                                    "role": "Staff AI Engineer at Gauss Labs"}}
    changes = cc.diff_contacts(previous, current)
    assert [c["change_type"] for c in changes] == ["org_change"]
    leads = cc.vendor_leads(changes)
    assert leads[0]["organization"] == "Lockheed Martin"
    assert leads[0]["action"] == "consulting_outreach_inmail"
    assert leads[0]["transmitted_by"] == "human"  # Graham sends every message
    assert "Chris Fregly" in leads[0]["warm_path"]
    assert "new mandate and budget" in leads[0]["why_now"]


def test_first_sighting_is_not_a_change() -> None:
    current = cc.normalize_contacts([{"name": "New Person", "current": "CTO at Acme"}], "x")
    assert cc.diff_contacts({}, current) == []


def test_unchanged_contact_produces_no_lead() -> None:
    current = cc.normalize_contacts([{"name": "Same Person", "current": "CTO at Acme"}], "x")
    previous = {current[0]["_key"]: dict(current[0])}
    assert cc.diff_contacts(previous, current) == []


def test_project_win_regex_matches_real_headlines_not_prose() -> None:
    assert cc._PROJECT_WIN.search("Acme Corp awarded $4M Navy contract")
    assert cc._PROJECT_WIN.search("Startup raises $12M Series B")
    assert not cc._PROJECT_WIN.search("Acme publishes a blog post about contracts")


def test_role_change_regex_matches_announcements() -> None:
    assert cc._ROLE_CHANGE.search("Jane Roe joins Acme as VP of Engineering")
    assert cc._ROLE_CHANGE.search("Acme named John Doe Chief Data Officer")
    assert not cc._ROLE_CHANGE.search("Acme sells widgets to customers")


def test_public_signal_pass_is_failsoft_without_search(monkeypatch) -> None:
    monkeypatch.setattr(cc, "_brave", lambda *a, **k: "")
    contacts = cc.normalize_contacts([{"name": "Jane Roe", "current": "CTO at Acme"}], "x")
    assert cc.public_signal_changes(contacts) == []


def test_public_signal_win_becomes_lead(monkeypatch) -> None:
    monkeypatch.setattr(cc, "_brave", lambda *a, **k: "Acme awarded $4M contract by DoD")
    contacts = cc.normalize_contacts([{"name": "Jane Roe", "current": "CTO at Acme"}], "x")
    changes = cc.public_signal_changes(contacts)
    assert changes[0]["change_type"] == "project_win"
    assert changes[0]["evidence_source"] == "brave-search"
    leads = cc.vendor_leads(changes)
    assert "staff up and hire vendors" in leads[0]["why_now"]


def test_relationship_signals_include_adjacent_no_linkedin_profile_contacts() -> None:
    candidates = [
        {
            "candidate_id": "candidate:c:darpa-arcos",
            "organization": "DARPA I2O",
            "title": "ARCOS reconnect",
            "source_receipt_id": "src:sos-vo:william-brad-martin",
            "primary_evidence_url": "https://sos-vo.org/user/91",
            "known_monitor_contacts": ["William Brad Martin"],
            "adjacent_contacts": ["Eric Mertens", "David Archer"],
        }
    ]
    signals = cc.relationship_signals_from_candidates(candidates)
    assert {row["signal_type"] for row in signals} == {"direct_contact", "adjacent_contact"}
    assert any(row["subject"] == "William Brad Martin" for row in signals)
    assert any(row["subject"] == "Eric Mertens" for row in signals)
    assert all(row["external_effects"] is False for row in signals)
    assert all(row["visible_in_report"] is True for row in signals)
    assert all("https://sos-vo.org/user/91" in row["evidence_refs"] for row in signals)
