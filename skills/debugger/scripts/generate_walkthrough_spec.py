#!/usr/bin/env python3
"""Generate a debugger.walkthrough.v1 spec from a real captured debug session.

Turns any headless breakpoint capture (debugger.proof.v1 from `run.sh break`)
into a runnable narrated walkthrough: no hand-authored JSON. The stops come from
the session's actual hits -- real files, real lines, real observed locals -- so
the walkthrough replays exactly what the debugger saw, and each stop's `expect`
pins the first observed values (a bridge stop pauses at the first hit).

    ./run.sh spec-from-proof <proof.json> --out spec.json \
        [--workspace P] [--title T] [--mode review|blocked] [--max-stops N]

Narration is a deterministic template (file, function, observed locals). Pass
--narrate <handler> to have /ask rewrite each stop's say-line naturally; the
template text is the fail-soft fallback, so generation never depends on a model.

Fail-closed: a proof with zero hits, or one that fails the independent proof
validator, refuses to generate (exit 1) -- a walkthrough must replay a session
that actually happened.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

SKILL = Path(__file__).resolve().parent.parent


def validate_proof(proof_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SKILL / "run.sh"), "validate", str(proof_path), "--expect-valid"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise typer.Exit(code=_fail(
            f"proof failed independent validation; refusing to generate a walkthrough from it: "
            f"{(result.stderr or result.stdout).strip()[-300:]}"
        ))


def _fail(message: str) -> int:
    print(f"SPEC-GENERATION-REFUSED {message}", file=sys.stderr)
    return 1


def relativize(file_path: str, workspace: Path | None) -> str:
    if workspace is None:
        return file_path
    try:
        return str(Path(file_path).resolve().relative_to(workspace.resolve()))
    except ValueError:
        return file_path


def derive_launch(command: list[str] | None, workspace: Path | None, stops: list[dict]) -> dict:
    """Launch block from the captured repro command: `python3 x/y/main.py` ->
    module main + PYTHONPATH to its directory (workspace-relative when known)."""
    launch: dict[str, Any] = {"python": "/usr/bin/python3",
                              "config_name": "Debugger walkthrough ($debugger)"}
    script: Path | None = None
    for part in command or []:
        if part.endswith(".py"):
            script = Path(part)
            break
    if script is None:
        # Fall back to the first stop's file as the entry module.
        first = stops[0]["file"] if stops else "main.py"
        script = Path(first)
    launch["module"] = script.stem
    parent = script.parent
    if workspace is not None and parent.is_absolute():
        try:
            parent = parent.resolve().relative_to(workspace.resolve())
        except ValueError:
            pass
    # A relative repro (captured from inside its own directory) does not record
    # its cwd; the stops' own (already workspace-relative) directory is the
    # reliable anchor for the module path.
    if str(parent) in (".", "") and stops:
        parent = Path(stops[0]["file"]).parent
    launch["env"] = [f"PYTHONPATH=${{workspaceFolder}}/{parent}"]
    return launch


def template_say(hit: dict, seen_count: int) -> str:
    fn = hit.get("function") or "module level"
    locals_map = hit.get("locals") or {}
    shown = ", ".join(f"{k} is {v}" for k, v in list(locals_map.items())[:4]) or "no captured locals"
    source = (hit.get("source") or "").strip()
    prefix = f"This line ran {seen_count} times in the session; here is the first pause. " if seen_count > 1 else ""
    return (f"{prefix}We are paused in {fn} at line {hit['line']}"
            + (f", on `{source}`" if source else "")
            + f". At this moment {shown}.")


def narrate_with_ask(say_lines: list[str], title: str, handler: str) -> list[str]:
    """Optional: one /ask call rewrites the template narration naturally.
    Fail-soft -- any problem returns the template lines unchanged."""
    prompt = (
        f"Rewrite these debugger walkthrough narration lines for the tour '{title}'. "
        f"Keep every fact (function names, line numbers, variable values) exactly; make the "
        f"prose natural and spoken. Return a JSON array of the rewritten strings, same order, "
        f"in a ```json fenced block.\n" + json.dumps(say_lines, indent=1)
    )
    try:
        child_env = {k: v for k, v in os.environ.items()
                     if k not in ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "UV_LINK_MODE")}
        result = subprocess.run(
            ["bash", str(SKILL.parent / "ask" / "run.sh"), "one-shot", prompt, "--handler", handler],
            capture_output=True, text=True, timeout=300, env=child_env,
        )
        for row in result.stdout.splitlines():
            if row.startswith("ANSWER ") and ":" in row:
                text = Path(row.split(":", 1)[1].strip()).read_text(encoding="utf-8", errors="replace")
                import re
                match = re.search(r"```json\s*(\[.*?\])\s*```", text, re.S)
                if match:
                    rewritten = json.loads(match.group(1))
                    if isinstance(rewritten, list) and len(rewritten) == len(say_lines) \
                            and all(isinstance(item, str) and item for item in rewritten):
                        return rewritten
    except Exception:
        pass
    return say_lines


def main(
    proof: Annotated[Path, typer.Argument(help="debugger.proof.v1 JSON from run.sh break.")],
    out: Annotated[Path, typer.Option("--out", help="Where to write the walkthrough spec.")],
    workspace: Annotated[Path | None, typer.Option("--workspace", help="Workspace root for relative stop paths.")] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    mode: Annotated[str, typer.Option("--mode")] = "review",
    max_stops: Annotated[int, typer.Option("--max-stops")] = 5,
    narrate: Annotated[str | None, typer.Option("--narrate", help="/ask handler to rewrite narration naturally (fail-soft).")] = None,
    skip_validation: Annotated[bool, typer.Option("--skip-validation", help="Trust the proof without re-validating (evals only).")] = False,
) -> None:
    raw = json.loads(proof.read_text(encoding="utf-8"))
    hits = raw.get("hits") or []
    if int(raw.get("hit_count") or 0) < 1 or not hits:
        raise typer.Exit(code=_fail("proof recorded zero breakpoint hits; there is no session to walk through"))
    if mode not in ("review", "blocked"):
        raise typer.Exit(code=_fail(f"mode must be review or blocked, got {mode!r}"))
    if not skip_validation:
        validate_proof(proof)

    # First hit per (file,line), in session order; count repeats for narration.
    ordered: list[tuple[str, int]] = []
    first_hit: dict[tuple[str, int], dict] = {}
    counts: dict[tuple[str, int], int] = {}
    for hit in hits:
        key = (str(hit.get("file")), int(hit.get("line") or 0))
        counts[key] = counts.get(key, 0) + 1
        if key not in first_hit:
            first_hit[key] = hit
            ordered.append(key)
    ordered = ordered[:max_stops]

    stops = []
    for key in ordered:
        hit = first_hit[key]
        locals_map = dict(hit.get("locals") or {})
        stop: dict[str, Any] = {
            "file": relativize(key[0], workspace),
            "line": key[1],
            "say": template_say(hit, counts[key]),
            "locals": list(locals_map.keys()),
        }
        if locals_map:
            stop["expect"] = locals_map
        stops.append(stop)

    spec_title = title or f"Session replay: {Path(str(hits[0].get('file'))).stem} ({len(stops)} stops from {len(hits)} hits)"
    if narrate:
        rewritten = narrate_with_ask([s["say"] for s in stops], spec_title, narrate)
        for stop, say in zip(stops, rewritten):
            stop["say"] = say

    spec = {
        "schema": "debugger.walkthrough.v1",
        "title": spec_title,
        "mode": mode,
        "launch": derive_launch(raw.get("command"), workspace, stops),
        "stops": stops,
        "generatedFrom": {"proof": str(proof.resolve()), "hit_count": raw.get("hit_count")},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"SPEC-GENERATED {out} stops={len(stops)} from_hits={len(hits)}")


if __name__ == "__main__":
    typer.run(main)
