#!/usr/bin/env python3
"""
Collect labeled merge/separate pairs from the corpus for training a
cross-page table merge classifier.

**Positive pairs** (label=merge): Tables whose S05c output contains
``merged_with`` or ``components`` fields — S05c merged them.

**Negative pairs** (label=separate): Adjacent tables on consecutive pages
that S05c did NOT merge.

Outputs two datasets for classifier-lab:
  - ``data/merge_images/{merge,separate}/*.png``  (vision track)
  - ``data/merge_features.jsonl``                  (tabular track)

Usage::

    python collect_merge_data.py --corpus /mnt/storage12tb/extractor_corpus --limit 500
    python collect_merge_data.py --corpus /mnt/storage12tb/extractor_corpus --vlm-verify 500
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
MERGE_IMAGES_DIR = DATA_DIR / "merge_images"
MERGE_FEATURES_PATH = DATA_DIR / "merge_features.jsonl"

# ---------------------------------------------------------------------------
# Feature vector
# ---------------------------------------------------------------------------

@dataclass
class MergePairFeatures:
    """Tabular features for a candidate merge pair."""
    col_count_match: bool = False
    width_ratio: float = 0.0
    horizontal_iou: float = 0.0
    title_has_continued: bool = False
    same_section: bool = False
    s00_domain: str = "unknown"
    s05b_title_similarity: float = 0.0
    gap_between_tables_px: float = 0.0
    row_count_ratio: float = 0.0
    label: str = "separate"        # merge | separate
    source_pdf: str = ""
    page_n: int = 0
    page_n1: int = 0
    image_path: str = ""


def _horizontal_iou(b1: List[float], b2: List[float]) -> float:
    """1-D IOU on X axis."""
    x0_1, x1_1 = b1[0], b1[2]
    x0_2, x1_2 = b2[0], b2[2]
    inter = max(0, min(x1_1, x1_2) - max(x0_1, x0_2))
    union = max(x1_1, x1_2) - min(x0_1, x0_2)
    return inter / union if union > 0 else 0.0


def _width_ratio(b1: List[float], b2: List[float]) -> float:
    w1 = abs(b1[2] - b1[0])
    w2 = abs(b2[2] - b2[0])
    if max(w1, w2) == 0:
        return 0.0
    return min(w1, w2) / max(w1, w2)


def _title_similarity(t1: str, t2: str) -> float:
    """Very cheap word-overlap cosine between two titles."""
    if not t1 or not t2:
        return 0.0
    w1 = set(t1.lower().split())
    w2 = set(t2.lower().split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / (len(w1) ** 0.5 * len(w2) ** 0.5)


def _extract_header_text(t: Dict) -> str:
    """Extract a pseudo-title from the table's first row or header."""
    # Try header_text field first
    header = t.get("header_text") or t.get("caption") or ""
    if header:
        return header
    # Fall back to first row of pandas_df (often contains column headers)
    df = t.get("pandas_df", [])
    if df and len(df) > 0:
        return " ".join(str(c) for c in df[0] if c).strip()
    return ""


def _row_count_ratio(t1: Dict, t2: Dict) -> float:
    r1 = len(t1.get("pandas_df", []))
    r2 = len(t2.get("pandas_df", []))
    if max(r1, r2) == 0:
        return 0.0
    return min(r1, r2) / max(r1, r2)


def _gap_px(t1: Dict, t2: Dict) -> float:
    """Normalized vertical gap between bottom of t1 and top of t2.

    For cross-page pairs: use distance from bottom of t1 to page bottom
    + distance from page top to top of t2, normalized by page height.
    Returns 0-1 where 0 = adjacent (likely merge), 1 = far apart.
    """
    b1 = t1.get("bbox")
    b2 = t2.get("bbox")
    if not b1 or not b2:
        return 0.5  # unknown → neutral, not zero
    p1 = t1.get("page_index", 0)
    p2 = t2.get("page_index", 0)
    if p1 == p2:
        # Same page: direct gap (Camelot: y grows upward, bbox=[x0,y0,x1,y1])
        gap = b2[3] - b1[1]  # top of t2 - bottom of t1
        page_h = max(b1[3], b2[3], 1)
        return max(0.0, min(1.0, abs(gap) / page_h))
    # Cross-page: how far t1 is from bottom + how far t2 is from top
    # Approximate page height from bbox (max y seen)
    page_h = max(b1[3], 800)  # Camelot default ~800 for letter
    dist_t1_to_bottom = b1[1]  # distance from t1 bottom to page bottom (y=0)
    dist_top_to_t2 = page_h - b2[3]  # distance from page top to t2 top
    total_gap = dist_t1_to_bottom + dist_top_to_t2
    return max(0.0, min(1.0, total_gap / page_h))


def compute_features(
    t1: Dict[str, Any],
    t2: Dict[str, Any],
    label: str,
    domain: str = "unknown",
    pdf_name: str = "",
) -> MergePairFeatures:
    """Compute the 9-feature vector for a candidate merge pair."""
    df1_data = t1.get("pandas_df", [])
    df2_data = t2.get("pandas_df", [])
    cols1 = len(df1_data[0]) if df1_data else 0
    cols2 = len(df2_data[0]) if df2_data else 0

    b1 = t1.get("bbox", [0, 0, 0, 0])
    b2 = t2.get("bbox", [0, 0, 0, 0])

    title1 = t1.get("llm_title") or t1.get("title") or _extract_header_text(t1) or ""
    title2 = t2.get("llm_title") or t2.get("title") or _extract_header_text(t2) or ""

    # Check "continued" in title, header row, or first-row text of t2
    first_row_text = " ".join(str(c) for c in (df2_data[0] if df2_data else []))
    has_continued = (
        "continued" in title2.lower()
        or "continued" in first_row_text.lower()
        or "(cont" in first_row_text.lower()
    )

    return MergePairFeatures(
        col_count_match=(cols1 == cols2 and cols1 > 0),
        width_ratio=_width_ratio(b1, b2),
        horizontal_iou=_horizontal_iou(b1, b2),
        title_has_continued=has_continued,
        same_section=(t1.get("section_id") or "") == (t2.get("section_id") or "") and bool(t1.get("section_id")),
        s00_domain=domain,
        s05b_title_similarity=_title_similarity(title1, title2),
        gap_between_tables_px=_gap_px(t1, t2),
        row_count_ratio=_row_count_ratio(t1, t2),
        label=label,
        source_pdf=pdf_name,
        page_n=t1.get("page_index", 0),
        page_n1=t2.get("page_index", 0),
    )


# ---------------------------------------------------------------------------
# Corpus scanner
# ---------------------------------------------------------------------------

def _find_profiles(corpus_dir: Path, limit: int = 0) -> List[Path]:
    """Find all profile directories that have S05c output."""
    results_dir = corpus_dir / "results"
    if not results_dir.exists():
        results_dir = corpus_dir
    profiles = []
    for d in sorted(results_dir.iterdir()):
        if not d.is_dir():
            continue
        s05c = d / "05c_table_merger" / "json_output" / "05c_merged_tables.json"
        s05 = d / "05_table_extractor" / "json_output" / "05_tables.json"
        if s05c.exists() or s05.exists():
            profiles.append(d)
        if limit and len(profiles) >= limit:
            break
    return profiles


def _load_domain(profile_dir: Path) -> str:
    """Read S00 domain from profile.json."""
    pf = profile_dir / "00_profile_detector" / "profile.json"
    if pf.exists():
        try:
            return json.loads(pf.read_text()).get("domain", "unknown")
        except Exception as e:
            logger.debug("JSON parse failed: {}", e)
    return "unknown"


def _load_tables(profile_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    """Load pre-merge (S05/S05b) and post-merge (S05c) tables."""
    # Post-merge
    s05c_path = profile_dir / "05c_table_merger" / "json_output" / "05c_merged_tables.json"
    post = []
    if s05c_path.exists():
        try:
            post = json.loads(s05c_path.read_text()).get("tables", [])
        except Exception as e:
            logger.debug("JSON parse failed: {}", e)

    # Pre-merge (prefer S05b, fall back to S05)
    s05b_path = profile_dir / "05b_table_describer" / "json_output" / "05b_tables.json"
    s05_path = profile_dir / "05_table_extractor" / "json_output" / "05_tables.json"
    pre = []
    for p in [s05b_path, s05_path]:
        if p.exists():
            try:
                pre = json.loads(p.read_text()).get("tables", [])
                break
            except Exception:
                continue
    return pre, post


def _pdf_path_for(profile_dir: Path) -> Optional[Path]:
    """Resolve the source PDF from profile.json, pipeline_context, or naming."""
    # 1. profile.json "file" field (most reliable in this corpus)
    pf = profile_dir / "00_profile_detector" / "profile.json"
    if pf.exists():
        try:
            data = json.loads(pf.read_text())
            src = data.get("file") or data.get("source_pdf") or ""
            if src and Path(src).exists():
                return Path(src)
        except Exception as e:
            logger.debug("path resolution failed: {}", e)

    # 2. pipeline_context.json
    ctx = profile_dir / "pipeline_context.json"
    if ctx.exists():
        try:
            data = json.loads(ctx.read_text())
            for key in ("source_pdf", "pdf_path", "file"):
                src = data.get(key, "")
                if src and Path(src).exists():
                    return Path(src)
        except Exception as e:
            logger.debug("path resolution failed: {}", e)

    # 3. Look in common corpus locations
    slug = profile_dir.name
    corpus_root = profile_dir.parent.parent  # results/../
    for subdir in ("inbox/arxiv", "inbox", "industry", "standards", "adversarial", ""):
        candidate = corpus_root / subdir / f"{slug}.pdf"
        if candidate.exists():
            return candidate

    # 4. Fallback: any PDF in the profile dir itself
    for f in profile_dir.glob("*.pdf"):
        return f
    return None


def _pair_key(pdf: str, p1: int, p2: int) -> str:
    h = hashlib.md5(pdf.encode()).hexdigest()[:8]
    return f"{Path(pdf).stem}_{h}_p{p1}_p{p2}"


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

def _generate_pair_image(pdf_path: Path, page_n: int, page_n1: int, out_path: Path) -> bool:
    """Generate side-by-side page-half image.  Returns True on success."""
    try:
        from extractor.pipeline.utils.tables.extraction import concat_page_halves
        concat_page_halves(pdf_path, page_n, page_n1, output_path=out_path)
        return True
    except Exception as e:
        logger.warning(f"Image generation failed for {pdf_path.name} p{page_n}-p{page_n1}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------

def collect(
    corpus_dir: Path,
    limit: int = 0,
    vlm_verify: int = 0,
    skip_images: bool = False,
) -> Dict[str, Any]:
    """Scan corpus and generate labeled datasets.

    Returns summary dict with counts.
    """
    # Setup output dirs
    for label in ("merge", "separate"):
        (MERGE_IMAGES_DIR / label).mkdir(parents=True, exist_ok=True)

    profiles = _find_profiles(corpus_dir, limit=limit)
    logger.info(f"Found {len(profiles)} profiles with table data")

    features_file = open(MERGE_FEATURES_PATH, "w")
    stats = {"merge": 0, "separate": 0, "profiles_scanned": 0, "image_ok": 0, "image_fail": 0}

    for profile_dir in profiles:
        stats["profiles_scanned"] += 1
        pre_tables, post_tables = _load_tables(profile_dir)
        if len(pre_tables) < 2:
            continue

        domain = _load_domain(profile_dir)
        pdf_path = _pdf_path_for(profile_dir)
        pdf_name = pdf_path.name if pdf_path else profile_dir.name

        # Build index of merged table indices from S05c
        merged_indices = set()
        for t in post_tables:
            if t.get("merged_with") is not None:
                merged_indices.add(t.get("table_index"))
                merged_indices.add(t.get("merged_with"))
            for comp in t.get("components", []):
                # components don't always have table_index, but page_index is there
                pass

        # Sort pre-merge tables by page/y-position
        pre_tables.sort(key=lambda t: (t.get("page_index", 0), t.get("bbox", [0])[1]))

        # Walk consecutive pairs on adjacent pages
        for i in range(len(pre_tables) - 1):
            t1 = pre_tables[i]
            t2 = pre_tables[i + 1]

            p1 = t1.get("page_index", 0)
            p2 = t2.get("page_index", 0)

            # Only consider cross-page pairs (consecutive pages)
            if p2 != p1 + 1:
                continue

            # Determine label from S05c output
            idx1 = t1.get("table_index")
            idx2 = t2.get("table_index")

            # Check if S05c merged these two
            is_merged = False
            for pt in post_tables:
                if pt.get("merged_with") == idx2 and pt.get("table_index") == idx1:
                    is_merged = True
                    break
                comps = pt.get("components", [])
                if len(comps) >= 2:
                    comp_pages = [c.get("page_index") for c in comps]
                    if p1 in comp_pages and p2 in comp_pages:
                        is_merged = True
                        break

            label = "merge" if is_merged else "separate"

            # Compute features
            feat = compute_features(t1, t2, label=label, domain=domain, pdf_name=pdf_name)

            # Generate image
            key = _pair_key(pdf_name, p1, p2)
            img_path = MERGE_IMAGES_DIR / label / f"{key}.png"

            if not skip_images and pdf_path and pdf_path.exists():
                feat.image_path = str(img_path.relative_to(DATA_DIR))
                if _generate_pair_image(pdf_path, p1, p2, img_path):
                    stats["image_ok"] += 1
                else:
                    stats["image_fail"] += 1
                    feat.image_path = ""

            # Write feature row
            features_file.write(json.dumps(asdict(feat)) + "\n")
            stats[label] += 1

    features_file.close()

    logger.info(
        f"Collection complete: {stats['merge']} merge + {stats['separate']} separate pairs "
        f"from {stats['profiles_scanned']} profiles.  "
        f"Images: {stats['image_ok']} ok, {stats['image_fail']} fail."
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import typer

    cli_app = typer.Typer(help="Collect merge training data from corpus")

    @cli_app.command()
    def main(
        corpus: Path = typer.Argument(..., help="Corpus root directory"),
        limit: int = typer.Option(0, "--limit", help="Max profiles to scan (0=all)"),
        vlm_verify: int = typer.Option(0, "--vlm-verify", help="Number of pairs to verify with VLM"),
        skip_images: bool = typer.Option(False, "--skip-images", help="Skip image generation"),
        json_out: bool = typer.Option(False, "--json", help="JSON output"),
    ):
        """Harvest labeled merge/separate pairs from corpus."""
        stats = collect(corpus, limit=limit, vlm_verify=vlm_verify, skip_images=skip_images)
        if json_out:
            print(json.dumps(stats, indent=2))

    cli_app()


if __name__ == "__main__":
    _cli()
