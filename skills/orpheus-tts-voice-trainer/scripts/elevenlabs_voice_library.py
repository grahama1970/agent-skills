#!/usr/bin/env python3
"""Search and add ElevenLabs shared voices for Orpheus persona bakeoffs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import typer

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

app = typer.Typer(add_completion=False, help=__doc__)


def api_key_from_env() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise typer.BadParameter("ELEVENLABS_API_KEY is required")
    return key


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def compact_voice(raw: dict[str, Any]) -> dict[str, Any]:
    labels = raw.get("labels") or {}
    return {
        "voice_id": raw.get("voice_id"),
        "public_owner_id": raw.get("public_owner_id"),
        "name": raw.get("name"),
        "description": raw.get("description"),
        "category": raw.get("category"),
        "accent": labels.get("accent") or raw.get("accent"),
        "gender": labels.get("gender") or raw.get("gender"),
        "age": labels.get("age") or raw.get("age"),
        "use_case": labels.get("use case") or labels.get("use_case") or raw.get("use_case"),
        "preview_url": raw.get("preview_url"),
        "rate": raw.get("rate"),
        "similarity": raw.get("similarity"),
        "raw_labels": labels,
    }


@app.command()
def search(
    query: str = typer.Option(..., "--query", "-q", help="Voice Library search text"),
    gender: str | None = typer.Option(None, "--gender", help="male, female, or neutral"),
    accent: str | None = typer.Option(None, "--accent", help="Accent filter, e.g. british"),
    age: str | None = typer.Option(None, "--age", help="young, middle_aged, or old"),
    category: str | None = typer.Option(None, "--category", help="narration, conversational, characters, etc."),
    page_size: int = typer.Option(20, "--page-size", min=1, max=100),
    out: Path | None = typer.Option(None, "--out", help="Optional JSON output path"),
) -> None:
    """Search ElevenLabs shared voices and print voice_id/public_owner_id candidates."""
    params: dict[str, Any] = {"search": query, "page_size": page_size}
    for key, value in {
        "gender": gender,
        "accent": accent,
        "age": age,
        "category": category,
    }.items():
        if value:
            params[key] = value

    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.get(
            "https://api.elevenlabs.io/v1/shared-voices",
            headers={"xi-api-key": api_key_from_env()},
            params=params,
        )
    if response.status_code != 200:
        typer.echo(
            json.dumps(
                {
                    "status": "error",
                    "status_code": response.status_code,
                    "error": response.text[:1000],
                    "request": {"endpoint": "/v1/shared-voices", "params": params},
                },
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    body = response.json()
    raw_voices = body.get("voices") or body.get("results") or []
    voices = [compact_voice(voice) for voice in raw_voices]
    payload = {
        "status": "ok",
        "endpoint": "/v1/shared-voices",
        "query": params,
        "count": len(voices),
        "voices": voices,
    }
    write_json(out, payload)
    typer.echo(json.dumps(payload, indent=2))


@app.command("add")
def add_voice(
    public_owner_id: str = typer.Option(..., "--public-owner-id"),
    voice_id: str = typer.Option(..., "--voice-id"),
    new_name: str = typer.Option(..., "--new-name"),
    out: Path | None = typer.Option(None, "--out", help="Optional JSON output path"),
) -> None:
    """Add a shared voice to the account so TTS can use its voice_id."""
    url = f"https://api.elevenlabs.io/v1/voices/add/{public_owner_id}/{voice_id}"
    request = {"new_name": new_name}
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.post(
            url,
            headers={"xi-api-key": api_key_from_env(), "Content-Type": "application/json"},
            json=request,
        )
    payload = {
        "status": "ok" if response.status_code in {200, 201} else "error",
        "status_code": response.status_code,
        "endpoint": "/v1/voices/add/{public_owner_id}/{voice_id}",
        "voice_id": voice_id,
        "public_owner_id": public_owner_id,
        "new_name": new_name,
        "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:1000],
    }
    write_json(out, payload)
    typer.echo(json.dumps(payload, indent=2))
    if payload["status"] != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
