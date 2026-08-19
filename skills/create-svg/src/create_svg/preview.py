"""Generate a local, self-contained HTML viewer for an SVG artifact.

The viewer has no scripts or external resources. It is a convenience artifact, not a
validation receipt.
"""

from __future__ import annotations

import html
from pathlib import Path


def write_preview(svg_path: Path, output_path: Path) -> None:
    """Write an HTML page that displays the SVG with a neutral dark surround."""

    relative = Path(svg_path.name) if svg_path.parent == output_path.parent else svg_path.resolve().as_uri()
    source = html.escape(str(relative), quote=True)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>README SVG preview</title>
<style>
html,body{{margin:0;min-height:100%;background:#20252d;color:#fff;font-family:system-ui,sans-serif}}
main{{display:grid;place-items:center;min-height:100vh;padding:24px;box-sizing:border-box}}
img{{display:block;width:min(100%,1200px);height:auto;box-shadow:0 12px 45px rgba(0,0,0,.45)}}
</style>
</head>
<body><main><img src="{source}" alt="README SVG preview"></main></body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
