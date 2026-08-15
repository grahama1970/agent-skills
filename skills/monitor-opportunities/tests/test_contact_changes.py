"""Contact-change detection: role/org moves and project wins become vendor leads."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from monitor_opportunities import contact_changes as cc

RELATIONSHIP_CANDIDATE_SCHEMA = Path(
    "skills/monitor-opportunities/schemas/relationship-candidate.schema.json"
)


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
    assert all(signal["memory_recall_found"] is True for signal in signals)
    assert all(signal["memory_recall_degraded"] is False for signal in signals)
    assert signals[0]["schema"] == "monitor_opportunities.relationship_candidate.v1"
    assert signals[0]["relationship_degree"] == 1
    assert signals[0]["degree_label"] == "direct"
    assert signals[0]["relationship_degree"] == len(signals[0]["contact_path"])
    assert signals[0]["contact_path"][0]["from"] == "Graham Anderson"
    assert signals[0]["contact_path"][0]["to"] == "William Brad Martin"
    assert signals[0]["contact_path"][0]["evidence_status"] == "MATCHES"
    assert signals[0]["contact_path"][0]["evidence_refs"]
    assert signals[0]["recommended_human_channel"] == "LINKEDIN_HUMAN_HANDOFF"
    assert signals[0]["channel_rationale"]
    assert signals[0]["channel_limitations"]
    assert 0 < signals[0]["confidence"] <= 1
    assert "RECONNECT" in signals[0]["human_decision_options"]


def test_arcos_contact_csv_keeps_relationship_signals_when_memory_recall_misses(
    tmp_path, monkeypatch
) -> None:
    csv_path = tmp_path / "darpa_arcos_contacts.csv"
    csv_path.write_text(
        "\n".join(
            [
                "first_name,last_name,organization,email,status",
                "William Brad,Martin,DARPA I2O,william@example.com,",
                "David,Archer,Galois Inc.,dwa@galois.com,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cc, "ARCOS_CONTACT_PATH", csv_path)
    monkeypatch.setattr(
        cc,
        "_memory_recall",
        lambda *_args, **_kwargs: {"found": False, "items": []},
    )

    signals = cc.relationship_signals_from_memory("http://memory", limit=10)

    assert [signal["subject"] for signal in signals] == ["William Brad Martin", "David Archer"]
    assert signals[0]["signal_type"] == "direct_contact"
    assert signals[1]["signal_type"] == "adjacent_contact"
    assert all(signal["memory_recall_found"] is False for signal in signals)
    assert all(signal["memory_recall_degraded"] is True for signal in signals)
    assert all("memory://" not in ref for signal in signals for ref in signal["evidence_refs"])
    assert all(csv_path.as_uri() in signal["evidence_refs"] for signal in signals)
    assert all("Memory recall did not return this seed" in signal["provenance"] for signal in signals)
    assert all(signal["external_effects"] is False for signal in signals)
    assert all(signal["confidence"] < 0.85 for signal in signals)


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
    validator = Draft202012Validator(json.loads(RELATIONSHIP_CANDIDATE_SCHEMA.read_text()))
    for signal in signals:
        validator.validate(signal)
    direct = next(row for row in signals if row["subject"] == "William Brad Martin")
    adjacent = next(row for row in signals if row["subject"] == "Eric Mertens")
    assert direct["relationship_degree"] == 1
    assert direct["degree_label"] == "direct"
    assert direct["relationship_degree"] == len(direct["contact_path"])
    assert direct["relationship_path"] == ["Graham Anderson", "William Brad Martin"]
    assert adjacent["relationship_degree"] == 2
    assert adjacent["degree_label"] == "second_degree"
    assert adjacent["relationship_degree"] == len(adjacent["contact_path"])
    assert adjacent["contact_path"][0]["from"] == "Graham Anderson"
    assert adjacent["contact_path"][0]["to"] == "ARCOS/formal-methods network"
    assert adjacent["contact_path"][1]["to"] == "Eric Mertens"
    assert adjacent["contact_path"][0]["evidence_refs"] == ["https://sos-vo.org/user/91"]
    assert adjacent["recommended_human_channel"] == "LINKEDIN_HUMAN_HANDOFF"


def test_relationship_signals_attach_to_opportunities_by_exact_id_and_unique_org() -> None:
    opportunities = [
        {"opportunity_id": "candidate:a:galois", "organization": "Galois, Inc."},
        {"opportunity_id": "candidate:a:other", "organization": "Other Systems"},
    ]
    signals = [
        {
            "signal_id": "rel-exact",
            "source_opportunity_id": "candidate:a:galois",
            "organization": "Unrelated Org",
        },
        {
            "signal_id": "rel-org",
            "source_opportunity_id": "memory:darpa-arcos-contact-network",
            "organization": "Galois Inc",
        },
        {
            "signal_id": "rel-other",
            "source_opportunity_id": "memory:darpa-arcos-contact-network",
            "organization": "SRI International",
        },
    ]

    attached = cc.attach_relationship_signals_to_opportunities(opportunities, signals)

    assert attached[0]["relationship_signal_ids"] == ["rel-exact", "rel-org"]
    assert attached[0]["relationship_signal_count"] == 2
    assert attached[1]["relationship_signal_ids"] == []
    assert attached[1]["relationship_signal_count"] == 0


def test_relationship_signal_binding_quarantines_ambiguous_and_unsafe_org_matches() -> None:
    opportunities = [
        {"opportunity_id": "candidate:a:galois-1", "organization": "Galois, Inc."},
        {"opportunity_id": "candidate:a:galois-2", "organization": "Galois LLC"},
        {"opportunity_id": "candidate:a:galois-federal", "organization": "Galois Federal"},
        {"opportunity_id": "candidate:a:unique", "organization": "Unique Research"},
    ]
    signals = [
        {
            "signal_id": "rel-exact-stale-ok",
            "source_opportunity_id": "candidate:a:galois-1",
            "organization": "Different Org",
            "relationship_freshness": "stale",
        },
        {
            "signal_id": "rel-ambiguous",
            "source_opportunity_id": "memory:arcos",
            "organization": "Galois Inc",
        },
        {
            "signal_id": "rel-parent-subsidiary",
            "source_opportunity_id": "memory:arcos",
            "organization": "Galois Federal Research",
        },
        {
            "signal_id": "rel-stale",
            "source_opportunity_id": "memory:arcos",
            "organization": "Unique Research Inc",
            "current_role_verified": False,
        },
        {
            "signal_id": "rel-unique",
            "source_opportunity_id": "memory:arcos",
            "organization": "Unique Research Inc",
        },
    ]

    diagnostics = cc.bind_relationship_signals_to_opportunities(opportunities, signals)

    assert opportunities[0]["relationship_signal_ids"] == ["rel-exact-stale-ok"]
    assert opportunities[1]["relationship_signal_ids"] == []
    assert opportunities[2]["relationship_signal_ids"] == []
    assert opportunities[3]["relationship_signal_ids"] == ["rel-unique"]
    assert {row["reason_code"] for row in diagnostics} == {
        "AMBIGUOUS_ORGANIZATION_ALIAS",
        "NO_ORGANIZATION_MATCH",
        "RELATIONSHIP_FRESHNESS_UNVERIFIED",
    }
    assert all(row["external_effects"] is False for row in diagnostics)
    assert all(row["visible_in_report"] is True for row in diagnostics)


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
