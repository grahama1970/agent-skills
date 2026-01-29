"""
Animatic Assembler for create-storyboard skill.

Combines generated panels into a video animatic using FFmpeg.
Supports MP4 output and interactive HTML gallery.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AnimaticConfig:
    """Configuration for animatic assembly."""
    fps: int = 24
    default_duration: float = 3.0  # seconds per panel if not specified
    transition: str = "fade"  # fade, cut, dissolve
    transition_duration: float = 0.5
    audio_track: Optional[Path] = None


def create_concat_file(
    panels: list[Path],
    durations: list[float],
    output_path: Path
) -> Path:
    """Create FFmpeg concat demuxer input file."""
    with open(output_path, 'w') as f:
        for panel, duration in zip(panels, durations):
            f.write(f"file '{panel.absolute()}'\n")
            f.write(f"duration {duration}\n")
        # Repeat last frame to avoid cut-off
        if panels:
            f.write(f"file '{panels[-1].absolute()}'\n")
    return output_path


def assemble_mp4(
    panels_dir: Path,
    shot_plan: dict,
    output_path: Path,
    config: Optional[AnimaticConfig] = None
) -> Path:
    """
    Assemble panels into MP4 video.
    
    Args:
        panels_dir: Directory containing panel images
        shot_plan: Shot plan with timing info
        output_path: Output MP4 path
        config: Animatic configuration
        
    Returns:
        Path to generated MP4
    """
    if config is None:
        config = AnimaticConfig()
    
    # Collect panels and durations
    panels = sorted(panels_dir.glob("panel_*.png"))
    if not panels:
        raise ValueError(f"No panels found in {panels_dir}")
    
    # Get durations from shot plan
    shots = shot_plan.get('shots', [])
    durations = []
    for i, panel in enumerate(panels):
        if i < len(shots):
            durations.append(shots[i].get('duration', config.default_duration))
        else:
            durations.append(config.default_duration)
    
    # Create concat file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_file = Path(f.name)
        for panel, duration in zip(panels, durations):
            f.write(f"file '{panel.absolute()}'\n")
            f.write(f"duration {duration}\n")
        # Repeat last frame
        if panels:
            f.write(f"file '{panels[-1].absolute()}'\n")
    
    try:
        # Build FFmpeg command
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-vf', f'fps={config.fps},format=yuv420p',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
        ]
        
        # Add audio if provided
        if config.audio_track and config.audio_track.exists():
            cmd.extend(['-i', str(config.audio_track), '-c:a', 'aac', '-shortest'])
        
        cmd.append(str(output_path))
        
        # Run FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        return output_path
        
    finally:
        # Cleanup
        concat_file.unlink(missing_ok=True)


def generate_html_gallery(
    panels_dir: Path,
    shot_plan: dict,
    output_path: Path
) -> Path:
    """
    Generate an interactive HTML gallery for the storyboard.
    
    Features:
    - Clickable panels with metadata
    - Timeline navigation
    - Keyboard controls
    """
    panels = sorted(panels_dir.glob("panel_*.png"))
    shots = shot_plan.get('shots', [])
    
    # Build panel data
    panel_data = []
    for i, panel in enumerate(panels):
        shot = shots[i] if i < len(shots) else {}
        panel_data.append({
            'src': panel.name,
            'scene': shot.get('scene_number', 1),
            'shot': shot.get('shot_number', 1),
            'code': shot.get('shot_code', 'MS'),
            'name': shot.get('shot_name', ''),
            'duration': shot.get('duration', 3),
            'movement': shot.get('camera_movement', 'static'),
            'description': shot.get('description', ''),
            'lens': shot.get('lens_suggestion', '50mm')
        })
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Storyboard: {shot_plan.get('title', 'Untitled')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }}
        header {{
            background: #16213e;
            padding: 1rem 2rem;
            border-bottom: 1px solid #0f3460;
        }}
        h1 {{ font-size: 1.5rem; font-weight: 500; }}
        .stats {{ color: #888; font-size: 0.9rem; margin-top: 0.5rem; }}
        
        .viewer {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem;
        }}
        
        .panel-container {{
            position: relative;
            max-width: 960px;
            width: 100%;
        }}
        
        .panel-img {{
            width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }}
        
        .info-bar {{
            background: #16213e;
            padding: 1rem;
            border-radius: 8px;
            margin-top: 1rem;
            max-width: 960px;
            width: 100%;
        }}
        
        .info-row {{
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
        }}
        
        .info-item {{
            display: flex;
            flex-direction: column;
        }}
        
        .info-label {{ color: #888; font-size: 0.75rem; text-transform: uppercase; }}
        .info-value {{ font-size: 1rem; margin-top: 0.25rem; }}
        
        .description {{
            margin-top: 1rem;
            color: #aaa;
            font-style: italic;
        }}
        
        .timeline {{
            display: flex;
            gap: 4px;
            margin-top: 2rem;
            flex-wrap: wrap;
            justify-content: center;
            max-width: 960px;
        }}
        
        .timeline-item {{
            width: 60px;
            height: 34px;
            background: #0f3460;
            border-radius: 4px;
            cursor: pointer;
            overflow: hidden;
            border: 2px solid transparent;
            transition: all 0.2s;
        }}
        
        .timeline-item:hover {{ border-color: #e94560; }}
        .timeline-item.active {{ border-color: #e94560; }}
        
        .timeline-item img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .controls {{
            margin-top: 1rem;
            display: flex;
            gap: 1rem;
        }}
        
        .btn {{
            background: #0f3460;
            border: none;
            color: #eee;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            transition: background 0.2s;
        }}
        
        .btn:hover {{ background: #e94560; }}
        
        .keyboard-hint {{
            margin-top: 1rem;
            color: #666;
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1>{shot_plan.get('title', 'Storyboard')}</h1>
        <div class="stats">
            {len(panels)} shots • {shot_plan.get('total_duration', 0):.1f}s total
        </div>
    </header>
    
    <div class="viewer">
        <div class="panel-container">
            <img id="panel-img" class="panel-img" src="" alt="Panel">
        </div>
        
        <div class="info-bar">
            <div class="info-row">
                <div class="info-item">
                    <span class="info-label">Scene/Shot</span>
                    <span class="info-value" id="info-scene">-</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Shot Type</span>
                    <span class="info-value" id="info-shot">-</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Duration</span>
                    <span class="info-value" id="info-duration">-</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Camera</span>
                    <span class="info-value" id="info-camera">-</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Lens</span>
                    <span class="info-value" id="info-lens">-</span>
                </div>
            </div>
            <div class="description" id="info-desc">-</div>
        </div>
        
        <div class="timeline" id="timeline"></div>
        
        <div class="controls">
            <button class="btn" onclick="prev()">← Previous</button>
            <button class="btn" onclick="play()">▶ Play</button>
            <button class="btn" onclick="next()">Next →</button>
        </div>
        
        <div class="keyboard-hint">
            Use ← → arrow keys to navigate, Space to play/pause
        </div>
    </div>
    
    <script>
        const panels = {json.dumps(panel_data)};
        let currentIndex = 0;
        let isPlaying = false;
        let playInterval = null;
        
        function updatePanel(index) {{
            if (index < 0 || index >= panels.length) return;
            currentIndex = index;
            
            const p = panels[index];
            document.getElementById('panel-img').src = p.src;
            document.getElementById('info-scene').textContent = `S${{p.scene}} - ${{p.shot}}`;
            document.getElementById('info-shot').textContent = `${{p.code}} (${{p.name}})`;
            document.getElementById('info-duration').textContent = `${{p.duration.toFixed(1)}}s`;
            document.getElementById('info-camera').textContent = p.movement;
            document.getElementById('info-lens').textContent = p.lens;
            document.getElementById('info-desc').textContent = p.description || '-';
            
            // Update timeline
            document.querySelectorAll('.timeline-item').forEach((el, i) => {{
                el.classList.toggle('active', i === index);
            }});
        }}
        
        function next() {{
            updatePanel((currentIndex + 1) % panels.length);
        }}
        
        function prev() {{
            updatePanel((currentIndex - 1 + panels.length) % panels.length);
        }}
        
        function play() {{
            if (isPlaying) {{
                clearInterval(playInterval);
                isPlaying = false;
            }} else {{
                isPlaying = true;
                const tick = () => {{
                    const duration = panels[currentIndex].duration * 1000;
                    playInterval = setTimeout(() => {{
                        next();
                        if (currentIndex < panels.length - 1) {{
                            tick();
                        }} else {{
                            isPlaying = false;
                        }}
                    }}, duration);
                }};
                tick();
            }}
        }}
        
        // Build timeline
        const timeline = document.getElementById('timeline');
        panels.forEach((p, i) => {{
            const item = document.createElement('div');
            item.className = 'timeline-item' + (i === 0 ? ' active' : '');
            item.innerHTML = `<img src="${{p.src}}" alt="Shot ${{i+1}}">`;
            item.onclick = () => updatePanel(i);
            timeline.appendChild(item);
        }});
        
        // Keyboard controls
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowLeft') prev();
            if (e.key === 'ArrowRight') next();
            if (e.key === ' ') {{ e.preventDefault(); play(); }}
        }});
        
        // Initialize
        updatePanel(0);
    </script>
</body>
</html>
"""
    
    output_path.write_text(html_content)
    return output_path


def assemble(
    panels_dir: Path,
    shot_plan_path: Path,
    output_path: Path,
    format: str = 'mp4',
    config: Optional[AnimaticConfig] = None
) -> Path:
    """
    Main assembly function.
    
    Args:
        panels_dir: Directory with panel images
        shot_plan_path: Path to shot plan JSON
        output_path: Output file path
        format: 'mp4' or 'html'
        config: Optional configuration
        
    Returns:
        Path to output file
    """
    shot_plan = json.loads(shot_plan_path.read_text())
    
    if format == 'html':
        return generate_html_gallery(panels_dir, shot_plan, output_path)
    else:
        return assemble_mp4(panels_dir, shot_plan, output_path, config)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python animatic_assembler.py <panels_dir> [--shot-plan plan.json] [--output out.mp4] [--format mp4|html]")
        sys.exit(1)
    
    panels_dir = Path(sys.argv[1])
    shot_plan_path = None
    output_path = Path("animatic.mp4")
    format_type = "mp4"
    
    for i, arg in enumerate(sys.argv):
        if arg == '--shot-plan' and i + 1 < len(sys.argv):
            shot_plan_path = Path(sys.argv[i + 1])
        elif arg == '--output' and i + 1 < len(sys.argv):
            output_path = Path(sys.argv[i + 1])
        elif arg == '--format' and i + 1 < len(sys.argv):
            format_type = sys.argv[i + 1]
    
    if shot_plan_path is None:
        # Create minimal shot plan
        panels = sorted(panels_dir.glob("panel_*.png"))
        shot_plan = {"title": "Animatic", "shots": [{"duration": 3.0} for _ in panels]}
        shot_plan_path = panels_dir / "shot_plan.json"
        shot_plan_path.write_text(json.dumps(shot_plan))
    
    result = assemble(panels_dir, shot_plan_path, output_path, format_type)
    print(f"Created: {result}")
