"""veo_client - create-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import time
import json
import httpx
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console

console = Console()

VEO_MODEL = "veo-3.1-generate-preview"
VEO_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300


class VeoClient:
    """Client for Google Veo Video Generation API."""

    def __init__(self):
        self.api_key = self._get_api_key()
        self.base_url = VEO_BASE_URL

    def _get_api_key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set")
        return key

    def generate_video(self, prompt: str, model: str = VEO_MODEL, duration: str = "8") -> Optional[str]:
        """
        Generate a video from a text prompt.
        Returns the URL of the generated video or None if failed.

        Args:
            prompt: Text description of the video to generate.
            model: Veo model name.
            duration: Duration in seconds as a string. Valid values: "4", "6", "8".
        """
        url = f"{self.base_url}/models/{model}:predictLongRunning?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        # Payload - durationSeconds must be a string per API docs
        data = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "durationSeconds": str(duration)
            }
        }

        console.print(f"[cyan]Submitting to Google Veo ({model})...[/cyan]")

        # Retry loop with exponential backoff for rate limits
        backoff = INITIAL_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES + 1):
            resp = httpx.post(url, headers=headers, json=data)

            if resp.status_code == 200:
                break

            if resp.status_code == 429:
                # Rate limited - extract retry delay from header or use backoff
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after else backoff

                if attempt < MAX_RETRIES:
                    console.print(
                        f"[yellow]Rate limited (429). "
                        f"Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...[/yellow]"
                    )
                    time.sleep(wait)
                    backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                    continue
                else:
                    console.print(f"[red]Rate limited after {MAX_RETRIES} retries. Giving up.[/red]")
                    return None

            # Non-retryable error
            console.print(f"[red]Veo API Error ({resp.status_code}): {resp.text[:300]}[/red]")
            return None

        task_name = resp.json().get("name")
        if not task_name:
            return None

        return self._poll_for_url(task_name)

    def _poll_for_url(self, task_name: str) -> Optional[str]:
        """Poll task and return video URL."""
        url = f"{self.base_url}/{task_name}?key={self.api_key}"
        console.print(f"[dim]Polling operation {task_name}...[/dim]")
        
        for _ in range(120): # 20 mins max
            resp = httpx.get(url)
            if resp.status_code != 200:
                continue
                
            result = resp.json()
            if result.get("done"):
                if "error" in result:
                    console.print(f"[red]Veo Error: {result['error']}[/red]")
                    return None
                
                # Extract URL
                try:
                    response_data = result.get("response", {})
                    # Try different response formats
                    if "predictions" in response_data:
                        pred = response_data["predictions"][0]
                        uri = pred.get("video", {}).get("uri") or pred.get("uri")
                        return self._authenticate_url(uri)
                    
                    if "generateVideoResponse" in response_data:
                        samples = response_data["generateVideoResponse"].get("generatedSamples", [])
                        if samples:
                            uri = samples[0].get("video", {}).get("uri")
                            return self._authenticate_url(uri)
                except Exception as e:
                    console.print(f"[red]Parsing error: {e}[/red]")
                    return None
                    
            time.sleep(10)
            
        return None

    def _authenticate_url(self, url: str) -> str:
        """Add API key to URL if needed."""
        if not url: return ""
        if "generativelanguage.googleapis.com" in url and "key=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}key={self.api_key}"
        
        # Convert file URI to download URI if needed
        if "/files/" in url and ":download" not in url:
             url = url.replace("/v1beta/files/", "/download/v1beta/files/").split("?")[0] + ":download?alt=media&key=" + self.api_key
        return url

    def download_video(self, url: str, output_path: str):
        """Download video to path."""
        path = Path(output_path)
        console.print(f"[dim]Downloading to {path.name}...[/dim]")
        with httpx.stream("GET", url) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        console.print(f"[green]✓ Saved: {path.name}[/green]")

# Legacy/Helper function
def submit_shot(shot: Dict[str, Any], output_path: Path, dry_run: bool = False, monitor: Any = None) -> bool:
    """Submit a shot (legacy wrapper)."""
    if dry_run: return True
    
    client = VeoClient()
    prompt = _compile_prompt(shot)
    
    # Handle image if present (VeoClient.generate_video needs update if we want image support, 
    # but for now this wrapper can handle it or we simplify)
    # The current VeoClient.generate_video is text-to-video only.
    # If we need image support we should extend it. 
    # For Dream Movie, we strictly use text prompts (from scenes).
    
    url = client.generate_video(prompt)
    if url:
        client.download_video(url, str(output_path))
        return True
    return False

def _compile_prompt(shot: Dict[str, Any]) -> str:
    """Compile shot fields into a single Veo prompt.

    Handles both:
    - Compiled HorusShotSpec format: {"prompt": "...", "config": {...}}
    - Legacy KSML format: {"visual": {"subject": "..."}, "camera": {...}}
    """
    # Compiled format has prompt at top level
    if "prompt" in shot:
        return shot["prompt"]

    # Legacy KSML format
    parts = []
    if "visual" in shot:
        vis = shot["visual"]
        desc = vis.get("subject", "")
        if vis.get("action"): desc += f" {vis['action']}"
        if vis.get("environment"): desc += f" in {vis['environment']}"
        if desc: parts.append(desc)

    if "camera" in shot:
        cam = shot["camera"]
        cam_desc = []
        if cam.get("framing"): cam_desc.append(cam["framing"])
        if cam.get("movement"): cam_desc.append(cam["movement"])
        if cam_desc: parts.append(f"Cinematography: {', '.join(cam_desc)}")

    return ". ".join(parts)

