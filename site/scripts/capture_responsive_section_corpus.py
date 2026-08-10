#!/usr/bin/env python3
"""Capture a responsive, section-by-section screenshot corpus for grahama.co.

This is a review-corpus generator, not a readiness gate. It uses the local Surf
CDP client to capture bounded section/page-state crops with a manifest that can
be referenced by the formal design receipts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageStat
except ImportError as exc:  # pragma: no cover - environment gate
    raise SystemExit("Pillow is required to build contact sheets") from exc

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SURF = REPO / "skills" / "surf"
sys.path.insert(0, str(SURF))

from cdp_client import CDPController  # noqa: E402

SECTIONS = [
    "top",
    "search",
    "work",
    "competence",
    "dream",
    "ledger",
    "proof",
    "receipts",
    "about",
    "contact",
]

VIEWPORTS = [
    {"id": "phone-390", "width": 390, "height": 844, "mobile": True},
    {"id": "phone-430", "width": 430, "height": 932, "mobile": True},
    {"id": "tablet-768", "width": 768, "height": 1024, "mobile": False},
    {"id": "desktop-1366", "width": 1366, "height": 768, "mobile": False},
    {"id": "desktop-1440", "width": 1440, "height": 900, "mobile": False},
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def evaluate_json(cdp: CDPController, source: str) -> dict:
    value = cdp.evaluate(source)
    if isinstance(value, str):
        return json.loads(value)
    return value


def set_viewport(cdp: CDPController, viewport: dict) -> None:
    cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": viewport["width"],
            "height": viewport["height"],
            "deviceScaleFactor": 1,
            "mobile": viewport["mobile"],
        },
    )


def wait_for_section_dom(cdp: CDPController, timeout_seconds: float = 8.0) -> dict:
    deadline = time.time() + timeout_seconds
    last: dict = {}
    while time.time() < deadline:
        last = evaluate_json(
            cdp,
            """
JSON.stringify({
  readyState: document.readyState,
  title: document.title,
  url: location.href,
  hasTop: !!document.getElementById('top'),
  sections: Array.from(document.querySelectorAll('section[id]')).map((el) => el.id),
  bodyText: (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 240)
})
            """,
        )
        if last.get("hasTop"):
            return {"status": "PASS", **last}
        time.sleep(0.25)
    return {"status": "FAIL", **last}


def capture_section(cdp: CDPController, out: Path, viewport: dict, section_id: str) -> dict:
    meta = evaluate_json(
        cdp,
        f"""
(async () => {{
  const id = {json.dumps(section_id)};
  const el = document.getElementById(id);
  if (!el) return JSON.stringify({{
    error: 'section_not_found',
    id,
    readyState: document.readyState,
    url: location.href,
    title: document.title,
    bodyText: (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 240),
    presentSectionIds: Array.from(document.querySelectorAll('section[id]')).map((s) => s.id),
  }});
  const nav = document.querySelector('nav, header');
  const navRect = nav ? nav.getBoundingClientRect() : {{ bottom: 0 }};
  const absoluteTop = el.getBoundingClientRect().top + scrollY;
  const targetY = Math.max(0, absoluteTop - (navRect.bottom || 0) - 8);
  window.scrollTo({{ top: targetY, left: 0, behavior: 'instant' }});
  for (let i = 0; i < 18; i++) {{
    await new Promise((resolve) => requestAnimationFrame(resolve));
    if (Math.abs(scrollY - targetY) < 3 || Math.abs(scrollY - Math.max(0, document.documentElement.scrollHeight - innerHeight)) < 3) break;
  }}
  const rect = el.getBoundingClientRect();
  const visibleTop = Math.max(0, rect.top, navRect.bottom > 0 ? Math.min(navRect.bottom, innerHeight - 1) : 0);
  const visibleBottom = Math.min(innerHeight, Math.max(visibleTop + 1, rect.bottom));
  const visibleLeft = Math.max(0, rect.left);
  const visibleRight = Math.min(innerWidth, Math.max(visibleLeft + 1, rect.right));
  return JSON.stringify({{
    id,
    url: location.href,
    title: document.title,
    scrollY,
    viewport: {{ width: innerWidth, height: innerHeight, dpr: devicePixelRatio || 1 }},
    section: {{
      id,
      selector: '#' + CSS.escape(id),
      text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 260),
      rect: {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom }},
    }},
    nav: {{ bottom: navRect.bottom || 0 }},
    clip: {{
      x: visibleLeft,
      y: visibleTop,
      width: visibleRight - visibleLeft,
      height: visibleBottom - visibleTop,
      scale: 1,
    }},
  }});
}})()
        """,
    )
    if meta.get("error"):
        return {"status": "FAIL", **meta}

    clip = meta["clip"]
    if clip["width"] < 20 or clip["height"] < 20:
        return {"status": "FAIL", "error": "section_not_visible", **meta}

    crop_stats = {}
    dimensions = {}
    for attempt in range(6):
        if attempt:
            time.sleep(0.45)
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(shot["data"])
        with Image.open(BytesIO(data)) as viewport_image:
            scale_x = viewport_image.width / max(1, meta["viewport"]["width"])
            scale_y = viewport_image.height / max(1, meta["viewport"]["height"])
            left = max(0, int(round(clip["x"] * scale_x)))
            top = max(0, int(round(clip["y"] * scale_y)))
            right = min(viewport_image.width, int(round((clip["x"] + clip["width"]) * scale_x)))
            bottom = min(viewport_image.height, int(round((clip["y"] + clip["height"]) * scale_y)))
            crop = viewport_image.crop((left, top, right, bottom)).convert("RGB")
            gray = crop.convert("L")
            stat = ImageStat.Stat(gray)
            hist = gray.histogram()
            total = max(1, crop.width * crop.height)
            crop_stats = {
                "attempt": attempt + 1,
                "mean": round(float(stat.mean[0]), 3),
                "stddev": round(float(stat.stddev[0]), 3),
                "bright_ratio": round(sum(hist[80:]) / total, 5),
            }
            dimensions = {"width": crop.width, "height": crop.height}
            if crop_stats["stddev"] >= 8 or crop_stats["bright_ratio"] >= 0.015:
                crop.save(out)
                break
    else:
        return {
            "status": "FAIL",
            "error": "low_information_crop",
            "id": section_id,
            "route": f"/#{section_id}",
            "viewport_id": viewport["id"],
            "viewport": viewport,
            "dimensions": dimensions,
            "image_stats": crop_stats,
            "page_state": meta,
        }

    return {
        "status": "PASS",
        "id": section_id,
        "route": f"/#{section_id}",
        "viewport_id": viewport["id"],
        "viewport": viewport,
        "path": rel(out),
        "sha256": sha256(out),
        "dimensions": dimensions,
        "image_stats": crop_stats,
        "page_state": meta,
        "intended_proof": (
            "Surf CDP section/page-state crop at a responsive viewport; "
            "not a full-page or whole-site screenshot."
        ),
    }


def draw_contact_sheet(
    images: list[dict],
    output: Path,
    title: str,
    *,
    thumb_w: int = 260,
    thumb_h: int = 170,
    cols: int = 3,
) -> None:
    pad = 18
    label_h = 54
    rows = (len(images) + cols - 1) // cols
    sheet_w = cols * thumb_w + (cols + 1) * pad
    sheet_h = 58 + rows * (thumb_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#10100f")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((pad, pad), title, fill="#eee8dc", font=font)

    for index, item in enumerate(images):
        row, col = divmod(index, cols)
        x = pad + col * (thumb_w + pad)
        y = 58 + row * (thumb_h + label_h + pad)
        with Image.open(REPO / item["path"]) as source:
            source.thumbnail((thumb_w, thumb_h))
            frame = Image.new("RGB", (thumb_w, thumb_h), "#171512")
            frame.paste(source.convert("RGB"), ((thumb_w - source.width) // 2, (thumb_h - source.height) // 2))
        sheet.paste(frame, (x, y))
        label = f'{item["viewport_id"]} / #{item["id"]}'
        draw.text((x, y + thumb_h + 8), label, fill="#e7b75f", font=font)
        draw.text((x, y + thumb_h + 26), f'{item["dimensions"]["width"]}x{item["dimensions"]["height"]}', fill="#b9ad9f", font=font)

    sheet.save(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3003/")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "design-roundtable" / "rendered-screens" / f"responsive-section-corpus-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cdp = CDPController(port=args.port)
    records: list[dict] = []
    failures: list[dict] = []
    try:
        cdp.connect()
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        for viewport in VIEWPORTS:
            set_viewport(cdp, viewport)
            cdp.navigate(args.url, wait=False)
            readiness = wait_for_section_dom(cdp)
            if readiness.get("status") != "PASS":
                failures.append(
                    {
                        "status": "FAIL",
                        "error": "page_sections_not_ready",
                        "viewport_id": viewport["id"],
                        "viewport": viewport,
                        "readiness": readiness,
                    }
                )
                continue
            viewport_records: list[dict] = []
            for index, section_id in enumerate(SECTIONS):
                filename = f'{viewport["id"]}-{index:02d}-{section_id}.png'
                record = capture_section(cdp, out_dir / filename, viewport, section_id)
                if record.get("status") != "PASS":
                    record.setdefault("viewport_id", viewport["id"])
                    record.setdefault("viewport", viewport)
                    failures.append(record)
                else:
                    records.append(record)
                    viewport_records.append(record)
            draw_contact_sheet(
                viewport_records,
                out_dir / f'{viewport["id"]}-contact-sheet.png',
                f'blind section crops / {viewport["id"]}',
            )
    finally:
        cdp.close()

    draw_contact_sheet(records, out_dir / "contact-sheet.png", "blind responsive section corpus")
    section_contact_sheets = []
    for section_id in SECTIONS:
        section_records = [record for record in records if record["id"] == section_id]
        if not section_records:
            continue
        output = out_dir / f"section-{section_id}-contact-sheet.png"
        draw_contact_sheet(
            section_records,
            output,
            f"blind section crop / #{section_id}",
            thumb_w=720,
            thumb_h=520,
            cols=1,
        )
        section_contact_sheets.append(
            {
                "section_id": section_id,
                "path": rel(output),
                "sha256": sha256(output),
                "viewports": [record["viewport_id"] for record in section_records],
            }
        )

    manifest = {
        "schema": "grahama.responsive_section_corpus.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "capture_tool": "surf-cdp Page.captureScreenshot with section scrollIntoView crops",
        "mocked": False,
        "live": True,
        "viewports": VIEWPORTS,
        "sections": SECTIONS,
        "counts": {
            "viewports": len(VIEWPORTS),
            "sections": len(SECTIONS),
            "screenshots": len(records),
            "failures": len(failures),
        },
        "review_note": (
            "Review units are section/page-state crops. Full-page screenshots are not "
            "primary evidence for this corpus. Section contact sheets preserve one "
            "section across viewport states for web-LLM and human review."
        ),
        "screenshots": records,
        "failures": failures,
        "contact_sheet": {
            "path": rel(out_dir / "contact-sheet.png"),
            "sha256": sha256(out_dir / "contact-sheet.png"),
        },
        "viewport_contact_sheets": [
            {
                "viewport_id": viewport["id"],
                "path": rel(out_dir / f'{viewport["id"]}-contact-sheet.png'),
                "sha256": sha256(out_dir / f'{viewport["id"]}-contact-sheet.png'),
            }
            for viewport in VIEWPORTS
        ],
        "section_contact_sheets": section_contact_sheets,
        "does_not_prove": [
            "blind-rater distinctiveness",
            "WCAG 2.2 AA completion",
            "performance budgets",
            "independent finish-loop review",
            "full bespoke-design READY status",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": rel(out_dir / "manifest.json"), "counts": manifest["counts"]}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
