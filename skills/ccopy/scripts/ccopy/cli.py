"""Typer CLI for ccopy."""

from __future__ import annotations

import enum
import pathlib
import sys
from typing import Optional

import typer

from ccopy.clipboard import copy_to_clipboard
from ccopy.core import build_last_turn
from ccopy.diagnostics import diagnose_storage, list_conversations, list_workspaces
from ccopy.errors import CursorCopyError
from ccopy.formatters import format_turn
from ccopy.models import SOURCE_SQLITE, SOURCE_TRANSCRIPT
from ccopy.sqlite_backend import discover_workspaces, match_workspace
from ccopy.utils import find_user_dir

app = typer.Typer(
    name="ccopy",
    help="Copy the last complete Cursor user/assistant turn to the clipboard.",
    add_completion=False,
    no_args_is_help=False,
)


class OutputFormat(str, enum.Enum):
    markdown = "markdown"
    plain = "plain"
    json = "json"
    xml = "xml"


class SourceBackend(str, enum.Enum):
    auto = "auto"
    sqlite = SOURCE_SQLITE
    agent_transcript = SOURCE_TRANSCRIPT


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    cursor_user_dir: Optional[pathlib.Path] = typer.Option(None, help="Override Cursor User directory"),
    workspace: Optional[str] = typer.Option(None, help="Workspace hash/path/URI or project slug substring"),
    composer: Optional[str] = typer.Option(None, help="Exact composer/session id"),
    latest: bool = typer.Option(False, help="Use latest conversation globally"),
    fmt: OutputFormat = typer.Option(OutputFormat.markdown, "--format", help="Output format"),
    include_meta: bool = typer.Option(False, "--include-meta", help="Include metadata in output"),
    print_only: bool = typer.Option(False, "--print", help="Print to stdout instead of copying"),
    list_workspaces_flag: bool = typer.Option(False, "--list-workspaces", help="List SQLite workspaces"),
    list_conversations_flag: bool = typer.Option(False, "--list-conversations", help="List conversations"),
    source: SourceBackend = typer.Option(SourceBackend.auto, help="Storage backend"),
    diagnose: bool = typer.Option(False, help="Print storage diagnostics"),
    cwd: Optional[pathlib.Path] = typer.Option(None, hidden=True),
    debug: bool = typer.Option(False, help="Show debug tracebacks"),
) -> None:
    """Copy the last complete user/assistant turn from Cursor chat storage."""
    if ctx.invoked_subcommand is not None:
        return
    work_cwd = cwd or pathlib.Path.cwd()
    try:
        user_dir = find_user_dir(cursor_user_dir)
        if diagnose:
            typer.echo(diagnose_storage(user_dir, work_cwd))
            return
        if list_workspaces_flag:
            typer.echo(list_workspaces(user_dir))
            return

        ws_obj = None
        if not latest:
            workspaces = discover_workspaces(user_dir)
            ws_obj = match_workspace(workspaces, workspace, work_cwd)
        if list_conversations_flag:
            typer.echo(list_conversations(user_dir, ws_obj))
            return

        turn = build_last_turn(
            user_dir=user_dir,
            workspace_selector=workspace,
            composer_id=composer,
            latest_global=latest,
            cwd=work_cwd,
            source=source.value,
        )
        text = format_turn(turn, fmt.value, include_meta=include_meta)
        if print_only:
            typer.echo(text, nl=not text.endswith("\n"))
            return
        tool = copy_to_clipboard(text)
        via = turn.source
        if turn.transcript_path:
            via = f"{turn.source} ({turn.transcript_path})"
        typer.echo(
            f"Copied Cursor last turn from {turn.conversation_name or turn.composer_id} "
            f"via {via} ({len(text)} chars) using {tool}."
        )
    except typer.Exit as exc:
        raise SystemExit(exc.exit_code) from exc
    except CursorCopyError as exc:
        typer.echo(f"ccopy: {exc}", err=True)
        raise SystemExit(2) from exc
    except Exception as exc:
        if debug:
            raise
        typer.echo(f"ccopy: unexpected error: {exc}", err=True)
        raise SystemExit(1) from exc


def run(argv: Optional[list[str]] = None) -> int:
    """Programmatic entry for tests and wrappers."""
    try:
        app(argv or sys.argv[1:])
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
