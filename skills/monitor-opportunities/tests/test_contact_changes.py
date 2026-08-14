"""Contact-change detection: role/org moves and project wins become vendor leads."""
from __future__ import annotations

from monitor_opportunities import contact_changes as cc


def test_memory_recall_arcos_contacts_become_linkedin_first_relationship_signals(
    tmp_path, monkeypatch
) -> None:
    csv_path = tmp_path / "darpa_arcos_contacts.csv"
    csv_path.write_text(
        "\n".join(
            [
                "first_name,last_name,organization,email,status",
                "William Brad,Martin,DARPA I2O,william@example.com,",
                "David,Archer,Galois Inc.,dwa@galois.com,",
                "Paul,Cuddihy,GE Research,paul@example.com,deceased",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cc, "ARCOS_CONTACT_PATH", csv_path)
    monkeypatch.setattr(
        cc,
        "_memory_recall",
        lambda *_args, **_kwargs: {"found": True, "items": [{"_key": "arcos-network"}]},
    )

    signals = cc.relationship_signals_from_memory("http://memory", limit=10)

    assert [signal["subject"] for signal in signals] == ["William Brad Martin", "David Archer"]
    assert signals[0]["signal_type"] == "direct_contact"
    assert signals[1]["signal_type"] == "adjacent_contact"
    assert all(signal["external_effects"] is False for signal in signals)
    assert all(signal["visible_in_report"] is True for signal in signals)
    assert all(signal["recommended_action"] == "human_decide_reconnect_or_defer" for signal in signals)
    assert all("LINKEDIN_HUMAN_HANDOFF" in signal["preferred_human_channels"] for signal in signals)
    assert all("AUTHORIZED_PERSONA_GMAIL" in signal["preferred_human_channels"] for signal in signals)
    assert all("memory://arcos-network" in signal["evidence_refs"] for signal in signals)
    assert all(csv_path.as_uri() in signal["evidence_refs"] for signal in signals)


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
    assert all(row["contact_channel_risk"] == "corporate_email_may_be_blocked_after_long_gap" for row in signals)
    assert all("LINKEDIN_HUMAN_HANDOFF" in row["preferred_human_channels"] for row in signals)
    assert all("AUTHORIZED_PERSONA_GMAIL" in row["preferred_human_channels"] for row in signals)
    assert all(any("Corporate email may be blocked" in item for item in row["channel_guidance"]) for row in signals)


def test_relationship_signals_can_be_disabled_for_scheduler_diagnostic(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_RELATIONSHIP_SIGNALS_ENABLED", "0")
    candidates = [
        {
            "candidate_id": "candidate:c:darpa-arcos",
            "organization": "DARPA I2O",
            "known_monitor_contacts": ["William Brad Martin"],
            "adjacent_contacts": ["Eric Mertens"],
        }
    ]
    assert cc.relationship_signals_from_candidates(candidates) == []
