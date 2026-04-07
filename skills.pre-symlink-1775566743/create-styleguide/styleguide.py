"""create-styleguide — Per-surface visual styleguide lifecycle for Embry OS."""

from __future__ import annotations
import os

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

from annotator import annotate_screenshots
from debt import load_debt, merge_audit_debt, parse_style_guide_debt, save_debt
from differ import diff_directories
from registry import SURFACE_REGISTRY, get_surface, ready_surfaces

app = typer.Typer(help="Per-surface visual styleguide lifecycle.")

SKILLS_DIR = Path(__file__).parent.parent
EMBRY_ROOT = SKILLS_DIR.parent.parent  # .pi/skills -> .pi -> repo root

# Try to resolve the embry-os repo root (may differ if symlinked from pi-mono)
_embry_os_candidates = [
    Path("/home/graham/workspace/experiments/embry-os"),
    EMBRY_ROOT,
]
EMBRY_OS_ROOT = next((p for p in _embry_os_candidates if (p / "embry.yaml").exists()), EMBRY_ROOT)

DOCS_DIR = EMBRY_OS_ROOT / "docs" / "styleguides"
STORAGE_DIR = Path("/mnt/storage12tb/skills/create-styleguide")
STYLE_GUIDE_PATH = EMBRY_OS_ROOT / "docs" / "STYLE_GUIDE.md"


def _run_skill(skill_name: str, args: list[str]) -> subprocess.CompletedProcess:
    """Call a sibling skill via its run.sh."""
    run_sh = SKILLS_DIR / skill_name / "run.sh"
    if not run_sh.exists():
        logger.warning(f"Skill {skill_name} not found at {run_sh}")
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=f"Skill not found: {skill_name}")
    return subprocess.run(
        ["bash", str(run_sh)] + args,
        capture_output=True, text=True, timeout=600,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


def _load_tokens(token_path: Path) -> dict:
    """Load design tokens JSON file."""
    if not token_path.exists():
        raise typer.BadParameter(f"Token file not found: {token_path}")
    return json.loads(token_path.read_text())


def _resolve_path(p: str | None, base: Path | None = None) -> Path | None:
    """Resolve a path, trying both absolute and relative to EMBRY_OS_ROOT."""
    if p is None:
        return None
    path = Path(p)
    if path.is_absolute():
        return path
    # Try relative to embry-os root
    candidate = EMBRY_OS_ROOT / path
    if candidate.exists():
        return candidate
    # Try relative to cwd
    return path


def _surface_output_dir(surface_id: str) -> Path:
    """Get the docs output dir for a surface."""
    cfg = get_surface(surface_id)
    slug = cfg["name"].lower().replace(" ", "-")
    return DOCS_DIR / f"{surface_id}-{slug}"


def _surface_storage_dir(surface_id: str) -> Path:
    """Get the heavy-artifact storage dir for a surface."""
    return STORAGE_DIR / surface_id


def _assemble_styleguide(
    surface_id: str,
    annotated_paths: list[Path],
    debt_items: list[dict],
    audit_summary: str | None = None,
) -> str:
    """Generate STYLEGUIDE.md content from collected data."""
    cfg = get_surface(surface_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# {surface_id}: {cfg['name']} — Visual Styleguide",
        f"Generated: {now} | App: {cfg['app']} | Distance: {cfg['distance_mode']}",
        "",
    ]

    if cfg.get("token_source"):
        lines += [
            "## Token Source",
            f"`{cfg['token_source']}`",
            "",
        ]

    if annotated_paths:
        lines += ["## Annotated Reference Sheets", ""]
        for p in annotated_paths:
            lines.append(f"![{p.stem}]({p.name})")
        lines.append("")

    if audit_summary:
        lines += [
            "## Design Audit Summary",
            "",
            audit_summary,
            "",
        ]

    if debt_items:
        lines += [
            "## Token Debt",
            "",
            "| ID | Issue | Severity | Status |",
            "|----|-------|----------|--------|",
        ]
        for item in debt_items:
            status = "Resolved" if item.get("resolved") else "Open"
            lines.append(f"| {item['id']} | {item['issue']} | {item.get('severity', 'MEDIUM')} | {status} |")
        lines.append("")

    lines += [
        "## Visual History",
        "",
        "| Round | Date | Notes |",
        "|-------|------|-------|",
        f"| 1 | {now} | Initial build |",
        "",
    ]

    return "\n".join(lines)


# --- Commands ---


@app.command()
def build(
    surface: str = typer.Option(..., "--surface", help="Surface ID (e.g. S4)"),
    screenshots: str | None = typer.Option(None, "--screenshots", help="Screenshots directory"),
    tokens: str | None = typer.Option(None, "--tokens", help="Design tokens JSON path"),
    reference: str | None = typer.Option(None, "--reference", help="Reference images directory"),
    regions: str | None = typer.Option(None, "--regions", help="Regions JSON for annotation"),
    skip_audit: bool = typer.Option(False, "--skip-audit", help="Skip LLM audit step"),
    provider: str = typer.Option("gemini", "--provider", help="Audit provider (gemini/claude)"),
):
    """Full pipeline: annotate -> audit -> debt -> assemble STYLEGUIDE.md."""
    cfg = get_surface(surface)
    logger.info(f"Building styleguide for {surface}: {cfg['name']}")

    # Resolve paths from flags or registry
    shots_dir = _resolve_path(screenshots) or _resolve_path(cfg.get("screenshots_dir"))
    token_path = _resolve_path(tokens) or _resolve_path(cfg.get("token_source"))
    ref_dir = _resolve_path(reference) or _resolve_path(cfg.get("reference_dir"))

    if not shots_dir or not shots_dir.exists():
        logger.error(f"Screenshots directory not found: {shots_dir}")
        raise typer.Exit(1)
    if not token_path or not token_path.exists():
        logger.error(f"Token file not found: {token_path}")
        raise typer.Exit(1)

    token_data = _load_tokens(token_path)
    out_dir = _surface_output_dir(surface)
    storage = _surface_storage_dir(surface)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Annotate
    region_data = None
    if regions:
        region_path = Path(regions)
        if region_path.exists():
            region_data = json.loads(region_path.read_text())

    annotated_dir = storage / "annotated"
    annotated_paths = annotate_screenshots(shots_dir, token_data, annotated_dir, region_data)
    logger.info(f"Annotated {len(annotated_paths)} screenshots")

    # Step 2: Audit (optional)
    audit_summary = None
    if not skip_audit and ref_dir and ref_dir.exists():
        logger.info("Running /review-design audit...")
        result = _run_skill("review-design", [
            "review",
            "--screenshots", str(shots_dir),
            "--reference", str(ref_dir),
            "--provider", provider,
        ])
        if result.returncode == 0:
            audit_summary = result.stdout
        else:
            logger.warning(f"Audit returned non-zero: {result.stderr[:200]}")

    # Step 3: Debt
    global_debt = parse_style_guide_debt(STYLE_GUIDE_PATH)
    surface_debt_ids = set(cfg.get("debt_items", []))
    surface_debt = [d for d in global_debt if d["id"] in surface_debt_ids]

    debt_path = out_dir / "debt.json"
    existing_debt = load_debt(debt_path)
    merged_debt = merge_audit_debt(existing_debt, [], audit_round=1) if existing_debt else surface_debt
    if not merged_debt:
        merged_debt = surface_debt
    save_debt(debt_path, merged_debt)

    # Step 4: Assemble STYLEGUIDE.md
    # Copy annotated images to docs dir
    for ap in annotated_paths:
        shutil.copy2(ap, out_dir / ap.name)

    md_content = _assemble_styleguide(surface, annotated_paths, merged_debt, audit_summary)
    md_path = out_dir / "STYLEGUIDE.md"
    md_path.write_text(md_content)
    logger.info(f"Styleguide written: {md_path}")

    # Step 5: History snapshot
    history_dir = storage / "history" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    history_dir.mkdir(parents=True, exist_ok=True)
    for ap in annotated_paths:
        shutil.copy2(ap, history_dir / ap.name)
    shutil.copy2(md_path, history_dir / "STYLEGUIDE.md")

    # Step 6: Learn to /memory
    _run_skill("memory", [
        "learn",
        "--scope", "embry_os",
        "--problem", f"What is the visual styleguide status for {surface} {cfg['name']}?",
        "--solution", f"Styleguide built {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. "
                      f"{len(annotated_paths)} annotated sheets. "
                      f"{len(merged_debt)} debt items ({sum(1 for d in merged_debt if not d.get('resolved'))} open). "
                      f"Token source: {cfg.get('token_source', 'N/A')}.",
    ])

    logger.info(f"PASS: {surface} styleguide build complete")


@app.command()
def annotate(
    screenshots: str = typer.Option(..., "--screenshots", help="Screenshots directory"),
    tokens: str = typer.Option(..., "--tokens", help="Design tokens JSON path"),
    output: str = typer.Option(..., "--output", help="Output directory for annotated images"),
    regions: str | None = typer.Option(None, "--regions", help="Regions JSON path"),
):
    """Annotate screenshots with token callouts (Pillow step only)."""
    shots_dir = Path(screenshots)
    token_path = Path(tokens)
    out_dir = Path(output)

    if not shots_dir.exists():
        logger.error(f"Screenshots directory not found: {shots_dir}")
        raise typer.Exit(1)

    token_data = _load_tokens(token_path)
    region_data = None
    if regions:
        region_path = Path(regions)
        if region_path.exists():
            region_data = json.loads(region_path.read_text())

    results = annotate_screenshots(shots_dir, token_data, out_dir, region_data)
    logger.info(f"PASS: Annotated {len(results)} screenshots to {out_dir}")


@app.command()
def audit(
    surface: str = typer.Option(..., "--surface", help="Surface ID"),
    screenshots: str = typer.Option(..., "--screenshots", help="Current screenshots"),
    reference: str = typer.Option(..., "--reference", help="Reference/target images"),
    provider: str = typer.Option("gemini", "--provider", help="LLM provider"),
):
    """Run /review-design audit on a surface."""
    cfg = get_surface(surface)
    logger.info(f"Auditing {surface}: {cfg['name']} via {provider}")

    result = _run_skill("review-design", [
        "review",
        "--screenshots", screenshots,
        "--reference", reference,
        "--provider", provider,
    ])

    if result.returncode == 0:
        print(result.stdout)
        logger.info("PASS: Audit complete")
    else:
        logger.error(f"Audit failed: {result.stderr[:500]}")
        raise typer.Exit(1)


@app.command()
def diff(
    surface: str = typer.Option(..., "--surface", help="Surface ID"),
    before: str = typer.Option(..., "--before", help="Before (previous round) directory"),
    after: str = typer.Option(..., "--after", help="After (current round) directory"),
    threshold: float = typer.Option(0.95, "--threshold", help="Similarity threshold (0.0-1.0)"),
):
    """Visual regression between rounds."""
    cfg = get_surface(surface)
    before_dir = Path(before)
    after_dir = Path(after)
    out_dir = _surface_storage_dir(surface) / "diffs"

    results = diff_directories(before_dir, after_dir, out_dir, threshold=int((1.0 - threshold) * 255))

    if not results:
        logger.warning("No matching images found for comparison")
        raise typer.Exit(1)

    for r in results:
        flag = "OK" if r["similarity"] >= threshold else "DRIFT"
        logger.info(f"  [{flag}] {r['name']}: {r['similarity']:.1%} pixel / {r['ssim']:.3f} SSIM")

    avg_sim = sum(r["similarity"] for r in results) / len(results)
    logger.info(f"PASS: Average similarity: {avg_sim:.1%} across {len(results)} images")


@app.command()
def status():
    """Show which surfaces have styleguides, debt counts, last audit dates."""
    logger.info("Surface styleguide status:")
    logger.info(f"{'ID':<5} {'Name':<25} {'Ready':<7} {'Styleguide':<12} {'Debt':<6}")
    logger.info("-" * 60)

    for sid, cfg in SURFACE_REGISTRY.items():
        out_dir = _surface_output_dir(sid)
        has_guide = (out_dir / "STYLEGUIDE.md").exists()
        debt_count = 0
        debt_path = out_dir / "debt.json"
        if debt_path.exists():
            items = json.loads(debt_path.read_text())
            debt_count = sum(1 for d in items if not d.get("resolved"))

        ready = "Yes" if cfg.get("ready") else "No"
        guide = "Built" if has_guide else "-"
        logger.info(f"{sid:<5} {cfg['name']:<25} {ready:<7} {guide:<12} {debt_count:<6}")

    logger.info("PASS: status complete")


@app.command(name="dry-run")
def dry_run():
    """Generate sample output without LLM calls (used by sanity.sh)."""
    logger.info("dry-run: creating synthetic test data...")

    tmp = Path(tempfile.mkdtemp(prefix="styleguide-dry-"))
    try:
        # Create synthetic screenshot
        from PIL import Image
        img = Image.new("RGB", (680, 460), (20, 20, 28))
        shot_path = tmp / "test-screenshot.png"
        img.save(shot_path)

        # Create synthetic tokens
        token_data = {
            "colors": {"background": {"base": "#141414"}},
            "layout": {"window": {"width": 680, "height": 460}},
            "typography": {"body": {"size": 14}},
        }
        token_path = tmp / "tokens.json"
        token_path.write_text(json.dumps(token_data))

        # Test annotate
        annotated_dir = tmp / "annotated"
        results = annotate_screenshots(tmp, token_data, annotated_dir)
        assert len(results) == 1, f"Expected 1 annotated image, got {len(results)}"
        assert results[0].exists(), "Annotated image not created"

        # Test debt parser (with synthetic content)
        from debt import merge_audit_debt
        merged = merge_audit_debt([], [{"issue": "test issue", "severity": "LOW"}], audit_round=0)
        assert len(merged) == 1, "Debt merge failed"

        # Test diff (self-diff should be 1.0)
        from differ import compute_pixel_diff
        diff_out = tmp / "diff.png"
        sim = compute_pixel_diff(shot_path, shot_path, diff_out)
        assert sim == 1.0, f"Self-diff should be 1.0, got {sim}"

        # Test registry
        from registry import get_surface, ready_surfaces
        s4 = get_surface("S4")
        assert s4["name"] == "Launcher Overlay"
        assert "S4" in ready_surfaces()

        # Test styleguide assembly
        md = _assemble_styleguide("S4", results, merged)
        assert "S4" in md
        assert "Launcher Overlay" in md

        logger.info("PASS: dry-run verified — all components functional")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app()
