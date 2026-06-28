"""CDP proof for Watch modal live tracking overlays.

This script verifies the browser-facing rung that endpoint receipts do not
cover: a user can open a Watch movie-segment modal and see event-stream-backed
tracking boxes rendered in the page.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = (
    ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_modal_tracking_overlay_browser_proof"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3014/#watch")
    parser.add_argument("--row-time", default="01:36")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--wait-seconds", type=float, default=45.0)
    parser.add_argument("--cdp-port", type=int, default=9222)
    args = parser.parse_args()

    surf_dir = find_surf_dir()
    sys.path.insert(0, str(surf_dir))
    from cdp_client import CDPController  # type: ignore

    subprocess.run([str(surf_dir / "run.sh"), "cdp", "start", "--headless"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    cdp = CDPController(port=args.cdp_port)
    try:
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1600, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        cdp.send("Network.clearBrowserCache")
        cdp.navigate(cache_busted_url(args.url))
        cdp.send("Page.bringToFront")
        time.sleep(2)

        clicked = cdp.evaluate(click_tracking_button_js(args.row_time))
        if not clicked.get("clicked"):
            raise RuntimeError(f"could not click tracking overlay button for row {args.row_time}: {clicked}")

        deadline = time.time() + args.wait_seconds
        proof: dict[str, Any] = {}
        while time.time() < deadline:
            time.sleep(1)
            proof = cdp.evaluate(modal_tracking_probe_js())
            if proof.get("modal") and proof.get("box_count", 0) > 0:
                break

        args.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        screenshot_path = args.out_dir / f"{stamp}.png"
        receipt_path = args.out_dir / f"{stamp}.receipt.json"
        cdp.screenshot(output_path=str(screenshot_path), full_page=False)

        receipt = {
            "schema": "watch.modal_tracking_overlay_browser_proof.v1",
            "status": "MODAL_BOXES_RENDERED" if proof.get("box_count", 0) > 0 else "MODAL_BOXES_NOT_RENDERED",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "url": args.url,
            "row_time": args.row_time,
            "screenshot": str(screenshot_path),
            "proof": proof,
            "clicked": clicked,
            "claim_boundary": (
                "Browser proof shows the Watch modal rendered tracking boxes from "
                "the live tracker event stream. Candidate entity labels are still "
                "provisional and do not prove promoted character identity."
            ),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"receipt": str(receipt_path), "status": receipt["status"], "proof": proof}, indent=2, sort_keys=True))
        return 0 if proof.get("box_count", 0) > 0 else 1
    finally:
        cdp.close()


def find_surf_dir() -> Path:
    candidates = [
        Path("/home/graham/workspace/experiments/pi-mono/.pi/skills/surf"),
        ROOT / ".pi" / "skills" / "surf",
        ROOT / "skills" / "surf",
    ]
    for candidate in candidates:
        if (candidate / "run.sh").exists() and (candidate / "cdp_client.py").exists():
            return candidate
    raise FileNotFoundError("could not find surf CDP skill")


def click_tracking_button_js(row_time: str) -> str:
    return f"""
(() => {{
  const rowTime = {json.dumps(row_time)};
  const buttons = Array.from(document.querySelectorAll('button[title="Open event-backed tracking overlay"]'));
  const target = buttons.find((button) => {{
    const article = button.closest('article');
    if (!article) return false;
    const lines = (article.innerText || '').split(/\\n+/).map((item) => item.trim()).filter(Boolean);
    return lines[0] === rowTime;
  }});
  if (!target) {{
    return {{
      clicked: false,
      row_time: rowTime,
      button_count: buttons.length,
      article_texts: buttons.map((button) => (button.closest('article')?.innerText || '').slice(0, 160)),
    }};
  }}
  target.scrollIntoView({{ block: 'center', inline: 'center' }});
  target.click();
  return {{
    clicked: true,
    row_time: rowTime,
    button_count: buttons.length,
    article_text: (target.closest('article')?.innerText || '').slice(0, 240),
  }};
}})()
"""


def cache_busted_url(url: str) -> str:
    parts = urlsplit(url)
    query = f"{parts.query}&" if parts.query else ""
    query += f"watch_modal_tracking_proof={int(time.time())}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def modal_tracking_probe_js() -> str:
    return """
(() => {
  const modal = document.querySelector('[data-watch-tracking-modal="true"]');
  const boxes = Array.from(document.querySelectorAll('[data-watch-tracking-box="true"]'));
  const empty = document.querySelector('[data-watch-tracking-empty="true"]');
  return {
    modal: Boolean(modal),
    modal_text: modal ? (modal.innerText || '').slice(0, 500) : null,
    box_count: boxes.length,
    empty_visible: Boolean(empty),
    boxes: boxes.slice(0, 8).map((box) => {
      const rect = box.getBoundingClientRect();
      return {
        track_id: box.getAttribute('data-track-id'),
        track_time: box.getAttribute('data-track-time'),
        text: (box.innerText || '').trim(),
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) },
      };
    }),
  };
})()
"""


if __name__ == "__main__":
    raise SystemExit(main())
