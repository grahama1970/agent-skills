"""Tests for the grahama.co update cascade contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills/monitor-website/scripts/monitor_website.py"


def load_module():
    spec = importlib.util.spec_from_file_location("monitor_website_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_grahamaco_update_plan_covers_resume_site_and_linkedin(tmp_path):
    module = load_module()

    result = module.grahamaco_update(
        plan_only=True,
        resume_exports=True,
        site=True,
        linkedin_draft=True,
        linkedin_sync_plan=True,
        accept_linkedin_account_risk=True,
        build=True,
        output_dir=tmp_path,
    )

    assert result["schema"] == "monitor-website.grahamaco_update.v1"
    assert result["status"] == "UPDATE_PLAN"
    step_names = [step["name"] for step in result["steps"]]
    assert step_names == [
        "resume_pdf",
        "resume_docx",
        "site_content",
        "site_generated_surfaces",
        "linkedin_profile_entry",
        "linkedin_profile_sync_plan",
        "site_build",
    ]
    assert "site/public/llms.txt" in result["steps"][3]["writes"]
    assert result["linkedin_boundary"] == {
        "owner": "ops-linkedin",
        "execution_claim": "NOT_EXECUTED",
        "platform_verified": False,
        "no_browser_or_linkedin_access": True,
    }


def test_linkedin_sync_plan_requires_account_risk_ack(tmp_path):
    module = load_module()

    with pytest.raises(SystemExit) as exc:
        module.grahamaco_update(
            plan_only=True,
            resume_exports=False,
            site=False,
            linkedin_draft=True,
            linkedin_sync_plan=True,
            accept_linkedin_account_risk=False,
            build=False,
            output_dir=tmp_path,
        )

    assert "--accept-linkedin-account-risk is required" in str(exc.value)
