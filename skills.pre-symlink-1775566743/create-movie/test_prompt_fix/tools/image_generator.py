#!/usr/bin/env python3
"""Image Generator Tool - Uses /create-image skill"""
import os
import json
import subprocess
import sys
from pathlib import Path

def generate_image(prompt: str, output_path: str, style: str = "") -> bool:
    """Generate an image using the create-image skill."""
    full_prompt = f"{style} {prompt}".strip() if style else prompt

    result = subprocess.run([
        "bash", "../create-image/run.sh",
        "generate",
        "--prompt", full_prompt,
        "--output", output_path,
    ], capture_output=True, text=True,
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )

    return result.returncode == 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python image_generator.py <prompt> <output_path> [style]")
        sys.exit(1)

    prompt = sys.argv[1]
    output = sys.argv[2]
    style = sys.argv[3] if len(sys.argv) > 3 else ""

    success = generate_image(prompt, output, style)
    sys.exit(0 if success else 1)
