"""
Phase 5: Assemble

Assemble final output as MP4 or interactive HTML.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

# Skill directory paths
SKILL_DIR = Path(__file__).parent.parent.parent


def create_ffmpeg_concat_file(images: list, durations: list, output_file: Path) -> Path:
    """Create an FFmpeg concat demuxer file for images."""
    concat_file = output_file.parent / "concat.txt"
    with open(concat_file, "w") as f:
        for img, duration in zip(images, durations):
            f.write(f"file '{img}'\n")
            f.write(f"duration {duration}\n")
        # Repeat last frame to avoid duration issues
        if images:
            f.write(f"file '{images[-1]}'\n")
    return concat_file


def assemble_veo_clips(assets_path: Path, output_path: Path, fps: int = 24) -> bool:
    """Assemble Veo-rendered video clips into a single MP4 using FFmpeg concat."""
    veo_dir = assets_path / "veo"
    clips = sorted(veo_dir.glob("*.mp4"))

    if not clips:
        return False

    console.print(f"[dim]Concatenating {len(clips)} Veo clips[/dim]")

    # Create FFmpeg concat file for video clips
    concat_file = output_path.parent / "veo_concat.txt"
    with open(concat_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip.absolute()}'\n")

    # Concatenate with re-encoding for consistent format
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-movflags", "+faststart",
        str(output_path),
    ]

    console.print("[dim]Running FFmpeg concat...[/dim]")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and output_path.exists():
        return True
    else:
        console.print(f"[red]FFmpeg concat error: {result.stderr[:200]}[/red]")
        return False


def assemble_mp4(assets_path: Path, manifest: dict, output_path: Path, fps: int = 24) -> bool:
    """Assemble images and audio into MP4 using FFmpeg."""
    # First check for Veo video clips (higher priority than images)
    veo_dir = assets_path / "veo"
    if veo_dir.exists() and list(veo_dir.glob("*.mp4")):
        return assemble_veo_clips(assets_path, output_path, fps)

    images_dir = assets_path / "images"
    audio_dir = assets_path / "audio"

    # Get sorted images
    images = sorted(images_dir.glob("*.png"))
    if not images:
        console.print("[yellow]No images or video clips found to assemble[/yellow]")
        return False

    # Calculate duration per image
    script_data = manifest.get("script_data", {})
    total_duration = script_data.get("duration_seconds", 30)
    duration_per_image = total_duration / len(images)

    console.print(f"[dim]Assembling {len(images)} images at {duration_per_image:.2f}s each[/dim]")

    # Create concat file
    concat_file = create_ffmpeg_concat_file(
        [str(img.absolute()) for img in images],
        [duration_per_image] * len(images),
        output_path
    )

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
    ]

    # Add audio if available
    audio_files = sorted(audio_dir.glob("*.wav"))
    if audio_files:
        # Merge all audio files
        audio_list = assets_path / "audio_list.txt"
        with open(audio_list, "w") as f:
            for af in audio_files:
                f.write(f"file '{af.absolute()}'\n")

        # Concat audio
        merged_audio = assets_path / "merged_audio.wav"
        audio_merge_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(audio_list),
            "-c", "copy",
            str(merged_audio)
        ]
        subprocess.run(audio_merge_cmd, capture_output=True)

        if merged_audio.exists() and merged_audio.stat().st_size > 0:
            cmd.extend(["-i", str(merged_audio), "-c:a", "aac", "-shortest"])
            console.print(f"[dim]Including {len(audio_files)} audio tracks[/dim]")

    # Video encoding with scaling
    vf_chain = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

    # Check for LUT in manifest/preset
    preset_data = manifest.get("preset_data", {})
    lut_id = preset_data.get("post", {}).get("color", {}).get("lut_id")
    if lut_id:
        lut_path = SKILL_DIR / "assets" / "luts" / f"{lut_id}.cube"
        if lut_path.exists():
            console.print(f"[bold cyan]Applying LUT: {lut_id}[/bold cyan]")
            vf_chain += f",lut3d=file='{lut_path}'"
        else:
            console.print(f"[yellow]Warning: LUT file not found: {lut_path}[/yellow]")

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-vf", vf_chain,
        str(output_path)
    ])

    console.print(f"[dim]Running FFmpeg...[/dim]")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return True
    else:
        console.print(f"[red]FFmpeg error: {result.stderr[:200]}[/red]")
        return False


def assemble_html(assets_path: Path, manifest: dict, output_dir: Path):
    """Create interactive HTML viewer for the movie."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy assets
    assets_dest = output_dir / "assets"
    assets_dest.mkdir(exist_ok=True)

    images_dir = assets_path / "images"
    images = sorted(images_dir.glob("*.png"))

    script_data = manifest.get("script_data", {})
    scenes = script_data.get("scenes", [])
    total_duration = script_data.get("duration_seconds", 30)
    duration_per_scene = total_duration / len(scenes) if scenes else 5

    # Build scene data for player
    scene_data = []
    for i, (img, scene) in enumerate(zip(images, scenes)):
        # Copy image
        dest_img = assets_dest / img.name
        shutil.copy(img, dest_img)

        scene_data.append({
            "image": f"assets/{img.name}",
            "duration": scene.get("duration_seconds", duration_per_scene),
            "heading": scene.get("heading", f"Scene {i+1}"),
            "dialogue": scene.get("dialogue", []),
            "audio": scene.get("audio", ""),
        })

    # Create HTML
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{script_data.get("title", "Horus Movie")}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0a0a0a; color: #fff; }}
        .player {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .screen {{ position: relative; width: 100%; aspect-ratio: 16/9; background: #000; overflow: hidden; }}
        .screen img {{ width: 100%; height: 100%; object-fit: contain; }}
        .subtitle {{ position: absolute; bottom: 40px; left: 50%; transform: translateX(-50%);
                     background: rgba(0,0,0,0.8); padding: 10px 20px; border-radius: 4px;
                     max-width: 80%; text-align: center; font-size: 1.2rem; }}
        .controls {{ display: flex; gap: 10px; margin-top: 20px; justify-content: center; }}
        .controls button {{ padding: 10px 20px; font-size: 1rem; cursor: pointer;
                           background: #333; color: #fff; border: none; border-radius: 4px; }}
        .controls button:hover {{ background: #555; }}
        .progress {{ width: 100%; height: 4px; background: #333; margin-top: 10px; }}
        .progress-bar {{ height: 100%; background: #c9a227; width: 0%; transition: width 0.1s; }}
        .info {{ margin-top: 20px; padding: 20px; background: #1a1a1a; border-radius: 8px; }}
        h1 {{ color: #c9a227; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="player">
        <div class="screen">
            <img id="frame" src="" alt="Scene">
            <div id="subtitle" class="subtitle" style="display: none;"></div>
        </div>
        <div class="progress"><div id="progress-bar" class="progress-bar"></div></div>
        <div class="controls">
            <button onclick="player.prev()">⏮ Prev</button>
            <button onclick="player.toggle()" id="play-btn">▶ Play</button>
            <button onclick="player.next()">Next ⏭</button>
        </div>
        <div class="info">
            <h1>{script_data.get("title", "Untitled")}</h1>
            <p>{script_data.get("synopsis", "A Horus production")}</p>
            <p><small>Scenes: {len(scenes)} | Duration: {total_duration}s</small></p>
        </div>
    </div>
    <script>
        const scenes = {json.dumps(scene_data)};
        const player = {{
            current: 0,
            playing: false,
            timer: null,
            init() {{
                this.show(0);
            }},
            show(idx) {{
                if (idx < 0 || idx >= scenes.length) return;
                this.current = idx;
                const scene = scenes[idx];
                document.getElementById('frame').src = scene.image;
                const sub = document.getElementById('subtitle');
                if (scene.dialogue && scene.dialogue.length) {{
                    const text = scene.dialogue.map(d => typeof d === 'string' ? d : d.line).join(' ');
                    sub.textContent = text;
                    sub.style.display = 'block';
                }} else {{
                    sub.style.display = 'none';
                }}
                this.updateProgress();
            }},
            updateProgress() {{
                const pct = ((this.current + 1) / scenes.length) * 100;
                document.getElementById('progress-bar').style.width = pct + '%';
            }},
            next() {{ this.show(this.current + 1); }},
            prev() {{ this.show(this.current - 1); }},
            toggle() {{
                this.playing = !this.playing;
                document.getElementById('play-btn').textContent = this.playing ? '⏸ Pause' : '▶ Play';
                if (this.playing) this.play();
                else clearTimeout(this.timer);
            }},
            play() {{
                if (!this.playing) return;
                const scene = scenes[this.current];
                this.timer = setTimeout(() => {{
                    if (this.current < scenes.length - 1) {{
                        this.next();
                        this.play();
                    }} else {{
                        this.playing = false;
                        document.getElementById('play-btn').textContent = '▶ Play';
                    }}
                }}, (scene.duration || 5) * 1000);
            }}
        }};
        player.init();
    </script>
</body>
</html>'''

    with open(output_dir / "index.html", "w") as f:
        f.write(html_content)


def assemble_movie(
    assets_path: Path,
    output_path: Path,
    output_format: str = "mp4",
    fps: int = 24,
) -> bool:
    """
    Assemble final output as MP4 or interactive HTML.

    Args:
        assets_path: Path to assets directory
        output_path: Output file path
        output_format: Output format (mp4 or html)
        fps: Frames per second for MP4

    Returns:
        True if successful
    """
    if not assets_path.exists():
        console.print(f"[red]Assets directory not found: {assets_path}[/red]")
        sys.exit(1)

    manifest_path = assets_path / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No manifest.json found. Run generate phase first.[/red]")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    if output_format == "mp4":
        # Check FFmpeg
        ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if ffmpeg_check.returncode != 0:
            console.print("[red]FFmpeg not available.[/red]")
            sys.exit(1)

        console.print(f"[dim]Assembling MP4: {output_path}[/dim]")
        success = assemble_mp4(assets_path, manifest, output_path, fps)

        if success and output_path.exists():
            file_size = output_path.stat().st_size / (1024 * 1024)
            console.print(f"\n[bold green]Movie created: {output_path}[/bold green]")
            console.print(f"[dim]Size: {file_size:.1f} MB[/dim]")
            return True
        else:
            console.print("[red]Assembly failed[/red]")
            return False

    elif output_format == "html":
        console.print(f"[dim]Creating HTML bundle: {output_path}[/dim]")
        assemble_html(assets_path, manifest, output_path)

        html_dir = output_path.parent / output_path.stem
        html_dir.mkdir(parents=True, exist_ok=True)

        # Create basic HTML viewer structure
        index_html = html_dir / "index.html"
        with open(index_html, "w") as f:
            f.write(
                """<!DOCTYPE html>
<html>
<head>
    <title>Horus Movie</title>
    <style>
        body { font-family: sans-serif; background: #1a1a1a; color: #fff; }
        .player { max-width: 800px; margin: 0 auto; padding: 20px; }
    </style>
</head>
<body>
    <div class="player">
        <h1>Movie Player</h1>
        <div id="canvas"></div>
        <div id="controls"></div>
    </div>
    <script src="player.js"></script>
</body>
</html>"""
            )

        console.print(f"[bold green]HTML bundle created at: {html_dir}[/bold green]")
        return True

    return False
