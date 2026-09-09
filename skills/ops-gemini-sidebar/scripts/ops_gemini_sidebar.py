#!/usr/bin/env python3
"""Operate Chrome's Gemini sidebar through typed OS-level clipboard receipts.

Inputs: coordinate plans, prompt files, optional DISPLAY override.
Outputs: JSON receipts for dry-run/live submit and copy-response steps.
Failure modes: missing desktop display, missing xdotool/xclip, absent files, or
subprocess failures are reported as typed receipts instead of silent guesses.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

app = typer.Typer(add_completion=False, no_args_is_help=True)


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class CoordinatePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["ops_gemini_sidebar.coordinate_plan.v1"] = Field(
        default="ops_gemini_sidebar.coordinate_plan.v1",
        alias="schema",
    )
    window_title: str = Field(default="Explain Project Cockpit", min_length=1)
    composer: Point
    send: Point | None = None
    copy_button: Point | None = Field(default=None, alias="copy")
    display: str | None = None
    note: str = "Coordinates are screen-space unless your window manager command supplies relative coordinates."


class CommandReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["ops_gemini_sidebar.command_receipt.v1"] = Field(
        default="ops_gemini_sidebar.command_receipt.v1",
        alias="schema",
    )
    command: str
    status: Literal["PASS", "DRY_RUN", "FAILED"]
    executed: bool
    created_at: str
    plan: CoordinatePlan | None = None
    output_path: str | None = None
    clipboard_chars: int | None = None
    errors: list[dict] = Field(default_factory=list)
    next_step: str | None = None


def now() -> str:
    return datetime.now(UTC).isoformat()


def emit(receipt: CommandReceipt, json_output: bool) -> None:
    data = receipt.model_dump(mode="json", by_alias=True)
    if json_output:
        print(json.dumps(data, indent=2))
    else:
        print(json.dumps(data))


def fail(command: str, errors: list[dict], json_output: bool, plan: CoordinatePlan | None = None) -> None:
    emit(
        CommandReceipt(
            command=command,
            status="FAILED",
            executed=False,
            created_at=now(),
            plan=plan,
            errors=errors,
        ),
        json_output,
    )
    raise typer.Exit(2)


def load_plan(path: Path) -> CoordinatePlan:
    try:
        return CoordinatePlan.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise typer.BadParameter(json.dumps(exc.errors(), indent=2)) from exc


def require_tool(name: str) -> dict | None:
    if shutil.which(name):
        return None
    return {"type": "missing_tool", "loc": [name], "msg": f"{name} not found on PATH", "ctx": {"tool": name}}


def desktop_env(plan: CoordinatePlan, display: str | None) -> dict[str, str]:
    env = os.environ.copy()
    chosen = display or plan.display or env.get("DISPLAY")
    if chosen:
        env["DISPLAY"] = chosen
    return env


def run_checked(argv: list[str], env: dict[str, str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    logger.info("running {}", argv[0])
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout, env=env)


def set_clipboard(text: str, env: dict[str, str]) -> None:
    logger.info("setting clipboard")
    proc = subprocess.Popen(
        ["xclip", "-selection", "clipboard", "-i"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if proc.stdin is None:
        raise RuntimeError("xclip stdin pipe was not opened")
    proc.stdin.write(text)
    proc.stdin.close()


def preflight(plan: CoordinatePlan, display: str | None) -> list[dict]:
    errors = [err for tool in ("xdotool", "xclip") if (err := require_tool(tool))]
    env = desktop_env(plan, display)
    if not env.get("DISPLAY"):
        errors.append({
            "type": "missing_display",
            "loc": ["DISPLAY"],
            "msg": "desktop DISPLAY is absent; pass --display or run inside the desktop session",
            "ctx": {"example": "--display :0"},
        })
    return errors


@app.command()
def plan(
    composer_x: Annotated[int, typer.Option()],
    composer_y: Annotated[int, typer.Option()],
    send_x: Annotated[int | None, typer.Option()] = None,
    send_y: Annotated[int | None, typer.Option()] = None,
    copy_x: Annotated[int | None, typer.Option()] = None,
    copy_y: Annotated[int | None, typer.Option()] = None,
    window_title: Annotated[str, typer.Option()] = "Explain Project Cockpit",
    display: Annotated[str | None, typer.Option()] = None,
    out: Annotated[Path | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Write or print a typed coordinate plan."""
    if (send_x is None) != (send_y is None):
        raise typer.BadParameter("send-x and send-y must be supplied together")
    if (copy_x is None) != (copy_y is None):
        raise typer.BadParameter("copy-x and copy-y must be supplied together")
    coord_plan = CoordinatePlan(
        window_title=window_title,
        composer=Point(x=composer_x, y=composer_y),
        send=Point(x=send_x, y=send_y) if send_x is not None and send_y is not None else None,
        copy=Point(x=copy_x, y=copy_y) if copy_x is not None and copy_y is not None else None,
        display=display,
    )
    text = coord_plan.model_dump_json(indent=2, by_alias=True)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
    print(text if json_output or not out else str(out))


@app.command()
def submit(
    prompt_file: Annotated[Path, typer.Option()],
    coords: Annotated[Path, typer.Option()],
    execute: Annotated[bool, typer.Option("--execute")] = False,
    display: Annotated[str | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Paste a prompt into the Gemini sidebar composer and optionally click send."""
    plan_obj = load_plan(coords)
    if not prompt_file.exists():
        fail("submit", [{"type": "missing_prompt_file", "loc": [str(prompt_file)], "msg": "prompt file does not exist", "ctx": {}}], json_output, plan_obj)
    if not execute:
        emit(CommandReceipt(command="submit", status="DRY_RUN", executed=False, created_at=now(), plan=plan_obj, next_step="rerun with --execute after screenshot calibration"), json_output)
        return
    errors = preflight(plan_obj, display)
    if errors:
        fail("submit", errors, json_output, plan_obj)
    env = desktop_env(plan_obj, display)
    try:
        set_clipboard(prompt_file.read_text(encoding="utf-8"), env)
        run_checked(["xdotool", "search", "--name", plan_obj.window_title, "windowactivate", "%@"], env)
        run_checked(["xdotool", "mousemove", str(plan_obj.composer.x), str(plan_obj.composer.y)], env)
        run_checked(["xdotool", "click", "1"], env)
        run_checked(["xdotool", "key", "ctrl+a"], env)
        run_checked(["xdotool", "key", "BackSpace"], env)
        run_checked(["xdotool", "key", "ctrl+v"], env)
        if plan_obj.send:
            run_checked(["xdotool", "mousemove", str(plan_obj.send.x), str(plan_obj.send.y)], env)
            run_checked(["xdotool", "click", "1"], env)
        run_checked(["xdotool", "key", "ctrl+Return"], env)
    except subprocess.CalledProcessError as exc:
        fail("submit", [{"type": "desktop_command_failed", "loc": exc.cmd, "msg": exc.stderr or exc.stdout or str(exc), "ctx": {"returncode": exc.returncode}}], json_output, plan_obj)
    except subprocess.TimeoutExpired as exc:
        fail("submit", [{"type": "desktop_command_timeout", "loc": exc.cmd, "msg": str(exc), "ctx": {"timeout": exc.timeout}}], json_output, plan_obj)
    emit(CommandReceipt(command="submit", status="PASS", executed=True, created_at=now(), plan=plan_obj, clipboard_chars=len(prompt_file.read_text(encoding="utf-8"))), json_output)


@app.command("copy-response")
def copy_response(
    coords: Annotated[Path, typer.Option()],
    out: Annotated[Path, typer.Option()],
    execute: Annotated[bool, typer.Option("--execute")] = False,
    display: Annotated[str | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Click Gemini's copy control and read clipboard back to a file."""
    plan_obj = load_plan(coords)
    if plan_obj.copy_button is None:
        fail("copy-response", [{"type": "missing_copy_coordinates", "loc": ["copy"], "msg": "coordinate plan has no copy point", "ctx": {}}], json_output, plan_obj)
    if not execute:
        emit(CommandReceipt(command="copy-response", status="DRY_RUN", executed=False, created_at=now(), plan=plan_obj, output_path=str(out), next_step="rerun with --execute after a fresh post-response screenshot"), json_output)
        return
    errors = preflight(plan_obj, display)
    if errors:
        fail("copy-response", errors, json_output, plan_obj)
    env = desktop_env(plan_obj, display)
    try:
        run_checked(["xdotool", "search", "--name", plan_obj.window_title, "windowactivate", "%@"], env)
        run_checked(["xdotool", "mousemove", str(plan_obj.copy_button.x), str(plan_obj.copy_button.y)], env)
        run_checked(["xdotool", "click", "1"], env)
        result = run_checked(["xclip", "-selection", "clipboard", "-o"], env)
    except subprocess.CalledProcessError as exc:
        fail("copy-response", [{"type": "desktop_command_failed", "loc": exc.cmd, "msg": exc.stderr or exc.stdout or str(exc), "ctx": {"returncode": exc.returncode}}], json_output, plan_obj)
    except subprocess.TimeoutExpired as exc:
        fail("copy-response", [{"type": "desktop_command_timeout", "loc": exc.cmd, "msg": str(exc), "ctx": {"timeout": exc.timeout}}], json_output, plan_obj)
    out.write_text(result.stdout, encoding="utf-8")
    emit(CommandReceipt(command="copy-response", status="PASS", executed=True, created_at=now(), plan=plan_obj, output_path=str(out), clipboard_chars=len(result.stdout)), json_output)


@app.command("self-test")
def self_test(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Run deterministic schema and dry-run checks without touching the desktop."""
    coord_plan = CoordinatePlan(composer=Point(x=10, y=20), send=Point(x=30, y=40), copy=Point(x=50, y=60))
    roundtrip = CoordinatePlan.model_validate(json.loads(coord_plan.model_dump_json()))
    status = "PASS" if roundtrip == coord_plan else "FAILED"
    emit(CommandReceipt(command="self-test", status=status, executed=False, created_at=now(), plan=roundtrip), json_output)
    if status != "PASS":
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
