"""Trigger signal: fit-gated, receipted pass over the shortlist."""
from __future__ import annotations

from monitor_opportunities import trigger_signals


def test_triggers_for_shortlist_gates_by_fit_and_receipts(monkeypatch) -> None:
    # Stub the live brave-search so the test is deterministic and offline.
    calls: list[str] = []

    def fake_trigger(org: str) -> dict[str, object]:
        calls.append(org)
        return {"trigger": 0.9, "evidence": f"{org} raised $10M"}

    monkeypatch.setattr(trigger_signals, "company_trigger", fake_trigger)

    rows = [
        {"organization": "HighFit", "fit_score": 0.9},
        {"organization": "LowFit", "fit_score": 0.2},  # below min_fit -> not searched
        {"organization": "HighFit", "fit_score": 0.5},  # dup org, keeps best fit
    ]
    lookup, receipt = trigger_signals.triggers_for_shortlist(rows, min_fit=0.6)

    assert calls == ["HighFit"]  # only the fit-clearing org was searched
    assert lookup["HighFit"]["trigger"] == 0.9
    assert receipt["schema"] == "monitor_opportunities.trigger_receipt.v1"
    assert receipt["orgs_searched"] == 1
    low = next(r for r in receipt["records"] if r["org"] == "LowFit")
    assert low["searched"] is False and low["skip_reason"] == "below_min_fit"


def test_triggers_for_shortlist_respects_budget_limit(monkeypatch) -> None:
    monkeypatch.setattr(trigger_signals, "company_trigger",
                        lambda org: {"trigger": 0.0, "evidence": None})
    rows = [{"organization": f"Org{i}", "fit_score": 0.9} for i in range(20)]
    lookup, receipt = trigger_signals.triggers_for_shortlist(rows, min_fit=0.6, limit=5)
    assert receipt["orgs_searched"] == 5
    assert sum(1 for r in receipt["records"] if r.get("skip_reason") == "over_budget") == 15
