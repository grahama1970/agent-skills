"""Thin Typer commands for source examination, routing, and draft delivery.

JSON inputs are validated before delegation. Failures emit structured Pydantic
steering or a stable hub error code on stderr and exit nonzero.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from hub import HubError, examine, load_request, render, select_route
from hub_models import ErrorCode, Surface, View
from loguru import logger
from pydantic import ValidationError


def emit(action: Callable) -> None:
    try:
        result = action()
        data = (
            result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        )
        typer.echo(json.dumps(data, indent=2, default=str))
    except ValidationError as exc:
        logger.error(
            "Architecture request validation failed: {} error(s)", exc.error_count()
        )
        typer.echo(
            json.dumps(
                {
                    "code": ErrorCode.INVALID_REQUEST,
                    "errors": exc.errors(include_input=False),
                },
                default=str,
            ),
            err=True,
        )
        raise typer.Exit(2) from exc
    except Exception as exc:
        logger.error("Architecture operation failed: {}", exc)
        typer.echo(
            json.dumps(
                {
                    "code": exc.code
                    if isinstance(exc, HubError)
                    else ErrorCode.OPERATION_FAILED,
                    "message": str(exc),
                }
            ),
            err=True,
        )
        raise typer.Exit(1) from exc


def register(app: typer.Typer) -> None:
    @app.command("examine")
    def examine_command(target: Annotated[Path, typer.Argument()] = Path(".")) -> None:
        """Inventory a module/repo for agent source reading; does not invent topology."""
        emit(lambda: examine(target))

    @app.command("route")
    def route_command(
        view: Annotated[View, typer.Option("--view")] = View.STRUCTURE,
        surface: Annotated[Surface, typer.Option("--surface")] = Surface.AUTO,
    ) -> None:
        """Choose a specialist from explicit semantics and delivery constraints."""
        emit(lambda: select_route(view, surface))

    @app.command("render")
    def render_command(
        request: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
        output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
    ) -> None:
        """Render agent-authored native input into an immutable DRAFT bundle."""
        emit(lambda: render(load_request(request), output_dir))
