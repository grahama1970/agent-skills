#!/usr/bin/env python3
"""scillm batch completions CLI.

Adheres to SCILLM_PAVED_PATH_CONTRACT.md.
Uses `parallel_acompletions_iter` for batch processing as requested.

Usage:
    # Single prompt
    python batch.py single "What is 2+2?"

    # Batch from JSONL (one {"prompt": "..."} per line)
    python batch.py batch --input prompts.jsonl

    # Batch with JSON mode
    python batch.py batch --input prompts.jsonl --json
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

# Use Rich for better output
console = Console(stderr=True)

# Standardize env loading (uv handles python-dotenv if installed, but explicit load is safer for scripts)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass  # Assume environment is already set if dotenv missing

app = typer.Typer(add_completion=False, help="Batch LLM completions via scillm")


def _get_env(key: str) -> str:
    """Get env var with error if missing."""
    val = os.getenv(key)
    if not val:
        # Fallback for common aliases
        if key == "CHUTES_MODEL_ID":
            val = os.getenv("CHUTES_TEXT_MODEL")
    return val


def _load_json_schema(path: Optional[Path]) -> Optional[dict]:
    if not path:
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to load schema {path}: {exc}[/red]")
        raise typer.Exit(1)


def _set_strict_json(strict_flag: Optional[bool], *, enable_by_default: bool) -> bool:
    """Derive strict JSON behavior and set env for downstream scillm calls."""
    if strict_flag is None:
        strict_flag = enable_by_default
    if strict_flag:
        os.environ["SCILLM_JSON_STRICT"] = "1"
    else:
        os.environ.setdefault("SCILLM_JSON_STRICT", "0")
    return bool(strict_flag)


@app.command()
def batch(
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="JSONL file (or - for stdin)"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Single prompt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSONL"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (default: $CHUTES_MODEL_ID)"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Request JSON response"),
    concurrency: int = typer.Option(6, "--concurrency", "-c", help="Parallel requests (default: 6)"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Per-request timeout (s)"),
    wall_time: int = typer.Option(300, "--wall-time", help="Total wall time (s)"),
    max_tokens: int = typer.Option(1024, "--max-tokens", help="Max tokens"),
    strict_json: Optional[bool] = typer.Option(None, "--strict-json/--no-strict-json", help="Force strict JSON validation (default: on when --json)"),
    retry_invalid_json: int = typer.Option(0, "--retry-invalid-json", help="Retries for invalid JSON chunks"),
    repair_invalid_json: bool = typer.Option(False, "--repair-invalid-json/--no-repair-invalid-json", help="Attempt auto-repair for malformed JSON"),
    schema: Optional[Path] = typer.Option(None, "--schema", help="JSON schema file (requires --json)"),
):
    """Run batch completions using parallel_acompletions_iter."""
    # Strict contract: Import directly from scillm
    try:
        from scillm import batch_acompletions_iter
    except ImportError:
        console.print("[red]Error: scillm not installed. Run 'uv sync' or 'pip install scillm'.[/red]")
        raise typer.Exit(1)

    api_base = _get_env("CHUTES_API_BASE")
    api_key = _get_env("CHUTES_API_KEY")
    model_id = model or _get_env("CHUTES_MODEL_ID")

    if not api_base or not api_key:
        console.print("[red]Error: CHUTES_API_BASE and CHUTES_API_KEY required.[/red]")
        raise typer.Exit(1)
    if not model_id:
        console.print("[red]Error: No model specified (--model or $CHUTES_MODEL_ID).[/red]")
        raise typer.Exit(1)

    schema_obj = _load_json_schema(schema)
    if schema_obj and not json_mode:
        console.print("[yellow]Warning: --schema ignored without --json.[/yellow]")

    strict_mode = _set_strict_json(strict_json, enable_by_default=json_mode)

    # 1. Collect Requests
    prompts: list[str] = []
    if prompt:
        prompts.append(prompt)
    elif input_file:
        content = sys.stdin.read() if str(input_file) == "-" else input_file.read_text()
        lines = content.strip().split("\n")
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                prompts.append(data.get("prompt") or data.get("text") or line)
            except json.JSONDecodeError:
                prompts.append(line)
    else:
        console.print("[red]Error: Must provide --input or --prompt.[/red]")
        raise typer.Exit(1)

    if not prompts:
        console.print("[yellow]Warning: No prompts to process.[/yellow]")
        raise typer.Exit(0)

    # 2. Build Request Objects
    # Per Contract: model/messages go INSIDE the request dict
    reqs = []
    for p in prompts:
        req = {
            "model": model_id,
            "messages": [{"role": "user", "content": p}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            req["response_format"] = {"type": "json_object"}
        reqs.append(req)

    # 3. Execute with Iterator Pattern
    async def _run():
        console.print(f"[bold blue]Processing {len(reqs)} items (concurrency={concurrency})...[/bold blue]")
        
        results = []
        ok_count = 0
        err_count = 0

        # batch_acompletions_iter yields results as they complete
        async for res in batch_acompletions_iter(
            reqs,
            api_base=api_base,
            api_key=api_key,
            custom_llm_provider="openai_like",
            concurrency=concurrency,
            timeout=timeout,
            wall_time_s=wall_time,
            response_format={"type": "json_object"} if json_mode else None,
            tenacious=False,
            schema=schema_obj if (schema_obj and json_mode) else None,
            retry_invalid_json=retry_invalid_json if json_mode else 0,
            repair_invalid_json=repair_invalid_json if json_mode else False,
        ):
            # Contract: res contains index, status, ok, error, content
            results.append(res)
            
            if res.get("ok"):
                ok_count += 1
                # Optional: print progress dot
                print(".", end="", flush=True, file=sys.stderr)
            else:
                err_count += 1
                print("x", end="", flush=True, file=sys.stderr)
        
        print("", file=sys.stderr) # Newline
        return results, ok_count, err_count

    results, ok_count, err_count = asyncio.run(_run())

    # 4. Output Results
    out_lines = []
    # Sort results to match input order? Iterator yields as they finish, so index check is needed if order matters.
    # We will just dump them with index.
    results.sort(key=lambda x: x.get("index", 0))

    for r in results:
        # Standardize output format
        item = {
            "index": r.get("index"),
            "ok": r.get("ok"),
            "status": r.get("status"),
        }
        if r.get("ok"):
            item["content"] = r.get("content")
        else:
            item["error"] = r.get("error")
        out_lines.append(json.dumps(item))

    if output:
        output.write_text("\n".join(out_lines))
        console.print(f"[green]Wrote {len(out_lines)} results to {output}[/green]")
    else:
        for line in out_lines:
            print(line)

    console.print(f"[bold]Summary:[/bold] {ok_count} OK, {err_count} Failed")
    if err_count > 0:
        raise typer.Exit(1)


@app.command()
def single(
    prompt: str = typer.Argument(..., help="Prompt text"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    json_mode: bool = typer.Option(False, "--json", "-j"),
    timeout: int = typer.Option(30, "--timeout", "-t"),
    strict_json: Optional[bool] = typer.Option(None, "--strict-json/--no-strict-json", help="Force strict JSON parsing when --json is set"),
):
    """Run a single completion (Simple Wrapper)."""
    try:
        from scillm import acompletion
    except ImportError:
        console.print("[red]Error: scillm not installed.[/red]")
        raise typer.Exit(1)

    api_base = _get_env("CHUTES_API_BASE")
    api_key = _get_env("CHUTES_API_KEY")
    model_id = model or _get_env("CHUTES_MODEL_ID")

    if not api_base or not api_key or not model_id:
        console.print("[red]Error: Credentials or model missing.[/red]")
        raise typer.Exit(1)

    _set_strict_json(strict_json, enable_by_default=json_mode)

    async def _run():
        return await acompletion(
            model=model_id,
            api_base=api_base,
            api_key=api_key,
            custom_llm_provider="openai_like",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if json_mode else None,
            max_tokens=1024,
            temperature=0.2,
            timeout=timeout,
        )

    try:
        resp = asyncio.run(_run())
        content = resp.choices[0].message.content
        if json_mode:
            # Pretty print JSON
            try:
                print(json.dumps(json.loads(content), indent=2))
            except:
                print(content)
        else:
            print(content)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
