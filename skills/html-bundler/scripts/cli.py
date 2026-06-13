#!/usr/bin/env python3
"""Typer CLI for html-bundler."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from capture_lib import CaptureOptions, run_capture

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Capture and zip a local webpage for WebGPT analysis.",
)


@app.command()
def capture(
    html: Path | None = typer.Option(None, "--html", help="Local HTML file to serve and package."),
    url: str | None = typer.Option(None, "--url", help="Already-running URL, e.g. http://localhost:3000."),
    root: Path | None = typer.Option(None, "--root", help="Site root for local assets."),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Output zip path. Default: /tmp/html-bundler-<timestamp>.zip",
    ),
    surf_bin: str = typer.Option("surf", "--surf-bin", help="Path to skills/surf/run.sh"),
    fetcher_bin: str = typer.Option("", "--fetcher-bin", help="Path to skills/fetcher/run.sh for source fallback."),
    desktop: str = typer.Option("1440x1000", "--desktop", help="Desktop viewport, e.g. 1440x1000."),
    mobile: str = typer.Option("390x844", "--mobile", help="Mobile viewport, e.g. 390x844."),
    no_mobile: bool = typer.Option(False, "--no-mobile", help="Skip mobile viewport capture."),
    wait_ms: int = typer.Option(1500, "--wait-ms", help="Extra wait after load before capture."),
    keep_workdir: bool = typer.Option(False, "--keep-workdir", help="Keep temp work directory."),
    no_source: bool = typer.Option(False, "--no-source", help="Skip copying local source/assets."),
    source_entry: Path | None = typer.Option(
        None,
        "--source-entry",
        help="HTML entry file under --root when capturing a dev-server --url.",
    ),
    max_scroll_slices: int = typer.Option(12, "--max-scroll-slices", help="Max viewport scroll slices per form factor."),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip same-origin source fetch for --url captures."),
    fetch_backend: str = typer.Option("auto", "--fetch-backend", help="Source backend: auto, urllib, or fetcher."),
) -> None:
    """Render a page through /surf and write an upload-ready zip under /tmp by default."""
    if html is None and url is None:
        typer.echo("error: provide --html or --url", err=True)
        raise typer.Exit(2)

    options = CaptureOptions(
        html=html,
        url=url,
        root=root,
        out=out,
        surf_bin=surf_bin,
        desktop=desktop,
        mobile=mobile,
        no_mobile=no_mobile,
        wait_ms=wait_ms,
        keep_workdir=keep_workdir,
        no_source=no_source,
        source_entry=source_entry,
        max_scroll_slices=max_scroll_slices,
        no_fetch=no_fetch,
        fetcher_bin=fetcher_bin,
        fetch_backend=fetch_backend,
    )
    zip_path = run_capture(options)
    typer.echo(str(zip_path))


if __name__ == "__main__":
    app()
