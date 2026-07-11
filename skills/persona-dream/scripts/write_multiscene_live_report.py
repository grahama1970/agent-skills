#!/usr/bin/env python3
"""Write a source-derived HTML report for a multi-scene live smoke receipt."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def copy_asset(src: Path, asset_dir: Path) -> str:
    scene_id = src.parents[1].name if len(src.parents) > 1 else "scene"
    target = asset_dir / scene_id / src.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return str(target.relative_to(asset_dir.parent))


def image_block(record: dict[str, Any], *, asset_dir: Path, label: str) -> str:
    path = Path(str(record.get("image_path") or ""))
    if path.is_file():
        rel = copy_asset(path, asset_dir)
        image = f'<img src="{html.escape(rel)}" alt="{html.escape(label)}">'
    else:
        image = '<div class="missing">missing image</div>'
    bits = [
        f"<strong>{html.escape(label)}</strong>",
        f"{html.escape(str(record.get('width')))}x{html.escape(str(record.get('height')))}",
        f"{html.escape(str(record.get('bytes')))} bytes",
        f"<code>{html.escape(str(record.get('sha256')))}</code>",
    ]
    return f"<figure>{image}<figcaption>{' · '.join(bits)}</figcaption></figure>"


def write_report(receipt_path: Path, validation_path: Path, output: Path) -> None:
    receipt = load_json(receipt_path)
    validation = load_json(validation_path) if validation_path.is_file() else {}
    asset_dir = output.parent / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    scenes_html: list[str] = []
    for scene in receipt.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or "scene")
        scenes_html.append(
            "<section class=\"scene\">"
            f"<h2>{html.escape(scene_id)}</h2>"
            "<div class=\"grid\">"
            + image_block(scene.get("contact_sheet") or {}, asset_dir=asset_dir, label="Contact sheet")
            + image_block(scene.get("panel") or {}, asset_dir=asset_dir, label="Panel")
            + "</div>"
            "</section>"
        )
    blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
    blocker_html = "<p>No validation blockers.</p>" if not blockers else "<pre>" + html.escape(json.dumps(blockers, indent=2)) + "</pre>"
    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Persona Dream Multi-Scene Live Smoke</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, system-ui, sans-serif; color: #17202a; background: #f7f8fa; }}
    body {{ margin: 0; }}
    header {{ padding: 28px 32px; background: #ffffff; border-bottom: 1px solid #d8dee8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px 20px 48px; }}
    h1 {{ margin: 0 0 10px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ font-size: 20px; margin: 0 0 14px; letter-spacing: 0; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 16px; }}
    .summary div, .scene, .blockers {{ background: #ffffff; border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; }}
    .summary span {{ display: block; color: #5b6472; font-size: 12px; margin-bottom: 4px; }}
    .summary strong {{ font-size: 15px; }}
    .scene {{ margin-top: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
    figure {{ margin: 0; }}
    img {{ display: block; width: 100%; height: auto; border-radius: 6px; border: 1px solid #d8dee8; background: #eef1f5; }}
    figcaption {{ margin-top: 8px; color: #364152; font-size: 12px; line-height: 1.45; word-break: break-word; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }}
    .blockers {{ margin-top: 18px; }}
    .missing {{ min-height: 220px; display: grid; place-items: center; background: #f0f2f5; color: #6b7280; border-radius: 6px; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>Persona Dream Multi-Scene Live Smoke</h1>
    <p>Source-derived report from real Scillm/Codex OAuth image calls. No Kling call was made.</p>
    <div class="summary">
      <div><span>Status</span><strong>{html.escape(str(receipt.get('status')))}</strong></div>
      <div><span>Validation</span><strong>{html.escape(str(validation.get('status')))}</strong></div>
      <div><span>Mocked</span><strong>{html.escape(str(receipt.get('mocked')))}</strong></div>
      <div><span>Live</span><strong>{html.escape(str(receipt.get('live')))}</strong></div>
      <div><span>Scenes</span><strong>{html.escape(str(receipt.get('scene_count')))}</strong></div>
      <div><span>Workers</span><strong>{html.escape(str(receipt.get('max_workers')))}</strong></div>
      <div><span>Elapsed</span><strong>{html.escape(str(receipt.get('elapsed_s')))}s</strong></div>
      <div><span>Kling Called</span><strong>{html.escape(str(receipt.get('kling_called')))}</strong></div>
    </div>
  </header>
  <main>
    {''.join(scenes_html)}
    <section class="blockers"><h2>Validation Blockers</h2>{blocker_html}</section>
    <section class="blockers"><h2>Artifacts</h2>
      <p>Receipt: <code>{html.escape(str(receipt_path))}</code></p>
      <p>Validation: <code>{html.escape(str(validation_path))}</code></p>
    </section>
  </main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()
    write_report(args.receipt, args.validation, args.output)
    result = {"status": "PASS_REPORT_WRITTEN", "report": str(args.output)}
    print(json.dumps(result, indent=2) if args.json_out else result["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
