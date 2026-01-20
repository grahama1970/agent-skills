#!/usr/bin/env python3
"""CLI helpers for SciLLM paved-path preflight & discovery."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console

# Load env vars if python-dotenv is available (parity with other skill CLIs)
try:  # pragma: no cover - best effort
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except Exception:  # noqa: BLE001
    pass


console = Console(stderr=True)
app = typer.Typer(add_completion=False, help="SciLLM paved-path preflight helpers")


def _require_env(key: str, *, alias: Optional[str] = None) -> str:
    val = os.getenv(key) or (os.getenv(alias) if alias else None)
    if not val:
        console.print(f"[red]Error: {key} (or {alias}) is required.[/red]")
        raise typer.Exit(1)
    return val


def _load_json_file(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to parse JSON schema {path}: {exc}[/red]")
        raise typer.Exit(1)


def _get_sanity_preflight():
    try:
        from scillm.paved import sanity_preflight  # type: ignore

        return sanity_preflight
    except Exception:
        return None


def _get_list_models():
    try:
        from scillm.paved import list_models_openai_like  # type: ignore

        return list_models_openai_like
    except Exception:
        return None


def _fallback_preflight(*, api_base: str, api_key: str, model: str, timeout: float) -> Dict[str, Any]:
    try:
        from litellm.extras.preflight import preflight_models  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("sanity_preflight not available and litellm extras missing") from exc

    ids = sorted(preflight_models(api_base=api_base, api_key=api_key, timeout_s=timeout))
    return {
        "ok": model in ids if model else bool(ids),
        "checked_model": model,
        "models": ids,
        "source": "litellm.extras.preflight",
    }


def _run_sanity_preflight(
    *,
    api_base: str,
    api_key: str,
    model: str,
    parallel: int,
    wall_time: int,
    attempts: int,
    timeout: float,
) -> Dict[str, Any]:
    helper = _get_sanity_preflight()
    if helper:
        return helper(
            api_base=api_base,
            api_key=api_key,
            model=model,
            parallel=parallel,
            wall_time_s=wall_time,
            attempts=attempts,
        )
    return _fallback_preflight(api_base=api_base, api_key=api_key, model=model, timeout=timeout)


def _run_list_models(*, api_base: str, api_key: str, provider: str, timeout: float) -> Dict[str, Any]:
    helper = _get_list_models()
    if helper:
        return helper(api_base=api_base, api_key=api_key, custom_llm_provider=provider)

    try:
        from litellm.extras.preflight import preflight_models  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("list_models_openai_like not available and litellm extras missing") from exc

    ids = sorted(preflight_models(api_base=api_base, api_key=api_key, timeout_s=timeout))
    return {
        "provider": provider,
        "api_base": api_base,
        "models": ids,
        "source": "litellm.extras.preflight",
    }


def _print_json_or_table(data: Dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        console.print_json(json.dumps(data))
    else:
        console.print_json(json.dumps(data, indent=2, default=str))


@app.command()
def preflight(  # noqa: D401
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model ID (defaults to $CHUTES_MODEL_ID/$CHUTES_TEXT_MODEL)"),
    parallel: int = typer.Option(3, "--parallel", "-p", help="Concurrent sanity requests (default: 3)"),
    wall_time: int = typer.Option(30, "--wall-time", help="Wall clock limit per attempt (seconds)"),
    attempts: int = typer.Option(1, "--attempts", help="Number of attempts before failing"),
    timeout: float = typer.Option(10.0, "--timeout", help="HTTP timeout for discovery fallback"),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON instead of pretty text"),
):
    """Run paved-path sanity preflight (model availability + auth probe)."""

    api_base = _require_env("CHUTES_API_BASE")
    api_key = _require_env("CHUTES_API_KEY")
    model_id = model or os.getenv("CHUTES_MODEL_ID") or os.getenv("CHUTES_TEXT_MODEL")

    if not model_id:
        console.print("[red]Error: Set --model or $CHUTES_MODEL_ID/$CHUTES_TEXT_MODEL.[/red]")
        raise typer.Exit(1)

    try:
        result = _run_sanity_preflight(
            api_base=api_base,
            api_key=api_key,
            model=model_id,
            parallel=parallel,
            wall_time=wall_time,
            attempts=attempts,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc), "type": exc.__class__.__name__}
        _print_json_or_table(payload, json_mode=json_mode)
        raise typer.Exit(1)

    ok = bool(result.get("ok"))
    payload = {
        **result,
        "api_base": api_base,
        "model": model_id,
        "parallel": parallel,
        "wall_time_s": wall_time,
    }
    _print_json_or_table(payload, json_mode=json_mode)
    raise typer.Exit(0 if ok else 1)


@app.command()
def models(  # noqa: D401
    provider: str = typer.Option("openai_like", "--provider", "-p", help="Custom LLM provider"),
    timeout: float = typer.Option(10.0, "--timeout", help="HTTP timeout for discovery fallback"),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON instead of pretty text"),
    schema: Optional[Path] = typer.Option(None, "--schema", help="Optional jsonschema to include in output"),
):
    """List models via paved-path helper (fallbacks to /v1/models)."""

    api_base = _require_env("CHUTES_API_BASE")
    api_key = _require_env("CHUTES_API_KEY")

    try:
        result = _run_list_models(api_base=api_base, api_key=api_key, provider=provider, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc), "type": exc.__class__.__name__}
        _print_json_or_table(payload, json_mode=json_mode)
        raise typer.Exit(1)

    if schema:
        result["schema"] = _load_json_file(schema)

    _print_json_or_table(result, json_mode=json_mode)


if __name__ == "__main__":
    app()
