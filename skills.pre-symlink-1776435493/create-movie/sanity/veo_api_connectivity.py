"""veo_api_connectivity - sanity.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import httpx
from rich.console import Console

console = Console()

def check_veo_connectivity():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[yellow]SKIP: GEMINI_API_KEY not set[/yellow]")
        return
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        resp = httpx.get(url)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            # Check if any model name contains 'veo'
            veo_models = [m for m in models if "veo" in m.get("name", "").lower()]
            if veo_models:
                console.print(f"[green]PASS: Veo API connectivity OK. Found {len(veo_models)} Veo models.[/green]")
                for m in veo_models:
                    console.print(f"  - {m['name']}")
            else:
                # Veo might be restricted even if API works
                console.print("[yellow]WARN: API works but no 'veo' models found in models list. May be restricted.[/yellow]")
        else:
            console.print(f"[red]FAIL: Veo API Error ({resp.status_code}): {resp.text}[/red]")
    except Exception as e:
        console.print(f"[red]FAIL: Unexpected error: {e}[/red]")

if __name__ == "__main__":
    check_veo_connectivity()
