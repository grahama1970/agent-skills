"""Visual diff engine — pixel diff + approximate block-SSIM, pure Pillow (no OpenCV)."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PIL import Image, ImageChops


def compute_pixel_diff(
    img_a_path: Path,
    img_b_path: Path,
    output_path: Path,
    threshold: int = 30,
) -> float:
    """Compute pixel difference between two images.

    Saves a diff image (red overlay where delta > threshold).
    Returns similarity score 0.0-1.0.
    """
    a = Image.open(img_a_path).convert("RGB")
    b = Image.open(img_b_path).convert("RGB")

    # Resize b to match a if needed
    if a.size != b.size:
        logger.warning(f"Size mismatch: {a.size} vs {b.size}, resizing to match")
        b = b.resize(a.size, Image.LANCZOS)

    # Grayscale difference
    ga = a.convert("L")
    gb = b.convert("L")
    diff = ImageChops.difference(ga, gb)

    # Count pixels above threshold
    diff_pixels = diff.load()
    w, h = diff.size
    total = w * h
    changed = 0
    for y in range(h):
        for x in range(w):
            if diff_pixels[x, y] > threshold:
                changed += 1

    similarity = 1.0 - (changed / total) if total > 0 else 1.0

    # Create red-overlay diff image
    diff_img = a.copy()
    diff_overlay = Image.new("RGBA", a.size, (0, 0, 0, 0))
    diff_data = diff.load()
    overlay_data = diff_overlay.load()
    for y in range(h):
        for x in range(w):
            if diff_data[x, y] > threshold:
                overlay_data[x, y] = (255, 0, 0, 128)

    diff_img = diff_img.convert("RGBA")
    diff_img = Image.alpha_composite(diff_img, diff_overlay)
    diff_img = diff_img.convert("RGB")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    diff_img.save(output_path, "PNG")
    logger.info(f"Diff: {similarity:.1%} similar, saved to {output_path}")
    return similarity


def _block_ssim(a: Image.Image, b: Image.Image, block_size: int = 16) -> float:
    """Approximate SSIM via block-level mean/variance comparison.

    Not true SSIM but correlates well enough for design drift detection.
    """
    ga = a.convert("L")
    gb = b.convert("L")

    if ga.size != gb.size:
        gb = gb.resize(ga.size, Image.LANCZOS)

    w, h = ga.size
    pa = ga.load()
    pb = gb.load()

    scores = []
    for by in range(0, h, block_size):
        for bx in range(0, w, block_size):
            bw = min(block_size, w - bx)
            bh = min(block_size, h - by)
            n = bw * bh
            if n == 0:
                continue

            sum_a = sum_b = sum_a2 = sum_b2 = sum_ab = 0.0
            for dy in range(bh):
                for dx in range(bw):
                    va = pa[bx + dx, by + dy]
                    vb = pb[bx + dx, by + dy]
                    sum_a += va
                    sum_b += vb
                    sum_a2 += va * va
                    sum_b2 += vb * vb
                    sum_ab += va * vb

            mean_a = sum_a / n
            mean_b = sum_b / n
            var_a = (sum_a2 / n) - mean_a * mean_a
            var_b = (sum_b2 / n) - mean_b * mean_b
            cov = (sum_ab / n) - mean_a * mean_b

            C1 = (0.01 * 255) ** 2
            C2 = (0.03 * 255) ** 2

            num = (2 * mean_a * mean_b + C1) * (2 * cov + C2)
            den = (mean_a**2 + mean_b**2 + C1) * (var_a + var_b + C2)
            scores.append(num / den if den > 0 else 1.0)

    return sum(scores) / len(scores) if scores else 1.0


def diff_directories(
    before_dir: Path,
    after_dir: Path,
    output_dir: Path,
    threshold: int = 30,
) -> list[dict]:
    """Match filenames between before/after dirs, compute diffs.

    Returns list of {name, similarity, ssim, diff_path} dicts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    before_files = {p.name: p for p in sorted(before_dir.glob("*.png"))}
    after_files = {p.name: p for p in sorted(after_dir.glob("*.png"))}

    common = set(before_files) & set(after_files)
    if not common:
        logger.warning(f"No matching filenames between {before_dir} and {after_dir}")
        return []

    results = []
    for name in sorted(common):
        diff_path = output_dir / f"diff-{name}"
        sim = compute_pixel_diff(before_files[name], after_files[name], diff_path, threshold)

        a = Image.open(before_files[name])
        b = Image.open(after_files[name])
        ssim = _block_ssim(a, b)

        results.append({
            "name": name,
            "similarity": round(sim, 4),
            "ssim": round(ssim, 4),
            "diff_path": str(diff_path),
        })

    return results
