"""Sanity tests for create-architecture-diagram.

RECONSTRUCTED 2026-08-12 from the surviving pytest-compiled bytecode
(test_sanity.cpython-312-pytest-8.3.5.pyc) after the .py source was lost. This
test module is the ONLY surviving source for this skill; SKILL.md, run.sh, and
the diagram-generation logic it references were not tracked anywhere (absent
from all git refs, the working tree, and origin/main) and could not be
recovered. The pytest assertion-rewrite artifacts have been de-rewritten back to
plain asserts. Now TRACKED.
"""
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent


def test_skill_md_exists():
    assert (SKILL_DIR / "SKILL.md").exists()


def test_run_sh_exists():
    assert (SKILL_DIR / "run.sh").exists()


def test_run_sh_executable():
    run_sh = SKILL_DIR / "run.sh"
    assert run_sh.stat().st_mode & 0o111, "run.sh is not executable"
