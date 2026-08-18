"""Typer command tests using real files and the production render/validate pipeline."""

from pathlib import Path

from typer.testing import CliRunner

from readme_svg_animator.cli import app

RUNNER = CliRunner()


def test_new_render_and_validate(tmp_path: Path) -> None:
    scene = tmp_path / "scene.yml"
    svg = tmp_path / "scene.svg"
    receipt = tmp_path / "receipt.json"

    created = RUNNER.invoke(app, ["new", "positive-negative", str(scene)])
    assert created.exit_code == 0, created.output

    rendered = RUNNER.invoke(app, ["render", str(scene), str(svg)])
    assert rendered.exit_code == 0, rendered.output
    assert svg.exists()

    validated = RUNNER.invoke(app, ["validate", str(svg), "--receipt", str(receipt)])
    assert validated.exit_code == 0, validated.output
    assert '"status": "PASS"' in receipt.read_text(encoding="utf-8")


def test_unsafe_cli_returns_nonzero() -> None:
    fixture = Path(__file__).parent / "fixtures" / "unsafe-script.svg"
    result = RUNNER.invoke(app, ["validate", str(fixture)])
    assert result.exit_code == 1
    assert '"status": "FAIL"' in result.output
