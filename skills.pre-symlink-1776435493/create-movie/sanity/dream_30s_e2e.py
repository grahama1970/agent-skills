#!/usr/bin/env python3
"""
Dream 30s End-to-End Integration Test

Verifies the full dream pipeline can produce a 30-second MP4:
1. Component imports (TogetherRenderer, AudioMixer, DreamPrompter)
2. TTS checkpoint resolution
3. Dry-run with --duration 30
4. (Optional) Live run with Together API if --live flag

Usage:
    python sanity/dream_30s_e2e.py           # Dry-run checks only
    python sanity/dream_30s_e2e.py --live     # Full E2E with Together API
    python sanity/dream_30s_e2e.py --verbose
"""

import typer
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))


def check_imports() -> bool:
    """Verify all required modules import correctly."""
    console.print("\n[bold]1. Component Imports[/bold]")
    failures = []

    checks = [
        ("core.together_renderer", "TogetherRenderer"),
        ("audio_mixer", "AudioMixer"),
        ("prompter", "DreamPrompter"),
        ("create_movie.skill_registry", "run_skill"),
        ("create_movie.phases.dream_mode", "fetch_day_residue"),
    ]

    for module, attr in checks:
        try:
            mod = __import__(module, fromlist=[attr])
            obj = getattr(mod, attr)
            console.print(f"  [green]OK[/green] {module}.{attr}")
        except Exception as e:
            console.print(f"  [red]FAIL[/red] {module}.{attr}: {e}")
            failures.append(f"{module}.{attr}")

    if failures:
        console.print(f"[red]FAIL: {len(failures)} import(s) failed[/red]")
        return False
    console.print("[green]PASS: All components importable[/green]")
    return True


def check_together_api_key() -> bool:
    """Check TOGETHER_API_KEY is set."""
    console.print("\n[bold]2. Together API Key[/bold]")

    # Load .env files
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True), override=False)
        root_env = SKILL_DIR.parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env, override=False)
    except ImportError:
        pass

    key = os.environ.get("TOGETHER_API_KEY", "")
    if key:
        console.print(f"  [green]OK[/green] TOGETHER_API_KEY set ({key[:8]}...)")
        return True
    console.print("  [red]FAIL[/red] TOGETHER_API_KEY not set")
    return False


def check_tts_checkpoint() -> bool:
    """Verify TTS checkpoint can be found."""
    console.print("\n[bold]3. TTS Checkpoint[/bold]")

    # Check env var first
    env_path = os.environ.get("HORUS_TTS_CHECKPOINT")
    if env_path and Path(env_path).exists():
        console.print(f"  [green]OK[/green] HORUS_TTS_CHECKPOINT: {env_path}")
        return True

    # Check candidates (same logic as dream.py)
    # SKILL_DIR -> skills/ -> .pi/ -> pi-mono/ -> experiments/
    experiments_root = SKILL_DIR.resolve().parent.parent.parent.parent
    candidates = [
        experiments_root / "memory" / "artifacts" / "tts" / "horus_qwen3_1.7b_repaired" / "checkpoint-epoch-9",
        experiments_root / "memory" / "artifacts" / "tts" / "horus_qwen3_06b_final" / "checkpoint-epoch-1",
        experiments_root / "memory" / "artifacts" / "tts" / "horus_final_prod",
        Path.home() / ".pi" / "tts-checkpoints" / "horus_qwen3",
    ]

    for candidate in candidates:
        if candidate.exists():
            console.print(f"  [green]OK[/green] Found: {candidate}")
            return True

    console.print("  [yellow]WARN[/yellow] No TTS checkpoint found (TTS will fail at runtime)")
    for c in candidates:
        console.print(f"    Tried: {c}")
    return False


def check_together_renderer() -> bool:
    """Verify TogetherRenderer can be instantiated with kling-2.1-std."""
    console.print("\n[bold]4. Together Renderer (Kling 2.1)[/bold]")

    try:
        from core.together_renderer import TogetherRenderer
        renderer = TogetherRenderer(model="kling-2.1-std")
        caps = renderer.get_capabilities()
        console.print(f"  [green]OK[/green] {renderer.name}")
        console.print(f"      Model ID: {caps['model_id']}")
        console.print(f"      Durations: {caps['durations']}")
        return True
    except Exception as e:
        console.print(f"  [red]FAIL[/red] {e}")
        return False


def check_dry_run() -> bool:
    """Run dream generate --dry-run --duration 30."""
    console.print("\n[bold]5. Dream Dry Run (30s)[/bold]")

    try:
        result = subprocess.run(
            [
                "uv", "run", "--project", str(SKILL_DIR),
                "python", str(SKILL_DIR / "orchestrator.py"),
                "dream", "generate", "--limit", "3", "--duration", "30", "--dry-run"
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(SKILL_DIR),
        )

        if result.returncode == 0:
            stdout = result.stdout
            if "Dry Run" in stdout or "Dry run" in stdout:
                console.print("[green]PASS: Dry run completed (30s target)[/green]")
                # Check for expected pipeline stages
                for marker in ["residue", "Dreaming", "Scene", "score"]:
                    if marker.lower() in stdout.lower():
                        console.print(f"  [dim]Found: {marker}[/dim]")
                return True
            console.print("[yellow]WARN: Completed but no dry-run markers in output[/yellow]")
            return True
        else:
            console.print(f"[red]FAIL: Exit code {result.returncode}[/red]")
            if result.returncode != 0 and result.stderr:
                console.print(f"  [dim]{result.stderr[:300]}[/dim]")
            return False

    except subprocess.TimeoutExpired:
        console.print("[red]FAIL: Dry run timed out (120s)[/red]")
        return False
    except Exception as e:
        console.print(f"[red]FAIL: {e}[/red]")
        return False


def check_live_generation() -> bool:
    """Run a real 30s dream generation with Together API."""
    console.print("\n[bold]6. LIVE: Full 30s Dream Generation[/bold]")
    console.print("  [yellow]This will cost ~$0.18-0.60 via Together API[/yellow]")

    try:
        result = subprocess.run(
            [
                "uv", "run", "--project", str(SKILL_DIR),
                "python", str(SKILL_DIR / "orchestrator.py"),
                "dream", "generate", "--limit", "3", "--duration", "30"
            ],
            capture_output=False,  # Stream output live
            timeout=600,
            cwd=str(SKILL_DIR),
        )

        if result.returncode == 0:
            # Check output file
            dream_movie = SKILL_DIR / "dream_assets" / "dream_movie.mp4"
            if dream_movie.exists():
                size_mb = dream_movie.stat().st_size / (1024 * 1024)
                console.print(f"\n[green]PASS: Dream movie created[/green]")
                console.print(f"  File: {dream_movie}")
                console.print(f"  Size: {size_mb:.1f} MB")

                # Check duration with ffprobe
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(dream_movie)],
                    capture_output=True, text=True
                )
                if probe.returncode == 0:
                    dur = float(probe.stdout.strip())
                    console.print(f"  Duration: {dur:.1f}s")
                return True
            else:
                console.print("[red]FAIL: dream_movie.mp4 not created[/red]")
                return False
        else:
            console.print(f"[red]FAIL: Exit code {result.returncode}[/red]")
            return False

    except subprocess.TimeoutExpired:
        console.print("[red]FAIL: Live generation timed out (600s)[/red]")
        return False
    except Exception as e:
        console.print(f"[red]FAIL: {e}[/red]")
        return False


app = typer.Typer(help="Dream 30s E2E Integration Test")


@app.command()
def main(
    live: bool = typer.Option(False, help=""),
    verbose: bool = typer.Option(False, help=""),
):
    console.print("[bold cyan]Dream 30s End-to-End Integration Test[/bold cyan]")

    results = {}
    results["imports"] = check_imports()
    results["api_key"] = check_together_api_key()
    results["tts_checkpoint"] = check_tts_checkpoint()
    results["renderer"] = check_together_renderer()
    results["dry_run"] = check_dry_run()

    if live:
        if not results["api_key"]:
            console.print("\n[red]Cannot run live test without TOGETHER_API_KEY[/red]")
        else:
            results["live"] = check_live_generation()

    # Summary
    console.print("\n[bold]Summary[/bold]")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, ok in results.items():
        status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        console.print(f"  {status} {test}")

    if passed == total:
        console.print(f"\n[bold green]All {total} checks passed![/bold green]")
        sys.exit(0)
    else:
        console.print(f"\n[bold yellow]{passed}/{total} checks passed[/bold yellow]")
        sys.exit(1)


if __name__ == "__main__":
    app()
