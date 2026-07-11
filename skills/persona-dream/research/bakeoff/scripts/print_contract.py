#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from persona_dream_av_bakeoff.contract import load_contract  # noqa: E402

print(json.dumps(load_contract(None), indent=2, ensure_ascii=False))
