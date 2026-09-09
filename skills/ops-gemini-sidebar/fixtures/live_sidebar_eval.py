#!/usr/bin/env python3
"""Live eval for a calibrated Gemini/side-panel desktop session.

Requires:
- DISPLAY or OPS_GEMINI_SIDEBAR_DISPLAY
- OPS_GEMINI_SIDEBAR_COORDS pointing to a CoordinatePlan JSON
- an already-open Chrome Gemini/sidebar composer at those coordinates
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MARKER_PREFIX = "SIDEBARLIVEOK"


def run(argv: list[str], env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout, env=env)


def main() -> int:
    coords = Path(os.environ["OPS_GEMINI_SIDEBAR_COORDS"])
    display = os.environ.get("OPS_GEMINI_SIDEBAR_DISPLAY") or os.environ.get("DISPLAY")
    if not display:
        raise SystemExit("DISPLAY is required")
    prompt = Path(os.environ.get("OPS_GEMINI_SIDEBAR_PROMPT", "/tmp/ops-gemini-sidebar-live-prompt.txt"))
    receipt = Path(os.environ.get("OPS_GEMINI_SIDEBAR_SUBMIT_RECEIPT", "/tmp/ops-gemini-sidebar-live-submit.json"))
    screenshot = Path(os.environ.get("OPS_GEMINI_SIDEBAR_SCREENSHOT", "/tmp/ops-gemini-sidebar-live-screenshot.png"))
    crop = Path(os.environ.get("OPS_GEMINI_SIDEBAR_CROP", "/tmp/ops-gemini-sidebar-live-crop.png"))
    ocr_base = Path(os.environ.get("OPS_GEMINI_SIDEBAR_OCR_BASE", "/tmp/ops-gemini-sidebar-live-ocr"))
    result_path = Path(os.environ.get("OPS_GEMINI_SIDEBAR_RESULT", "/tmp/ops-gemini-sidebar-live-result.json"))

    marker = os.environ.get("OPS_GEMINI_SIDEBAR_MARKER") or f"{MARKER_PREFIX}{int(time.time())}"
    prompt.write_text(f"Reply with one short sentence that starts with {marker} and includes the product of 9 and 7.\n", encoding="utf-8")
    env = os.environ.copy()
    env["DISPLAY"] = display

    submit = run([
        str(ROOT / "run.sh"),
        "submit",
        "--prompt-file", str(prompt),
        "--coords", str(coords),
        "--display", display,
        "--execute",
        "--json",
    ], env)
    receipt.write_text(submit.stdout, encoding="utf-8")
    time.sleep(int(os.environ.get("OPS_GEMINI_SIDEBAR_WAIT_SECONDS", "18")))
    run(["import", "-window", "root", str(screenshot)], env, timeout=30)

    plan = json.loads(coords.read_text(encoding="utf-8"))
    img = Image.open(screenshot)
    w, h = img.size
    x1 = max(0, plan["composer"]["x"] - 1800)
    y1 = max(0, plan["composer"]["y"] - 1700)
    x2 = min(w, plan["send"]["x"] + 500)
    y2 = min(h, plan["composer"]["y"] + 80)
    img.crop((x1, y1, x2, y2)).save(crop)
    run(["tesseract", str(crop), str(ocr_base)], env, timeout=60)
    text = ocr_base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
    normalized = re.sub(r"[^A-Z0-9]", "", text.upper())
    passed = marker.upper() in normalized and "63" in normalized
    result = {
        "schema": "ops_gemini_sidebar.live_eval.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "marker": marker,
        "receipt": str(receipt),
        "screenshot": str(screenshot),
        "crop": str(crop),
        "ocr": str(ocr_base.with_suffix(".txt")),
        "ocr_excerpt": text[:1000],
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
