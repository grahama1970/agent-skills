#!/usr/bin/env python3
"""Write a VS Code launch.json entry for a debugger reproduction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def parse_env(items: list[str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise typer.BadParameter(f"--env must be KEY=VALUE, got {item!r}")
        env[key] = value
    return env


def loads_jsonc(text: str) -> dict:
    cleaned: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            cleaned.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
            index += 1
            continue
        if char == "/" and nxt == "/":
            index = text.find("\n", index)
            if index == -1:
                break
            cleaned.append("\n")
            index += 1
            continue
        if char == "/" and nxt == "*":
            end = text.find("*/", index + 2)
            if end == -1:
                raise ValueError("unterminated block comment in JSONC")
            cleaned.append("\n" * text[index:end + 2].count("\n"))
            index = end + 2
            continue
        cleaned.append(char)
        index += 1
    return json.loads(strip_trailing_commas("".join(cleaned)))


def strip_trailing_commas(text: str) -> str:
    cleaned: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            cleaned.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        cleaned.append(char)
        index += 1
    return "".join(cleaned)


def main(
    workspace: Annotated[Path, typer.Option("--workspace", help="Project workspace folder.")] = Path.cwd(),
    name: Annotated[str, typer.Option("--name", help="VS Code debug configuration name.")] = "Debug with $debugger",
    python: Annotated[str, typer.Option("--python", help="Python interpreter path, VS Code variables allowed.")] = (
        "${workspaceFolder}/.venv/bin/python"
    ),
    module: Annotated[str, typer.Option("--module", help="Python module to launch, such as pytest.")] = "pytest",
    arg: Annotated[list[str] | None, typer.Option("--arg", help="Debuggee argument. Repeat in order.")] = None,
    env: Annotated[list[str] | None, typer.Option("--env", help="Environment KEY=VALUE. Repeat as needed.")] = None,
    just_my_code: Annotated[bool, typer.Option("--just-my-code/--all-code")] = False,
) -> None:
    workspace = workspace.resolve()
    launch_path = workspace / ".vscode" / "launch.json"
    launch_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "name": name,
        "type": "debugpy",
        "request": "launch",
        "module": module,
        "args": arg or [],
        "cwd": "${workspaceFolder}",
        "python": python,
        "env": parse_env(env),
        "console": "integratedTerminal",
        "justMyCode": just_my_code,
    }

    document = {"version": "0.2.0", "configurations": []}
    if launch_path.exists():
        try:
            document = loads_jsonc(launch_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"existing launch.json is invalid JSON: {launch_path}: {exc}") from exc
    configurations = document.setdefault("configurations", [])
    configurations[:] = [entry for entry in configurations if entry.get("name") != name]
    configurations.append(config)

    launch_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(launch_path)


if __name__ == "__main__":
    typer.run(main)
