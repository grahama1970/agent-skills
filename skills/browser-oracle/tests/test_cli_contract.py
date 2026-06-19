import json
from pathlib import Path

from typer.testing import CliRunner

from browser_oracle.cli import app


def test_resolve_missing_binding_is_needs_attention(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "resolve",
            "--from",
            str(tmp_path),
            "--project",
            "missing-project",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_attention"
    assert payload["reason"] == "binding_missing"
    assert payload["tab_id"] is None
