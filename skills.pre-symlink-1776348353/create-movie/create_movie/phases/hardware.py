"""
Phase 0: Hardware Detection

Detects GPU and RAM capabilities via /ops-workstation skill
and auto-selects optimal model variant for video generation.
"""
import os

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table
from loguru import logger

console = Console()

# Skill directory paths
SKILL_DIR = Path(__file__).parent.parent.parent
PI_SKILLS_DIR = SKILL_DIR.parent


@dataclass
class HardwareProfile:
    """Detected hardware capabilities."""
    gpu_name: str = "Unknown"
    vram_gb: int = 0
    ram_gb: int = 0
    cuda_available: bool = False

    # Auto-selected settings
    model_variant: str = "ltx2-distilled"  # Default to safest option
    resolution: str = "720p"
    max_clip_seconds: int = 10
    audio_enabled: bool = True
    weight_streaming: bool = False
    runpod_suggested: bool = False


def detect_hardware() -> HardwareProfile:
    """Detect GPU and RAM via /ops-workstation skill."""
    profile = HardwareProfile()

    # Check for ops-workstation skill in common locations
    ops_workstation_paths = [
        Path.home() / ".claude" / "skills" / "ops-workstation" / "run.sh",
        Path.home() / ".pi" / "skills" / "ops-workstation" / "run.sh",
        PI_SKILLS_DIR / "ops-workstation" / "run.sh",
    ]

    ops_workstation = None
    for path in ops_workstation_paths:
        if path.exists():
            ops_workstation = path
            break

    if not ops_workstation:
        console.print("[yellow]ops-workstation skill not found, using defaults[/yellow]")
        return profile

    # Use the new summary command for structured JSON output
    console.print("[dim]Detecting hardware via /ops-workstation summary...[/dim]")
    try:
        result = subprocess.run(
            ["bash", str(ops_workstation), "summary", "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ops_workstation.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            data = json.loads(result.stdout)

            # GPU info
            gpu = data.get("gpu", {})
            profile.gpu_name = gpu.get("name", "Unknown")
            profile.vram_gb = gpu.get("vram_free_gb", 0)  # Use free VRAM for model selection
            profile.cuda_available = gpu.get("available", False)

            # RAM info
            ram = data.get("ram", {})
            profile.ram_gb = ram.get("total_gb", 0)

            # Capabilities
            caps = data.get("capabilities", {})
            profile.weight_streaming = caps.get("weight_streaming_eligible", False)

            console.print(f"[dim]Detected: {profile.gpu_name} ({profile.vram_gb}GB free), {profile.ram_gb}GB RAM[/dim]")

    except json.JSONDecodeError as e:
        console.print(f"[yellow]Failed to parse hardware summary: {e}[/yellow]")
        # Fallback to legacy detection
        return _detect_hardware_legacy(ops_workstation)
    except Exception as e:
        console.print(f"[yellow]Hardware detection failed: {e}[/yellow]")

    return profile


def _detect_hardware_legacy(ops_workstation: Path) -> HardwareProfile:
    """Legacy hardware detection using regex parsing (fallback)."""
    import re
    profile = HardwareProfile()

    # Get GPU info
    try:
        gpu_result = subprocess.run(
            ["bash", str(ops_workstation), "gpu"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ops_workstation.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if gpu_result.returncode == 0:
            output = gpu_result.stdout
            vram_match = re.search(r'(\d+)\s*MiB.*Free', output, re.IGNORECASE)
            if vram_match:
                profile.vram_gb = int(vram_match.group(1)) // 1024
            gpu_name_match = re.search(r'(RTX\s*\w+|A\d+|Tesla\s*\w+|H100|A100)', output, re.IGNORECASE)
            if gpu_name_match:
                profile.gpu_name = gpu_name_match.group(1)
            profile.cuda_available = True
    except Exception as e:
        logger.debug("matching failed: {}", e)

    # Get RAM info
    try:
        ram_result = subprocess.run(
            ["bash", str(ops_workstation), "memory"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ops_workstation.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if ram_result.returncode == 0:
            ram_match = re.search(r'(\d+)\s*GB.*Total', ram_result.stdout, re.IGNORECASE)
            if ram_match:
                profile.ram_gb = int(ram_match.group(1))
    except Exception as e:
        logger.debug("matching failed: {}", e)

    return profile


def select_model_variant(profile: HardwareProfile) -> HardwareProfile:
    """Select optimal model variant based on detected hardware."""
    vram = profile.vram_gb
    ram = profile.ram_gb

    console.print(f"[dim]Detected: {profile.gpu_name} ({vram}GB VRAM), {ram}GB RAM[/dim]")

    # Model selection based on VRAM
    if vram >= 24:
        # High-end: RTX 4090, A5000, A6000
        profile.model_variant = "ltx2-fp8"
        profile.resolution = "1080p"
        profile.max_clip_seconds = 15
        profile.audio_enabled = True
        profile.runpod_suggested = False
    elif vram >= 16:
        # Mid-range: RTX 4080, A4000
        profile.model_variant = "ltx2-fp4"
        profile.resolution = "720p"
        profile.max_clip_seconds = 10
        profile.audio_enabled = True
        profile.runpod_suggested = False
    elif vram >= 12:
        # Entry: RTX 3060, RTX 4070
        profile.model_variant = "ltx2-distilled"
        profile.resolution = "720p"
        profile.max_clip_seconds = 8
        profile.audio_enabled = False  # Save VRAM
        profile.runpod_suggested = False
    else:
        # Insufficient VRAM
        profile.model_variant = "runpod"
        profile.resolution = "1080p"
        profile.max_clip_seconds = 15
        profile.audio_enabled = True
        profile.runpod_suggested = True

    # RAM-based optimizations
    if ram >= 128:
        profile.weight_streaming = True
        # With weight streaming, we can push limits slightly
        if profile.model_variant == "ltx2-fp8":
            profile.max_clip_seconds = 20
    elif ram >= 64:
        profile.weight_streaming = True  # Partial offloading
    else:
        profile.weight_streaming = False

    return profile


def display_hardware_profile(profile: HardwareProfile):
    """Display detected hardware and selected settings."""
    table = Table(title="Hardware Detection (Phase 0)", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_column("Setting", style="green")

    table.add_row("GPU", profile.gpu_name, "")
    table.add_row("VRAM", f"{profile.vram_gb}GB", f"Model: {profile.model_variant}")
    table.add_row("RAM", f"{profile.ram_gb}GB", f"Weight Streaming: {'ON' if profile.weight_streaming else 'OFF'}")
    table.add_row("CUDA", "Yes" if profile.cuda_available else "No", "")
    table.add_row("", "", "")
    table.add_row("Resolution", "", profile.resolution)
    table.add_row("Max Clip", "", f"{profile.max_clip_seconds}s")
    table.add_row("Audio", "", "ON" if profile.audio_enabled else "OFF")

    if profile.runpod_suggested:
        table.add_row("[yellow]RunPod[/yellow]", "", "[yellow]SUGGESTED - insufficient local VRAM[/yellow]")

    console.print(table)
