from __future__ import annotations

import json
from pathlib import Path

import pytest

import monitor_opportunities.nightly_digest as nightly_digest
from monitor_opportunities.contracts import ContractError
from monitor_opportunities.nightly_digest import run_digest_phase


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
    monkeypatch.setattr(
        "monitor_opportunities.trigger_signals.triggers_for_shortlist",
        lambda _rows: ({}, {"schema": "monitor_opportunities.trigger_receipt.v1", "records": []}),
    )

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
