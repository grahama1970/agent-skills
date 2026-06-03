#!/usr/bin/env python3
"""Write VS Code Rust debugger launch configurations."""

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


def cargo_config(
    *,
    name: str,
    cargo_args: list[str],
    arg: list[str] | None,
    env: list[str] | None,
    cwd: str,
    filter_name: str | None,
    filter_kind: str | None,
) -> dict[str, object]:
    cargo: dict[str, object] = {"args": cargo_args}
    if filter_name or filter_kind:
        cargo["filter"] = {
            key: value
            for key, value in {
                "name": filter_name,
                "kind": filter_kind,
            }.items()
            if value
        }
    return {
        "name": name,
        "type": "lldb",
        "request": "launch",
        "cargo": cargo,
        "args": arg or [],
        "cwd": cwd,
        "env": parse_env(env),
        "sourceLanguages": ["rust"],
    }


def main(
    workspace: Annotated[Path, typer.Option("--workspace", help="Project workspace folder.")] = Path.cwd(),
    name: Annotated[str, typer.Option("--name", help="VS Code debug configuration name.")] = (
        "Debug Rust with $debugger"
    ),
    kind: Annotated[
        Literal["cargo-test", "cargo-run", "program"],
        typer.Option("--kind", help="Rust debug target kind."),
    ] = "cargo-test",
    cargo_arg: Annotated[
        list[str] | None, typer.Option("--cargo-arg", help="Cargo argument. Repeat in order.")
    ] = None,
    arg: Annotated[list[str] | None, typer.Option("--arg", help="Debuggee argument. Repeat in order.")] = None,
    env: Annotated[list[str] | None, typer.Option("--env", help="Environment KEY=VALUE. Repeat as needed.")] = None,
    program: Annotated[
        str | None, typer.Option("--program", help="Compiled binary path for --kind program.")
    ] = None,
    cwd: Annotated[str, typer.Option("--cwd", help="Working directory, VS Code variables allowed.")] = "${workspaceFolder}",
    filter_name: Annotated[
        str | None, typer.Option("--filter-name", help="CodeLLDB cargo filter name, such as crate or binary.")
    ] = None,
    filter_kind: Annotated[
        str | None, typer.Option("--filter-kind", help="CodeLLDB cargo filter kind, such as bin, lib, test.")
    ] = None,
) -> None:
    workspace = workspace.resolve()
    launch_path = workspace / ".vscode" / "launch.json"
    launch_path.parent.mkdir(parents=True, exist_ok=True)

    if kind == "program":
        if not program:
            raise typer.BadParameter("--program is required for --kind program")
        config: dict[str, object] = {
            "name": name,
            "type": "lldb",
            "request": "launch",
            "program": program,
            "args": arg or [],
            "cwd": cwd,
            "env": parse_env(env),
            "sourceLanguages": ["rust"],
        }
    elif kind == "cargo-run":
        config = cargo_config(
            name=name,
            cargo_args=cargo_arg or ["run", "--bin", "${workspaceFolderBasename}"],
            arg=arg,
            env=env,
            cwd=cwd,
            filter_name=filter_name,
            filter_kind=filter_kind or "bin",
        )
    else:
        config = cargo_config(
            name=name,
            cargo_args=cargo_arg or ["test", "--no-run"],
            arg=arg,
            env=env,
            cwd=cwd,
            filter_name=filter_name,
            filter_kind=filter_kind,
        )

    upsert_config(launch_path, config)
    print(launch_path)


if __name__ == "__main__":
    typer.run(main)
