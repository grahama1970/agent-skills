"""Contact freshness: changes detected, staleness reported, nothing invented."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitor_contacts.freshness import PROJECT_WIN, ROLE_CHANGE, detect_changes, stale_contacts
from monitor_contacts.relationship_graph import reconnect_signals_from_observations
from monitor_contacts.store import contact_key

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def test_contact_key_survives_an_org_move() -> None:
    assert contact_key("Yusuke Sakamoto") == contact_key(" yusuke  sakamoto ")


def test_org_move_is_detected() -> None:
    key = contact_key("Jane Roe")
    stored = {key: {"_key": key, "name": "Jane Roe", "org": "Gauss Labs", "role": "Staff"}}
    observed = [{"_key": key, "name": "Jane Roe", "org": "Lockheed Martin", "role": "Staff"}]
    ch = detect_changes(stored, observed, research_limit=0)
    assert ch[0]["change_type"] == "org_change" and ch[0]["to"] == "Lockheed Martin"


def test_unchanged_contact_yields_no_change() -> None:
    key = contact_key("Same Person")
    rec = {"_key": key, "name": "Same Person", "org": "Acme", "role": "CTO"}
    assert detect_changes({key: rec}, [dict(rec)], research_limit=0) == []


def test_first_sighting_is_not_a_change() -> None:
    key = contact_key("New Person")
    observed = [{"_key": key, "name": "New Person", "org": "Acme", "role": "CTO"}]
    assert detect_changes({}, observed, research_limit=0) == []


def test_stale_contacts_are_reported_not_assumed_unchanged() -> None:
    old = (NOW - timedelta(days=90)).isoformat()
    fresh = (NOW - timedelta(days=2)).isoformat()
    out = stale_contacts(
        [{"name": "Old", "org": "A", "observed_at": old},
         {"name": "Fresh", "org": "B", "observed_at": fresh}],
        stale_days=30, now=NOW,
    )
    assert [c["name"] for c in out] == ["Old"]


def test_contact_with_no_observation_date_counts_as_stale() -> None:
    out = stale_contacts([{"name": "Unknown", "org": "A"}], stale_days=30, now=NOW)
    assert out and out[0]["age_days"] is None


def test_signal_regexes_match_announcements_not_prose() -> None:
    assert PROJECT_WIN.search("Acme awarded $4M contract")
    assert ROLE_CHANGE.search("Jane joins Acme as VP")
    assert not PROJECT_WIN.search("Acme blogs about contracts")


def test_reconnect_graph_export_is_local_only_and_channel_aware() -> None:
    signals = reconnect_signals_from_observations(
        [
            {
                "name": "William Brad Martin",
                "organization": "DARPA I2O",
                "source_url": "https://sos-vo.org/user/91",
                "relationship_type": "direct_contact",
                "relationship_path": ["Graham Anderson", "DARPA ARCOS network", "William Brad Martin"],
            }
        ],
        source_id="memory:darpa-arcos-contact-network",
    )

    assert signals[0]["subject"] == "William Brad Martin"
    assert signals[0]["signal_type"] == "direct_contact"
    assert signals[0]["organization"] == "DARPA I2O"
    assert signals[0]["external_effects"] is False
    assert signals[0]["visible_in_report"] is True
    assert "LINKEDIN_HUMAN_HANDOFF" in signals[0]["preferred_human_channels"]
    assert "AUTHORIZED_PERSONA_GMAIL" in signals[0]["preferred_human_channels"]
    assert "https://sos-vo.org/user/91" in signals[0]["evidence_refs"]
