#!/usr/bin/env python3
"""Read-only Gmail access through the authenticated Chrome tab via $surf.

READ-ONLY surface. Commands:
  tabs   - find the Gmail tab id
  inbox  - snapshot the visible inbox rows (from, subject, time)
  read   - extract the newest thread body text matching a keyword
Proven live 2026-09-11 (GoDaddy code hunt + Moog bounce diagnosis).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer

SURF = Path(__file__).resolve().parents[2] / "surf" / "run.sh"
app = typer.Typer(help=__doc__)

ROWS_JS = """(() => JSON.stringify(
  Array.from(document.querySelectorAll('tr, [role=row]'))
    .map(r => (r.innerText||'').replace(/\\s+/g,' ').trim())
    .filter(t => t.length > 15 && /\\bAM\\b|\\bPM\\b/.test(t))
    .slice(0, 25)))()"""


def _surf(*args: str) -> str:
    out = subprocess.run(["bash", str(SURF), *args], capture_output=True, text=True, timeout=90)
    if out.returncode != 0 and not out.stdout.strip().startswith(('"', '[')):
        typer.echo(json.dumps({"ok": False, "error": (out.stderr or out.stdout)[:200]}))
        raise typer.Exit(code=1)
    return out.stdout.strip()


def _find_tab() -> str:
    listing = _surf("tab.list", "--json")
    data = json.loads(listing)
    tabs = data if isinstance(data, list) else (data.get("tabs") or [])
    for t in tabs:
        if "mail.google.com" in (t.get("url") or ""):
            return str(t.get("id"))
    typer.echo(json.dumps({"ok": False, "error_type": "gmail_tab_not_found",
                           "fix": "open Gmail in Chrome, then rerun"}))
    raise typer.Exit(code=2)


def tabs() -> None:
    """Print the Gmail tab id."""
    typer.echo(json.dumps({"tab_id": _find_tab()}))


def inbox(limit: int = typer.Option(25)) -> None:
    """Snapshot visible inbox rows."""
    tab = _find_tab()
    raw = _surf("js", "--tab-id", tab, "--code", ROWS_JS)
    rows = json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw)
    typer.echo(json.dumps({"schema": "gmail.inbox_snapshot.v1", "count": len(rows[:limit]), "rows": rows[:limit]}, indent=2))


def read(keyword: str = typer.Option(..., help="keyword to find the thread, e.g. godaddy")) -> None:
    """Click the newest row matching keyword and extract its body text."""
    tab = _find_tab()
    raw = _surf("js", "--tab-id", tab, "--code", ROWS_JS)
    rows = json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw)
    match = next((r for r in rows if keyword.lower() in r.lower()), None)
    if not match:
        typer.echo(json.dumps({"ok": False, "error_type": "thread_not_found", "keyword": keyword}))
        raise typer.Exit(code=3)
    click = _surf("js", "--tab-id", tab, "--code",
                  f"(() => {{ const row = Array.from(document.querySelectorAll('tr,[role=row]')).find(r => (r.innerText||'').includes({json.dumps(keyword)})); if (row) {{ row.click(); return 'opened'; }} return 'not found'; }})()")
    body = _surf("js", "--tab-id", tab, "--code",
                 "(() => JSON.stringify((document.querySelector('[role=main]')||document.body).innerText.replace(/\\s+/g,' ').slice(0,3000)))()")
    text = json.loads(json.loads(body)) if body.startswith('"') else body
    typer.echo(json.dumps({"schema": "gmail.thread_read.v1", "keyword": keyword, "row": match[:120], "body": text[:2000]}, indent=2))


for c in (tabs, inbox, read):
    app.command()(c)

if __name__ == "__main__":
    app()
