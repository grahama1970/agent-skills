#!/usr/bin/env python3
"""YouTube transcript extraction CLI - thin entry point.

This module provides backward compatibility with the original monolithic script.
All functionality has been modularized into the youtube_transcripts package.

See cli.py for the full implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add skill directory to path for package imports
SKILL_DIR = Path(__file__).resolve().parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# Import and run CLI
from cli import app

if __name__ == "__main__":
    app()
