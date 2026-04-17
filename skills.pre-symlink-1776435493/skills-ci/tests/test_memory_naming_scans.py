"""Tests for scan_memory_integration() and scan_naming_convention()."""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skills_ci", ROOT / "skills_ci.py")
skills_ci = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["skills_ci"] = skills_ci
spec.loader.exec_module(skills_ci)


# ---------------------------------------------------------------------------
# scan_memory_integration tests
# ---------------------------------------------------------------------------

def test_valid_memory_integration_zero_violations(tmp_path: Path):
    """A well-formed memory_integration.py should produce 0 violations."""
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\n")
    mi = skill / "memory_integration.py"
    mi.write_text(
        '_HAS_MEMORY = False\n'
        'try:\n'
        '    from common.memory_client import MemoryClient\n'
        '    _HAS_MEMORY = True\n'
        'except ImportError:\n'
        '    pass\n'
        '_BRIDGE_KEYWORDS = {"Precision": ["accurate"]}\n'
        'def extract_bridges(text): return []\n'
        'def recall_prior(k=3): return ""\n'
        'def learn_result(): return []\n'
    )
    violations = skills_ci.scan_memory_integration(skill)
    assert len(violations) == 0


def test_missing_has_memory_flag(tmp_path: Path):
    """memory_integration.py without _HAS_MEMORY should emit 1 violation."""
    skill = tmp_path / "bad-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: bad-skill\ndescription: test\n---\n")
    mi = skill / "memory_integration.py"
    mi.write_text(
        'try:\n'
        '    from common.memory_client import MemoryClient\n'
        'except ImportError:\n'
        '    pass\n'
        '_BRIDGE_KEYWORDS = {"Precision": ["accurate"]}\n'
        'def extract_bridges(text): return []\n'
        'def recall_prior(k=3): return ""\n'
        'def learn_result(): return []\n'
    )
    violations = skills_ci.scan_memory_integration(skill)
    rules = [v.rule for v in violations]
    assert "memory.missing_has_memory_flag" in rules
    assert len(violations) == 1


def test_common_discovery_import_recognized(tmp_path: Path):
    """Skills importing from common.discovery should skip memory validation."""
    skill = tmp_path / "discover-things"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: discover-things\ndescription: test\n---\n")
    cli = skill / "cli.py"
    cli.write_text('from common.discovery import gather_context\n')
    # No memory_integration.py at all
    violations = skills_ci.scan_memory_integration(skill)
    assert len(violations) == 0


def test_no_violation_for_opt_in_absence(tmp_path: Path):
    """Skills without memory_integration.py should produce 0 violations."""
    skill = tmp_path / "simple-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: simple-skill\ndescription: test\n---\n")
    (skill / "main.py").write_text('print("hello")\n')
    violations = skills_ci.scan_memory_integration(skill)
    assert len(violations) == 0


# ---------------------------------------------------------------------------
# scan_naming_convention tests
# ---------------------------------------------------------------------------

def test_noun_only_name_warned(tmp_path: Path):
    """A noun-only skill name not in allowlist should emit warning."""
    skill = tmp_path / "frobnicator"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: frobnicator\ndescription: test\n---\n")
    violations = skills_ci.scan_naming_convention(skill)
    assert len(violations) == 1
    assert violations[0].rule == "naming.noun_only"
    assert violations[0].severity == "warn"


def test_allowlisted_name_passes(tmp_path: Path):
    """A noun-only skill name on the allowlist should produce 0 violations."""
    skill = tmp_path / "memory"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: memory\ndescription: test\n---\n")
    violations = skills_ci.scan_naming_convention(skill)
    assert len(violations) == 0
