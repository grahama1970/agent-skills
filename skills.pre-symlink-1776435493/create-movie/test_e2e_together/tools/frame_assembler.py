#!/usr/bin/env python3
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
            f.write(f"file '{frame.absolute()}'\n")
            f.write(f"duration {duration_per_frame}\n")

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
