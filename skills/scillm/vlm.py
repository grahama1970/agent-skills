#!/usr/bin/env python3
"""scillm VLM (Vision-Language Model) completions CLI.

Adheres to SCILLM_PAVED_PATH_CONTRACT.md.
Uses `aconfig` and `parallel_acompletions_iter` for multimodal calls.

Usage:
    # Describe an image
    python vlm.py describe /path/to/image.png

    # Batch describe
    python vlm.py batch --input images.jsonl
"""
import asyncio
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

import typer
from rich.console import Console

console = Console(stderr=True)

# Standardize env loading
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

app = typer.Typer(add_completion=False, help="VLM (multimodal) completions via scillm")


def _get_env(key: str) -> str:
    return os.getenv(key) or ""


def _env_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _set_strict_json(strict_flag: Optional[bool], *, enable_by_default: bool) -> bool:
    if strict_flag is None:
        strict_flag = enable_by_default
    if strict_flag:
        os.environ["SCILLM_JSON_STRICT"] = "1"
    else:
        os.environ.setdefault("SCILLM_JSON_STRICT", "0")
    return bool(strict_flag)


def _encode_image(path: Path) -> str:
    """Read image file and return base64-encoded data URI."""
    suffix = path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_types.get(suffix, "image/png")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def _inline_remote_image(url: str, *, timeout: int) -> str:
    """Download a remote image and return a data URI."""
    req = urllib_request.Request(url, headers={"User-Agent": "scillm-skill/1.0"})
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read()
            content_type = resp.info().get_content_type()
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(url)
        content_type = guessed or "image/png"
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def _resolve_image_input(
    value: str,
    *,
    inline_remote: bool,
    inline_timeout: int,
    base_dir: Optional[Path] = None,
    allow_skip: bool = False,
) -> Optional[Tuple[str, str, str]]:
    """Return (image_url, source, display) for file paths, data URIs, or remote URLs."""
    target = (value or "").strip()
    if not target:
        if allow_skip:
            console.print("[yellow]Skip empty image entry[/yellow]")
            return None
        console.print("[red]Error: empty image path/url provided[/red]")
        raise typer.Exit(1)

    if target.startswith("data:"):
        return target, "data", target[:64] + ("..." if len(target) > 64 else "")

    if target.startswith(("http://", "https://", "file://")):
        if inline_remote:
            try:
                return _inline_remote_image(target, timeout=inline_timeout), "remote-inline", target
            except RuntimeError as exc:
                if allow_skip:
                    console.print(f"[yellow]Skip remote {target}: {exc}[/yellow]")
                    return None
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(1)
        return target, "remote", target

    path = Path(target)
    if base_dir and not path.is_absolute():
        path = (base_dir / path).resolve()
    if not path.exists():
        msg = f"Image not found: {path}"
        if allow_skip:
            console.print(f"[yellow]{msg} (skipping)[/yellow]")
            return None
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    try:
        return _encode_image(path), "file", str(path)
    except Exception as exc:  # noqa: BLE001
        if allow_skip:
            console.print(f"[yellow]Skip failed read {path}: {exc}[/yellow]")
            return None
        console.print(f"[red]Error reading image: {path} ({exc})[/red]")
        raise typer.Exit(1)


def _inline_flag(value: Optional[bool]) -> bool:
    if value is None:
        return _env_truthy(os.getenv("SCILLM_INLINE_REMOTE_IMAGES"))
    if value:
        os.environ["SCILLM_INLINE_REMOTE_IMAGES"] = "1"
    return value


def _maybe_exit_dry_run(payload: Dict[str, Any], *, message: str = "") -> None:
    if message:
        console.print(message)
    print(json.dumps(payload, indent=2))
    raise typer.Exit(0)


@app.command()
def describe(
    image: str = typer.Argument(..., help="Image path, data URI, or https:// URL"),
    prompt: str = typer.Option("Describe this image in detail.", "--prompt", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    json_mode: bool = typer.Option(False, "--json", "-j"),
    timeout: int = typer.Option(45, "--timeout", "-t"),
    strict_json: Optional[bool] = typer.Option(None, "--strict-json/--no-strict-json", help="Force strict JSON validation when --json is set"),
    inline_remote_images: Optional[bool] = typer.Option(None, "--inline-remote-images/--no-inline-remote-images", help="Download https images and inline as data URIs"),
    inline_remote_timeout: int = typer.Option(10, "--inline-remote-timeout", help="Timeout (s) for downloading remote images when inlining"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print request payload and exit without calling scillm"),
):
    """Describe a single image using VLM."""
    api_base = _get_env("CHUTES_API_BASE")
    api_key = _get_env("CHUTES_API_KEY")
    model_id = model or _get_env("CHUTES_VLM_MODEL") or "Qwen/Qwen3-VL-235B-A22B-Instruct"

    if not dry_run and (not api_base or not api_key):
        console.print("[red]Error: CHUTES_API_BASE and CHUTES_API_KEY required.[/red]")
        raise typer.Exit(1)

    inline_remote = _inline_flag(inline_remote_images)
    resolved = _resolve_image_input(
        image,
        inline_remote=inline_remote,
        inline_timeout=inline_remote_timeout,
        base_dir=Path.cwd(),
    )
    if resolved is None:
        raise typer.Exit(1)
    image_url, source, display = resolved

    # Contract: Explicit structure for multimodal content
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    }]

    _set_strict_json(strict_json, enable_by_default=json_mode)

    request_preview = {
        "model": model_id,
        "json": json_mode,
        "source": source,
        "image": display,
    }

    if dry_run:
        _maybe_exit_dry_run(request_preview, message="[green]Dry-run only (no API call).[/green]")

    # Contract: Import directly from scillm (only when executing)
    try:
        from scillm import acompletion
    except ImportError:
        console.print("[red]Error: scillm not installed.[/red]")
        raise typer.Exit(1)

    async def _run():
        return await acompletion(
            model=model_id,
            api_base=api_base,
            api_key=api_key,
            custom_llm_provider="openai_like",
            messages=messages,
            response_format={"type": "json_object"} if json_mode else None,
            max_tokens=1024,
            temperature=0.2,
            timeout=timeout,
        )

    try:
        resp = asyncio.run(_run())
        content = resp.choices[0].message.content
        if json_mode:
            try:
                print(json.dumps(json.loads(content), indent=2))
            except Exception:  # noqa: BLE001
                print(content)
        else:
            print(content)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def batch(
    input_file: Path = typer.Option(..., "--input", "-i", help="JSONL file with image paths"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSONL"),
    prompt: str = typer.Option("Describe this image.", "--prompt", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    json_mode: bool = typer.Option(False, "--json", "-j"),
    concurrency: int = typer.Option(4, "--concurrency", "-c"),
    timeout: int = typer.Option(45, "--timeout", "-t"),
    wall_time: int = typer.Option(300, "--wall-time", help="Total wall time (s)"),
    strict_json: Optional[bool] = typer.Option(None, "--strict-json/--no-strict-json", help="Force strict JSON validation when --json is set"),
    retry_invalid_json: int = typer.Option(0, "--retry-invalid-json", help="Retries for invalid JSON chunks"),
    repair_invalid_json: bool = typer.Option(False, "--repair-invalid-json/--no-repair-invalid-json", help="Attempt auto-repair for malformed JSON"),
    inline_remote_images: Optional[bool] = typer.Option(None, "--inline-remote-images/--no-inline-remote-images", help="Download https image URLs and inline them as data URIs"),
    inline_remote_timeout: int = typer.Option(10, "--inline-remote-timeout", help="Timeout (s) for downloading remote images when inlining"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prepared batch and skip API call"),
):
    """Batch describe images using parallel_acompletions_iter."""
    api_base = _get_env("CHUTES_API_BASE")
    api_key = _get_env("CHUTES_API_KEY")
    model_id = model or _get_env("CHUTES_VLM_MODEL") or "Qwen/Qwen3-VL-235B-A22B-Instruct"

    if not dry_run and (not api_base or not api_key):
        console.print("[red]Error: CHUTES_API_BASE and CHUTES_API_KEY required.[/red]")
        raise typer.Exit(1)

    _set_strict_json(strict_json, enable_by_default=json_mode)

    # 1. Prepare Requests
    console.print(f"[blue]Reading {input_file}...[/blue]")
    lines = input_file.read_text().strip().split("\n")
    requests: List[Dict[str, Any]] = []

    # Keep track of original path per index for result mapping
    meta_map: Dict[int, Dict[str, str]] = {}
    inline_remote = _inline_flag(inline_remote_images)
    base_dir = input_file.parent if input_file and input_file != Path("-") else Path.cwd()

    valid_count = 0
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            img_value = (
                data.get("path")
                or data.get("image")
                or data.get("image_url")
                or data.get("url")
                or line.strip()
            )
            item_prompt = data.get("prompt", prompt)
        except json.JSONDecodeError:
            img_value = line.strip()
            item_prompt = prompt

        resolved = _resolve_image_input(
            str(img_value),
            inline_remote=inline_remote,
            inline_timeout=inline_remote_timeout,
            base_dir=base_dir,
            allow_skip=True,
        )
        if resolved is None:
            continue
        image_url, source, display = resolved

        # Contract: Per-request object
        requests.append({
            "model": model_id,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": item_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
            }],
            "response_format": {"type": "json_object"} if json_mode else None,
            "max_tokens": 1024,
            "temperature": 0.2,
            "index": idx,  # Pass index to track which item this is
        })
        meta_map[idx] = {"path": display, "source": source}
        valid_count += 1

    if not requests:
        console.print("[red]No valid images to process.[/red]")
        raise typer.Exit(1)

    if dry_run:
        for req in requests:
            idx = req.get("index", -1)
            meta = meta_map.get(idx, {})
            preview = {
                "index": idx,
                "path": meta.get("path"),
                "source": meta.get("source"),
                "json": json_mode,
            }
            print(json.dumps(preview))
        console.print("[green]Dry-run only (no API call).[/green]")
        return

    # Contract: Import parallel_acompletions_iter only when running
    from scillm import batch_acompletions_iter

    # 2. Execute via Iterator
    async def _run():
        console.print(f"[bold blue]Processing {len(requests)} images (concurrency={concurrency})...[/bold blue]")
        
        results = []
        ok_count = 0
        err_count = 0

        async for res in batch_acompletions_iter(
            requests,
            api_base=api_base,
            api_key=api_key,
            custom_llm_provider="openai_like",
            concurrency=concurrency,
            timeout=timeout,
            wall_time_s=wall_time,
            tenacious=False,
            retry_invalid_json=retry_invalid_json if json_mode else 0,
            repair_invalid_json=repair_invalid_json if json_mode else False,
        ):
            idx = res.get("index") # Recover index from response
            meta = meta_map.get(idx, {})
            path = meta.get("path", "unknown")

            item = {
                "index": idx,
                "path": path,
                "source": meta.get("source"),
                "ok": res.get("ok"),
                "status": res.get("status")
            }
            if res.get("ok"):
                item["content"] = res.get("content")
                ok_count += 1
                print(".", end="", flush=True, file=sys.stderr)
            else:
                item["error"] = res.get("error")
                err_count += 1
                print("x", end="", flush=True, file=sys.stderr)
            
            results.append(item)

        print("", file=sys.stderr)
        return results, ok_count, err_count

    results, ok_count, err_count = asyncio.run(_run())

    # 3. Output
    if output:
        out_lines = [json.dumps(r) for r in results]
        output.write_text("\n".join(out_lines))
        console.print(f"[green]Wrote {len(out_lines)} results to {output}[/green]")
    else:
        for r in results:
            print(json.dumps(r))

    if err_count > 0:
        console.print(f"[yellow]Done with errors: {ok_count} ok, {err_count} failed[/yellow]")
        raise typer.Exit(1)
    else:
        console.print(f"[green]Success: {ok_count}/{len(results)} ok[/green]")


if __name__ == "__main__":
    app()
