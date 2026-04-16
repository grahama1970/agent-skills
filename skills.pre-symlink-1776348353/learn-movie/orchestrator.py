#!/usr/bin/env python3
"""
Learn-Movie Orchestrator

Analyzes video files to extract cinematographic techniques and store them in memory.
"""

import json
import shutil
import subprocess
import typer
from pathlib import Path
from typing import Optional, Any, Dict
import os
from loguru import logger

# Optional toggles; default disabled to preserve current behavior
LEARN_MOVIE_FLAGS = {
    "ENABLE_EVENT_LOGGING": os.environ.get("LEARN_MOVIE_ENABLE_EVENT_LOGGING", "0") == "1",
}

def _maybe_log_event(name: str, payload: Dict[str, Any]) -> None:
    # Guarded logging to avoid side effects unless explicitly enabled
    if not LEARN_MOVIE_FLAGS["ENABLE_EVENT_LOGGING"]:
        return
    try:
        print(f"[learn-movie:event] {name}: {payload}")
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

app = typer.Typer(help="Analyze movies for cinematographic learning")

def detect_scenes_and_extract_keyframes(video_path: Path, output_dir: Path) -> list[Path]:
    """
    Use ffmpeg to detect scenes and extract a middle keyframe for each scene.
    Returns list of keyframe paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check ffmpeg
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    # Simple scene detection and extraction
    # We use select filter to find scene changes > 0.3
    # and extract the frame.
    # Note: Accurately getting the "middle" frame is hard in one pass without 2 passes,
    # so we will just take the first frame of the new scene for now.
    
    # Always extract the first frame (start) to ensure we have at least one
    start_frame = output_dir / "scene_000.png"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(start_frame)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    pattern = str(output_dir / "scene_%03d.png")
    
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", "select='gt(scene,0.3)',scale=960:-1",
        "-vsync", "vfr",
        pattern
    ]
    
    typer.echo(f"Running scene detection on {video_path.name}...")
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    
    # Return unique sorted frames (in case scene detection output scene_000 which overwrites)
    return sorted(list(set(output_dir.glob("scene_*.png"))))

def analyze_frame_with_vlm(frame_path: Path, context: str = "") -> dict:
    """
    Call scillm HTTP proxy to analyze the frame via VLM.
    """
    import base64
    import httpx

    prompt = (
        "Analyze this movie frame as a cinematographer. "
        "Provide a JSON object with keys: "
        "'shot_type' (e.g. Medium Shot), "
        "'camera_angle' (e.g. Low Angle), "
        "'lighting_key' (e.g. High Key, Chiaroscuro), "
        "'color_palette' (list of dominant colors), "
        "'emotional_tone' (adjectives), "
        "'composition' (notes on framing). "
        "Output ONLY valid JSON."
    )

    if context:
        prompt += f" Context: {context}"

    # Encode frame as base64 for VLM
    image_data = base64.b64encode(frame_path.resolve().read_bytes()).decode()
    image_url = f"data:image/png;base64,{image_data}"

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

    try:
        resp = httpx.post(
            "http://localhost:4001/v1/chat/completions",
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        output = resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        typer.echo(f"VLM Analysis fail: HTTP {e.response.status_code}", err=True)
        return {}
    except Exception as e:
        typer.echo(f"VLM Analysis fail: {e}", err=True)
        return {}

    try:
        # Simple heuristic to find JSON blob
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = output[start:end]
            return json.loads(json_str)
        else:
            return {"raw_analysis": output}

    except json.JSONDecodeError:
        return {"raw_analysis": output}

def memorize_technique(movie_title: str, scene_idx: int, analysis: dict):
    """
    Store the analysis in memory.
    """
    problem = f"Cinematographic Pattern: {movie_title} Scene {scene_idx}"
    solution = json.dumps(analysis, indent=2)

    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            client.post("/learn", json={
                "problem": problem,
                "solution": solution,
                "tags": ["cinematography", "movie_analysis"],
            })
    except Exception as e:
        print(f"Memory storage failed: {e}")

@app.callback()
def main():
    """
    Analyze a movie file for cinematographic techniques.
    """
    pass

@app.command()
def analyze(
    path: Path = typer.Argument(..., help="Path to video file", exists=True),
    director: str = typer.Option("Unknown", help="Director name for context"),
    limit: int = typer.Option(10, help="Limit number of scenes to analyze")
):
    """
    Analyze a movie file for cinematographic techniques and store in memory.
    """
    movie_title = path.stem
    typer.echo(f"Analyzing '{movie_title}' (Director: {director})...")

    # Pre-hook: Recall prior analyses for this movie
    try:
        from memory_integration import recall_prior_analyses
        prior = recall_prior_analyses(movie_title, k=5)
        if prior:
            typer.echo(f"  Recalled prior analyses from memory")
    except ImportError:
        prior = ""
    except Exception as e:
        prior = ""
        print(f"  Prior recall skipped: {e}")

    temp_dir = Path("./temp_frames")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    try:
        # 1. Detect Scenes
        frames = detect_scenes_and_extract_keyframes(path, temp_dir)
        typer.echo(f"Detected {len(frames)} scenes.")

        # 2. Analyze
        all_techniques = []
        all_scenes = []
        count = 0
        for i, frame in enumerate(frames):
            if count >= limit:
                break

            typer.echo(f"Analyzing Scene {i+1}...")
            analysis = analyze_frame_with_vlm(frame, context=f"Director: {director}")

            if analysis:
                # 3. Memorize (legacy per-scene storage)
                memorize_technique(movie_title, i+1, analysis)
                print(f"  Learned: {analysis.get('shot_type', 'Unknown')} - {analysis.get('emotional_tone', 'Unknown')}")
                all_techniques.append(analysis)
                all_scenes.append({"scene_idx": i + 1, **analysis})

            count += 1

        # Post-hook: Learn full analysis to memory with taxonomy tags
        try:
            from memory_integration import learn_analysis
            insights = [f"Director: {director}, Scenes analyzed: {len(all_scenes)}"]
            ids = learn_analysis(
                movie_name=movie_title,
                techniques=all_techniques,
                scenes=all_scenes,
                insights=insights,
            )
            if ids:
                typer.echo(f"  Stored {len(ids)} entries to memory")
        except ImportError:
            pass
        except Exception as e:
            print(f"  Memory learn skipped: {e}")

        typer.echo("Analysis complete.")

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    app()
