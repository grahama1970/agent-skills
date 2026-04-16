#!/usr/bin/env python3
"""
Waveform visualization for voice-lab.
Provides ASCII waveform for terminal/agent and HTML for interactive viewing.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import typer


@dataclass
class AudioStats:
    """Statistics about an audio file."""
    duration_sec: float
    sample_rate: int
    channels: int
    peak_db: float
    rms_db: float
    min_amplitude: float
    max_amplitude: float


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load audio file and return samples + sample rate."""
    try:
        import soundfile as sf
        audio, sr = sf.read(str(path))
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)  # Convert to mono
        return audio, sr
    except ImportError:
        # Fallback to scipy
        from scipy.io import wavfile
        sr, audio = wavfile.read(str(path))
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        # Normalize to -1, 1
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0
        return audio, sr


def compute_stats(audio: np.ndarray, sample_rate: int) -> AudioStats:
    """Compute audio statistics."""
    duration = len(audio) / sample_rate
    peak = np.max(np.abs(audio))
    rms = np.sqrt(np.mean(audio ** 2))

    # Convert to dB (avoid log of zero)
    peak_db = 20 * np.log10(peak + 1e-10)
    rms_db = 20 * np.log10(rms + 1e-10)

    return AudioStats(
        duration_sec=duration,
        sample_rate=sample_rate,
        channels=1,
        peak_db=peak_db,
        rms_db=rms_db,
        min_amplitude=float(np.min(audio)),
        max_amplitude=float(np.max(audio)),
    )


def resample_for_display(audio: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Resample audio to display width, returning min/max per column."""
    samples_per_col = len(audio) // width
    if samples_per_col == 0:
        samples_per_col = 1

    mins = []
    maxs = []

    for i in range(width):
        start = i * samples_per_col
        end = min(start + samples_per_col, len(audio))
        chunk = audio[start:end]
        if len(chunk) > 0:
            mins.append(np.min(chunk))
            maxs.append(np.max(chunk))
        else:
            mins.append(0)
            maxs.append(0)

    return np.array(mins), np.array(maxs)


def ascii_waveform(
    audio: np.ndarray,
    sample_rate: int,
    width: int = 80,
    height: int = 16,
    title: Optional[str] = None,
) -> str:
    """Generate ASCII waveform visualization."""
    stats = compute_stats(audio, sample_rate)
    mins, maxs = resample_for_display(audio, width - 4)  # Leave room for borders

    # Normalize to display height
    amplitude_range = max(abs(mins.min()), abs(maxs.max()), 0.001)
    half_height = height // 2

    # Create character grid
    grid = [[' ' for _ in range(width - 4)] for _ in range(height)]

    # Unicode block characters for different fill levels
    blocks = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']

    for col in range(width - 4):
        # Get amplitude at this column
        min_val = mins[col] / amplitude_range  # -1 to 0
        max_val = maxs[col] / amplitude_range  # 0 to 1

        # Convert to row positions (center is half_height)
        center_row = half_height

        # Draw positive amplitude (above center)
        if max_val > 0:
            top_row = center_row - int(max_val * half_height)
            for row in range(top_row, center_row):
                # Calculate fill level for this row
                row_pos = (center_row - row) / half_height
                if row_pos <= max_val:
                    fill = min(8, int((max_val - row_pos) * 16))
                    grid[row][col] = blocks[fill]

        # Draw negative amplitude (below center)
        if min_val < 0:
            bottom_row = center_row + int(abs(min_val) * half_height)
            for row in range(center_row, min(bottom_row + 1, height)):
                row_pos = (row - center_row) / half_height
                if row_pos <= abs(min_val):
                    fill = min(8, int((abs(min_val) - row_pos) * 16))
                    grid[row][col] = blocks[fill]

        # Always mark center line
        grid[center_row][col] = '─' if grid[center_row][col] == ' ' else grid[center_row][col]

    # Build output string
    lines = []

    # Title bar
    title_text = title or "Waveform"
    title_line = f" {title_text} ({stats.duration_sec:.1f}s, {stats.sample_rate}Hz)"
    lines.append('┌' + '─' * (width - 2) + '┐')
    lines.append('│' + title_line.ljust(width - 2) + '│')
    lines.append('├' + '─' * (width - 2) + '┤')

    # Waveform
    for row in grid:
        lines.append('│ ' + ''.join(row) + ' │')

    # Stats bar
    lines.append('├' + '─' * (width - 2) + '┤')
    stats_line = f" Duration: {stats.duration_sec:.1f}s | Peak: {stats.peak_db:.1f}dB | RMS: {stats.rms_db:.1f}dB"
    lines.append('│' + stats_line.ljust(width - 2) + '│')
    lines.append('└' + '─' * (width - 2) + '┘')

    return '\n'.join(lines)


def html_waveform(
    audio: np.ndarray,
    sample_rate: int,
    audio_path: Path,
    output_path: Optional[Path] = None,
) -> str:
    """Generate interactive HTML waveform viewer."""
    stats = compute_stats(audio, sample_rate)

    # Resample for display (500 points is good for web)
    display_width = 500
    mins, maxs = resample_for_display(audio, display_width)

    # Convert to JSON-safe format
    waveform_data = {
        "mins": mins.tolist(),
        "maxs": maxs.tolist(),
        "duration": stats.duration_sec,
        "sampleRate": sample_rate,
        "peakDb": stats.peak_db,
        "rmsDb": stats.rms_db,
    }

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Lab - Waveform Viewer</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ margin-bottom: 20px; color: #00d4ff; }}
        .waveform-container {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        canvas {{
            width: 100%;
            height: 200px;
            background: #0f0f23;
            border-radius: 4px;
            cursor: pointer;
        }}
        .controls {{
            display: flex;
            gap: 10px;
            margin-top: 15px;
            align-items: center;
        }}
        button {{
            background: #00d4ff;
            color: #1a1a2e;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
        }}
        button:hover {{ background: #00a3cc; }}
        .time-display {{
            font-family: monospace;
            font-size: 14px;
            color: #888;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-top: 20px;
        }}
        .stat {{
            background: #16213e;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #00d4ff;
        }}
        .stat-label {{
            font-size: 12px;
            color: #888;
            margin-top: 5px;
        }}
        audio {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Voice Lab - Waveform Viewer</h1>

        <div class="waveform-container">
            <canvas id="waveform"></canvas>
            <div class="controls">
                <button id="playBtn">Play</button>
                <button id="stopBtn">Stop</button>
                <span class="time-display">
                    <span id="currentTime">0:00.0</span> / <span id="totalTime">{stats.duration_sec:.1f}</span>s
                </span>
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{stats.duration_sec:.2f}s</div>
                <div class="stat-label">Duration</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats.sample_rate}</div>
                <div class="stat-label">Sample Rate</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats.peak_db:.1f}dB</div>
                <div class="stat-label">Peak Level</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats.rms_db:.1f}dB</div>
                <div class="stat-label">RMS Level</div>
            </div>
        </div>

        <audio id="audio" src="{audio_path.name}"></audio>
    </div>

    <script>
        const waveformData = {json.dumps(waveform_data)};
        const canvas = document.getElementById('waveform');
        const ctx = canvas.getContext('2d');
        const audio = document.getElementById('audio');
        const playBtn = document.getElementById('playBtn');
        const stopBtn = document.getElementById('stopBtn');
        const currentTimeEl = document.getElementById('currentTime');

        // High DPI canvas
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);

        let playheadPosition = 0;

        function drawWaveform() {{
            const width = rect.width;
            const height = rect.height;
            const centerY = height / 2;

            ctx.clearRect(0, 0, width, height);

            // Draw waveform
            const barWidth = width / waveformData.mins.length;

            for (let i = 0; i < waveformData.mins.length; i++) {{
                const x = i * barWidth;
                const minVal = waveformData.mins[i];
                const maxVal = waveformData.maxs[i];

                // Draw bar
                const barTop = centerY - (maxVal * centerY * 0.9);
                const barBottom = centerY - (minVal * centerY * 0.9);

                ctx.fillStyle = i < playheadPosition ? '#00d4ff' : '#4a9eff';
                ctx.fillRect(x, barTop, barWidth - 1, barBottom - barTop);
            }}

            // Draw center line
            ctx.strokeStyle = '#333';
            ctx.beginPath();
            ctx.moveTo(0, centerY);
            ctx.lineTo(width, centerY);
            ctx.stroke();

            // Draw playhead
            const playheadX = (playheadPosition / waveformData.mins.length) * width;
            ctx.strokeStyle = '#ff0066';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(playheadX, 0);
            ctx.lineTo(playheadX, height);
            ctx.stroke();
            ctx.lineWidth = 1;
        }}

        function updateTime() {{
            const time = audio.currentTime;
            const mins = Math.floor(time / 60);
            const secs = (time % 60).toFixed(1);
            currentTimeEl.textContent = `${{mins}}:${{secs.padStart(4, '0')}}`;

            playheadPosition = (time / waveformData.duration) * waveformData.mins.length;
            drawWaveform();

            if (!audio.paused) {{
                requestAnimationFrame(updateTime);
            }}
        }}

        playBtn.addEventListener('click', () => {{
            audio.play();
            requestAnimationFrame(updateTime);
        }});

        stopBtn.addEventListener('click', () => {{
            audio.pause();
            audio.currentTime = 0;
            playheadPosition = 0;
            drawWaveform();
            currentTimeEl.textContent = '0:00.0';
        }});

        canvas.addEventListener('click', (e) => {{
            const clickX = e.offsetX;
            const progress = clickX / rect.width;
            audio.currentTime = progress * waveformData.duration;
            playheadPosition = progress * waveformData.mins.length;
            drawWaveform();
            updateTime();
        }});

        // Initial draw
        drawWaveform();
    </script>
</body>
</html>'''

    if output_path:
        output_path.write_text(html)

    return html


def main(
    audio_file: str = typer.Argument(..., help="Audio file to visualize"),
    width: int = typer.Option(80, help="ASCII width"),
    height: int = typer.Option(16, help="ASCII height"),
    html: bool = typer.Option(False, help="Generate HTML viewer"),
    output: Optional[str] = typer.Option(None, help="Output path for HTML"),
):
    """CLI for waveform visualization."""

    if not audio_file.exists():
        print(f"Error: File not found: {audio_file}")
        return 1

    audio, sr = load_audio(audio_file)

    if html:
        output_path = output or audio_file.with_suffix('.html')
        html_waveform(audio, sr, audio_file, output_path)
        print(f"Generated HTML viewer: {output_path}")
    else:
        print(ascii_waveform(audio, sr, width, height, audio_file.name))

    return 0


if __name__ == "__main__":
    exit(main())
