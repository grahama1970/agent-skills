"""Agentic regression for Workday commit gating.

This intentionally checks command-surface presence first. Before the fix,
Workday roles could be shortlisted but `run.sh --help` exposed only the generic
Stage 0 `apply` gate, so this script fails before any synthetic gate assertion.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from monitor_opportunities.ats.workday_apply import (
    WorkdayCommitError,
    build_fixture_authorization,
    commit_workday_application,
    require_workday_authorization,
)

CANDIDATE_ID = "candidate:a:7365acb741a30650"
POSTING_URL = "https://moog.wd5.myworkdayjobs.com/MOOG_External_Career_Site/job/Buffalo-NY/AI-Program-Manager_R-26-19530"
APPLY_URL = POSTING_URL
PAYLOAD_DIGEST = "a" * 64
SITE = "MOOG_External_Career_Site"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _help_text() -> str:
    proc = subprocess.run(
        [str(_repo_root() / "skills" / "monitor-opportunities" / "run.sh"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_repo_root(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"run.sh --help failed: {proc.stderr[-300:] or proc.stdout[-300:]}")
    return proc.stdout


def _form(observation: str | None = None) -> dict:
    return {
        "provider": "workday",
        "site": SITE,
        "posting_id": "AI-Program-Manager_R-26-19530",
        "url": APPLY_URL,
        "title": "AI Program Manager",
        "organization": "Moog",
        "fields": [
            {
                "name": "First Name",
                "field_type": "text",
                "required": True,
                "selector": "#firstName",
            },
            {"name": "Email", "field_type": "email", "required": True, "selector": "#email"},
        ],
        "policy_observations": [observation] if observation else [],
    }


def _promotion() -> dict:
    return {
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


def _authorization(**overrides: object) -> dict:
    payload = build_fixture_authorization(
        candidate_id=CANDIDATE_ID,
        posting_url=POSTING_URL,
        apply_url=APPLY_URL,
        payload_digest=PAYLOAD_DIGEST,
    )
    payload.update(overrides)
    return payload


def _assert_mismatch_refused() -> None:
    mismatches = {
        "candidate_id": "candidate:a:other",
        "posting_url": "https://example.invalid/posting",
        "apply_url": "https://example.invalid/apply",
        "payload_digest": "b" * 64,
    }
    for field, bad_value in mismatches.items():
        auth = _authorization(**{field: bad_value})
        try:
            require_workday_authorization(
                auth,
                candidate_id=CANDIDATE_ID,
                posting_url=POSTING_URL,
                apply_url=APPLY_URL,
                payload_digest=PAYLOAD_DIGEST,
            )
        except WorkdayCommitError:
            continue
        raise AssertionError(f"AUTHORIZATION_ACCEPTED_BAD_{field.upper()}")


def _assert_handoff_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="monitor-opportunities-workday-gate-") as tmp:
        receipt = commit_workday_application(
            candidate_id=CANDIDATE_ID,
            posting_url=POSTING_URL,
            apply_url=APPLY_URL,
            payload_digest=PAYLOAD_DIGEST,
            form_schema=_form("Workday sign in requires password, captcha, and 2FA."),
            approved_answers={
                "schema": "monitor_opportunities.answer_bank.v1",
                "answers": {"First Name": "Graham", "Email": "graham@grahama.co"},
            },
            promotion=_promotion(),
            authorization=_authorization(),
            out_dir=Path(tmp),
            submit=True,
            adapter=None,
            allow_duplicate=True,
            mocked=True,
            live=False,
        )
    if receipt["state"] != "BLOCKED":
        raise AssertionError("WORKDAY_HANDOFF_NOT_BLOCKED")
    if receipt["blocked_reason"] != "WORKDAY_HUMAN_HANDOFF_REQUIRED":
        raise AssertionError(f"WORKDAY_HANDOFF_REASON_WRONG:{receipt['blocked_reason']}")
    if receipt["external_effects"] is not False or receipt["submitted"] is not False:
        raise AssertionError("WORKDAY_HANDOFF_RECORDED_EFFECT")
    required_receipt_fields = (
        "mocked",
        "live",
        "external_effects",
        "submitted",
        "blocked_reason",
        "browser_evidence_paths",
    )
    for key in required_receipt_fields:
        if key not in receipt:
            raise AssertionError(f"WORKDAY_RECEIPT_FIELD_MISSING:{key}")


def main() -> int:
    help_text = _help_text()
    if "apply" not in help_text:
        print("GENERIC_APPLY_COMMAND_MISSING", file=sys.stderr)
        return 1
    if "commit-workday" not in help_text:
        print("WORKDAY_COMMIT_COMMAND_MISSING generic_apply_present=True", file=sys.stderr)
        return 1
    _assert_mismatch_refused()
    _assert_handoff_receipt()
    print("WORKDAY_COMMIT_GATE_OK command=commit-workday mismatches_refused=4 submitted=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
