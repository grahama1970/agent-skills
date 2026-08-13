from __future__ import annotations

import json
from pathlib import Path

import pytest

import monitor_opportunities.nightly_digest as nightly_digest
from monitor_opportunities.contracts import ContractError
from monitor_opportunities.nightly_digest import run_digest_phase


def _quiet_enrichments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "monitor_opportunities.trigger_signals.triggers_for_shortlist",
        lambda _rows: ({}, {"schema": "monitor_opportunities.trigger_receipt.v1", "records": []}),
    )
    monkeypatch.setattr("monitor_opportunities.prospect_research.mailbox_warm_contacts", lambda *_args: {})
    monkeypatch.setattr("monitor_opportunities.prospect_research.research_prospects", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_who_viewed",
        lambda _capture_dir: {"status": "EMPTY", "viewers_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_actively_hiring",
        lambda _capture_dir: {"status": "EMPTY", "contacts_captured": 0},
    )
    monkeypatch.setattr(
        "monitor_opportunities.browser_capture.capture_linkedin_job_insights",
        lambda _urls: {},
    )
    monkeypatch.setattr(
        "monitor_opportunities.contact_changes.detect",
        lambda *_args, **_kwargs: ([], {"schema": "monitor_opportunities.contact_changes.v1"}),
    )
    monkeypatch.setattr("monitor_opportunities.prospect_queue.build_prospect_queue", lambda *_args: [])


def test_diagnostic_digest_contract_violation_is_withheld_and_degraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "run"
    discovery = out / "discovery"
    ranking = out / "ranking"
    capture = out / "browser-capture"
    discovery.mkdir(parents=True)
    ranking.mkdir(parents=True)
    capture.mkdir(parents=True)
    (discovery / "source-receipts.jsonl").write_text("", encoding="utf-8")
    (ranking / "shortlist.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "c1",
                    "organization": "Acme",
                    "title": "Consulting lead",
                    "lane": "C",
                    "fit_score": 0.8,
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        nightly_digest,
        "build_digest",
        lambda *_args, **_kwargs: {
            "top": [{"candidate_id": "c1", "organization": "Acme", "title": "Consulting lead"}],
            "counts": {"total": 1},
            "signals_wired": {},
        },
    )
    _quiet_enrichments(monkeypatch)

    strict_steps: dict[str, object] = {}
    with pytest.raises(ContractError) as strict_error:
        run_digest_phase(out, tmp_path, capture, "http://127.0.0.1:1", strict_steps)
    assert strict_error.value.code == "NIGHTLY_DIGEST_CONTRACT_VIOLATION"

    degraded_steps: dict[str, object] = {}
    run_digest_phase(
        out,
        tmp_path,
        capture,
        "http://127.0.0.1:1",
        degraded_steps,
        degrade_digest_contract=True,
    )
    assert degraded_steps["prepublish_contract"]["ok"] is False
    assert degraded_steps["digest"]["phase"] == "DIGEST_DEGRADED"
    assert degraded_steps["digest"]["artifact"] is None
    assert degraded_steps["digest"]["seam_validation"]["status"] == "DEGRADED_WITHHELD"
    assert degraded_steps["degraded_contracts"][0]["code"] == "NIGHTLY_DIGEST_CONTRACT_VIOLATION"
    assert (out / "prepublish-contract.json").exists()
    assert not (out / "morning-digest.json").exists()


def test_consulting_research_rows_are_bound_to_current_run_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "run"
    discovery = out / "discovery"
    ranking = out / "ranking"
    capture = out / "browser-capture"
    discovery.mkdir(parents=True)
    ranking.mkdir(parents=True)
    capture.mkdir(parents=True)
    client_receipt = {
        "receipt_id": "src:c:client-research:test",
        "required_source_id": "client_research",
        "lane": "C",
        "provider": "client-research",
        "channel": "brave_search",
        "source_class": "source_locator",
        "result_status": "MATCHES",
    }
    (discovery / "source-receipts.jsonl").write_text(json.dumps(client_receipt) + "\n", encoding="utf-8")
    (ranking / "shortlist.json").write_text("[]\n", encoding="utf-8")
    consulting_row = {
        "candidate_id": "candidate:c:research:test",
        "organization": "Acme",
        "title": "Acme wins AI modernization contract",
        "lane": "C",
        "signal_type": "commercial",
        "fit_score": 0.8,
        "posting_url": "https://example.com/acme-ai-contract",
    }
    monkeypatch.setattr(
        "monitor_opportunities.consulting_discovery.discover",
        lambda: ([dict(consulting_row)], {"queries_run": 1, "candidates": 1}),
    )
    _quiet_enrichments(monkeypatch)

    steps: dict[str, object] = {}
    run_digest_phase(out, tmp_path, capture, "http://127.0.0.1:1", steps)

    assert steps["prepublish_contract"]["ok"] is True
    digest = json.loads((out / "morning-digest.json").read_text(encoding="utf-8"))
    assert digest["top"][0]["candidate_id"] == "candidate:c:research:test"
    saved = json.loads((out / "consulting-research.json").read_text(encoding="utf-8"))
    row = saved["candidates"][0]
    assert row["eligibility_state"] == "ELIGIBLE_CONSULTING"
    assert row["source_receipt_id"] == "src:c:client-research:test"
