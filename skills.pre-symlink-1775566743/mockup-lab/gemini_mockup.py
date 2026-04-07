"""Generate HTML/CSS mockups via Gemini 3 Flash with full project context as ZIP.

Bundles code files, DESIGN.md, best-practices rules, screenshots, and research
into a ZIP → sends to Gemini via /scillm → saves HTML + renders PNG via headless Chrome.

Usage:
    python gemini_mockup.py generate \
        --brief "Compliance posture dashboard with NIST family bars" \
        --files src/hooks/usePostureData.ts src/components/sparta/dashboard/PostureDashboard.tsx \
        --screenshots captures/sparta-overview.png \
        --references https://example.com/dashboard.png \
        --research "dogpile synthesis text or file path" \
        --design DESIGN.md \
        --output captures/posture-dashboard-design/ \
        --variations 3
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SCILLM = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"
MODEL = "text-gemini"  # Gemini 2.5 Flash — 1M context, supports ZIP inlineData

# Direct Gemini API (bypasses scillm queue timeout for large requests)
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

SKILL_DIR = Path(__file__).parent
COMMON_DIR = SKILL_DIR.parent / "common"
REPO_ROOT = SKILL_DIR.parent.parent.parent  # .pi/skills/mockup-lab -> repo root

# Best practices to bundle
BEST_PRACTICES = [
    Path.home() / ".claude/skills/best-practices-react/skills/react-best-practices/rules/interaction-queryspec-registration.md",
    Path.home() / ".pi/skills/best-practices-d3/SKILL.md",
]

EMBRY_STYLE = Path.home() / "workspace/experiments/pi-mono/packages/ux-lab/src/components/sparta/common/EmbryStyle.ts"


def _build_zip(
    brief: str,
    files: list[str],
    screenshots: list[str],
    references: list[str],
    research: Optional[str],
    design_md: Optional[str],
) -> bytes:
    """Bundle all context into a ZIP for Gemini."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Brief
        zf.writestr("BRIEF.md", f"# Design Brief\n\n{brief}\n")

        # DESIGN.md
        if design_md and Path(design_md).exists():
            zf.write(design_md, "DESIGN.md")
        elif design_md:
            zf.writestr("DESIGN.md", design_md)

        # Code files
        for f in files:
            p = Path(f)
            if p.exists():
                # Use relative path from repo root if inside repo
                try:
                    rel = p.resolve().relative_to(REPO_ROOT.resolve())
                    zf.write(str(p), f"code/{rel}")
                except ValueError:
                    zf.write(str(p), f"code/{p.name}")
            else:
                logger.warning(f"File not found, skipping: {f}")

        # EmbryStyle.ts (always include for color tokens)
        if EMBRY_STYLE.exists():
            zf.write(str(EMBRY_STYLE), "code/EmbryStyle.ts")

        # Best practices
        for bp in BEST_PRACTICES:
            if bp.exists():
                zf.write(str(bp), f"best-practices/{bp.name}")

        # Screenshots (local files)
        for s in screenshots:
            p = Path(s)
            if p.exists():
                # Preprocess with vlm_image if available
                try:
                    import sys
                    sys.path.insert(0, str(COMMON_DIR))
                    from vlm_image import prepare_for_vlm
                    from PIL import Image
                    img = Image.open(p)
                    processed = prepare_for_vlm(img, min_width=1200)
                    img_buf = io.BytesIO()
                    processed.save(img_buf, format="PNG", optimize=True)
                    zf.writestr(f"screenshots/{p.name}", img_buf.getvalue())
                except ImportError:
                    zf.write(str(p), f"screenshots/{p.name}")
            else:
                logger.warning(f"Screenshot not found: {s}")

        # Reference images (URLs — fetch them)
        for i, url in enumerate(references):
            try:
                resp = httpx.get(url, timeout=15.0, follow_redirects=True)
                ext = "png" if "png" in resp.headers.get("content-type", "") else "jpg"
                zf.writestr(f"references/ref_{i}.{ext}", resp.content)
            except Exception as e:
                logger.warning(f"Failed to fetch reference {url}: {e}")

        # Research context
        if research:
            p = Path(research)
            if p.exists():
                zf.write(str(p), "RESEARCH.md")
            else:
                zf.writestr("RESEARCH.md", research)

    return buf.getvalue()


def _get_gemini_key() -> str:
    """Get Gemini API key from environment or .env file."""
    import os
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        for env_file in [Path.home() / "workspace/experiments/pi-mono/.env", Path.home() / ".env"]:
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"')
                        break
            if key:
                break
    return key


def _send_to_gemini(zip_bytes: bytes, prompt: str, variations: int = 3) -> str:
    """Explode ZIP and send individual files to Gemini as inlineData parts."""
    api_key = _get_gemini_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in environment or .env")

    full_prompt = f"""{prompt}

INSTRUCTIONS:
- Generate {variations} different HTML/CSS mockup variation(s)
- Each variation should be a complete, self-contained HTML file
- Use the EMBRY dark theme from EmbryStyle.ts (bg=#0d0f12, card=#12151a, green=#00ff88, amber=#ffaa00, red=#ff4444, blue=#4a9eff, accent=#7c4dff, white=#e8eaed)
- Match the code patterns in the attached files (React inline styles → translate to CSS)
- Use monospace fonts for data, uppercase labels, glow effects for status indicators
- Reference the screenshots for visual style consistency
- Reference the best-practices files for interaction patterns
- The mockup is for DESKTOP (1920x1080 viewport)
- Return ONLY the HTML. No explanation. Each variation separated by <!-- VARIATION N -->
"""

    # Explode ZIP into individual parts
    parts: list[dict] = [{"text": full_prompt}]
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            data = zf.read(name)
            if not data:
                continue
            # Determine MIME type
            lower = name.lower()
            if lower.endswith((".png",)):
                mime = "image/png"
            elif lower.endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif lower.endswith((".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".css", ".html", ".json", ".yaml", ".yml")):
                # Text files: send as text parts with filename prefix
                try:
                    text_content = data.decode("utf-8")
                    parts.append({"text": f"=== {name} ===\n{text_content}"})
                    continue
                except UnicodeDecodeError:
                    mime = "application/octet-stream"
            else:
                # Skip binary files Gemini can't handle
                logger.debug(f"Skipping unsupported file: {name}")
                continue

            b64 = base64.b64encode(data).decode()
            parts.append({"inlineData": {"mimeType": mime, "data": b64}})

    logger.info(f"Sending {len(parts)} parts to Gemini ({len([p for p in parts if 'inlineData' in p])} images, {len([p for p in parts if 'text' in p])} text)")

    resp = httpx.post(
        f"{GEMINI_API}?key={api_key}",
        json={
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 32768,
            },
        },
        timeout=300.0,
    )
    if resp.status_code != 200:
        logger.error(f"Gemini returned {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _screenshot_html(html_path: Path, output_path: Path, width: int = 1920, height: int = 1080) -> bool:
    """Render HTML to PNG via headless Chrome."""
    try:
        cmd = [
            "google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
            f"--window-size={width},{height}",
            f"--screenshot={output_path}",
            f"file://{html_path.resolve()}"
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if output_path.exists():
            logger.info(f"Screenshot saved: {output_path}")
            return True
        logger.warning(f"Chrome exited {result.returncode} but no screenshot produced")
        return False
    except FileNotFoundError:
        # Try chromium-browser as fallback
        try:
            cmd[0] = "chromium-browser"
            subprocess.run(cmd, capture_output=True, timeout=30)
            return output_path.exists()
        except FileNotFoundError:
            logger.error("Neither google-chrome nor chromium-browser found")
            return False
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return False


@app.command()
def generate(
    brief: str = typer.Option(..., "--brief", "-b", help="Design brief (what to build)"),
    files: list[str] = typer.Option([], "--files", "-f", help="Code files to include"),
    screenshots: list[str] = typer.Option([], "--screenshots", "-s", help="Local screenshot paths"),
    references: list[str] = typer.Option([], "--references", "-r", help="Reference image URLs to fetch"),
    research: Optional[str] = typer.Option(None, "--research", help="Research text or file path"),
    design: Optional[str] = typer.Option(None, "--design", "-d", help="DESIGN.md path or inline text"),
    output: str = typer.Option("captures/mockup/", "--output", "-o", help="Output directory"),
    variations: int = typer.Option(3, "--variations", "-n", help="Number of design variations"),
):
    """Generate HTML/CSS mockups via Gemini 3 Flash with full context ZIP."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Bundling context: {len(files)} files, {len(screenshots)} screenshots, {len(references)} references")
    zip_bytes = _build_zip(brief, files, screenshots, references, research, design)
    zip_size = len(zip_bytes) / 1024
    logger.info(f"ZIP size: {zip_size:.1f} KB")

    # Save ZIP for debugging
    zip_path = out_dir / "context.zip"
    zip_path.write_bytes(zip_bytes)

    logger.info(f"Sending to Gemini ({MODEL}) for {variations} variation(s)...")
    html_response = _send_to_gemini(zip_bytes, brief, variations)

    # Split variations
    if "<!-- VARIATION" in html_response:
        parts = html_response.split("<!-- VARIATION")
        htmls = []
        for part in parts:
            # Strip the "N -->" prefix
            cleaned = part.strip()
            if cleaned.startswith("<!DOCTYPE") or cleaned.startswith("<html"):
                htmls.append(cleaned)
            elif ">" in cleaned:
                cleaned = cleaned[cleaned.index(">") + 1:].strip()
                if cleaned:
                    htmls.append(cleaned)
    else:
        # Single response — extract HTML
        html = html_response.strip()
        # Strip markdown code fences if present
        if html.startswith("```html"):
            html = html[7:]
        if html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]
        htmls = [html.strip()]

    logger.info(f"Got {len(htmls)} variation(s)")

    for i, html in enumerate(htmls):
        html_path = out_dir / f"variation_{i + 1}.html"
        png_path = out_dir / f"variation_{i + 1}.png"
        html_path.write_text(html)
        logger.info(f"Saved: {html_path}")

        if _screenshot_html(html_path, png_path):
            logger.info(f"Screenshot: {png_path}")
        else:
            logger.warning(f"Screenshot failed for variation {i + 1}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Generated {len(htmls)} mockup variation(s) in {out_dir}/")
    print(f"Context ZIP: {zip_size:.1f} KB")
    for i in range(len(htmls)):
        html_p = out_dir / f"variation_{i + 1}.html"
        png_p = out_dir / f"variation_{i + 1}.png"
        print(f"  Variation {i + 1}: {html_p}" + (f" + {png_p}" if png_p.exists() else " (no screenshot)"))
    print(f"{'=' * 60}")


@app.command()
def review(
    mockup: str = typer.Option(..., "--mockup", "-m", help="Path to mockup HTML or PNG"),
    reference: str = typer.Option(..., "--reference", "-r", help="Path to reference screenshot"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save review to file"),
):
    """VLM review: compare mockup against reference screenshot."""
    mockup_path = Path(mockup)
    ref_path = Path(reference)

    if not mockup_path.exists():
        logger.error(f"Mockup not found: {mockup}")
        raise typer.Exit(1)
    if not ref_path.exists():
        logger.error(f"Reference not found: {reference}")
        raise typer.Exit(1)

    # If mockup is HTML, screenshot it first
    if mockup_path.suffix == ".html":
        png_path = mockup_path.with_suffix(".png")
        if not _screenshot_html(mockup_path, png_path):
            logger.error("Failed to screenshot mockup HTML")
            raise typer.Exit(1)
        mockup_path = png_path

    # Send both images to Gemini for comparison
    mockup_b64 = base64.b64encode(mockup_path.read_bytes()).decode()
    ref_b64 = base64.b64encode(ref_path.read_bytes()).decode()

    resp = httpx.post(
        SCILLM,
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": """Compare these two images. Image 1 is the implementation, Image 2 is the approved design reference.

Score the match on a scale of 0-100. List specific discrepancies.
Return JSON: {"match_score": N, "discrepancies": ["..."], "overall": "PASS|FAIL"}
PASS = score >= 80."""},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{mockup_b64}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ref_b64}"}},
            ]}],
            "response_format": {"type": "json_object"},
            "max_tokens": 1024,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    result = resp.json()["choices"][0]["message"]["content"]

    print(result)
    if output:
        Path(output).write_text(result)
        logger.info(f"Review saved: {output}")


if __name__ == "__main__":
    app()
