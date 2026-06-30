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
