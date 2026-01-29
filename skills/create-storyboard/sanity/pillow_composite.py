#!/usr/bin/env python3
"""
Sanity script: Pillow composite operations
Purpose: Verify Pillow can composite images with text overlays
Exit codes: 0=PASS, 1=FAIL, 42=CLARIFY
"""
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("FAIL: Pillow not installed. Run: pip install pillow")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
FIXTURE_DIR = SCRIPT_DIR / "fixtures"
FIXTURE_DIR.mkdir(exist_ok=True)

try:
    # Test 1: Create base image
    base = Image.new("RGB", (640, 480), color=(40, 40, 60))
    
    # Test 2: Draw on image
    draw = ImageDraw.Draw(base)
    draw.rectangle([50, 50, 590, 430], outline=(100, 100, 120), width=2)
    draw.text((280, 220), "WIDE SHOT", fill=(255, 255, 255))
    
    # Test 3: Create overlay with transparency
    overlay = Image.new("RGBA", (200, 50), color=(0, 0, 0, 128))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.text((10, 15), "Scene 1 - Shot 1", fill=(255, 255, 255))
    
    # Test 4: Composite overlay onto base
    base_rgba = base.convert("RGBA")
    base_rgba.paste(overlay, (10, 10), overlay)
    
    # Test 5: Save result
    output_path = FIXTURE_DIR / "composite_test.png"
    base_rgba.convert("RGB").save(output_path)
    
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"PASS: Created composite image at {output_path}")
        output_path.unlink()  # Clean up
        sys.exit(0)
    else:
        print("FAIL: Output file not created or empty")
        sys.exit(1)
        
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
