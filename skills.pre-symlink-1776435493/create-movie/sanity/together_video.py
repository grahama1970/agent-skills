#!/usr/bin/env python3
"""
Sanity test: Together AI video generation.

Submits a 5-second test clip via Together AI Seedance-Lite
and verifies the video downloads successfully.

Usage:
    python sanity/together_video.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Load .env from nearest parent + monorepo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)
_root_env = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

key = os.environ.get("TOGETHER_API_KEY", "")
if not key:
    print("FAIL: TOGETHER_API_KEY not set")
    sys.exit(1)
print(f"TOGETHER_API_KEY: {key[:8]}...")

# Import renderer
from core.together_renderer import TogetherRenderer

renderer = TogetherRenderer(model="seedance-lite")
print(f"Renderer: {renderer.name}")
print(f"Model ID: {renderer.model_id}")

# Generate a 5-second test clip
with tempfile.TemporaryDirectory() as tmpdir:
    output_path = Path(tmpdir) / "sanity_test.mp4"
    print(f"\nSubmitting 5s test clip...")
    print(f"Prompt: 'A single candle flame flickering in darkness, close-up, cinematic'")

    result = renderer.render_shot(
        prompt="A single candle flame flickering in darkness, close-up, cinematic",
        output_path=output_path,
        duration_s=5,
        aspect_ratio="16:9",
    )

    if result.success:
        size_kb = output_path.stat().st_size / 1024
        print(f"\nPASS: Video generated successfully")
        print(f"  File: {output_path.name}")
        print(f"  Size: {size_kb:.1f} KB")
        print(f"  Cost: ${result.cost_estimate}")
    else:
        print(f"\nFAIL: {result.error}")
        sys.exit(1)
