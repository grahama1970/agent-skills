"""YouTube integration commands for discover-music CLI.

Pure delegation to existing skills — no bespoke yt-dlp code:
- ingest-youtube: search, download audio, transcript/lyrics extraction
- create-stems: stem separation
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
INGEST_YOUTUBE = SKILLS_DIR / "ingest-youtube"
CREATE_STEMS = SKILLS_DIR / "create-stems"

# Import ingest-youtube's Python API directly
_IY_DIR = str(INGEST_YOUTUBE)
if _IY_DIR not in sys.path:
    sys.path.insert(0, _IY_DIR)

try:
    from youtube_transcripts.downloader import search_videos, download_audio
    _IY_AVAILABLE = True
except ImportError:
    _IY_AVAILABLE = False


def _run_ingest_youtube(*args) -> subprocess.CompletedProcess:
    """Run ingest-youtube skill via run.sh (fallback when import unavailable)."""
    cmd = ["bash", str(INGEST_YOUTUBE / "run.sh")] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


def register_youtube_commands(app: typer.Typer) -> None:
    """Register YouTube commands on the main CLI app."""

    @app.command("youtube-search")
    def youtube_search(
        query: str = typer.Argument(..., help="Search query (artist + track)"),
        limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    ):
        """Search YouTube for music tracks via ingest-youtube."""
        console.print(f"[dim]Searching YouTube for: {query}[/dim]")

        if _IY_AVAILABLE:
            results = search_videos(query, max_results=limit)
        else:
            result = _run_ingest_youtube("search", query, "--max", str(limit), "--no-interactive")
            if result.returncode != 0:
                console.print(f"[red]Search failed: {result.stderr}[/red]")
                raise typer.Exit(code=1)
            try:
                results = json.loads(result.stdout)
            except json.JSONDecodeError:
                console.print("[red]Failed to parse search results[/red]")
                raise typer.Exit(code=1)

        if json_output:
            print(json.dumps(results, indent=2))
            return

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"YouTube Search: {query}")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Duration", justify="right")

        for r in results:
            dur = r.get("duration")
            dur_str = f"{dur // 60}:{dur % 60:02d}" if isinstance(dur, (int, float)) and dur else "?"
            table.add_row(r.get("id", ""), r.get("title", "")[:60], dur_str)

        console.print(table)
        console.print("\n[dim]To download: ./run.sh youtube-download <ID>[/dim]")

    @app.command("youtube-download")
    def youtube_download(
        video_id: str = typer.Argument(..., help="YouTube video ID"),
        out_dir: str = typer.Option("./downloads", "--out", "-o", help="Output directory"),
        audio_only: bool = typer.Option(True, "--audio/--video", help="Audio only (default)"),
    ):
        """Download audio from YouTube video via ingest-youtube."""
        console.print(f"[dim]Downloading {video_id} to {out_dir}...[/dim]")

        if _IY_AVAILABLE:
            audio_file, error = download_audio(video_id, Path(out_dir))
        else:
            console.print("[red]ingest-youtube not available[/red]")
            raise typer.Exit(code=1)

        if not audio_file:
            console.print(f"[red]Download failed: {error}[/red]")
            raise typer.Exit(code=1)

        console.print(f"[green]Downloaded: {audio_file}[/green]")
        return str(audio_file)

    @app.command("youtube-stems")
    def youtube_stems(
        video_id: str = typer.Argument(..., help="YouTube video ID"),
        out_dir: str = typer.Option("./work", "--out", "-o", help="Output directory"),
        model: str = typer.Option("htdemucs", "--model", "-m", help="Demucs model"),
        skip_srt: bool = typer.Option(False, "--skip-srt", help="Skip subtitle extraction"),
    ):
        """Full pipeline: download YouTube audio + lyrics -> separate stems.

        Delegates to ingest-youtube (download + lyrics) and create-stems (separation).
        """
        work_dir = Path(out_dir) / video_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Download audio via ingest-youtube
        console.print(f"[bold]Step 1/3: Downloading {video_id}...[/bold]")
        download_dir = work_dir / "download"

        if _IY_AVAILABLE:
            audio_file, error = download_audio(video_id, download_dir)
        else:
            console.print("[red]ingest-youtube not available[/red]")
            raise typer.Exit(code=1)

        if not audio_file:
            console.print(f"[red]Audio download failed: {error}[/red]")
            raise typer.Exit(code=1)
        console.print(f"[green]Downloaded: {audio_file}[/green]")

        # Step 2: Extract lyrics via ingest-youtube (3-tier fallback)
        lyrics_file = None
        if not skip_srt:
            console.print("[bold]Step 2/3: Extracting lyrics via ingest-youtube...[/bold]")
            result = _run_ingest_youtube("get", "-i", video_id)
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    full_text = data.get("full_text", "")
                    if full_text:
                        srt_dir = work_dir / "srt"
                        srt_dir.mkdir(exist_ok=True)
                        method = data.get("meta", {}).get("method", "unknown")
                        lyrics_file = srt_dir / f"{video_id}.{method}.txt"
                        lyrics_file.write_text(full_text)
                        console.print(f"[green]Lyrics ({method}): {lyrics_file}[/green]")
                    else:
                        console.print("[yellow]No lyrics available[/yellow]")
                except json.JSONDecodeError:
                    console.print("[yellow]Could not parse transcript output[/yellow]")
            else:
                console.print("[yellow]Lyrics extraction failed (continuing without)[/yellow]")
        else:
            console.print("[dim]Step 2/3: Skipping lyrics extraction[/dim]")

        # Step 3: Separate stems via create-stems
        console.print(f"[bold]Step 3/3: Separating stems with {model}...[/bold]")
        stems_dir = work_dir / "stems"

        if CREATE_STEMS.exists() and (CREATE_STEMS / "run.sh").exists():
            cmd = [
                "bash", str(CREATE_STEMS / "run.sh"),
                "separate", "--mix", str(audio_file),
                "--out", str(stems_dir), "--model", model,
            ]
        else:
            cmd = [
                sys.executable, "-m", "demucs",
                "--out", str(stems_dir), "-n", model, str(audio_file),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode != 0:
            console.print(f"[red]Stem separation failed: {result.stderr}[/red]",
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            raise typer.Exit(code=1)

        console.print(f"[green]Stems saved to: {stems_dir}[/green]")

        # Summary
        console.print(f"\n[bold]Pipeline complete:[/bold]")
        console.print(f"  Audio: {audio_file}")
        if lyrics_file:
            console.print(f"  Lyrics: {lyrics_file}")
        console.print("  Stems:")
        for stem in sorted(stems_dir.rglob("*.wav")):
            console.print(f"    - {stem.relative_to(stems_dir)}")
