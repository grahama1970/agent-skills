"""`ask api` — the local API transports (#1406).

    ./run.sh api stdio
    ./run.sh api serve --socket "$XDG_RUNTIME_DIR/ask/ask.sock"

Both transports share one dispatcher; no TCP listener exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from .local_api import LocalApi, serve_socket, serve_stdio

app = typer.Typer(help="Local Ask API (stdio or Unix socket).", no_args_is_help=True)


@app.command("stdio")
def stdio_command() -> None:
    """One JSON request per line on stdin; one response per line on stdout."""
    raise typer.Exit(serve_stdio(LocalApi()))


@app.command("serve")
def serve_command(
    socket_path: Annotated[str, typer.Option("--socket", help="Unix socket path.")] = "",
    max_connections: Annotated[int, typer.Option("--max-connections", help="0 serves forever.")] = 0,
) -> None:
    """Serve on an owner-only Unix socket."""
    default = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ask" / "ask.sock"
    raise typer.Exit(serve_socket(Path(socket_path or default), LocalApi(), max_connections=max_connections))


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
