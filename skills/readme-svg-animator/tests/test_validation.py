"""Positive and negative structural SVG validation tests without mocks."""

from readme_svg_animator.io import load_scene, load_theme, skill_root
from readme_svg_animator.render import render_scene
from readme_svg_animator.validate import validate_svg_text


def test_generated_svg_passes_strict_theme() -> None:
    root = skill_root()
    scene = load_scene(root / "assets" / "templates" / "positive-negative.yml")
    theme = load_theme(scene.theme)
    receipt = validate_svg_text(
        render_scene(scene, theme),
        "generated.svg",
        theme=theme,
        strict_theme=True,
    )
    assert receipt.status == "PASS"
    assert receipt.findings == ()


def test_script_bearing_svg_fails_closed() -> None:
    unsafe = (skill_root() / "tests" / "fixtures" / "unsafe-script.svg").read_text(encoding="utf-8")
    receipt = validate_svg_text(unsafe, "unsafe.svg")
    assert receipt.status == "FAIL"
    assert any(finding.code == "ACTIVE_TAG" for finding in receipt.findings)
