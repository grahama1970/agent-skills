#!/usr/bin/env python3
"""council - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import sys
import json
import os
import typer
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# Add skills dir to path to access siblings if needed (though we use CLI tools mainly)
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(_SKILLS_DIR))

def run_command(cmd: str) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}\n{e.stderr}", file=sys.stderr)
        return ""

def get_persona(name: str) -> Dict[str, Any]:
    """Fetch persona details using create-persona skill."""
    cmd = f"{_SKILLS_DIR / 'create-persona' / 'run.sh'} show '{name}' --json"
    output = run_command(cmd)
    if not output:
        raise ValueError(f"Persona '{name}' not found")
    return json.loads(output)

def take_screenshot(url: str, out_path: str):
    """Use surf to take a screenshot."""
    # Ensure surf cdp is running or use surf go
    # For simplicity in this script, we assume surf cdp execution or similar
    # But surf skill CLI is: surf go URL -> surf snap
    # We will wrap this in a simple sequence
    
    print(f"Taking screenshot of {url}...")
    run_command(f"surf cdp start")
    run_command(f"surf go '{url}'")
    run_command("surf wait 2")
    run_command(f"surf snap --output '{out_path}'")
    run_command("surf cdp stop")

def analyze_with_vlm(image_path: str, prompt: str) -> str:
    """Call VLM (scillm) to analyze the image."""
    # Using scillm skill if available, or raw API
    # Since scillm skill might accept image path via CLI?
    # Checking available skills... assuming we can use 'scillm' tool or equivalent.
    # For now, we'll shell out to a hypothetical scillm CLI or construct a request
    # NOTE: In the absence of a direct 'scillm' CLI for images in the skills list (only 'scillm' for text usually?),
    # We will use the 'create-image' or 'llm' ops. 
    # Actually, let's assume `scillm-cli` or similar exists or we use `llm` tool.
    # Given the environment, we might need to implement a VLM client here or use `scillm` python lib.
    
    raise NotImplementedError("VLM image analysis not yet implemented — requires scillm image endpoint integration")

def consult_expert(expert_name: str, topic: str, context: str) -> str:
    """Ask an expert persona for advice."""
    prompt = f"As {expert_name}, please advise on {topic}. Context: {context}"
    cmd = f"{_SKILLS_DIR / 'ask' / 'run.sh'} ask '{prompt}'"
    return run_command(cmd)

def main(
    url: str = typer.Option(..., help="URL to review"),
    persona: str = typer.Option(..., help="Primary persona name"),
    out: str = typer.Option(..., help="Output directory"),
):

    # 1. Load Primary Persona
    try:
        persona = get_persona(persona)
    except Exception as e:
        print(f"Error loading persona: {e}")
        sys.exit(1)

    print(f"Primary Persona: {persona['name']}")
    
    # 2. Take Screenshot
    screenshot_path = os.path.join(out, "screenshot.png")
    take_screenshot(url, screenshot_path)

    # 3. VLM Critique (Primary)
    # Construct prompt based on Persona traits (Taxonomy)
    traits = persona.get("bridge_weights", {})
    precision = traits.get("Precision", 0.5)
    
    vlm_prompt = f"You are {persona['name']}. Your traits are {traits}. Critique this UI screenshot. Output JSON with coordinates and comments."
    critique = analyze_with_vlm(screenshot_path, vlm_prompt)
    
    # 4. Confidence Check (Council Logic)
    # If High Precision persona finds issues or is vague, consult expert
    consultation_notes = []
    if precision > 0.8: # High precision requires high confidence
         # Simplified logic: If critique contains "unsure" or "maybe", ask expert
         if "unsure" in critique.lower() or "maybe" in critique.lower():
             print("Confidence low. Consulting Expert...")
             expert_advice = consult_expert("Nielsen", "UI Usability", critique)
             consultation_notes.append(f"Consulted Nielsen: {expert_advice}")

    # 5. Output
    output_data = {
        "persona": persona["name"],
        "critique": critique,
        "consultations": consultation_notes,
        "screenshot": screenshot_path
    }
    
    out_file = os.path.join(out, "ANNOTATIONS.jsonl")
    with open(out_file, "w") as f:
        f.write(json.dumps(output_data) + "\n")
    
    print(f"Council session complete. Feedback saved to {out_file}")

if __name__ == "__main__":
    main()
