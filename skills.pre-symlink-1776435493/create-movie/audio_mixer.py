"""audio_mixer - create-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional
from rich.console import Console

console = Console()

class AudioMixer:
    def __init__(self, tts_project_dir: Path, tts_checkpoint: Path):
        self.tts_project_dir = tts_project_dir
        self.tts_checkpoint = tts_checkpoint
        
    def generate_narration(self, text: str, output_path: Path, dry_run: bool = False) -> bool:
        """Generate TTS for the given text."""
        if not text:
            return False
            
        if dry_run:
            console.print(f"[dim]Dry run: Would generate TTS: '{text[:30]}...' -> {output_path}[/dim]")
            return True

        if output_path.exists():
            console.print(f"[dim]TTS already exists: {output_path}[/dim]")
            return True
            
        try:
            script_path = self.tts_project_dir / "qwen3_infer_simple.py"
            
            cmd = [
                "uv", "run", "--project", str(self.tts_project_dir),
                "python", str(script_path),
                "--text", text,
                "--output", str(output_path),
                "--model", str(self.tts_checkpoint),
                "--speaker", "horus"
            ]
            
            console.print(f"[dim]Generating TTS...[/dim]")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                console.print(f"[red]TTS failed: {result.stderr}[/red]")
                return False
                
            return True
        except Exception as e:
            console.print(f"[red]TTS Exception: {e}[/red]")
            return False

    def mix_scene_audio(self, narration_text: str, output_path: str, music_path: Optional[str] = None, sfx_path: Optional[str] = None, duration: float = 6.0, dry_run: bool = False) -> bool:
        """
        Generate narration and mix with optional SFX and background music.

        Args:
            narration_text: Text to speak.
            output_path: Path to save final audio.
            music_path: Path to background music file.
            sfx_path: Path to sound effect file.
            duration: Target duration of the clip in seconds.
            dry_run: If True, skip actual generation.
        """
        out_path = Path(output_path)
        
        if dry_run:
            console.print(f"[dim]Dry run: Would generate TTS & Mix -> {out_path}[/dim]")
            return True
            
        # 1. Generate TTS to a temporary file
        temp_voice_path = out_path.with_suffix(".voice.wav")
        if not self.generate_narration(narration_text, temp_voice_path, dry_run=False):
            console.print("[red]Failed to generate narration, skipping audio mix.[/red]")
            return False
            
        try:
            # 2. Mix with music (or just pad voice if no music)
            # We want the output to be exactly `duration` seconds.
            
            # Input 0: Voice (padded to target duration)
            # Input N: SFX (volume 50%) and/or Music (volume 30%)

            inputs = ["-i", str(temp_voice_path)]
            filter_complex = "[0:a]apad[voice]"
            input_idx = 1
            mix_streams = ["[voice]"]

            if sfx_path and os.path.exists(sfx_path):
                inputs.extend(["-i", sfx_path])
                filter_complex += f";[{input_idx}:a]volume=0.5[sfx]"
                mix_streams.append("[sfx]")
                input_idx += 1

            if music_path and os.path.exists(music_path):
                inputs.extend(["-i", music_path])
                filter_complex += f";[{input_idx}:a]volume=0.3[music]"
                mix_streams.append("[music]")
                input_idx += 1

            if len(mix_streams) > 1:
                filter_complex += f";{''.join(mix_streams)}amix=inputs={len(mix_streams)}:duration=longest[mix]"
                map_out = "[mix]"
            else:
                map_out = "[voice]"

            cmd = ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", map_out,
                "-t", str(duration), # Hard trim to target duration
                "-c:a", "aac", "-b:a", "192k",
                str(out_path)
            ]
            
            # console.print(f"[dim]Running FFmpeg: {' '.join(cmd)}[/dim]")
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Cleanup temp voice
            if temp_voice_path.exists():
                temp_voice_path.unlink()
                
            return True
            
        except subprocess.CalledProcessError as e:
            console.print(f"[red]FFmpeg Mix Failed: {e.stderr.decode() if e.stderr else str(e)}[/red]")
            if temp_voice_path.exists():
                temp_voice_path.unlink()
            return False
        except Exception as e:
            console.print(f"[red]Mixing Exception: {e}[/red]")
            return False
