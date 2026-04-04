"""ksml_bridge - ingest-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console
from utils import get_ffmpeg_bin, run_subprocess, format_hms

console = Console()

class KSMLBridge:
    """Bridge to convert movie metadata and frames into KSML."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.ref_dir = output_dir / "assets" / "ref"
        self.ref_dir.mkdir(parents=True, exist_ok=True)

    def extract_keyframes(self, video_path: Path, num_frames: int = 3) -> List[Path]:
        """Extract keyframes from the video clip to use as reference images."""
        frames = []
        try:
            # We'll extract frames at 25%, 50%, and 75% of the duration
            # But for a short clip, we can just take them at intervals
            import subprocess
            
            # Get duration
            cmd = [get_ffmpeg_bin(), "-i", str(video_path)]
            result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            import re
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.?\d*)', result.stderr)
            duration = 0
            if match:
                h, m, s = match.groups()
                duration = int(h) * 3600 + int(m) * 60 + float(s)
            
            if duration <= 0:
                duration = 10 # Fallback
                
            intervals = [duration * (i + 1) / (num_frames + 1) for i in range(num_frames)]
            
            for i, timestamp in enumerate(intervals):
                frame_path = self.ref_dir / f"frame_{i}.jpg"
                cmd = [
                    get_ffmpeg_bin(), "-y",
                    "-ss", format_hms(timestamp),
                    "-i", str(video_path),
                    "-frames:v", "1",
                    "-q:v", "2",
                    str(frame_path)
                ]
                run_subprocess(cmd, timeout_sec=30)
                if frame_path.exists():
                    frames.append(frame_path)
                    
            return frames
        except Exception as e:
            console.print(f"[yellow]Warning: Keyframe extraction failed: {e}[/yellow]")
            return []

    def analyze_frame(self, frame_path: Path) -> Dict[str, str]:
        """Analyze a frame using scillm VLM for cinematographic details."""
        import base64
        import httpx

        try:
            # Fetch cinematographic knowledge from memory via Unix socket
            cinematography_context = "High cinematic quality."
            try:
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as mem_client:
                    resp = mem_client.post("/recall", json={"q": "cinematography camera lighting", "k": 3})
                    if resp.status_code == 200:
                        cinematography_context = resp.text
            except Exception:
                pass

            prompt = (
                f"Context from memory: {cinematography_context}\n\n"
                "Analyze this movie frame for cinematographic details: "
                "Lighting (mood, direction), Composition (rule of thirds, framing), "
                "Color Palette (dominant colors), and Emotion. "
                "Use the provided context to guide your technical description. "
                "Output a concise breakdown."
            )

            # Encode frame as base64 for VLM
            image_data = base64.b64encode(frame_path.read_bytes()).decode()
            image_url = f"data:image/jpeg;base64,{image_data}"

            payload = {
                "model": "deepseek-ai/DeepSeek-V3",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }
            resp = httpx.post(
                "http://localhost:4001/v1/chat/completions",
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            return {"analysis": content} if content else {"analysis": "High cinematic quality."}
        except Exception as e:
            console.print(f"[yellow]Warning: scillm analysis failed for {frame_path.name}: {e}[/yellow]")
            return {"analysis": "High cinematic quality."}

    def create_ksml(self, movie_title: str, clip_video: Path, persona_json_path: Path) -> Path:
        """Create a KSML script from movie metadata."""
        try:
            with open(persona_json_path, "r") as f:
                persona_data = json.load(f)
            
            frames = self.extract_keyframes(clip_video)
            
            # Simple KSML structure
            ksml_data = {
                "version": "0.1",
                "project": {
                    "name": f"Study: {movie_title}",
                    "source": "ingest-movie",
                    "original_clip": str(clip_video.absolute())
                },
                "shots": []
            }
            
            # Map persona segments/transcript to shots
            meta = persona_data.get("meta", {})
            transcript = persona_data.get("full_text", "")
            emotion = persona_data.get("emotional_dimensions", {}).get("primary_emotion", "neutral")
            scene = meta.get("scene", "Unknown")
            
            # Create a shot for each frame extracted
            for i, frame in enumerate(frames):
                console.print(f"[dim]Analyzing frame {i+1}/{len(frames)}...[/dim]")
                analysis = self.analyze_frame(frame)
                
                shot = {
                    "id": f"shot_{i+1}",
                    "prompt": f"A scene from {movie_title} depicting {scene}. {emotion} emotion. {analysis['analysis']}",
                    "reference_image": str(frame.absolute()),
                    "duration": 5.0, # Default
                    "voiceover": transcript if i == 0 else "" # Put transcript on first shot
                }
                ksml_data["shots"].append(shot)
            
            ksml_path = self.output_dir / "project.ksml"
            with open(ksml_path, "w") as f:
                yaml.dump(ksml_data, f, sort_keys=False)
                
            console.print(f"[green]✓ KSML produced: {ksml_path}[/green]")
            return ksml_path
            
        except Exception as e:
            console.print(f"[red]Error producing KSML: {e}[/red]")
            raise
