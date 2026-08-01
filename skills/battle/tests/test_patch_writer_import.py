from __future__ import annotations

from pathlib import Path


def test_patch_writer_imports_from_package_path() -> None:
    from battle_skill.patch_writer import write_patch

    assert callable(write_patch)


def test_root_has_no_python_shim() -> None:
    skill_root = Path(__file__).resolve().parents[1]

    assert sorted(path.name for path in skill_root.glob("*.py")) == []
