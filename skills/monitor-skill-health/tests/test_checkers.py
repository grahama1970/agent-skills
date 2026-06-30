from pathlib import Path
import importlib.util
import sys


def load_checkers_module():
    module_path = Path(__file__).resolve().parents[1] / "checkers.py"
    skill_dir = str(module_path.parent)
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    spec = importlib.util.spec_from_file_location("monitor_skill_health_checkers", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_python_violations_accepts_shebang_before_module_docstring(tmp_path):
    checkers = load_checkers_module()
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    script = skill_dir / "run_tool.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Tool entrypoint.\"\"\"\n"
        "\n"
        "print('ok')\n",
        encoding="utf-8",
    )

    violations = checkers.python_violations(skill_dir, [script])

    assert not [
        violation
        for violation in violations
        if violation["rule"] == "style-module-docstring"
    ]


def test_python_violations_flags_missing_module_docstring(tmp_path):
    checkers = load_checkers_module()
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    script = skill_dir / "run_tool.py"
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    violations = checkers.python_violations(skill_dir, [script])

    assert [
        violation
        for violation in violations
        if violation["rule"] == "style-module-docstring"
    ]


def test_agent_violations_require_operational_frontmatter(tmp_path):
    checkers = load_checkers_module()
    agent_dir = tmp_path / "sample-agent"
    agent_dir.mkdir()
    (agent_dir / "AGENTS.md").write_text(
        "---\n"
        "id: sample-agent\n"
        "kind: worker\n"
        "---\n"
        "\n"
        "# Sample Agent\n",
        encoding="utf-8",
    )

    violations = checkers.agent_violations(agent_dir)

    missing = {violation["message"] for violation in violations}
    assert "Agent frontmatter is missing required key: title." in missing
    assert "Agent frontmatter is missing required key: mode." in missing
    assert "Agent frontmatter is missing required key: composes." in missing


def test_agent_violations_accept_complete_contract(tmp_path):
    checkers = load_checkers_module()
    agent_dir = tmp_path / "sample-agent"
    agent_dir.mkdir()
    (agent_dir / "AGENTS.md").write_text(
        "---\n"
        "id: sample-agent\n"
        "kind: worker\n"
        "title: Sample Agent\n"
        "mode: workspace_write\n"
        "composes:\n"
        "- memory\n"
        "---\n"
        "\n"
        "# Sample Agent\n",
        encoding="utf-8",
    )

    assert checkers.agent_violations(agent_dir) == []


def test_discover_agents_reads_agents_root(tmp_path, monkeypatch):
    checkers = load_checkers_module()
    agents_root = tmp_path / "agents"
    (agents_root / "worker-a").mkdir(parents=True)
    (agents_root / "worker-a" / "AGENTS.md").write_text("# Worker A\n", encoding="utf-8")
    (agents_root / "tests").mkdir()
    (agents_root / "tests" / "AGENTS.md").write_text("# Ignored\n", encoding="utf-8")
    monkeypatch.setattr(checkers, "AGENTS_ROOT", agents_root)

    assert [path.name for path in checkers.discover_agents()] == ["worker-a"]


def test_readme_allowed_when_skill_declares_provides(tmp_path):
    checkers = load_checkers_module()
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: sample-skill\n"
        "description: >\n"
        "  Sample skill.\n"
        "provides:\n"
        "- sample-capability\n"
        "composes: []\n"
        "---\n"
        "\n"
        "# Sample Skill\n",
        encoding="utf-8",
    )
    (skill_dir / "README.md").write_text("# Human docs\n", encoding="utf-8")

    violations = checkers.skills_violations(skill_dir)

    assert not [
        violation
        for violation in violations
        if violation["rule"] == "avoid-extra-docs" and violation["file"] == "README.md"
    ]


def test_readme_flagged_without_provides(tmp_path):
    checkers = load_checkers_module()
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: sample-skill\n"
        "description: >\n"
        "  Sample skill.\n"
        "composes: []\n"
        "---\n"
        "\n"
        "# Sample Skill\n",
        encoding="utf-8",
    )
    (skill_dir / "README.md").write_text("# Human docs\n", encoding="utf-8")

    violations = checkers.skills_violations(skill_dir)

    assert [
        violation
        for violation in violations
        if violation["rule"] == "avoid-extra-docs" and violation["file"] == "README.md"
    ]
