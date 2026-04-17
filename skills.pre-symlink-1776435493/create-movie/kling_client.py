"""kling_client - create-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import time
import json
import jwt
import httpx
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console

console = Console()

KLING_BASE_URL = "https://api.klingai.com"

def _get_kling_keys() -> tuple[str, str]:
    """Get KLING_ACCESS_KEY and KLING_SECRET_KEY from environment."""
    ak = os.environ.get("KLING_ACCESS_KEY")
    sk = os.environ.get("KLING_SECRET_KEY")
    if not ak or not sk:
        raise ValueError("KLING_ACCESS_KEY or KLING_SECRET_KEY not set")
    return ak, sk

def _generate_token(access_key: str, secret_key: str) -> str:
    """Generate JWT token for Kling API."""
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        "iss": access_key,
        "exp": int(time.time()) + 1800, # 30 mins
        "nbf": int(time.time()) - 5
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256", headers=headers)
    return token

def submit_shot(shot: Dict[str, Any], output_path: Path, dry_run: bool = False) -> bool:
    """Submit a shot to native Kling API."""
    if dry_run:
        console.print(f"[dim]Dry run: Would submit shot {shot.get('id')} to Kling[/dim]")
        return True

    try:
        ak, sk = _get_kling_keys()
        token = _generate_token(ak, sk)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        mode = shot.get("mode", "t2v")
        prompt = _compile_prompt(shot)
        
        # Native Kling V1 payload
        data = {
            "model": "kling-v1",
            "prompt": prompt,
            "duration": shot.get("duration", "5"), # "5" or "10"
            "aspect_ratio": shot.get("aspect_ratio", "16:9"),
        }

        # Negative prompt
        if "negative_prompt" in shot:
            data["negative_prompt"] = shot["negative_prompt"]

        endpoint = "/v1/videos/text2video"
        
        # Image-to-Video
        if "i2v" in mode or mode == "i2v":
            endpoint = "/v1/videos/image2video"
            start_img = shot.get("storyboard", {}).get("generated_url")
            if start_img:
                data["image"] = start_img
            else:
                console.print("[yellow]Warning: I2V mode but no image URL. Falling back to T2V.[/yellow]")
                endpoint = "/v1/videos/text2video"

        console.print(f"[cyan]Submitting to Kling ({endpoint})...[/cyan]")
        
        resp = httpx.post(f"{KLING_BASE_URL}{endpoint}", headers=headers, json=data)
        if resp.status_code != 200:
            console.print(f"[red]Kling API Error ({resp.status_code}): {resp.text}[/red]")
            return False

        task_id = resp.json().get("data", {}).get("task_id")
        if not task_id:
            console.print(f"[red]No task_id in response: {resp.text}[/red]")
            return False

        # Polling
        return _poll_task(task_id, token, output_path)

    except Exception as e:
        console.print(f"[red]Kling Error: {e}[/red]")
        return False

def _poll_task(task_id: str, token: str, output_path: Path) -> bool:
    """Poll task status until complete."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{KLING_BASE_URL}/v1/videos/{task_id}"
    
    console.print(f"[dim]Polling task {task_id}...[/dim]")
    
    max_attempts = 60 # 10 mins
    for _ in range(max_attempts):
        resp = httpx.get(url, headers=headers)
        if resp.status_code != 200:
            console.print(f"[red]Poll error: {resp.text}[/red]")
            return False
            
        data = resp.json().get("data", {})
        status = data.get("task_status")
        
        if status == "succeed":
            videos = data.get("video_result", [])
            if videos:
                video_url = videos[0].get("url")
                _download_video(video_url, output_path)
                return True
        elif status == "failed":
            console.print(f"[red]Task failed: {data.get('task_status_msg')}[/red]")
            return False
            
        time.sleep(10)
        
    console.print("[red]Polling timed out[/red]")
    return False

def _compile_prompt(shot: Dict[str, Any]) -> str:
    """Compile KSML shot fields into a single Kling prompt."""
    parts = []
    if "visual" in shot:
        vis = shot["visual"]
        for key in ["environment", "subject", "action"]:
            if vis.get(key): parts.append(vis[key])

    if "camera" in shot:
        cam = shot["camera"]
        if cam.get("framing"): parts.append(f"Framing: {cam['framing']}")
        if cam.get("movement"): parts.append(f"Camera movement: {cam['movement']}")

    return ". ".join(parts)

def _download_video(url: str, output_path: Path):
    """Download video from URL."""
    console.print(f"[dim]Downloading {output_path.name}...[/dim]")
    with httpx.stream("GET", url) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=8192):
                f.write(chunk)
    console.print(f"[green]✓ Saved to {output_path}[/green]")

