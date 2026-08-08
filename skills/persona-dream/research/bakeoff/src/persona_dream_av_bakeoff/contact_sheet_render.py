"""contact_sheet_render - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .io_utils import write_json, write_text
from .media import download, sha256_file


def parse_image_url(result: dict[str, Any]) -> str:
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            return first["url"]
        if isinstance(first, str) and first.startswith("http"):
            return first
    image = result.get("image")
    if isinstance(image, dict) and isinstance(image.get("url"), str):
        return image["url"]
    if isinstance(image, str) and image.startswith("http"):
        return image
    raise KeyError(f"No image URL found in fal result keys={list(result.keys())}")


def render_panel_fal(
    *,
    panel: dict[str, Any],
    out_dir: Path,
    model_id: str = "fal-ai/flux/dev",
    image_size: str = "landscape_16_9",
    with_logs: bool = True,
) -> dict[str, Any]:
    from .fal_utils import subscribe

    prompt = panel["prompt"]
    request = {
        "prompt": prompt,
        "image_size": image_size,
        "num_images": 1,
        "enable_safety_checker": True,
    }
    result = subscribe(model_id, request, with_logs=with_logs)
    image_url = parse_image_url(result)

    safe_panel_id = panel["panel_id"].replace("/", "_")
    image_path = download(image_url, out_dir, f"{safe_panel_id}.png")

    return {
        "panel_id": panel["panel_id"],
        "model_id": model_id,
        "request": request,
        "result": result,
        "image_url": image_url,
        "image_path": str(image_path),
        "image_sha256": sha256_file(image_path),
    }


def make_prompt_card(panel: dict[str, Any], path: Path, width: int = 1024, height: int = 576) -> Path:
    img = Image.new("RGB", (width, height), color=(246, 248, 252))
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        sub_font = ImageFont.truetype("DejaVuSans.ttf", 22)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except Exception:
        title_font = sub_font = body_font = ImageFont.load_default()

    x, y = 40, 34
    draw.text((x, y), panel.get("panel_id", "panel"), fill=(17, 24, 39), font=title_font)
    y += 48
    draw.text((x, y), panel.get("perspective", ""), fill=(75, 85, 99), font=sub_font)
    y += 42

    caption = panel.get("caption", "")
    for line in wrap_text(caption, 76):
        draw.text((x, y), line, fill=(17, 24, 39), font=body_font)
        y += 28

    y += 12
    draw.rounded_rectangle((x, y, width - 40, height - 36), radius=16, outline=(210, 216, 226), width=2)
    y += 22
    for line in wrap_text(panel.get("prompt", ""), 86)[:11]:
        draw.text((x + 20, y), line, fill=(31, 41, 55), font=body_font)
        y += 27

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    length = 0
    for word in words:
        add = len(word) + (1 if cur else 0)
        if length + add > max_chars and cur:
            lines.append(" ".join(cur))
            cur = [word]
            length = len(word)
        else:
            cur.append(word)
            length += add
    if cur:
        lines.append(" ".join(cur))
    return lines


def compile_contact_sheet(panel_image_paths: list[Path], out_path: Path, *, cols: int = 2) -> Path:
    if not panel_image_paths:
        raise ValueError("No panel images to compile.")

    images = [Image.open(p).convert("RGB") for p in panel_image_paths]
    # Normalize to first image size.
    w, h = images[0].size
    images = [img.resize((w, h)) if img.size != (w, h) else img for img in images]

    rows = (len(images) + cols - 1) // cols
    margin = 24
    sheet = Image.new("RGB", (cols * w + (cols + 1) * margin, rows * h + (rows + 1) * margin), color=(238, 242, 247))

    for idx, img in enumerate(images):
        row = idx // cols
        col = idx % cols
        x = margin + col * (w + margin)
        y = margin + row * (h + margin)
        sheet.paste(img, (x, y))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


def contact_sheet_html(sheet: dict[str, Any], panel_results: list[dict[str, Any]], sheet_png: Path) -> str:
    panels = []
    by_id = {r["panel_id"]: r for r in panel_results}
    for panel in sheet.get("panels", []):
        r = by_id.get(panel["panel_id"], {})
        img = r.get("image_path")
        rel_img = Path(img).name if img else ""
        panels.append(
            f"""
            <article class="panel">
              <img src="panels/{html.escape(rel_img)}" alt="{html.escape(panel['panel_id'])}">
              <h3>{html.escape(panel['panel_id'])}</h3>
              <p class="perspective">{html.escape(panel.get('perspective', ''))}</p>
              <p>{html.escape(panel.get('caption', ''))}</p>
              <pre>{html.escape(panel.get('prompt', ''))}</pre>
            </article>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(sheet.get("title", "Contact Sheet"))}</title>
<style>
body {{
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
  background: #f5f7fb;
  color: #111827;
}}
main {{ max-width: 1180px; margin: 32px auto; padding: 0 20px; }}
.card {{
  background: white;
  border: 1px solid #d9dee8;
  border-radius: 18px;
  padding: 20px;
  margin: 16px 0;
}}
.hero {{ max-width: 100%; border-radius: 14px; border: 1px solid #d9dee8; }}
.grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}}
.panel {{
  border: 1px solid #d9dee8;
  border-radius: 14px;
  padding: 14px;
  background: #fbfcff;
}}
.panel img {{ width: 100%; border-radius: 12px; }}
.perspective {{ color: #586174; font-weight: 650; }}
pre {{
  white-space: pre-wrap;
  background: #eef2f7;
  border-radius: 10px;
  padding: 12px;
}}
</style>
</head>
<body>
<main>
<section class="card">
<h1>{html.escape(sheet.get("title", "Contact Sheet"))}</h1>
<p>{html.escape(sheet.get("purpose", ""))}</p>
<img class="hero" src="{html.escape(sheet_png.name)}" alt="compiled contact sheet">
</section>
<section class="grid">
{''.join(panels)}
</section>
</main>
</body>
</html>
"""


def render_contact_sheets(
    *,
    contact_sheets: dict[str, Any],
    out_dir: str | Path,
    dry_run: bool = False,
    model_id: str = "fal-ai/flux/dev",
    image_size: str = "landscape_16_9",
    with_logs: bool = True,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    all_results = {
        "schema_version": "persona_dream_contact_sheet_render.v0.3",
        "dry_run": dry_run,
        "model_id": None if dry_run else model_id,
        "sheets": [],
    }

    for sheet in contact_sheets.get("contact_sheets", []):
        sheet_id = sheet["contact_sheet_id"]
        sheet_dir = out / sheet_id
        panels_dir = sheet_dir / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)

        panel_results: list[dict[str, Any]] = []
        panel_paths: list[Path] = []

        for panel in sheet.get("panels", []):
            if dry_run:
                panel_path = make_prompt_card(panel, panels_dir / f"{panel['panel_id']}.png")
                result = {
                    "panel_id": panel["panel_id"],
                    "model_id": "dry_run_prompt_card",
                    "request": {"prompt": panel["prompt"]},
                    "result": None,
                    "image_url": None,
                    "image_path": str(panel_path),
                    "image_sha256": sha256_file(panel_path),
                }
            else:
                result = render_panel_fal(
                    panel=panel,
                    out_dir=panels_dir,
                    model_id=model_id,
                    image_size=image_size,
                    with_logs=with_logs,
                )
                panel_path = Path(result["image_path"])

            panel_results.append(result)
            panel_paths.append(panel_path)

        sheet_png = compile_contact_sheet(panel_paths, sheet_dir / "contact_sheet.png")
        html_text = contact_sheet_html(sheet, panel_results, sheet_png)
        write_text(sheet_dir / "contact_sheet.html", html_text)

        sheet_result = {
            "contact_sheet_id": sheet_id,
            "title": sheet.get("title"),
            "purpose": sheet.get("purpose"),
            "contact_sheet_png": str(sheet_png),
            "contact_sheet_html": str(sheet_dir / "contact_sheet.html"),
            "panel_results": panel_results,
        }
        write_json(sheet_dir / "contact_sheet_result.json", sheet_result)
        all_results["sheets"].append(sheet_result)

    write_json(out / "contact_sheet_render_results.json", all_results)
    return all_results
