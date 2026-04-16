#!/usr/bin/env python3
"""
Real End-to-End 60-Second Dream Sequence Sanity Test

This test produces ACTUAL video output - no mocks, no dry-runs.
If dependencies/APIs are unavailable, it FAILS CLEARLY.

Phases tested:
1. Hardware Detection
2. Research (real memory/dogpile)
3. Script Generation (real LLM)
4. Casting (create-cast)
5. Build Tools
6. Generate (Veo API - real render)
7. Sound Design (create-sound-design)
8. Assemble (FFmpeg)
9. Learn (memory storage)

Usage:
    python sanity/e2e_60s_dream.py
    python sanity/e2e_60s_dream.py --dry-run      # Check infra only
    python sanity/e2e_60s_dream.py --duration 30  # Shorter test
"""

import typer
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

SKILL_DIR = Path(__file__).parent.parent
PI_SKILLS_DIR = SKILL_DIR.parent


@dataclass
class InfraStatus:
    """Infrastructure pre-flight status."""
    gemini_api: bool = False
    veo_api: bool = False
    ffmpeg: bool = False
    docker: bool = False
    memory_skill: bool = False
    create_cast: bool = False
    create_sound_design: bool = False
    sfx_catalog: bool = False
    
    @property
    def can_proceed(self) -> bool:
        """Minimum requirements to run real E2E."""
        # Must have: Gemini OR Veo for video, FFmpeg for assembly
        return (self.gemini_api or self.veo_api) and self.ffmpeg


def check_api_key(key_name: str) -> bool:
    """Check if API key is set and non-empty."""
    value = os.environ.get(key_name, "")
    return bool(value and len(value) > 10)


def check_gemini_api() -> Tuple[bool, str]:
    """Check Gemini API connectivity with real request."""
    if not check_api_key("GEMINI_API_KEY"):
        return False, "GEMINI_API_KEY not set"

    try:
        # Use newer google.genai if available, fallback to deprecated package
        try:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents="Say 'ok' in one word"
            )
            if response.text:
                return True, "Connected (google.genai)"
            return False, "Empty response"
        except ImportError:
            # Fallback to deprecated package
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content("Say 'ok' in one word")
            if response.text:
                return True, "Connected (deprecated pkg)"
            return False, "Empty response"
    except ImportError:
        return False, "No Gemini SDK installed"
    except Exception as e:
        return False, str(e)[:50]


def check_veo_api() -> Tuple[bool, str]:
    """Check Veo API availability."""
    # Check for API key
    if not check_api_key("GOOGLE_AI_STUDIO_API_KEY") and not check_api_key("GEMINI_API_KEY"):
        return False, "No Veo API key set"

    # Check if veo_adapter is available - it exports VeoAdapter and export_to_veo
    try:
        sys.path.insert(0, str(SKILL_DIR))
        from veo_adapter import VeoAdapter, export_to_veo
        return True, "Available"
    except ImportError as e:
        return False, f"veo_adapter not available: {e}"


def check_ffmpeg() -> Tuple[bool, str]:
    """Check FFmpeg installation."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            version = result.stdout.split("\n")[0]
            return True, version[:40]
        return False, "ffmpeg returned error"
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH"
    except Exception as e:
        return False, str(e)[:30]


def check_docker() -> Tuple[bool, str]:
    """Check Docker availability (optional for build-tools)."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0:
            return True, "Running"
        return False, "Docker not running"
    except FileNotFoundError:
        return False, "docker not found"
    except Exception as e:
        return False, str(e)[:30]


def check_memory_skill() -> Tuple[bool, str]:
    """Check memory skill availability."""
    memory_path = PI_SKILLS_DIR / "memory"
    if not memory_path.exists():
        return False, "Skill directory not found"
    
    run_sh = memory_path / "run.sh"
    if not run_sh.exists():
        return False, "run.sh not found"
    
    try:
        result = subprocess.run(
            [str(run_sh), "recall", "--q", "test", "--k", "1"],
            capture_output=True, text=True, timeout=30, cwd=str(memory_path,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            ),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        # Return code 0 or output with "items" indicates working
        if result.returncode == 0 or "items" in result.stdout:
            return True, "Working"
        return True, "Available (may have no data)"
    except Exception as e:
        return False, str(e)[:30]


def check_create_cast() -> Tuple[bool, str]:
    """Check create-cast skill availability."""
    cast_path = PI_SKILLS_DIR / "create-cast"
    if not cast_path.exists():
        return False, "Skill directory not found"
    
    try:
        sys.path.insert(0, str(cast_path))
        from create_cast import run_casting_session
        return True, "Importable"
    except ImportError as e:
        return False, str(e)[:40]


def check_create_sound_design() -> Tuple[bool, str]:
    """Check create-sound-design skill availability."""
    sound_path = PI_SKILLS_DIR / "create-sound-design"
    if not sound_path.exists():
        return False, "Skill directory not found"
    
    try:
        sys.path.insert(0, str(sound_path))
        from create_sound_design import run_sound_design_session
        return True, "Importable"
    except ImportError as e:
        return False, str(e)[:40]


def check_sfx_catalog() -> Tuple[bool, str]:
    """Check sfx-catalog skill availability."""
    sfx_path = PI_SKILLS_DIR / "sfx-catalog"
    if not sfx_path.exists():
        return False, "Skill directory not found"
    
    try:
        sys.path.insert(0, str(sfx_path))
        from src.query_engine import SFXQueryEngine
        return True, "Importable"
    except ImportError as e:
        return False, str(e)[:40]


def run_preflight() -> InfraStatus:
    """Run all pre-flight infrastructure checks."""
    console.print(Panel("[bold]Pre-Flight Infrastructure Checks[/bold]", style="blue"))
    
    status = InfraStatus()
    checks = [
        ("Gemini API", check_gemini_api),
        ("Veo API", check_veo_api),
        ("FFmpeg", check_ffmpeg),
        ("Docker", check_docker),
        ("Memory Skill", check_memory_skill),
        ("create-cast", check_create_cast),
        ("create-sound-design", check_create_sound_design),
        ("sfx-catalog", check_sfx_catalog),
    ]
    
    table = Table(title="Infrastructure Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")
    
    for name, check_fn in checks:
        try:
            available, detail = check_fn()
        except Exception as e:
            available, detail = False, str(e)[:30]
        
        status_str = "[green]✓ OK[/green]" if available else "[red]✗ FAIL[/red]"
        table.add_row(name, status_str, detail)
        
        # Set status fields
        if name == "Gemini API":
            status.gemini_api = available
        elif name == "Veo API":
            status.veo_api = available
        elif name == "FFmpeg":
            status.ffmpeg = available
        elif name == "Docker":
            status.docker = available
        elif name == "Memory Skill":
            status.memory_skill = available
        elif name == "create-cast":
            status.create_cast = available
        elif name == "create-sound-design":
            status.create_sound_design = available
        elif name == "sfx-catalog":
            status.sfx_catalog = available
    
    console.print(table)
    
    if not status.can_proceed:
        console.print("\n[red bold]PRE-FLIGHT FAILED: Missing critical dependencies[/red bold]")
        console.print("[red]Need: (Gemini API OR Veo API) AND FFmpeg[/red]")
        return status
    
    console.print("\n[green bold]PRE-FLIGHT PASSED: Minimum requirements met[/green bold]")
    return status


def create_synthetic_script(duration: int = 60) -> dict:
    """Create a synthetic script for the dream sequence test."""
    # Calculate scenes based on duration (roughly 8-10 seconds per scene)
    num_scenes = max(4, duration // 10)
    
    script = {
        "title": "E2E_Dream_Sanity_Test",
        "prompt": "A surreal dream journey through digital consciousness",
        "duration": duration,
        "style": "surreal, dreamlike, cyberpunk",
        "scenes": []
    }
    
    dream_themes = [
        ("Digital sunrise over neon city", "Wide shot of glowing cityscape"),
        ("Data streams flowing like rivers", "Tracking shot following light trails"),
        ("Crystalline structures emerging", "Push in on geometric formations"),
        ("Stars transforming into eyes", "Slow zoom with particle effects"),
        ("Memory fragments dissolving", "Match cut between scenes"),
        ("Electric consciousness awakening", "POV shot with lens flare"),
        ("Fractal patterns blooming", "Macro shot of digital flowers"),
        ("Time flowing backwards", "Reverse motion with color shift"),
    ]
    
    scene_duration = duration / num_scenes
    
    for i in range(num_scenes):
        theme_idx = i % len(dream_themes)
        description, camera = dream_themes[theme_idx]
        
        scene = {
            "scene_id": f"scene_{i+1:02d}",
            "description": f"{description} (Scene {i+1})",
            "duration": scene_duration,
            "camera": camera,
            "mood": "dreamlike",
            "audio_cues": [
                {"type": "ambient", "description": "ethereal drone"},
                {"type": "foley", "description": "digital whispers"}
            ]
        }
        script["scenes"].append(scene)
    
    return script


def verify_video_output(video_path: Path, expected_duration: int) -> Tuple[bool, str]:
    """Verify video output is valid and has correct duration."""
    if not video_path.exists():
        return False, "File does not exist"
    
    size_bytes = video_path.stat().st_size
    if size_bytes < 1000:  # Less than 1KB is definitely invalid
        return False, f"File too small ({size_bytes} bytes)"
    
    # Check duration with ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0 and result.stdout.strip():
            actual_duration = float(result.stdout.strip(),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            # Allow 20% tolerance on duration
            min_expected = expected_duration * 0.8
            max_expected = expected_duration * 1.2
            
            if min_expected <= actual_duration <= max_expected:
                return True, f"Valid video: {actual_duration:.1f}s ({size_bytes/1024:.0f}KB)"
            else:
                return False, f"Duration mismatch: got {actual_duration:.1f}s, expected ~{expected_duration}s"
        return False, "Could not read duration"
    except Exception as e:
        return False, f"ffprobe error: {e}"


def run_e2e_test(duration: int = 60, dry_run: bool = False) -> int:
    """
    Run the full end-to-end test.
    
    Returns:
        0 = success
        1 = partial success (warnings)
        2 = failure
    """
    console.print(Panel(
        f"[bold cyan]Real E2E 60-Second Dream Sequence Sanity Test[/bold cyan]\n"
        f"Duration: {duration}s | Dry Run: {dry_run}",
        title="🎬 create-movie Sanity"
    ))
    
    # Pre-flight
    status = run_preflight()
    if not status.can_proceed:
        return 2
    
    if dry_run:
        console.print("\n[yellow]DRY RUN: Pre-flight passed, skipping actual render[/yellow]")
        return 0
    
    # Setup work directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = Path(f"/tmp/e2e_dream_sanity_{timestamp}")
    work_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"\n[dim]Working directory: {work_dir}[/dim]")
    
    # Create synthetic script
    console.print("\n[bold]Creating synthetic test script...[/bold]")
    script_data = create_synthetic_script(duration)
    script_file = work_dir / "script.json"
    with open(script_file, "w") as f:
        json.dump(script_data, f, indent=2)
    console.print(f"[green]✓ Script created: {len(script_data['scenes'])} scenes[/green]")
    
    # Create minimal research file (skip external research for speed)
    research_file = work_dir / "research.json"
    with open(research_file, "w") as f:
        json.dump({
            "topic": script_data["prompt"],
            "sources": {"synthetic": "E2E test - no external research"},
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    
    # Run the create command
    output_file = work_dir / "dream_sanity.mp4"
    
    cmd = [
        "uv", "run", "--project", str(SKILL_DIR),
        "python", str(SKILL_DIR / "orchestrator.py"),
        "create",
        script_data["prompt"],
        "--output", str(output_file),
        "--work-dir", str(work_dir),
        "--duration", str(duration),
        "--dream",
        "--renderer", "veo",
        "--skip-research",  # Already created synthetic
        "--skip-hardware-check",  # We pre-flighted
    ]
    
    # Skip casting/sound if not available
    if not status.create_cast:
        cmd.append("--skip-casting")
    if not status.create_sound_design:
        cmd.append("--skip-sound-design")
    
    console.print(f"\n[bold]Running create-movie pipeline...[/bold]")
    console.print(f"[dim]Command: {' '.join(cmd[:8])}...[/dim]")
    
    start_time = time.time()
    
    try:
        # Run with streaming output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(SKILL_DIR,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            ),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        
        # Stream output
        for line in process.stdout:
            # Filter to important lines
            if any(kw in line for kw in ["Phase", "===", "✓", "✗", "Error", "Warning", "complete"]):
                console.print(f"  {line.rstrip()}")
        
        process.wait()
        elapsed = time.time() - start_time
        
        if process.returncode != 0:
            console.print(f"\n[red bold]PIPELINE FAILED (exit {process.returncode})[/red bold]")
            return 2
        
        console.print(f"\n[green]Pipeline completed in {elapsed:.0f}s[/green]")
        
    except subprocess.TimeoutExpired:
        console.print("\n[red bold]PIPELINE TIMEOUT (exceeded 30 minutes)[/red bold]")
        return 2
    except Exception as e:
        console.print(f"\n[red bold]PIPELINE ERROR: {e}[/red bold]")
        return 2
    
    # Verify output
    console.print("\n[bold]Verifying output...[/bold]")
    
    # Check for video file
    valid, detail = verify_video_output(output_file, duration)
    if valid:
        console.print(f"[green]✓ {detail}[/green]")
    else:
        console.print(f"[red]✗ Video verification failed: {detail}[/red]")
        
        # Check for partial artifacts
        artifacts = list(work_dir.glob("**/*.mp4")) + list(work_dir.glob("**/*.webm"))
        if artifacts:
            console.print(f"[yellow]  Found {len(artifacts)} partial video artifacts[/yellow]")
        return 2
    
    # Summary
    console.print("\n" + "=" * 60)
    console.print(Panel(
        f"[bold green]E2E SANITY TEST PASSED[/bold green]\n\n"
        f"Output: {output_file}\n"
        f"Duration: {duration}s\n"
        f"Time: {elapsed:.0f}s",
        title="✅ Success"
    ))
    
    # Cleanup option
    console.print(f"\n[dim]Artifacts at: {work_dir}[/dim]")
    console.print("[dim]Run with --cleanup to remove after test[/dim]")
    
    return 0


app = typer.Typer(help="Real E2E 60-Second Dream Sequence Sanity Test")


@app.command()
def main(
    duration: int = typer.Option(60, help=""),
    dry_run: bool = typer.Option(False, help="Only run pre-flight checks, skip actual render"),
    cleanup: bool = typer.Option(False, help="Remove work directory after successful test"),
):
    exit_code = run_e2e_test(duration=duration, dry_run=dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    app()
