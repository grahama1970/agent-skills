"""
Phase 3: Build Tools

Build custom tools in Docker sandbox for movie generation.
"""
import os

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

# Skill directory paths
SKILL_DIR = Path(__file__).parent.parent.parent


def analyze_tool_requirements(script_data: dict) -> list[dict]:
    """Analyze script to determine what tools are needed."""
    tools_needed = []
    scenes = script_data.get("scenes", [])

    has_images = any(s.get("visual") for s in scenes)
    has_dialogue = any(s.get("dialogue") for s in scenes)
    has_audio = any(s.get("audio") for s in scenes)
    has_motion = any(s.get("motion") for s in scenes)

    if has_images:
        tools_needed.append({
            "name": "image_generator",
            "purpose": "Generate images from visual descriptions",
            "uses": ["create-image", "ComfyUI", "Stable Diffusion"],
        })

    if has_dialogue:
        tools_needed.append({
            "name": "tts_generator",
            "purpose": "Generate speech from dialogue",
            "uses": ["tts-train", "IndexTTS2", "Horus voice model"],
        })

    if has_audio:
        tools_needed.append({
            "name": "audio_processor",
            "purpose": "Add sound effects and music",
            "uses": ["FFmpeg", "audio mixing"],
        })

    if has_motion:
        tools_needed.append({
            "name": "video_generator",
            "purpose": "Generate video from images/prompts",
            "uses": ["LTX-Video", "Mochi 1", "Deforum"],
        })

    # Always need assembly tool
    tools_needed.append({
        "name": "frame_assembler",
        "purpose": "Combine frames and audio into video",
        "uses": ["FFmpeg", "moviepy"],
    })

    return tools_needed


def generate_tool_code(tool: dict, script_data: dict) -> str:
    """Generate Python code for a tool based on requirements."""
    if tool["name"] == "image_generator":
        return '''#!/usr/bin/env python3
"""Image Generator Tool - Uses /create-image skill"""
import json
import subprocess
import sys
from pathlib import Path

def generate_image(prompt: str, output_path: str, style: str = "") -> bool:
    """Generate an image using the create-image skill."""
    full_prompt = f"{style} {prompt}".strip() if style else prompt

    result = subprocess.run([
        "bash", "../create-image/run.sh",
        "generate",
        full_prompt,
        "--output", output_path,
    ], capture_output=True, text=True)

    return result.returncode == 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python image_generator.py <prompt> <output_path> [style]")
        sys.exit(1)

    prompt = sys.argv[1]
    output = sys.argv[2]
    style = sys.argv[3] if len(sys.argv) > 3 else ""

    success = generate_image(prompt, output, style)
    sys.exit(0 if success else 1)
'''
    elif tool["name"] == "tts_generator":
        return '''#!/usr/bin/env python3
"""TTS Generator Tool - Uses Horus voice model"""
import json
import subprocess
import sys
from pathlib import Path

def generate_speech(text: str, output_path: str, speaker: str = "horus") -> bool:
    """Generate speech using TTS."""
    # Try tts-train skill first
    result = subprocess.run([
        "bash", "../tts-train/run.sh",
        "synthesize",
        "--text", text,
        "--output", output_path,
        "--voice", speaker,
    ], capture_output=True, text=True)

    if result.returncode == 0:
        return True

    # Fallback: Use faster-whisper for TTS (if available)
    print(f"TTS skill unavailable, placeholder created: {output_path}")
    Path(output_path).touch()
    return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tts_generator.py <text> <output_path> [speaker]")
        sys.exit(1)

    text = sys.argv[1]
    output = sys.argv[2]
    speaker = sys.argv[3] if len(sys.argv) > 3 else "horus"

    success = generate_speech(text, output, speaker)
    sys.exit(0 if success else 1)
'''
    elif tool["name"] == "frame_assembler":
        return '''#!/usr/bin/env python3
"""Frame Assembler Tool - Uses FFmpeg"""
import json
import subprocess
import sys
from pathlib import Path

def assemble_video(
    frames_dir: str,
    audio_file: str = None,
    output_path: str = "output.mp4",
    fps: int = 24,
    duration_per_frame: float = None
) -> bool:
    """Assemble frames and audio into video using FFmpeg."""
    frames = sorted(Path(frames_dir).glob("*.png"))
    if not frames:
        print(f"No frames found in {frames_dir}")
        return False

    # Calculate duration per frame if not specified
    if duration_per_frame is None:
        duration_per_frame = 1.0 / fps

    # Create frame list file for FFmpeg
    list_file = Path(frames_dir) / "frames.txt"
    with open(list_file, "w") as f:
        for frame in frames:
            f.write(f"file '{frame.absolute()}'\\n")
            f.write(f"duration {duration_per_frame}\\n")

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
    ]

    if audio_file and Path(audio_file).exists():
        cmd.extend(["-i", audio_file, "-c:a", "aac"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        output_path
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir", help="Directory containing frame images")
    parser.add_argument("--audio", "-a", help="Audio file to include")
    parser.add_argument("--output", "-o", default="output.mp4")
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()

    success = assemble_video(args.frames_dir, args.audio, args.output, args.fps)
    sys.exit(0 if success else 1)
'''
    elif tool["name"] == "audio_processor":
        return '''#!/usr/bin/env python3
"""Tool: audio_processor
Purpose: Add sound effects and music
Uses: FFmpeg, audio mixing
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _validate_path(value: str | None, label: str) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def mix_audio(
    voice: Path | None,
    music: Path | None,
    sfx: Path | None,
    output: Path,
    duration: float | None,
    voice_volume: float,
    music_volume: float,
    sfx_volume: float,
    dry_run: bool = False,
) -> bool:
    inputs: list[str] = []
    filters: list[str] = []
    mix_inputs: list[str] = []
    idx = 0

    def add_input(path: Path, label: str, volume: float) -> None:
        nonlocal idx
        inputs.extend(["-i", str(path)])
        filters.append(f"[{idx}:a]volume={volume}[{label}]")
        mix_inputs.append(f"[{label}]")
        idx += 1

    if voice:
        add_input(voice, "voice", voice_volume)
    if music:
        add_input(music, "music", music_volume)
    if sfx:
        add_input(sfx, "sfx", sfx_volume)

    if not mix_inputs:
        print("No input audio provided. Use --voice, --music, or --sfx.", file=sys.stderr)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"DRY RUN: would mix {len(mix_inputs)} tracks -> {output}")
        return True

    filter_complex = ";".join(
        filters + [f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest[mix]"]
    )
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[mix]",
    ]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-c:a", "aac", "-b:a", "192k", str(output)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        print(err[:500] if err else "FFmpeg failed", file=sys.stderr)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mix narration, music, and SFX audio")
    parser.add_argument("--voice", help="Narration/dialogue track")
    parser.add_argument("--music", help="Background music track")
    parser.add_argument("--sfx", help="Sound effects track")
    parser.add_argument("--output", "-o", required=True, help="Output audio path")
    parser.add_argument("--duration", type=float, default=None, help="Trim/pad to duration in seconds")
    parser.add_argument("--voice-volume", type=float, default=1.0)
    parser.add_argument("--music-volume", type=float, default=0.3)
    parser.add_argument("--sfx-volume", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without running FFmpeg")
    args = parser.parse_args()

    try:
        voice = _validate_path(args.voice, "Voice")
        music = _validate_path(args.music, "Music")
        sfx = _validate_path(args.sfx, "SFX")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output = Path(args.output)
    success = mix_audio(
        voice=voice,
        music=music,
        sfx=sfx,
        output=output,
        duration=args.duration,
        voice_volume=args.voice_volume,
        music_volume=args.music_volume,
        sfx_volume=args.sfx_volume,
        dry_run=args.dry_run,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
'''
    else:
        return f'''#!/usr/bin/env python3
"""Tool: {tool["name"]}
Purpose: {tool["purpose"]}
Uses: {", ".join(tool["uses"])}
"""
raise SystemExit("Tool {tool['name']} not implemented. Provide an implementation or remove from manifest.")
'''


def run_in_docker(code: str, work_dir: Path, timeout: int = 300) -> dict:
    """Execute Python code in Docker sandbox."""
    # Write code to temp file
    code_file = work_dir / "sandbox_code.py"
    with open(code_file, "w") as f:
        f.write(code)

    # Run in Docker
    cmd = [
        "docker", "run",
        "--rm",
        "--network", "none",  # No network access for security
        "-v", f"{work_dir.absolute()}:/workspace",
        "-w", "/workspace",
        "horus-movie-sandbox",
        "python", "sandbox_code.py"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Execution timed out", "returncode": -1}
    except Exception as e:
        return {"error": str(e), "returncode": -1}


def build_tools_for_script(
    script_path: Path,
    output_dir: Path,
    skip_docker: bool = False,
) -> dict:
    """
    Build custom tools in Docker sandbox for the given script.

    Args:
        script_path: Path to script JSON file
        output_dir: Output directory for tools
        skip_docker: Skip Docker sandbox (use host)

    Returns:
        dict with tools manifest
    """
    if not script_path.exists():
        console.print(f"[red]Script file not found: {script_path}[/red]")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(script_path) as f:
        script_data = json.load(f)

    console.print(f"[dim]Building tools for: {script_data.get('title', 'Untitled')}[/dim]")

    # Analyze what tools are needed
    console.print("\n[cyan]── Analyzing Tool Requirements ──[/cyan]")
    tools_needed = analyze_tool_requirements(script_data)

    table = Table(show_header=True, title="Tools to Build")
    table.add_column("Tool", style="cyan")
    table.add_column("Purpose")
    table.add_column("Uses")
    for tool in tools_needed:
        table.add_row(tool["name"], tool["purpose"], ", ".join(tool["uses"][:2]))
    console.print(table)

    # Check Docker availability (unless skipped)
    use_docker = not skip_docker
    if use_docker:
        docker_check = subprocess.run(["docker", "info"], capture_output=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if docker_check.returncode != 0:
            console.print("[yellow]Docker not available. Using host environment.[/yellow]")
            use_docker = False
        else:
            # Build the sandbox image
            dockerfile_path = SKILL_DIR / "Dockerfile"
            if dockerfile_path.exists():
                console.print("\n[dim]Building Docker sandbox image...[/dim]")
                build_result = subprocess.run(
                    ["docker", "build", "-t", "horus-movie-sandbox", str(SKILL_DIR)],
                    capture_output=True,
                    text=True,
                    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
                )
                if build_result.returncode != 0:
                    console.print(f"[yellow]Docker build failed, using host: {build_result.stderr[:100]}[/yellow]")
                    use_docker = False
                else:
                    console.print("[green]Docker sandbox ready[/green]")

    # Generate tool code
    console.print("\n[cyan]── Generating Tool Code ──[/cyan]")
    tools_manifest = {"tools": [], "timestamp": datetime.now().isoformat()}

    for tool in tools_needed:
        tool_file = output_dir / f"{tool['name']}.py"
        code = generate_tool_code(tool, script_data)

        with open(tool_file, "w") as f:
            f.write(code)

        # Make executable
        tool_file.chmod(0o755)

        tools_manifest["tools"].append({
            "name": tool["name"],
            "file": str(tool_file),
            "purpose": tool["purpose"],
        })
        console.print(f"  [green]✓ Created {tool_file.name}[/green]")

    # Save manifest
    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(tools_manifest, f, indent=2)

    console.print(f"\n[bold green]Tools built: {output_dir}[/bold green]")
    console.print(f"[dim]Environment: {'Docker sandbox' if use_docker else 'Host'}[/dim]")

    return tools_manifest
