#!/usr/bin/env python3
"""
Sanity script: Pillow (PIL) image validation
Purpose: Verify PIL can validate and load image files
Documentation: https://pillow.readthedocs.io/

Exit codes:
  0 = PASS (dependency works)
  1 = FAIL (dependency broken)
"""
import sys
import base64
from io import BytesIO

try:
    from PIL import Image
except ImportError as e:
    print(f"FAIL: Pillow not installed: {e}")
    print("Run: pip install Pillow")
    sys.exit(1)

try:
    # Create a minimal test image in memory
    img = Image.new('RGB', (100, 100), color='blue')

    # Test saving to bytes (for base64 encoding)
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    # Test base64 encoding for HTML embedding
    b64_data = base64.b64encode(buffer.read()).decode('utf-8')
    data_uri = f"data:image/png;base64,{b64_data[:50]}..."  # truncate for display

    # Test loading from bytes
    buffer.seek(0)
    loaded = Image.open(buffer)
    assert loaded.size == (100, 100), f"Size mismatch: {loaded.size}"

    print(f"PASS: PIL creates, saves, encodes, and loads images correctly")
    print(f"  Created: 100x100 RGB image")
    print(f"  Data URI prefix: {data_uri}")
    sys.exit(0)

except Exception as e:
    print(f"FAIL: Error with PIL operations: {e}")
    sys.exit(1)
