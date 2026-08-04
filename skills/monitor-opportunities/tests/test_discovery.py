from __future__ import annotations

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.discovery import (
    LINKEDIN_AUTOMATION_POLICY,
    LINKEDIN_AUTHORIZED_READ_ONLY_POLICY,
    _ashby_candidates,
    _candidate_id,
    _employment_candidates,
    _linkedin_evidence_candidates,
    _sam_receipt,
    _source_locator_receipt,
)

runner = CliRunner()


def test_fixture_sweep_writes_receipts_and_candidates(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "discovery"
    result = runner.invoke(app, ["sweep", "--fixture-dir", str(fixture_dir), "--lane", "A,B,C", "--out", str(out)])
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_effects"] is False
    receipts = (out / "source-receipts.jsonl").read_text(encoding="utf-8").splitlines()
    candidates = (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(receipts) == 3
    assert len(candidates) == 3
    lane_summaries = json.loads((out / "lane-summaries.json").read_text(encoding="utf-8"))
    assert {row["lane"]: row["result_status"] for row in lane_summaries}["B"] == "FEED_DOWN"


def test_unattempted_lane_is_not_searched(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "discovery"
    result = runner.invoke(app, ["sweep", "--fixture-dir", str(fixture_dir), "--lane", "A", "--out", str(out)])
    assert result.exit_code == 0, result.output
    lane_summaries = json.loads((out / "lane-summaries.json").read_text(encoding="utf-8"))
    assert {row["lane"]: row["result_status"] for row in lane_summaries}["B"] == "NOT_SEARCHED"


def test_source_locator_is_hint_only_and_admits_no_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://hiddenjobs.dev/"
        return httpx.Response(200, text="Remote roles from greenhouse and lever.")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    receipt = _source_locator_receipt(
        client,
        {
            "lane": "A",
            "name": "Hidden Jobs",
            "provider": "hiddenjobs.dev",
            "url": "https://hiddenjobs.dev/",
        },
    )
    assert receipt["source_class"] == "source_locator"
    assert receipt["result_status"] == "MATCHES"
    assert receipt["parser_result"] == "HINTS_ONLY"
    assert receipt["evidence_refs"] == ["https://hiddenjobs.dev/"]
    assert any("hint-only" in item for item in receipt["limitations"])


def test_employment_dispatch_rejects_unknown_provider() -> None:
    target = {"provider": "unknown-board", "name": "Example", "slug": "example"}
    receipt, rows = _employment_candidates(httpx.Client(), target)
    assert rows == []
    assert receipt["result_status"] == "INVALID_REQUEST"
    assert receipt["parser_result"] == "UNSUPPORTED_PROVIDER"


def test_ashby_candidate_maps_primary_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/posting-api/job-board/example")
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "Applied AI Engineer",
                        "location": {"name": "Remote"},
                        "jobUrl": "https://jobs.example/ai",
                        "applyUrl": "https://jobs.example/ai/apply",
                        "descriptionPlain": "Build applied AI systems.",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    receipt, rows = _ashby_candidates(client, {"name": "Example", "slug": "example"})
    assert receipt["provider"] == "ashby"
    assert receipt["result_status"] == "MATCHES"
    assert receipt["evidence_refs"] == ["https://api.ashbyhq.com/posting-api/job-board/example"]
    assert rows[0]["source_provider"] == "ashby"
    assert rows[0]["title"] == "Applied AI Engineer"
    assert rows[0]["primary_evidence_url"] == "https://jobs.example/ai"
    assert rows[0]["workplace_type"] == "REMOTE"


def test_sam_zero_records_is_no_matches(monkeypatch) -> None:
    monkeypatch.setenv("SAM_GOV_API_KEY", "example-key-not-secret")

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url: str, params: dict[str, str]) -> httpx.Response:
            assert params == {"api_key": "example-key-not-secret"}
            return httpx.Response(200, json={"totalRecords": 0, "opportunitiesData": []})

    monkeypatch.setattr("monitor_opportunities.discovery.httpx.Client", FakeClient)
    receipt = _sam_receipt({"name": "SAM.gov Opportunities", "provider": "sam.gov"})
    assert receipt["result_status"] == "NO_MATCHES"
    assert receipt["parser_result"] == "PARSED"


def test_human_supplied_linkedin_evidence_is_local_only_candidate() -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "linkedin-top-candidate.json"
    receipt, rows = _linkedin_evidence_candidates(fixture)
    assert receipt["source_class"] == "human_supplied_linkedin"
    assert receipt["automation_policy"] == LINKEDIN_AUTOMATION_POLICY
    assert receipt["result_status"] == "MATCHES"
    assert any("not logged into" in item for item in receipt["limitations"])
    assert rows[0]["source_provider"] == "human_supplied_linkedin"
    assert rows[0]["automation_policy"] == "linkedin_no_automation"
    assert rows[0]["top_candidate_evidence"] is True
    assert rows[0]["apply_url"] is None


def test_ops_linkedin_authorized_capture_yields_multiple_read_only_candidates() -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "ops-linkedin-jobs-capture.json"
    receipt, rows = _linkedin_evidence_candidates(fixture)
    assert receipt["source_class"] == "ops_linkedin_authorized_read_only"
    assert receipt["automation_policy"] == LINKEDIN_AUTHORIZED_READ_ONLY_POLICY
    assert receipt["result_status"] == "MATCHES"
    assert len(rows) == 2
    assert rows[0]["source_provider"] == "ops_linkedin_authorized_read_only"
    assert rows[0]["automation_policy"] == LINKEDIN_AUTHORIZED_READ_ONLY_POLICY
    assert rows[0]["top_candidate_evidence"] is True
    assert rows[0]["apply_url"] is None
    assert rows[1]["location_display"] == "New York, NY (On-site)"


def test_candidate_identity_ignores_mutable_content_receipts() -> None:
    base = {
        "lane": "C",
        "source_provider": "primary-company-source",
        "source_identity": "https://example.com/needs",
        "organization": "Example",
        "title": "Modernization signal",
        "primary_evidence_url": "https://example.com/needs",
        "source_receipt_id": "src:first",
        "content_hash": "hash:first",
    }
    changed = {**base, "source_receipt_id": "src:second", "content_hash": "hash:second"}
    assert _candidate_id("candidate:c", base) == _candidate_id("candidate:c", changed)
