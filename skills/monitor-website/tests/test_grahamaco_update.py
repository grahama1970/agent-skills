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
        "site_interactions",
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


def test_constellation_contract_covers_graph_click_and_private_overview_nodes(tmp_path):
    module = load_module()

    manifest_path = tmp_path / "constellation-manifest.json"
    module._write_constellation_contract_manifest(
        url="http://127.0.0.1:43210/",
        output_path=manifest_path,
    )

    manifest = manifest_path.read_text(encoding="utf-8")
    assert '"path": "/#project-watch"' in manifest
    assert '"contains": "/explore#project-watch"' in manifest
    assert "[data-qid='explore:card:watch']" in manifest
    assert "project-watch exists after root hash redirect" in manifest
    assert '"wait_ready": "body"' in manifest
    assert "[data-qid='constellation:jump:tau']" in manifest
    assert '"contains": "/explore#project-tau"' in manifest
    assert "[data-qid='explore:card:tau']" in manifest
    assert "project-tau exists on Explore index" in manifest
    assert "https://github.com/grahama1970/memory-public" in manifest
    assert "https://github.com/grahama1970/sparta-public" in manifest
    assert "[data-qid='constellation:node:project:memory'] .c-ring--private" in manifest
    assert "[data-qid='constellation:node:project:sparta-explorer'] .c-ring--private" in manifest
