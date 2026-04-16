"""Sonauto cloud music generation backend.

Cloud API for lyric-aware song generation. Complements local MusicGen (Docker/GPU)
with cloud fallback for lyrics-to-song, quick demos, and when GPU is busy.

API docs: sonauto.ai/developers
Costs: ~100 credits/song (150 for 2-song v2), free tier 1500 credits (~15 songs)
Songs expire after 1 week — download promptly.

Backends: v3 (variable 2-4min), v2 (fixed 1:35)
Editing: extend (add audio to start/end), inpaint (replace sections)
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger
from rich.console import Console

app = typer.Typer(help="Sonauto cloud music generation")
console = Console()

BASE_URL = "https://api.sonauto.ai/v1"


def _get_api_key() -> str:
    key = os.environ.get("SONAUTO_API_KEY", "")
    if not key:
        console.print("[red]SONAUTO_API_KEY not set. Check .env or export it.[/red]")
        raise typer.Exit(code=1)
    return key


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _poll_and_download(
    api_key: str,
    task_id: str,
    out: Path,
    poll_interval: int = 10,
    timeout: int = 300,
    align_lyrics: bool = False,
) -> dict:
    """Poll task until complete, download audio, return full status."""
    start = time.monotonic()
    status_url = f"{BASE_URL}/generations/{task_id}"

    while time.monotonic() - start < timeout:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(status_url, headers=_headers(api_key))
            resp.raise_for_status()
            status = resp.json()

        state = status.get("status", "UNKNOWN")
        logger.info(f"Status: {state}")

        if state == "SUCCESS":
            song_paths = status.get("song_paths", [])
            if not song_paths:
                console.print("[red]SUCCESS but no song_paths returned[/red]")
                raise typer.Exit(code=1)

            # Download all songs
            out.parent.mkdir(parents=True, exist_ok=True)
            for i, song_url in enumerate(song_paths):
                dest = out if i == 0 else out.with_stem(f"{out.stem}_{i+1}")
                with httpx.Client(timeout=120.0) as client:
                    audio_resp = client.get(song_url)
                    audio_resp.raise_for_status()
                    dest.write_bytes(audio_resp.content)
                console.print(f"[green]Song {i+1}: {dest} ({len(audio_resp.content)} bytes)[/green]")

            if status.get("lyrics"):
                lyrics_path = out.with_suffix(".lyrics.txt")
                lyrics_path.write_text(status["lyrics"])
                console.print(f"[green]Lyrics: {lyrics_path}[/green]")

            # Save full metadata
            meta_path = out.with_suffix(".meta.json")
            meta_path.write_text(json.dumps(status, indent=2))

            # Check alignment if requested
            if align_lyrics and status.get("alignment_status") != "SUCCESS":
                console.print("[yellow]Lyrics alignment still processing — check with 'status' command[/yellow]")

            return status

        if state == "FAILURE":
            console.print(f"[red]Generation failed: {status.get('error_message', 'unknown')}[/red]")
            raise typer.Exit(code=1)

        time.sleep(poll_interval)

    console.print(f"[red]Timeout after {timeout}s. Task {task_id} may still be processing.[/red]")
    console.print(f"[yellow]Check later: ./run.sh sonauto-status --task-id {task_id}[/yellow]")
    raise typer.Exit(code=1)


def _encode_audio(audio_file: Path) -> str:
    """Base64-encode a local audio file for upload."""
    data = audio_file.read_bytes()
    if len(data) > 40 * 1024 * 1024:
        console.print(f"[red]Audio file too large ({len(data) // 1024 // 1024}MB). Max 40MB.[/red]")
        raise typer.Exit(code=1)
    return base64.b64encode(data).decode("ascii")


@app.command("generate")
def generate(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Text prompt describing the song"),
    out: Path = typer.Option(..., "--out", "-o", help="Output audio file path"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated genre tags"),
    lyrics: Optional[str] = typer.Option(None, "--lyrics", "-l", help="Song lyrics"),
    lyrics_file: Optional[Path] = typer.Option(None, "--lyrics-file", help="Read lyrics from file"),
    instrumental: bool = typer.Option(False, "--instrumental", "-i", help="Instrumental only"),
    model: str = typer.Option("v3", "--model", "-m", help="v3 (variable length) or v2 (fixed 1:35)"),
    prompt_strength: float = typer.Option(2.0, "--prompt-strength", help="Prompt adherence (0-5)"),
    output_format: str = typer.Option("mp3", "--format", help="mp3, ogg, wav, flac, m4a"),
    align_lyrics: bool = typer.Option(False, "--align-lyrics", help="Enable word-level timing"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Reproducible generation (v2 only)"),
    bpm: Optional[str] = typer.Option(None, "--bpm", help="Tempo: integer or 'auto' (v2 only)"),
    balance_strength: Optional[float] = typer.Option(None, "--balance", help="Vocal vs instrumental (v2 only, 0-1)"),
    num_songs: int = typer.Option(1, "--num-songs", help="1 or 2 songs per request (v2 only, 2=150 credits)"),
    poll_interval: int = typer.Option(10, "--poll-interval", help="Seconds between status checks"),
    timeout: int = typer.Option(300, "--timeout", help="Max wait seconds"),
):
    """Generate a song from prompt, tags, and/or lyrics."""
    api_key = _get_api_key()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    actual_lyrics = lyrics or ""
    if lyrics_file and lyrics_file.exists():
        actual_lyrics = lyrics_file.read_text()

    payload = {
        "tags": tag_list,
        "lyrics": actual_lyrics,
        "prompt": prompt,
        "instrumental": instrumental,
        "prompt_strength": prompt_strength,
        "output_format": output_format,
        "align_lyrics": align_lyrics,
    }

    # v2-specific params
    if model == "v2":
        if seed is not None:
            payload["seed"] = seed
        if bpm is not None:
            payload["bpm"] = int(bpm) if bpm.isdigit() else bpm
        if balance_strength is not None:
            payload["balance_strength"] = balance_strength
        if num_songs > 1:
            payload["num_songs"] = num_songs

    url = f"{BASE_URL}/generations/{model}"
    logger.info(f"Submitting to Sonauto {model}: {prompt[:80]}...")

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json=payload, headers=_headers(api_key))
        resp.raise_for_status()
        result = resp.json()

    task_id = result.get("task_id")
    if not task_id:
        console.print(f"[red]No task_id in response: {result}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Task submitted: {task_id}[/green]")
    _poll_and_download(api_key, task_id, out, poll_interval, timeout, align_lyrics)


@app.command("extend")
def extend(
    audio: Path = typer.Option(..., "--audio", "-a", help="Source audio file to extend"),
    out: Path = typer.Option(..., "--out", "-o", help="Output file path"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Style prompt for extended section"),
    side: str = typer.Option("right", "--side", "-s", help="Extend from 'left' (start) or 'right' (end)"),
    duration: float = typer.Option(30.0, "--duration", "-d", help="Seconds to add (0-85)"),
    crop: float = typer.Option(0.0, "--crop", help="Seconds to trim before extending"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated genre tags"),
    lyrics: Optional[str] = typer.Option(None, "--lyrics", "-l", help="Lyrics for extended section"),
    output_format: str = typer.Option("mp3", "--format", help="mp3, ogg, wav, flac, m4a"),
    poll_interval: int = typer.Option(10, "--poll-interval", help="Seconds between status checks"),
    timeout: int = typer.Option(300, "--timeout", help="Max wait seconds"),
):
    """Extend an existing song from start or end. v2 only."""
    api_key = _get_api_key()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    if side not in ("left", "right"):
        console.print("[red]--side must be 'left' or 'right'[/red]")
        raise typer.Exit(code=1)
    if not 0 <= duration <= 85:
        console.print("[red]--duration must be 0-85 seconds[/red]")
        raise typer.Exit(code=1)

    payload = {
        "audio_base64": _encode_audio(audio),
        "side": side,
        "extend_duration": duration,
        "crop_duration": crop,
        "prompt": prompt,
        "tags": tag_list,
        "lyrics": lyrics or "",
        "output_format": output_format,
    }

    url = f"{BASE_URL}/generations/v2/extend"
    logger.info(f"Extending {audio.name} ({side}, +{duration}s)...")

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload, headers=_headers(api_key))
        resp.raise_for_status()
        result = resp.json()

    task_id = result.get("task_id")
    if not task_id:
        console.print(f"[red]No task_id: {result}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Extend task: {task_id}[/green]")
    _poll_and_download(api_key, task_id, out, poll_interval, timeout)


@app.command("inpaint")
def inpaint(
    audio: Path = typer.Option(..., "--audio", "-a", help="Source audio file"),
    out: Path = typer.Option(..., "--out", "-o", help="Output file path"),
    start: float = typer.Option(..., "--start", help="Section start time (seconds)"),
    end: float = typer.Option(..., "--end", help="Section end time (seconds)"),
    lyrics: str = typer.Option(..., "--lyrics", "-l", help="New lyrics for replaced section"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Style prompt"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated genre tags"),
    crop_to_section: bool = typer.Option(False, "--crop", help="Output only the inpainted section"),
    output_format: str = typer.Option("mp3", "--format", help="mp3, ogg, wav, flac, m4a"),
    poll_interval: int = typer.Option(10, "--poll-interval", help="Seconds between status checks"),
    timeout: int = typer.Option(300, "--timeout", help="Max wait seconds"),
):
    """Replace a section of audio with new content. v2 only."""
    api_key = _get_api_key()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    if end <= start:
        console.print("[red]--end must be greater than --start[/red]")
        raise typer.Exit(code=1)

    payload = {
        "audio_base64": _encode_audio(audio),
        "sections": [[start, end]],
        "lyrics": lyrics,
        "selection_crop": crop_to_section,
        "output_format": output_format,
        "tags": tag_list,
    }
    if prompt:
        payload["prompt"] = prompt

    url = f"{BASE_URL}/generations/v2/inpaint"
    logger.info(f"Inpainting {audio.name} [{start:.1f}s-{end:.1f}s]...")

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload, headers=_headers(api_key))
        resp.raise_for_status()
        result = resp.json()

    task_id = result.get("task_id")
    if not task_id:
        console.print(f"[red]No task_id: {result}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Inpaint task: {task_id}[/green]")
    _poll_and_download(api_key, task_id, out, poll_interval, timeout)


@app.command("status")
def check_status(
    task_id: str = typer.Option(..., "--task-id", help="Task ID to check"),
    download: Optional[Path] = typer.Option(None, "--download", "-o", help="Download if complete"),
):
    """Check status of a generation task. Optionally download if done."""
    api_key = _get_api_key()
    url = f"{BASE_URL}/generations/{task_id}"

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_headers(api_key))
        resp.raise_for_status()
        status = resp.json()

    state = status.get("status", "UNKNOWN")
    console.print(f"Status: [bold]{state}[/bold]")
    console.print(f"Model: {status.get('model_version', '?')}")

    if status.get("alignment_status"):
        console.print(f"Alignment: {status['alignment_status']}")

    if state == "SUCCESS":
        for i, path in enumerate(status.get("song_paths", [])):
            console.print(f"  Song {i+1}: {path}")

        if download:
            _poll_and_download(api_key, task_id, download, timeout=10)
    elif state == "FAILURE":
        console.print(f"[red]Error: {status.get('error_message', 'unknown')}[/red]")

    # Print full metadata as JSON
    console.print(json.dumps(status, indent=2, default=str))


@app.command("credits")
def check_credits():
    """Check remaining Sonauto API credits."""
    api_key = _get_api_key()
    url = f"{BASE_URL}/credits/balance"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, headers=_headers(api_key))
        resp.raise_for_status()
        data = resp.json()

    console.print(f"Subscription credits: [bold]{data.get('num_credits', '?')}[/bold]")
    console.print(f"Pay-as-you-go credits: [bold]{data.get('num_credits_payg', '?')}[/bold]")


if __name__ == "__main__":
    app()
