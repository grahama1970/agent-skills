# Code-enforced discovery gate: mandated sources cannot be silently skipped.
"""Behavioral gates for pipeline._enforce_required_sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from monitor_opportunities.contracts import ContractError
from monitor_opportunities.pipeline import _enforce_required_sources

SKILL_DIR = Path("skills/monitor-opportunities")


def _write_receipts(tmp: Path, providers_and_status: list[tuple[str, str]]) -> Path:
    import json

    d = tmp / "discovery"
    d.mkdir(parents=True)
    lines = []
    for i, (prov, status) in enumerate(providers_and_status):
        lines.append(json.dumps({
            "receipt_id": f"r{i}", "lane": "A", "provider": prov, "target": prov,
            "source_class": "employer_ats", "result_status": status,
            "observed_at": "2026-08-06T00:00:00Z", "request_summary": "x",
            "response_status": 200, "content_type": None, "response_bytes": 0,
            "content_sha256": None, "evidence_refs": [], "limitations": [],
        }))
    (d / "source-receipts.jsonl").write_text("\n".join(lines), encoding="utf-8")
    return d


def _all_required() -> list[tuple[str, str]]:
    import json
    cfg = json.loads((SKILL_DIR / "config" / "required_sources.json").read_text())
    return [(r["id"], "MATCHES") for r in cfg["required"]]


def test_all_required_present_passes(tmp_path: Path) -> None:
    d = _write_receipts(tmp_path, _all_required())
    result = _enforce_required_sources(SKILL_DIR, d)
    assert result["required_sources_enforced"] is True


def test_absent_required_source_fails(tmp_path: Path) -> None:
    rows = [r for r in _all_required() if r[0] != "client_research"]
    d = _write_receipts(tmp_path, rows)
    with pytest.raises(ContractError, match="must attempt every required source"):
        _enforce_required_sources(SKILL_DIR, d)


def test_not_searched_status_fails(tmp_path: Path) -> None:
    rows = [(rid, "NOT_SEARCHED" if rid == "indeed" else "MATCHES") for rid, _ in _all_required()]
    d = _write_receipts(tmp_path, rows)
    with pytest.raises(ContractError, match="must attempt every required source"):
        _enforce_required_sources(SKILL_DIR, d)


def test_honest_feed_down_is_allowed(tmp_path: Path) -> None:
    rows = [(rid, "FEED_DOWN" if rid == "sam.gov" else "MATCHES") for rid, _ in _all_required()]
    d = _write_receipts(tmp_path, rows)
    assert _enforce_required_sources(SKILL_DIR, d)["required_sources_enforced"] is True
