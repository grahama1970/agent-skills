#!/usr/bin/env python3
"""Capture Python breakpoint hits and frame state as JSON."""

from __future__ import annotations

import bdb
import json
import linecache
import runpy
import sys
import time
import traceback
from pathlib import Path
from typing import Annotated, Any

from loguru import logger
import typer


def safe_repr(value: Any, limit: int) -> str:
    try:
        text = repr(value)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("repr failed for captured debugger value: {}", exc)
        text = f"<repr failed: {type(exc).__name__}: {exc}>"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def parse_breakpoint(raw: str) -> tuple[str, int]:
    if ":" not in raw:
        raise typer.BadParameter(f"breakpoint must be file:line, got {raw!r}")
    file_part, line_part = raw.rsplit(":", 1)
    try:
        line = int(line_part)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid breakpoint line in {raw!r}") from exc
    path = str(Path(file_part).resolve())
    return path, line


class CaptureDebugger(bdb.Bdb):
    def __init__(
        self,
        watches: list[str],
        local_names: set[str],
        repr_limit: int,
        max_hits: int,
        *,
        allow_watch_eval: bool,
        capture_all_locals: bool,
    ) -> None:
        super().__init__()
        self.watches = watches
        self.local_names = local_names
        self.repr_limit = repr_limit
        self.max_hits = max_hits
        self.allow_watch_eval = allow_watch_eval
        self.capture_all_locals = capture_all_locals
        self.hits: list[dict[str, Any]] = []

    def user_line(self, frame) -> None:  # type: ignore[no-untyped-def]
        if not self.break_here(frame):
            self.set_continue()
            return
        filename = str(Path(frame.f_code.co_filename).resolve())
        lineno = frame.f_lineno
        source = linecache.getline(filename, lineno).strip()
        locals_snapshot = {
            key: safe_repr(value, self.repr_limit)
            for key, value in sorted(frame.f_locals.items())
            if not key.startswith("__") and (self.capture_all_locals or key in self.local_names)
        }
        watch_results: dict[str, dict[str, str]] = {}
        for expr in self.watches:
            if not self.allow_watch_eval:
                watch_results[expr] = {
                    "ok": "false",
                    "error": "watch evaluation disabled; rerun with --allow-watch-eval after confirming it is safe",
                }
                continue
            try:
                value = eval(expr, frame.f_globals, frame.f_locals)  # noqa: S307 - debugger watch expression
                watch_results[expr] = {"ok": "true", "value": safe_repr(value, self.repr_limit)}
            except Exception as exc:
                logger.error("watch expression failed at {}:{}: {} -> {}", filename, lineno, expr, exc)
                watch_results[expr] = {
                    "ok": "false",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        self.hits.append(
            {
                "file": filename,
                "line": lineno,
                "function": frame.f_code.co_name,
                "source": source,
                "locals": locals_snapshot,
                "watches": watch_results,
            }
        )
        if len(self.hits) >= self.max_hits:
            self.set_quit()
        else:
            self.set_continue()


def run_command(argv: list[str]) -> None:
    if not argv:
        raise SystemExit("missing command after --")
    if Path(argv[0]).name in {"python", "python3"}:
        argv = argv[1:]
        if not argv:
            raise SystemExit("missing Python command after interpreter")
    sys.argv = argv
    if argv[0] == "-m":
        if len(argv) < 2:
            raise SystemExit("missing module after -m")
        sys.argv = argv[1:]
        sys.path.insert(0, str(Path.cwd()))
        runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
        return
    script = Path(argv[0]).resolve()
    sys.argv = [str(script), *argv[1:]]
    runpy.run_path(str(script), run_name="__main__")


def main(
    breakpoints_raw: Annotated[
        list[str] | None,
        typer.Option("--break", help="Breakpoint as file:line. Repeat for multiple breakpoints."),
    ] = None,
    watch: Annotated[
        list[str] | None,
        typer.Option("--watch", help="Expression to evaluate only when --allow-watch-eval is set."),
    ] = None,
    local: Annotated[
        list[str] | None,
        typer.Option("--local", help="Local variable name to capture. Repeat for each allowed local."),
    ] = None,
    capture_all_locals: Annotated[
        bool,
        typer.Option("--capture-all-locals", help="Capture all non-dunder locals. Avoid when secrets may be present."),
    ] = False,
    allow_watch_eval: Annotated[
        bool,
        typer.Option("--allow-watch-eval", help="Evaluate watch expressions in the paused frame."),
    ] = False,
    out: Annotated[Path, typer.Option("--out", help="JSON proof output path.")] = Path(
        "/tmp/debugger-proof.json"
    ),
    repr_limit: Annotated[int, typer.Option("--repr-limit", help="Maximum repr length per captured value.")] = 1200,
    max_hits: Annotated[int, typer.Option("--max-hits", help="Maximum breakpoint hits before stopping.")] = 20,
    command: Annotated[
        list[str] | None,
        typer.Argument(help="Python command to run. Put it after -- so command flags are preserved."),
    ] = None,
) -> None:
    if not breakpoints_raw:
        raise typer.BadParameter("at least one --break file:line is required")
    breakpoints = [parse_breakpoint(raw) for raw in breakpoints_raw]
    watches = watch or []
    command = command or []
    if command and command[0] == "--":
        command = command[1:]

    debugger = CaptureDebugger(
        watches,
        set(local or []),
        repr_limit,
        max_hits,
        allow_watch_eval=allow_watch_eval,
        capture_all_locals=capture_all_locals,
    )
    for filename, lineno in breakpoints:
        err = debugger.set_break(filename, lineno)
        if err:
            raise typer.BadParameter(err)

    started = time.time()
    status: dict[str, Any] = {"ok": True, "exit": None, "error": None}
    try:
        debugger.runcall(run_command, command)
    except bdb.BdbQuit:
        status = {"ok": False, "exit": "max_hits_or_quit", "error": None}
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        status = {"ok": code == 0, "exit": code, "error": None if code == 0 else safe_repr(exc.code, 400)}
    except Exception as exc:  # pragma: no cover - intended diagnostic path
        logger.error("debugged command failed: {}", exc)
        status = {
            "ok": False,
            "exit": type(exc).__name__,
            "error": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
            "traceback": traceback.format_exc(),
        }

    result = {
        "command": command,
        "breakpoints": [{"file": file, "line": line} for file, line in breakpoints],
        "watches": watches,
        "locals_allowlist": local or [],
        "capture_all_locals": capture_all_locals,
        "allow_watch_eval": allow_watch_eval,
        "hit_count": len(debugger.hits),
        "hits": debugger.hits,
        "status": status,
        "duration_ms": round((time.time() - started) * 1000),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out} with {len(debugger.hits)} breakpoint hit(s)")
    if not status["ok"] or not debugger.hits:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
