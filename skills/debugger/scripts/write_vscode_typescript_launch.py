#!/usr/bin/env python3
"""Write VS Code JavaScript/TypeScript debugger launch configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

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


def upsert_config(launch_path: Path, config: dict[str, object]) -> None:
    document = {"version": "0.2.0", "configurations": []}
    if launch_path.exists():
        try:
            document = loads_jsonc(launch_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"existing launch.json is invalid JSON: {launch_path}: {exc}") from exc
    configurations = document.setdefault("configurations", [])
    configurations[:] = [entry for entry in configurations if entry.get("name") != config["name"]]
    configurations.append(config)
    launch_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main(
    workspace: Annotated[Path, typer.Option("--workspace", help="Project workspace folder.")] = Path.cwd(),
    name: Annotated[str, typer.Option("--name", help="VS Code debug configuration name.")] = (
        "Debug TypeScript with $debugger"
    ),
    kind: Annotated[
        Literal["node", "npm", "extensionHost"],
        typer.Option("--kind", help="TypeScript debug target kind."),
    ] = "node",
    program: Annotated[str | None, typer.Option("--program", help="Program path, VS Code variables allowed.")] = None,
    runtime_executable: Annotated[
        str | None, typer.Option("--runtime-executable", help="Runtime executable such as node, npm, or npx.")
    ] = None,
    runtime_arg: Annotated[
        list[str] | None, typer.Option("--runtime-arg", help="Runtime argument. Repeat in order.")
    ] = None,
    arg: Annotated[list[str] | None, typer.Option("--arg", help="Program argument. Repeat in order.")] = None,
    env: Annotated[list[str] | None, typer.Option("--env", help="Environment KEY=VALUE. Repeat as needed.")] = None,
    out_file: Annotated[
        list[str] | None, typer.Option("--out-file", help="Compiled JS sourcemap glob. Repeat as needed.")
    ] = None,
    cwd: Annotated[str, typer.Option("--cwd", help="Working directory, VS Code variables allowed.")] = "${workspaceFolder}",
) -> None:
    workspace = workspace.resolve()
    launch_path = workspace / ".vscode" / "launch.json"
    launch_path.parent.mkdir(parents=True, exist_ok=True)

    if kind == "extensionHost":
        config: dict[str, object] = {
            "name": name,
            "type": "extensionHost",
            "request": "launch",
            "args": arg or ["--extensionDevelopmentPath=${workspaceFolder}"],
            "outFiles": out_file or ["${workspaceFolder}/out/**/*.js"],
            "env": parse_env(env),
            "cwd": cwd,
        }
    else:
        config = {
            "name": name,
            "type": "pwa-node",
            "request": "launch",
            "cwd": cwd,
            "sourceMaps": True,
            "skipFiles": ["<node_internals>/**"],
            "outFiles": out_file or ["${workspaceFolder}/dist/**/*.js", "${workspaceFolder}/out/**/*.js"],
            "env": parse_env(env),
        }
        if kind == "npm":
            config["runtimeExecutable"] = runtime_executable or "npm"
            config["runtimeArgs"] = runtime_arg or ["run", "test", "--"]
            config["args"] = arg or []
        else:
            config["runtimeExecutable"] = runtime_executable or "node"
            config["runtimeArgs"] = runtime_arg or []
            if not program:
                raise typer.BadParameter("--program is required for --kind node")
            config["program"] = program
            config["args"] = arg or []

    upsert_config(launch_path, config)
    print(launch_path)


if __name__ == "__main__":
    typer.run(main)
