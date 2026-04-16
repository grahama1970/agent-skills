"""ops-stitch: Bundle design context for Google Stitch sessions."""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="Bundle design context for Google Stitch sessions.")

CAPTURES_DIR = Path(__file__).parent / "captures"


def _find_design_md(start: Path) -> Path | None:
    for d in [start, start.parent, start.parent.parent]:
        candidate = d / "DESIGN.md"
        if candidate.exists():
            return candidate
    return None


def _take_screenshot(url: str, hash_route: str | None, output: Path) -> bool:
    full_url = f"{url}/#{hash_route}" if hash_route else url
    cmd = [
        "google-chrome-stable",
        "--headless=new",
        f"--screenshot={output}",
        "--window-size=1920,1080",
        "--no-sandbox",
        "--disable-gpu",
        full_url,
    ]
    logger.info(f"Screenshotting {full_url}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        logger.error(f"Chrome failed: {result.stderr[:500]}")
        return False
    return output.exists()


def _write_prompt_md(output: Path, prompt: str, images: list[str]) -> None:
    lines = [
        "# Stitch Session Prompt\n",
        "## Prompt\n",
        prompt + "\n",
        "\n## Images to upload in Stitch web UI\n",
    ]
    for img in images:
        lines.append(f"- `{img}`\n")
    lines.extend([
        "\n## Instructions\n",
        "1. Open Google Stitch web UI\n",
        "2. Upload each image listed above\n",
        "3. Paste the prompt text into the Stitch prompt field\n",
        "4. Review generated designs and iterate\n",
    ])
    output.write_text("".join(lines))


@app.command()
def bundle(
    target: str = typer.Option(..., help="Component/view name (e.g. design-board-canvas)"),
    url: str = typer.Option("http://localhost:3001", help="URL to screenshot"),
    hash: str = typer.Option(None, help="Hash route to navigate to (e.g. music-lab-pipeline)"),
    design_md: str = typer.Option(None, help="Path to DESIGN.md (auto-detected if omitted)"),
    references: list[str] = typer.Option(None, help="Paths to reference images to include"),
    prompt: str = typer.Option(..., help="The Stitch prompt text"),
    output: str = typer.Option(None, help="Output directory (default: captures/{target}/context-bundle/)"),
) -> None:
    out_dir = Path(output) if output else CAPTURES_DIR / target / "context-bundle"
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Bundling context for '{target}' → {out_dir}")

    image_list: list[str] = []
    ts = datetime.now(timezone.utc).isoformat()

    # 1. Screenshot
    screenshot_path = out_dir / "current-state.png"
    if _take_screenshot(url, hash, screenshot_path):
        image_list.append("current-state.png")
        logger.info("Screenshot captured")
    else:
        logger.warning("Screenshot failed — continuing without it")

    # 2. DESIGN.md
    dm_path = Path(design_md) if design_md else _find_design_md(Path.cwd())
    if dm_path and dm_path.exists():
        shutil.copy2(dm_path, out_dir / "DESIGN.md")
        logger.info(f"Copied DESIGN.md from {dm_path}")
    else:
        logger.warning("No DESIGN.md found")

    # 3. Reference images
    if references:
        for i, ref in enumerate(references):
            ref_path = Path(ref)
            if not ref_path.exists():
                logger.warning(f"Reference not found: {ref}")
                continue
            dest_name = f"ref-{i:02d}{ref_path.suffix}"
            shutil.copy2(ref_path, out_dir / dest_name)
            image_list.append(dest_name)
            logger.info(f"Copied reference: {ref_path.name} → {dest_name}")

    # 4. PROMPT.md
    _write_prompt_md(out_dir / "PROMPT.md", prompt, image_list)

    # 5. manifest.json
    manifest = {
        "target": target,
        "timestamp": ts,
        "url": url,
        "hash": hash,
        "prompt": prompt,
        "images": image_list,
        "design_md_included": (out_dir / "DESIGN.md").exists(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Summary
    typer.echo(f"\nBundle ready: {out_dir}")
    typer.echo(f"  Images: {len(image_list)}")
    typer.echo(f"  DESIGN.md: {'yes' if manifest['design_md_included'] else 'no'}")
    typer.echo(f"  PROMPT.md: yes")
    typer.echo(f"  manifest.json: yes")


@app.command("list-bundles")
def list_bundles() -> None:
    if not CAPTURES_DIR.exists():
        typer.echo("No captures directory found.")
        raise typer.Exit()

    bundles = sorted(CAPTURES_DIR.glob("*/context-bundle/manifest.json"))
    if not bundles:
        typer.echo("No bundles found.")
        raise typer.Exit()

    for mf in bundles:
        data = json.loads(mf.read_text())
        target = data.get("target", "unknown")
        ts = data.get("timestamp", "unknown")
        n_images = len(data.get("images", []))
        typer.echo(f"  {target:30s}  {ts}  ({n_images} images)")


if __name__ == "__main__":
    app()
