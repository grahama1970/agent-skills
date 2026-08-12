"""Morning digest: ranks by response, classifies, attaches decision-makers."""
from __future__ import annotations
from monitor_opportunities.morning_digest import build_digest


def test_digest_ranks_classifies_and_flags_signals() -> None:
    sl = [
        {"organization": "Drata", "title": "Staff AI Engineer", "lane": "A", "fit_score": 0.8,
         "workplace_type": "REMOTE", "apply_url": "https://jobs.ashbyhq.com/drata/x", "source_class": "ashby"},
        {"organization": "CUBRC", "title": "AI research", "lane": "A", "fit_score": 0.8,
         "workplace_type": "WNY_ONSITE", "source_provider": "discover-contacts"},
        {"organization": "DARPA", "title": "Sources Sought", "lane": "B", "signal_type": "federal", "fit_score": 0.7},
    ]
    d = build_digest(sl)
    assert d["counts"]["employment"] == 2 and d["counts"]["consulting"] == 1
    assert d["signals_wired"]["warm_path"] is False  # honest: not wired yet
    # local Buffalo role outranks the remote cold-apply at equal fit
    orgs = [e["organization"] for e in d["top"]]
    assert orgs.index("CUBRC") < orgs.index("Drata")
    # consulting entry carries no apply action
    darpa = next(e for e in d["top"] if e["organization"] == "DARPA")
    assert darpa["opportunity_type"] == "consulting" and darpa["action"]["apply_on_site"] is None
    # known decision-maker attached
    drata = next(e for e in d["top"] if e["organization"] == "Drata")
    assert drata["inmail_target"] and "Lior" in drata["inmail_target"]["name"]
