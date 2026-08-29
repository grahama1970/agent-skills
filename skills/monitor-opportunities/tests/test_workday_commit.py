"""Regression coverage for the gated Workday commit path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from monitor_opportunities.ats.workday_apply import (
    WorkdayCommitError,
    build_fixture_authorization,
    commit_workday_application,
    require_workday_authorization,
)
from monitor_opportunities.cli import app

runner = CliRunner()

CANDIDATE_ID = "candidate:a:7365acb741a30650"
POSTING_URL = "https://moog.wd5.myworkdayjobs.com/MOOG_External_Career_Site/job/Buffalo-NY/AI-Program-Manager_R-26-19530"
APPLY_URL = POSTING_URL
PAYLOAD_DIGEST = "a" * 64
SITE = "MOOG_External_Career_Site"
POSTING_ID = "AI-Program-Manager_R-26-19530"


def _form(*, fields: list[dict] | None = None, observations: list[str] | None = None) -> dict:
    return {
        "provider": "workday",
        "site": SITE,
        "posting_id": POSTING_ID,
        "url": APPLY_URL,
        "title": "AI Program Manager",
        "organization": "Moog",
        "fields": fields
        if fields is not None
        else [
            {
                "name": "First Name",
                "field_type": "text",
                "required": True,
                "selector": "#firstName",
            },
            {"name": "Email", "field_type": "email", "required": True, "selector": "#email"},
        ],
        "policy_observations": observations or [],
    }


def _answers(extra: dict[str, str] | None = None) -> dict:
    return {
        "schema": "monitor_opportunities.answer_bank.v1",
        "answers": {
            "First Name": "Graham",
            "Email": "graham@grahama.co",
            **(extra or {}),
        },
    }


def _promotion(**overrides: object) -> dict:
    payload = {
        "schema": "monitor_opportunities.capability_promotion.v1",
        "capability": f"ats_form_submit:workday:{SITE}",
        "actor": "human",
        "decision": "PROMOTE",
        "scope": {
            "providers": ["workday"],
            "sites": [SITE],
            "candidate_ids": [CANDIDATE_ID],
            "apply_urls": [APPLY_URL],
        },
    }
    payload.update(overrides)
    return payload


def _authorization(**overrides: object) -> dict:
    payload = build_fixture_authorization(
        candidate_id=CANDIDATE_ID,
        posting_url=POSTING_URL,
        apply_url=APPLY_URL,
        payload_digest=PAYLOAD_DIGEST,
    )
    payload.update(overrides)
    return payload


class FakeWorkdayAdapter:
    def __init__(self) -> None:
        self.prefill_fields: list[dict[str, str]] = []
        self.submit_calls = 0

    def prefill(self, *, apply_url: str, fields: list[dict[str, str]], out_dir: Path) -> dict:
        self.prefill_fields = list(fields)
        evidence = out_dir / "fake-workday-prefill.png"
        evidence.write_bytes(b"png")
        return {
            "apply_url": apply_url,
            "field_results": [
                {"name": row["name"], "state": "FILLED_VERIFIED", "value": row["value"]}
                for row in fields
            ],
            "browser_evidence_paths": [str(evidence)],
        }

    def submit(self, *, posting_id: str, idempotency_key: str, out_dir: Path) -> dict:
        self.submit_calls += 1
        evidence = out_dir / "fake-workday-review.png"
        evidence.write_bytes(b"png")
        return {
            "state": "BLOCKED",
            "blocked_reason": "WORKDAY_REVIEW_STEP_REQUIRES_HUMAN",
            "submitted": False,
            "browser_evidence_paths": [str(evidence)],
            "posting_id": posting_id,
            "idempotency_key": idempotency_key,
        }


@pytest.mark.parametrize(
    ("field", "bad_value", "error"),
    [
        ("candidate_id", "candidate:a:other", "CANDIDATE_ID_MISMATCH"),
        ("posting_url", "https://example.invalid/posting", "POSTING_URL_MISMATCH"),
        ("apply_url", "https://example.invalid/apply", "APPLY_URL_MISMATCH"),
        ("payload_digest", "b" * 64, "PAYLOAD_DIGEST_MISMATCH"),
    ],
)
def test_workday_authorization_requires_exact_candidate_posting_apply_and_payload(
    field: str, bad_value: str, error: str
) -> None:
    auth = _authorization(**{field: bad_value})
    with pytest.raises(WorkdayCommitError, match=error):
        require_workday_authorization(
            auth,
            candidate_id=CANDIDATE_ID,
            posting_url=POSTING_URL,
            apply_url=APPLY_URL,
            payload_digest=PAYLOAD_DIGEST,
        )


def test_workday_commit_fills_only_schema_bound_approved_fields(tmp_path: Path) -> None:
    adapter = FakeWorkdayAdapter()
    receipt = commit_workday_application(
        candidate_id=CANDIDATE_ID,
        posting_url=POSTING_URL,
        apply_url=APPLY_URL,
        payload_digest=PAYLOAD_DIGEST,
        form_schema=_form(),
        approved_answers=_answers(),
        promotion=_promotion(),
        authorization=_authorization(),
        out_dir=tmp_path,
        submit=True,
        adapter=adapter,
        allow_duplicate=True,
        mocked=True,
        live=False,
    )

    assert [row["name"] for row in adapter.prefill_fields] == ["First Name", "Email"]
    assert receipt["state"] == "BLOCKED"
    assert receipt["blocked_reason"] == "WORKDAY_REVIEW_STEP_REQUIRES_HUMAN"
    assert receipt["external_effects"] is False
    assert receipt["submitted"] is False
    assert receipt["mocked"] is True
    assert receipt["live"] is False
    assert len(receipt["browser_evidence_paths"]) == 2
    written = json.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))
    assert written["blocked_reason"] == receipt["blocked_reason"]


def test_workday_commit_rejects_unbound_approved_answers(tmp_path: Path) -> None:
    receipt = commit_workday_application(
        candidate_id=CANDIDATE_ID,
        posting_url=POSTING_URL,
        apply_url=APPLY_URL,
        payload_digest=PAYLOAD_DIGEST,
        form_schema=_form(),
        approved_answers=_answers({"Uncaptured Workday Field": "do not fill"}),
        promotion=_promotion(),
        authorization=_authorization(),
        out_dir=tmp_path,
        submit=True,
        adapter=FakeWorkdayAdapter(),
        allow_duplicate=True,
        mocked=True,
        live=False,
    )

    assert receipt["state"] == "BLOCKED"
    assert receipt["blocked_reason"].startswith("WORKDAY_APPROVED_ANSWER_NOT_SCHEMA_BOUND")
    assert receipt["external_effects"] is False
    assert receipt["submitted"] is False


def test_workday_login_captcha_2fa_routes_to_human_handoff_before_prefill(tmp_path: Path) -> None:
    adapter = FakeWorkdayAdapter()
    receipt = commit_workday_application(
        candidate_id=CANDIDATE_ID,
        posting_url=POSTING_URL,
        apply_url=APPLY_URL,
        payload_digest=PAYLOAD_DIGEST,
        form_schema=_form(observations=["Workday sign in requires password, captcha, and 2FA."]),
        approved_answers=_answers(),
        promotion=_promotion(),
        authorization=_authorization(),
        out_dir=tmp_path,
        submit=True,
        adapter=adapter,
        allow_duplicate=True,
        mocked=True,
        live=False,
    )

    assert adapter.prefill_fields == []
    assert adapter.submit_calls == 0
    assert receipt["state"] == "BLOCKED"
    assert receipt["blocked_reason"] == "WORKDAY_HUMAN_HANDOFF_REQUIRED"
    assert "WORKDAY_HUMAN_HANDOFF_CAPTCHA" in receipt["handoff_reasons"]
    assert receipt["external_effects"] is False
    assert receipt["submitted"] is False


def test_commit_workday_command_is_exposed_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "commit-workday" in result.output
