"""Tests for the grahama.co update cascade contract."""

from __future__ import annotations

import importlib.util
import json
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


def test_audit_uses_inventory_stats_not_stale_readme_counts(tmp_path, monkeypatch):
    module = load_module()
    site = tmp_path / "site"
    site.mkdir()
    readme = tmp_path / "README.md"
    content = site / "content.json"
    inventory = site / "inventory.json"
    readme.write_text(
        """
| Inventory | Count |
|---|---:|
| Skills | 1 |
| With `sanity.sh` | 1 |
| Agent directories | 1 |
<a href="https://github.com/grahama1970/agent-skills/blob/main/skills/tau/README.md">
  <img src="tau.webp">
</a>
<br/><strong>T'au</strong><br/><em>Memory-First Zero-Trust Agent Harness</em>
""",
        encoding="utf-8",
    )
    content.write_text(
        '{"stats":{"skills":10,"sanity":9,"agents":2},"projects":[{"slug":"tau","name":"t\u0027au","href":"https://github.com/grahama1970/tau"}]}',
        encoding="utf-8",
    )
    inventory.write_text(
        '{"stats":{"skills":10,"sanity":9,"agents":2}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "README", readme)
    monkeypatch.setattr(module, "CONTENT", content)
    monkeypatch.setattr(module, "INVENTORY", inventory)
    monkeypatch.setattr(module, "_surface_coherence_drift", lambda ignore_surfaces=None: [])
    monkeypatch.setattr(module, "_project_provenance_drift", lambda readme_projects, site_projects: ([], []))

    result = module.audit(live=False)

    assert result["ok"] is True
    assert result["inventory_stats"] == {"skills": 10, "sanity": 9, "agents": 2}
    assert not any("README=" in drift for drift in result["drift"])


def test_apply_sync_preserves_inventory_stats_and_extra_site_projects(tmp_path, monkeypatch):
    module = load_module()
    site = tmp_path / "site"
    site.mkdir()
    readme = tmp_path / "README.md"
    content = site / "content.json"
    inventory = site / "inventory.json"
    readme.write_text(
        """
| Inventory | Count |
|---|---:|
| Skills | 1 |
| With `sanity.sh` | 1 |
| Agent directories | 1 |
<a href="https://github.com/grahama1970/agent-skills/blob/main/skills/tau/README.md">
  <img src="tau.webp">
</a>
<br/><strong>T'au</strong><br/><em>Memory-First Zero-Trust Agent Harness</em>
""",
        encoding="utf-8",
    )
    content.write_text(
        """{
  "stats": {"skills": 1, "sanity": 1, "agents": 1},
  "projects": [
    {"slug": "tau", "name": "t'au", "href": "https://github.com/grahama1970/tau", "why": "external source"},
    {"slug": "memory", "name": "memory", "href": "https://github.com/grahama1970/memory-public", "why": "public overview"}
  ]
}
""",
        encoding="utf-8",
    )
    inventory.write_text(
        '{"stats":{"skills":10,"sanity":9,"agents":2}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "README", readme)
    monkeypatch.setattr(module, "CONTENT", content)
    monkeypatch.setattr(module, "INVENTORY", inventory)

    result = module.apply_sync()
    updated = json.loads(content.read_text(encoding="utf-8"))

    assert result["changed"] is True
    assert updated["stats"] == {"skills": 10, "sanity": 9, "agents": 2}
    assert [project["slug"] for project in updated["projects"]] == ["tau", "memory"]
    assert updated["projects"][0]["href"] == "https://github.com/grahama1970/tau"
    assert updated["projects"][1]["href"] == "https://github.com/grahama1970/memory-public"


def test_project_provenance_accepts_intentional_dual_links():
    module = load_module()
    readme_projects = [
        {"slug": "tau", "href": "https://github.com/grahama1970/agent-skills/blob/main/skills/tau/README.md"},
        {"slug": "extractor", "href": "https://github.com/grahama1970/agent-skills/blob/main/skills/extractor/README.md"},
    ]
    site_projects = [
        {"slug": "tau", "href": "https://github.com/grahama1970/tau"},
        {"slug": "extractor", "href": "https://github.com/grahama1970/extractor"},
        {"slug": "memory", "href": "https://github.com/grahama1970/memory-public"},
    ]

    drift, provenance = module._project_provenance_drift(readme_projects, site_projects)

    assert drift == []
    by_slug = {project["slug"]: project for project in provenance}
    assert by_slug["tau"]["overview_href"] == "https://github.com/grahama1970/tau"
    assert by_slug["tau"]["skill_contract_href"].endswith("/skills/tau/README.md")
    assert by_slug["extractor"]["overview_href"] == "https://github.com/grahama1970/extractor"
    assert by_slug["memory"]["overview_href"] == "https://github.com/grahama1970/memory-public"
    assert by_slug["memory"]["skill_contract_href"].endswith("/skills/memory/SKILL.md")


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


def test_visibility_generator_keeps_configured_overview_when_remote_visibility_unknown(
    tmp_path, monkeypatch
):
    script = REPO / "site/scripts/gen_visibility.py"
    spec = importlib.util.spec_from_file_location("gen_visibility_under_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    site = tmp_path / "site"
    site.mkdir()
    (site / "content.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "slug": "memory",
                        "name": "memory",
                        "href": "https://github.com/grahama1970/private-memory",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (site / "private-abstracts.json").write_text(
        json.dumps({"abstracts": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "CONTENT", site / "content.json")
    monkeypatch.setattr(module, "ABSTRACTS", site / "private-abstracts.json")
    monkeypatch.setattr(module, "OUT", site / "project-visibility.json")
    monkeypatch.setattr(module, "PROJECT_REPO", {"memory": tmp_path / "missing-memory"})
    monkeypatch.setattr(module, "PROJECT_PUBLIC_OVERVIEW", {"memory": "grahama1970/memory-public"})
    monkeypatch.setattr(module, "_remote_visibility", lambda _repo: "UNKNOWN")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: "testsha\n")

    module.main()

    generated = json.loads((site / "project-visibility.json").read_text(encoding="utf-8"))
    [memory] = generated["projects"]
    assert memory["slug"] == "memory"
    assert memory["visibility"] == "public-overview"
    assert memory["evidence_access"] == "abstract"
    assert memory["href"] == "https://github.com/grahama1970/memory-public"
    assert generated["hidden"] == []
