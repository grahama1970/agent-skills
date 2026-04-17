#!/usr/bin/env python
"""Entry point for interview skill — handles package path setup."""
import os
import sys

# Add parent dir so 'interview' is importable as a package
# (the interview/ dir has __init__.py, so Python recognizes it as a package)
parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent not in sys.path:
    sys.path.insert(0, parent)

from interview.interview import app

app()
