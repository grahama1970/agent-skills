#!/usr/bin/env python3
"""
/ask learn entry point -- delegates to pipeline module.

This file exists so that `run.sh learn` can call `python3 learn.py`
while the actual implementation lives in the split modules.
"""
import sys
from pathlib import Path

# Add parent directory to path so modules can import each other
sys.path.insert(0, str(Path(__file__).parent))

from pipeline import app

if __name__ == "__main__":
    app()
