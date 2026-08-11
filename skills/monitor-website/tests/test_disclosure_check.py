from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills/monitor-website/scripts/disclosure_check.py"


def load_module():
    spec = importlib.util.spec_from_file_location("disclosure_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fixture(tmp_path: Path, *, mutate=None) -> Path:
    site = tmp_path / "site"
    app = site / "app"
    app.mkdir(parents=True)
    (app / "ledger").mkdir()
    (app / "how-proof-works").mkdir()
    (app / "explore").mkdir()
    (site / "inventory.json").write_text("{}", encoding="utf-8")
    (site / "artifacts.json").write_text("{}", encoding="utf-8")
    (site / "research-map.json").write_text("{}", encoding="utf-8")
    (site / "content.json").write_text("{}", encoding="utf-8")
    page = """
      <section id="top">I build agent systems that can prove what they did.</section>
      <section id="search"></section>
      <section id="ledger"></section>
      <section id="proof"></section>
      <section id="contact"><a data-qid="contact:action:email">Describe the problem</a></section>
    """
    (app / "page.tsx").write_text(page, encoding="utf-8")
    (app / "ledger" / "page.tsx").write_text("<main id=\"top\">ledger</main>", encoding="utf-8")
    (app / "how-proof-works" / "page.tsx").write_text("<main id=\"top\">proof</main>", encoding="utf-8")
    (app / "explore" / "page.tsx").write_text("<main id=\"top\">explore</main>", encoding="utf-8")

    contract = {
        "schema": "grahama.disclosure_map.v1",
        "version": 1,
        "tiers": ["default", "preview", "depth", "raw"],
        "visitor_jobs": ["buyer", "hiring-manager", "technical-inspector", "contract-inspector"],
        "initial_html": {
            "required_text": ["I build agent systems that can", "Describe the problem"],
            "required_qids": ["contact:action:email"],
        },
        "route_policy": {"max_nested_in_place_disclosures": 1},
        "homepage_depth_exclusions": [
            {"surface_id": "complete_contract_ledger", "tokens": ["SkillMosaic"], "reason": "depth only"}
        ],
        "surfaces": [
            {
                "surface_id": "hero",
                "route": "/",
                "fragment": "top",
                "source": "site/app/page.tsx",
                "tier": "default",
                "visitor_job": "buyer",
                "visible_claim": "proposition",
                "evidence_access": "none",
                "initial_html": "required",
                "lazy_load": False,
                "explicit_user_intent_required": False,
                "keyboard_equivalent": "tab",
                "no_javascript_equivalent": "text",
                "mobile_equivalent": "same",
                "human_approved_version": 1,
            },
            {
                "surface_id": "ledger_preview",
                "route": "/",
                "fragment": "ledger",
                "source": "site/app/page.tsx",
                "tier": "preview",
                "visitor_job": "contract-inspector",
                "visible_claim": "inventory preview",
                "evidence_access": "generated-source",
                "proof_boundary": "counts only",
                "inspect_target": "/ledger",
                "raw_target": "site/inventory.json",
                "initial_html": "optional",
                "lazy_load": True,
                "explicit_user_intent_required": True,
                "keyboard_equivalent": "link",
                "no_javascript_equivalent": "route",
                "mobile_equivalent": "same",
                "human_approved_version": 1,
            },
            {
                "surface_id": "ledger_depth",
                "route": "/ledger",
                "source": "site/app/ledger/page.tsx",
                "tier": "depth",
                "visitor_job": "contract-inspector",
                "visible_claim": "full inventory",
                "evidence_access": "generated-source",
                "proof_boundary": "counts only",
                "raw_target": "site/inventory.json",
                "initial_html": "direct-route",
                "lazy_load": False,
                "explicit_user_intent_required": True,
                "keyboard_equivalent": "url",
                "no_javascript_equivalent": "route",
                "mobile_equivalent": "same",
                "human_approved_version": 1,
            },
        ],
    }
    if mutate:
        mutate(contract, app / "page.tsx")
    (site / "disclosure-map.yml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    return tmp_path


def test_valid_canary_fixture_passes(tmp_path):
    module = load_module()
    repo = write_fixture(tmp_path)

    result = module.run_check(repo, canary=True)

    assert result["status"] == "PASS"
    assert result["counts"]["surfaces"] == 3


def test_missing_depth_target_fails(tmp_path):
    module = load_module()

    def mutate(contract, _page):
        contract["surfaces"][1]["inspect_target"] = "/missing-route"

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "route_not_directly_reloadable" for f in result["failures"])


def test_preview_stronger_than_source_missing_boundary_fails(tmp_path):
    module = load_module()

    def mutate(contract, _page):
        contract["surfaces"][1].pop("proof_boundary")

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "evidence_claim_missing_boundary" for f in result["failures"])


def test_hidden_primary_cta_fails(tmp_path):
    module = load_module()

    def mutate(_contract, page):
        page.write_text('<section id="top">I build agent systems that can</section>', encoding="utf-8")

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo, canary=True)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "initial_html_required_text_missing" for f in result["failures"])
    assert any(f["code"] == "initial_html_required_qid_missing" for f in result["failures"])


def test_full_ledger_reintroduced_to_homepage_fails(tmp_path):
    module = load_module()

    def mutate(_contract, page):
        page.write_text(page.read_text(encoding="utf-8") + "\n<SkillMosaic />", encoding="utf-8")

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "depth_module_in_homepage" for f in result["failures"])


def test_javascript_only_depth_fails(tmp_path):
    module = load_module()

    def mutate(contract, _page):
        contract["surfaces"][1]["no_javascript_equivalent"] = ""

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "missing_no_javascript_equivalent" for f in result["failures"])


def test_two_nested_disclosures_before_evidence_fails(tmp_path):
    module = load_module()

    def mutate(_contract, page):
        page.write_text(page.read_text(encoding="utf-8") + "\n<details><details>evidence</details></details>", encoding="utf-8")

    repo = write_fixture(tmp_path, mutate=mutate)
    result = module.run_check(repo)

    assert result["status"] == "FAIL"
    assert any(f["code"] == "too_many_in_place_disclosures" for f in result["failures"])
