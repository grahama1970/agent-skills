"""GitHub repository intelligence becomes governed contact source-intel."""

from __future__ import annotations

import copy
import inspect
import json
import base64
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from monitor_opportunities import cli
from monitor_opportunities import contact_changes as cc
from monitor_opportunities.cli import app
from monitor_opportunities.contracts import validate_manifest
from monitor_opportunities.discovery import _github_evidence_candidates
from monitor_opportunities.github_repo_intelligence import (
    GitHubRepoIntelligenceConfig,
    GitHubRepoIntelligenceError,
    collect_github_repo_intelligence,
    write_degraded_github_repo_intelligence,
)
from monitor_opportunities.pipeline import _source_intel
from monitor_opportunities.verification import built_in_fixture

RELATIONSHIP_CANDIDATE_SCHEMA = Path(
    "skills/monitor-opportunities/schemas/relationship-candidate.schema.json"
)
runner = CliRunner()


def _report_source_receipt(receipt: dict) -> dict:
    keys = {
        "receipt_id",
        "lane",
        "provider",
        "target",
        "source_class",
        "result_status",
        "observed_at",
        "request_summary",
        "response_status",
        "content_type",
        "response_bytes",
        "content_sha256",
        "evidence_refs",
        "limitations",
        "automation_policy",
        "required_source_id",
        "channel",
        "fallback_for_receipt_id",
    }
    projected = {key: value for key, value in receipt.items() if key in keys}
    projected.setdefault("response_status", None)
    projected.setdefault("content_type", None)
    projected.setdefault("content_sha256", None)
    return projected


def _github_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "monitor_opportunities.github_repo_intelligence.v1",
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "description": "ARCOS formal-methods support tools.",
                        "topics": ["darpa", "arcos", "formal-methods"],
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "role": "repository_owner",
                                "profile_url": "https://github.com/rtinney1",
                                "evidence_url": "https://github.com/rtinney1/arcos-tools",
                                "corroboration": [
                                    {
                                        "type": "profile_name_match",
                                        "evidence_refs": ["https://github.com/rtinney1"],
                                        "note": (
                                            "Profile evidence supports this handle mapping."
                                        ),
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_github_evidence_candidates_preserve_repo_contact_receipts(tmp_path: Path) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))

    assert receipt["result_status"] == "MATCHES"
    assert receipt["provider"] == "github"
    assert "https://github.com/rtinney1/arcos-tools" in receipt["evidence_refs"]
    assert "https://github.com/rtinney1" in receipt["evidence_refs"]
    assert candidates[0]["source_provider"] == "github_repo_intelligence"
    assert candidates[0]["source_receipt_id"] == receipt["receipt_id"]
    assert candidates[0]["adjacent_contacts"] == ["Randi Tinney (@rtinney1)"]
    assert candidates[0]["github_contact_hypotheses"][0]["mapping_status"] == "corroborated"
    assert candidates[0]["github_contact_hypotheses"][0]["corroboration"][0]["resolved"] is True
    assert candidates[0]["external_effects"] is False
    assert "No GitHub, LinkedIn, email, or application action" in candidates[0][
        "unresolved_assumptions"
    ][2]


def test_github_repo_contacts_emit_relationship_candidate_with_edge_receipts(
    tmp_path: Path,
) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))

    signals = cc.relationship_signals_from_candidates(candidates)

    assert len(signals) == 1
    signal = signals[0]
    assert signal["schema"] == "monitor_opportunities.relationship_candidate.v1"
    assert signal["signal_type"] == "adjacent_contact"
    assert signal["subject"] == "Randi Tinney (@rtinney1)"
    assert signal["source_receipt_ids"] == [receipt["receipt_id"]]
    assert signal["relationship_path"] == [
        "Graham Anderson",
        "GitHub repo rtinney1/arcos-tools",
        "Randi Tinney (@rtinney1)",
    ]
    assert signal["relationship_degree"] == 2
    assert all(
        edge["source_receipt_ids"] == [receipt["receipt_id"]]
        for edge in signal["contact_path"]
    )
    assert all(
        "https://github.com/rtinney1" in edge["evidence_refs"]
        for edge in signal["contact_path"]
    )
    assert "handle mapping status: corroborated" in signal["provenance"]
    assert signal["external_effects"] is False
    assert "LINKEDIN_HUMAN_HANDOFF" in signal["preferred_human_channels"]

    Draft202012Validator(json.loads(RELATIONSHIP_CANDIDATE_SCHEMA.read_text())).validate(signal)


def test_github_source_intel_and_relationship_signal_validate_in_report(tmp_path: Path) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))
    signal = cc.relationship_signals_from_candidates(candidates)[0]
    source_intel = _source_intel(candidates[0])
    assert source_intel is not None
    assert source_intel["signal_type"] == "GITHUB_REPO_INTELLIGENCE"
    assert source_intel["decision"] == "CONTACT_INTELLIGENCE_ONLY"

    manifest = copy.deepcopy(built_in_fixture())
    manifest["source_receipts"].append(_report_source_receipt(receipt))
    manifest.setdefault("source_intel", []).append(source_intel)
    manifest.setdefault("relationship_signals", []).append(signal)
    manifest["artifact_accounting"]["action_worthy_total"] += 2
    manifest["artifact_accounting"]["visible_total"] += 2

    loaded = validate_manifest(manifest)

    assert loaded.source_intel[-1].signal_type == "GITHUB_REPO_INTELLIGENCE"
    assert loaded.relationship_signals[-1].subject == "Randi Tinney (@rtinney1)"


def test_github_untyped_corroboration_stays_handle_only_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                                "corroboration": "confirmed",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert hypothesis["corroboration"][0]["type"] == "untyped"
    assert hypothesis["corroboration"][0]["resolved"] is False
    assert candidates[0]["adjacent_contacts"] == ["GitHub @rtinney1"]
    assert signal["subject"] == "GitHub @rtinney1"
    assert "Randi Tinney (@" not in signal["subject"]


def test_github_corroboration_refs_must_resolve_to_contact_evidence(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                                "corroboration": [
                                    {
                                        "type": "profile_name_match",
                                        "evidence_refs": ["https://example.invalid/not-in-receipt"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert hypothesis["corroboration"][0]["resolved"] is False
    assert signal["subject"] == "GitHub @rtinney1"


def test_github_name_and_handle_without_corroboration_stays_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert signal["subject"] == "GitHub @rtinney1"


def test_github_contacts_deduplicate_same_handle_across_roles(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/OpenC3_Cosmos_cFS_CFDP",
                        "repo_url": "https://github.com/rtinney1/OpenC3_Cosmos_cFS_CFDP",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                                "corroboration": [
                                    {
                                        "type": "human_confirmation",
                                        "evidence_refs": [
                                            "https://github.com/rtinney1",
                                            "https://github.com/rtinney1/OpenC3_Cosmos_cFS_CFDP",
                                        ],
                                    }
                                ],
                            }
                        ],
                        "commit_authors": [
                            {
                                "handle": "rtinney1",
                                "commit_url": (
                                    "https://github.com/rtinney1/"
                                    "OpenC3_Cosmos_cFS_CFDP/commit/abc"
                                ),
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)

    assert candidates[0]["adjacent_contacts"] == ["Randi Tinney (@rtinney1)"]
    assert len(candidates[0]["github_contact_hypotheses"]) == 1


def test_github_degraded_artifact_stays_degraded_through_sweep(tmp_path: Path) -> None:
    artifact = tmp_path / "github-degraded.json"
    degraded_receipt = write_degraded_github_repo_intelligence(
        GitHubRepoIntelligenceConfig(
            out=artifact,
            queries=("DARPA ARCOS",),
            owners=("rtinney1",),
            owner_names=(("rtinney1", "Randi Tinney"),),
        ),
        error="GitHub rate limit exceeded (HTTP 429)",
    )

    receipt, candidates = _github_evidence_candidates(artifact)
    sweep_out = tmp_path / "sweep"
    result = runner.invoke(
        app,
        [
            "sweep",
            "--lane",
            "C",
            "--out",
            str(sweep_out),
            "--github-evidence",
            str(artifact),
        ],
    )
    source_receipts = [
        json.loads(line)
        for line in (sweep_out / "source-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    github_receipts = [row for row in source_receipts if row.get("provider") == "github"]

    assert degraded_receipt["status"] == "DEGRADED"
    assert receipt["result_status"] == "RATE_LIMITED"
    assert receipt["parser_result"] == "DEGRADED"
    assert candidates == []
    assert result.exit_code == 0, result.output
    assert github_receipts
    assert github_receipts[0]["result_status"] == "RATE_LIMITED"
    assert github_receipts[0]["evidence_refs"] == [f"file://{artifact.resolve()}"]
    assert any("GitHub producer degraded" in item for item in github_receipts[0]["limitations"])


def test_github_rate_limit_from_api_becomes_degraded_sweep_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    def rate_limited_gh(*_args: str, timeout: int = 45) -> Any:
        del timeout
        raise GitHubRepoIntelligenceError("GitHub rate limit exceeded (HTTP 429)")

    monkeypatch.setattr(
        "monitor_opportunities.github_repo_intelligence._gh_json",
        rate_limited_gh,
    )
    artifact = tmp_path / "github-rate-limited.json"
    producer_receipt = collect_github_repo_intelligence(
        GitHubRepoIntelligenceConfig(
            out=artifact,
            queries=(),
            repos=(),
            owners=("rtinney1",),
            owner_names=(("rtinney1", "Randi Tinney"),),
        )
    )
    sweep_out = tmp_path / "sweep-rate-limited"
    result = runner.invoke(
        app,
        [
            "sweep",
            "--lane",
            "C",
            "--out",
            str(sweep_out),
            "--github-evidence",
            str(artifact),
        ],
    )
    source_receipts = [
        json.loads(line)
        for line in (sweep_out / "source-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    github_receipt = next(row for row in source_receipts if row.get("provider") == "github")

    assert producer_receipt["status"] == "DEGRADED"
    assert producer_receipt["repositories_captured"] == 0
    assert result.exit_code == 0, result.output
    assert github_receipt["result_status"] == "RATE_LIMITED"
    assert github_receipt["parser_result"] == "DEGRADED"
    assert any("owner_repos" in item for item in github_receipt["limitations"])


def _fake_gh_json(*args: str, timeout: int = 45) -> Any:
    raw_endpoint = args[1] if len(args) > 1 and args[0] == "api" else ""
    endpoint = raw_endpoint.split("?", 1)[0]
    if endpoint == "/repos/rtinney1/arcos-tools":
        return {
            "full_name": "rtinney1/arcos-tools",
            "html_url": "https://github.com/rtinney1/arcos-tools",
            "owner": {"login": "rtinney1", "html_url": "https://github.com/rtinney1"},
            "description": "ARCOS support tools",
            "topics": ["darpa", "arcos"],
            "updated_at": "2026-08-01T00:00:00Z",
            "pushed_at": "2026-08-02T00:00:00Z",
        }
    if endpoint == "/users/rtinney1/repos":
        return [
            {
                "full_name": "rtinney1/oss-security",
                "html_url": "https://github.com/rtinney1/oss-security",
                "owner": {"login": "rtinney1", "html_url": "https://github.com/rtinney1"},
                "description": "Security mailing-list mirror",
                "topics": ["security"],
            }
        ]
    if endpoint == "/search/repositories":
        return {
            "items": [
                {
                    "full_name": "galoisinc/arcos-notes",
                    "html_url": "https://github.com/galoisinc/arcos-notes",
                    "owner": {"login": "galoisinc", "html_url": "https://github.com/galoisinc"},
                    "description": "Public ARCOS notes",
                    "topics": ["arcos"],
                }
            ]
        }
    if endpoint == "/users/rtinney1":
        return {"login": "rtinney1", "name": "Randi Tinney", "html_url": "https://github.com/rtinney1"}
    if endpoint == "/users/galoisinc":
        return {"login": "galoisinc", "name": "Galois Inc", "html_url": "https://github.com/galoisinc"}
    if endpoint == "/users/formalAlice":
        return {"login": "formalAlice", "name": "Alice Formal", "html_url": "https://github.com/formalAlice"}
    if endpoint.endswith("/languages"):
        return {"Python": 1200, "Shell": 300}
    if endpoint.endswith("/readme"):
        full_name = endpoint.removeprefix("/repos/").removesuffix("/readme")
        readme = (
            "DARPA ARCOS repository intelligence for formal methods assurance, "
            "cFS CFDP aerospace workflows, and Galois-adjacent verification. "
            "Related profile: https://github.com/readmeEve"
        )
        return {
            "path": "README.md",
            "html_url": f"https://github.com/{full_name}/blob/HEAD/README.md",
            "encoding": "base64",
            "content": base64.b64encode(readme.encode("utf-8")).decode("ascii"),
        }
    if endpoint.endswith("/contributors"):
        return [{"login": "formalAlice", "html_url": "https://github.com/formalAlice"}]
    if endpoint.endswith("/issues"):
        return [
            {
                "html_url": endpoint.replace("/repos/", "https://github.com/").replace(
                    "/issues", "/issues/7"
                ),
                "title": "DARPA ARCOS assurance issue",
                "body": "Track formal methods evidence for aerospace verification.",
                "user": {"login": "issueBob"},
            },
            {
                "html_url": endpoint.replace("/repos/", "https://github.com/").replace(
                    "/issues", "/pull/99"
                ),
                "title": "PR masquerading as issue with ARCOS text",
                "body": "GitHub issues API returns pull requests too.",
                "pull_request": {"url": "https://api.github.com/repos/example/example/pulls/99"},
                "user": {"login": "duplicatePrUser"},
            }
        ]
    if endpoint.endswith("/pulls"):
        return [
            {
                "html_url": endpoint.replace("/repos/", "https://github.com/").replace(
                    "/pulls", "/pull/3"
                ),
                "title": "Galois ARCOS RACK update",
                "body": "Adds security evidence for RACK source intelligence.",
                "user": {"login": "prCarol"},
            }
        ]
    if endpoint.endswith("/commits"):
        return [
            {
                "html_url": endpoint.replace("/repos/", "https://github.com/").replace(
                    "/commits", "/commit/abc"
                ),
                "commit": {"message": "ARCOS CFDP verification maintenance"},
                "author": {"login": "commitDave"},
            }
        ]
    raise AssertionError(f"unexpected gh api call: {args!r} timeout={timeout}")


def test_live_github_intelligence_producer_writes_ingestable_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "monitor_opportunities.github_repo_intelligence._gh_json",
        _fake_gh_json,
    )
    artifact = tmp_path / "github-live.json"

    producer_receipt = collect_github_repo_intelligence(
        GitHubRepoIntelligenceConfig(
            out=artifact,
            queries=("Galois ARCOS",),
            repos=("rtinney1/arcos-tools",),
            owners=(),
            max_repos=2,
            max_contributors=2,
            max_issues=1,
            max_pull_requests=1,
            max_commits=1,
        )
    )
    receipt, candidates = _github_evidence_candidates(artifact)
    signals = cc.relationship_signals_from_candidates(candidates)

    assert producer_receipt["status"] == "PASS"
    assert producer_receipt["external_effects"] is False
    assert producer_receipt["repositories_captured"] == 2
    assert producer_receipt["contacts_captured"] >= 8
    assert receipt["result_status"] == "MATCHES"
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    first_record = artifact_payload["repositories"][0]
    analysis = first_record["repository_analysis"]
    assert analysis["languages"] == {"Python": 1200, "Shell": 300}
    assert "DARPA ARCOS" in analysis["matched_terms"]
    assert "formal methods" in analysis["matched_terms"]
    assert analysis["readme"]["path"] == "README.md"
    assert analysis["readme_snippets"]
    assert {row["kind"] for row in analysis["activity_snippets"]} == {
        "issue",
        "pull_request",
        "commit",
    }
    assert any("DARPA ARCOS assurance issue" in row["snippets"][0]["snippet"] for row in analysis["activity_snippets"])
    assert not any("masquerading" in row["snippets"][0]["snippet"] for row in analysis["activity_snippets"])
    assert "https://github.com/readmeEve" in first_record["evidence_refs"]
    assert any(contact["handle"] == "readmeEve" for contact in first_record["mentioned_contacts"])
    assert {row["github_repo"] for row in candidates} == {
        "rtinney1/arcos-tools",
        "galoisinc/arcos-notes",
    }
    assert any("README evidence snippets" in row["posting_text"] for row in candidates)
    assert any("Recent activity snippets" in row["posting_text"] for row in candidates)
    assert any("DARPA ARCOS assurance issue" in row["posting_text"] for row in candidates)
    assert any("DARPA ARCOS repository intelligence" in row["posting_text"] for row in candidates)
    assert any(row["subject"] == "Randi Tinney (@rtinney1)" for row in signals)
    assert any(row["subject"] == "GitHub @readmeEve" for row in signals)
    assert any(row["subject"] == "GitHub @issueBob" for row in signals)
    assert any(row["external_effects"] is False for row in signals)


def test_github_intelligence_producer_accepts_owner_handles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "monitor_opportunities.github_repo_intelligence._gh_json",
        _fake_gh_json,
    )
    artifact = tmp_path / "github-owner.json"

    producer_receipt = collect_github_repo_intelligence(
        GitHubRepoIntelligenceConfig(
            out=artifact,
            queries=(),
            repos=(),
            owners=("rtinney1",),
            max_repos=1,
            max_contributors=0,
            max_issues=0,
            max_pull_requests=0,
            max_commits=0,
        )
    )
    receipt, candidates = _github_evidence_candidates(artifact)

    assert producer_receipt["status"] == "PASS"
    assert producer_receipt["owner_handles"] == ["rtinney1"]
    assert receipt["result_status"] == "MATCHES"
    assert candidates[0]["github_repo"] == "rtinney1/oss-security"
    assert "Randi Tinney (@rtinney1)" in candidates[0]["adjacent_contacts"]
    assert "GitHub @readmeEve" in candidates[0]["adjacent_contacts"]


def test_github_intelligence_cli_writes_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "monitor_opportunities.github_repo_intelligence._gh_json",
        _fake_gh_json,
    )
    artifact = tmp_path / "github-cli.json"

    result = runner.invoke(
        app,
        [
            "github-intelligence",
            "--out",
            str(artifact),
            "--repo",
            "rtinney1/arcos-tools",
            "--owner",
            "rtinney1",
            "--max-repos",
            "1",
            "--max-contributors",
            "1",
            "--max-issues",
            "1",
            "--max-pull-requests",
            "1",
            "--max-commits",
            "1",
            "--max-readme-bytes",
            "4096",
            "--max-readme-snippets",
            "4",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["external_effects"] is False
    assert artifact_payload["automation_policy"] == "github_read_only_no_mutation_no_outreach"
    assert artifact_payload["external_effects"] is False
    assert artifact_payload["repositories"][0]["repo"] == "rtinney1/arcos-tools"
    assert artifact_payload["owner_handles"] == ["rtinney1"]
    assert artifact_payload["limits"]["max_readme_bytes"] == 4096
    assert artifact_payload["limits"]["max_readme_snippets"] == 4
    assert artifact_payload["repositories"][0]["repository_analysis"]["readme"]["path"] == "README.md"


def test_nightly_wires_github_intelligence_into_run() -> None:
    source = inspect.getsource(cli.nightly)

    assert "collect_github_repo_intelligence" in source
    assert "github-repo-intelligence.json" in source
    assert '"--github-evidence"' in source
    assert "MONITOR_GITHUB_INTEL_OWNERS" in source
    assert "MONITOR_GITHUB_INTEL_OWNER_NAMES" in source
    assert "MONITOR_GITHUB_INTEL_MAX_README_BYTES" in source
    assert "MONITOR_GITHUB_INTEL_MAX_README_SNIPPETS" in source
