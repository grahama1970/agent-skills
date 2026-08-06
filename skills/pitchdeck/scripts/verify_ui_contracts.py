"""Static write-time contract check for ui/src (best-practices-react).

Every element wiring an onClick must also carry data-qid, data-qs-action, and
title. This is a static approximation; the authoritative check is the live-DOM
query (surf js: document.querySelectorAll('[data-qid]')) recorded in sanity or
a /test-interactions manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


@app.command()
def check(
    ui_src: Path = typer.Argument(help="Path to ui/src directory."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Fail if any TSX file wires onClick handlers without the full interaction contract."""
    issues: list[dict[str, object]] = []
    files = sorted(ui_src.rglob("*.tsx"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        clicks = text.count("onClick={")
        if not clicks:
            continue
        for attr in ("data-qid", "data-qs-action", "title"):
            found = text.count(f"{attr}=")
            if found < clicks:
                issues.append(
                    {
                        "file": str(path),
                        "onClick_count": clicks,
                        "attribute": attr,
                        "attribute_count": found,
                        "message": f"{path.name}: {clicks} onClick handlers but only {found} {attr} attributes",
                    }
                )
    result = {"files_checked": len(files), "issues": issues, "passed": not issues}
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        for issue in issues:
            typer.echo(f"FAIL {issue['message']}")
        typer.echo(f"{'PASS' if result['passed'] else 'FAIL'}: {len(files)} tsx files checked")
    if issues:
        sys.exit(1)


if __name__ == "__main__":
    app()
