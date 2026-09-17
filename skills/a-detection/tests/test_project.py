"""Local structural guards; these do not impersonate the owning native skill validators."""
import ast
import json
from pathlib import Path

import yaml

from a_detection.contracts import Policy

ROOT = Path(__file__).resolve().parents[1]


def test_python_runtime_has_docstrings_bounded_modules_and_no_dynamic_execution():
    for path in (ROOT / "src/a_detection").rglob("*.py"):
        source = path.read_text()
        assert len(source.splitlines()) <= 800, path
        tree = ast.parse(source)
        assert ast.get_docstring(tree), path
        for node in ast.walk(tree):
            assert not isinstance(node, ast.Assert), path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec"}, path
            if isinstance(node, ast.Import):
                assert all(x.name.split(".")[0] not in {"pickle", "marshal", "requests"} for x in node.names)


def test_policy_spec_is_the_packaged_policy():
    spec = Policy.model_validate_json((ROOT / "specs/policy.json").read_text())
    packed = Policy.model_validate_json((ROOT / "src/a_detection/resources/policy.json").read_text())
    assert spec == packed


def test_retained_fixtures_have_three_trials_majority_negative_and_domain_claims():
    for name in ("agentic_eval.json", "mechanisms.json"):
        payload = json.loads((ROOT / "fixtures" / name).read_text())
        assert payload["trials"] >= 3
        assert payload["eval_tier"] == "compliance"
        cases = payload["cases"]
        assert sum(x["type"] in {"negative", "adversarial"} for x in cases) > len(cases) / 2
        assert any(x.get("real_world") for x in cases)
        assert any(x["evidence_class"] == "property_or_fuzz" for x in cases)
        assert all(x.get("supports_claims") and x.get("expected") for x in cases)
    full = json.loads((ROOT / "fixtures/agentic_eval.json").read_text())
    claim = next(x for x in full["capability_claims"] if x["id"] == "provider-agnostic-detection")
    assert claim["criticality"] == "critical"
    assert claim["evidence_required"]["human_evaluation"] is True


def test_native_setup_keeps_contract_gate_and_skill_composition():
    config = yaml.safe_load((ROOT / "setup-project.yaml").read_text())
    assert config["client_contract_gate"] == "required"
    for name in config["required_files"]:
        assert (ROOT / name).is_file(), name
    skill = ROOT / "SKILL.md"
    text = skill.read_text()
    assert text.startswith("---\n")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter["name"] == "a-detection"
    assert "agentic-evals" in frontmatter["composes"]
    assert "best-practices-python" in frontmatter["complies"]
    assert frontmatter["triggers"] and frontmatter["provides"]
