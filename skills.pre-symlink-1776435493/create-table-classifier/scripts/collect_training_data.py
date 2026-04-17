#!/usr/bin/env python3
"""
Collect training data for Table Strategy Classifier.

Sources:
1. S05 successful extractions (from /memory lessons)
2. 12TB corpus extraction logs
3. Manual annotations from fixture-tricky

Output format (JSONL):
{
  "image_path": "data/images/train/arxiv_2501_page3_table1.png",
  "source_pdf": "2501_15355.pdf",
  "page": 3,
  "bbox": [100, 200, 400, 350],
  "strategy": "lattice_sensitive",
  "params": {"line_scale": 15, "edge_tol": 300, "flavor": "lattice"},
  "quality_score": 0.92,
  "fallback_used": false,
  "preset": "arxiv_scientific",
  "domain": "scientific",
  "taxonomy": {"bridge_tags": ["Precision"], "confidence": 0.85}
}
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import typer
except ImportError:
    print("Installing typer...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:
    try:
        import fitz  # PyMuPDF < 1.24
    except ImportError:
        print("Installing pymupdf...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "pymupdf", "-q"],
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

try:
    from PIL import Image
except ImportError:
    print("Installing pillow...",
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "-q"],
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    from PIL import Image

try:
    import httpx
except ImportError:
    httpx = None

from loguru import logger

# Import taxonomy bridge
from taxonomy_bridge import extract_table_taxonomy, get_strategy_bridges

app = typer.Typer(help="Collect training data for Table Strategy Classifier",
env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
)

# Data directories
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
LABELS_DIR = DATA_DIR / "labels"


def ensure_dirs():
    """Create data directories if needed."""
    (IMAGES_DIR / "train").mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / "eval").mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)


def extract_table_image(
    pdf_path: Path,
    page_num: int,
    bbox: tuple[float, float, float, float],
    output_path: Path,
    dpi: int = 150,
) -> bool:
    """Extract table region as PNG image from PDF."""
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_num]

        # Convert bbox to fitz.Rect
        x0, y0, x1, y1 = bbox
        rect = fitz.Rect(x0, y0, x1, y1)

        # Expand slightly to include borders
        rect = rect + (-5, -5, 5, 5)

        # Render region at specified DPI
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        # Clip to page bounds
        rect = rect & page.rect

        pix = page.get_pixmap(matrix=mat, clip=rect)

        # Save as PNG
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))

        doc.close()
        return True

    except Exception as e:
        logger.warning(f"Failed to extract table image: {e}")
        return False


def fetch_memory_lessons(
    base_url: str = "http://localhost:8880",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch successful extraction lessons from /memory."""
    if httpx is None:
        logger.warning("httpx not available, skipping memory fetch")
        return []

    try:
        with httpx.Client(timeout=30.0) as client:
            # Search for table extraction lessons
            response = client.post(
                f"{base_url}/search",
                json={
                    "query": "camelot table extraction strategy successful",
                    "collection": "lessons",
                    "limit": limit,
                    "filters": {"status": "approved"},
                }
            )

            if response.status_code != 200:
                logger.warning(f"Memory search failed: {response.status_code}")
                return []

            data = response.json()
            return data.get("results", [])

    except Exception as e:
        logger.warning(f"Failed to fetch from memory: {e}")
        return []


def parse_memory_lesson(lesson: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a /memory lesson into training data format."""
    try:
        # Expected lesson format from S05:
        # {
        #   "problem": "Table extraction for arxiv_2501.pdf",
        #   "solution": "Used lattice_sensitive with line_scale=15...",
        #   "metadata": {
        #     "pdf_name": "...",
        #     "preset": "...",
        #     "strategy": "...",
        #     "params": {...}
        #   }
        # }
        metadata = lesson.get("metadata", {})

        if not metadata.get("pdf_name"):
            return None
        if not metadata.get("strategy"):
            return None

        return {
            "source_pdf": metadata["pdf_name"],
            "strategy": metadata["strategy"],
            "params": metadata.get("params", {}),
            "quality_score": metadata.get("quality_score", 0.8),
            "fallback_used": metadata.get("fallback_used", False),
            "preset": metadata.get("preset", "unknown"),
            "domain": metadata.get("domain", "unknown"),
        }

    except Exception as e:
        logger.debug(f"Failed to parse lesson: {e}")
        return None


def collect_from_s05_outputs(
    results_dir: Path,
    corpus_dir: Path,
    output_file: Path,
    limit: int = 5000,
) -> int:
    """Collect training data from S05 extraction results."""
    ensure_dirs()
    collected = 0
    skipped = 0

    # Find S05 result files - handle multiple naming conventions
    s05_files = list(results_dir.glob("**/05_table_extractor/json_output/05_tables.json"))
    if not s05_files:
        s05_files = list(results_dir.glob("**/05_table_extractor/*.json"))
    if not s05_files:
        s05_files = list(results_dir.glob("**/stage_05*.json"))

    logger.info(f"Found {len(s05_files)} S05 result files")

    with output_file.open("w") as f:
        for s05_file in s05_files:
            if collected >= limit:
                break

            try:
                data = json.loads(s05_file.read_text())

                # Extract metadata - handle both formats
                pdf_name = data.get("source_pdf", "")
                if not pdf_name:
                    pdf_name = data.get("metadata", {}).get("source_pdf", "")
                if not pdf_name:
                    continue

                # Extract just the filename from full path
                pdf_name = Path(pdf_name).name

                # Find source PDF in corpus
                pdf_path = None
                # Try direct match first
                for subdir in ["arxiv", "nasa", "nist", "defense", "archive_org", "ietf", "adversarial", "engineering", "edge_cases", "stress_test_pdfs"]:
                    candidate = corpus_dir / subdir / pdf_name
                    if candidate.exists():
                        pdf_path = candidate
                        break

                if not pdf_path:
                    # Try glob search
                    matches = list(corpus_dir.glob(f"**/{Path(pdf_name).stem}*.pdf"))
                    if matches:
                        pdf_path = matches[0]
                    else:
                        skipped += 1
                        continue

                # Get strategy stats from metrics
                metrics = data.get("metrics", {})
                strategies_stats = metrics.get("strategies", {})

                # Process each table
                tables = data.get("tables", [])
                for i, table in enumerate(tables):
                    if collected >= limit:
                        break

                    # Get extraction method and strategy
                    strategy = table.get("strategy", "lattice_default")
                    # Normalize strategy name
                    if "_" in strategy:
                        strategy_base = strategy.split("_")[0]  # e.g., "stream_default" -> "stream"
                    else:
                        strategy_base = strategy

                    # Map to our 3 classes
                    if strategy_base == "stream":
                        strategy_class = "stream"
                    elif "sensitive" in strategy.lower():
                        strategy_class = "lattice_sensitive"
                    else:
                        strategy_class = "lattice"

                    # Get params based on strategy
                    params = {
                        "line_scale": table.get("line_scale", 15 if strategy_class != "stream" else 30),
                        "edge_tol": table.get("edge_tol", 300),
                        "flavor": "stream" if strategy_class == "stream" else "lattice",
                    }

                    # Get bbox
                    bbox = table.get("bbox", table.get("table_area"))
                    if not bbox:
                        continue

                    # Get page - handle both formats
                    page = table.get("page_index", table.get("page", 0))

                    # Generate image path
                    pdf_stem = Path(pdf_name).stem
                    img_name = f"{pdf_stem}_page{page}_table{i}.png"
                    img_path = IMAGES_DIR / "train" / img_name

                    # Extract image
                    if isinstance(bbox, str):
                        # Parse "x1,y1,x2,y2" format
                        bbox = tuple(float(x) for x in bbox.split(","))
                    elif isinstance(bbox, list):
                        bbox = tuple(bbox)

                    if not extract_table_image(pdf_path, page, bbox, img_path):
                        continue

                    # Get preset and domain from path or infer from content
                    pdf_parent = pdf_path.parent.name if pdf_path else "unknown"
                    preset = data.get("metadata", {}).get("preset", pdf_parent)
                    domain = data.get("metadata", {}).get("domain", "unknown")

                    # Infer domain from directory name
                    if domain == "unknown":
                        if "arxiv" in str(pdf_path).lower():
                            domain = "scientific"
                            preset = "arxiv_scientific"
                        elif "nasa" in str(pdf_path).lower():
                            domain = "aerospace"
                            preset = "government_report"
                        elif "nist" in str(pdf_path).lower():
                            domain = "standards"
                            preset = "requirements_spec"
                        elif "defense" in str(pdf_path).lower():
                            domain = "military"
                            preset = "government_report"
                        elif "archive" in str(pdf_path).lower():
                            domain = "archive"
                            preset = "archive_scanned"
                        elif "ietf" in str(pdf_path).lower():
                            domain = "standards"
                            preset = "requirements_spec"

                    # Compute quality from fragmentation score if available
                    frag_score = table.get("fragmentation_score", 0)
                    quality = max(0.5, 1.0 - (frag_score * 0.1))  # Lower frag = higher quality

                    # Extract taxonomy
                    table_desc = f"Table from {pdf_name} using {strategy_class} strategy"
                    taxonomy = extract_table_taxonomy(table_desc, preset)

                    # Create training example
                    example = {
                        "image_path": str(img_path.relative_to(SKILL_DIR)),
                        "source_pdf": pdf_name,
                        "page": page,
                        "bbox": list(bbox) if isinstance(bbox, tuple) else bbox,
                        "strategy": strategy_class,
                        "params": params,
                        "quality_score": quality,
                        "fallback_used": False,
                        "preset": preset,
                        "domain": domain,
                        "taxonomy": taxonomy,
                    }

                    f.write(json.dumps(example) + "\n")
                    collected += 1

                    if collected % 100 == 0:
                        logger.info(f"Collected {collected} examples...")

            except Exception as e:
                logger.debug(f"Error processing {s05_file}: {e}")
                continue

    logger.info(f"Collected {collected} examples, skipped {skipped}")
    return collected


def collect_from_memory(
    memory_url: str,
    corpus_dir: Path,
    output_file: Path,
    limit: int = 1000,
) -> int:
    """Collect training data from /memory lessons."""
    ensure_dirs()

    lessons = fetch_memory_lessons(memory_url, limit)
    logger.info(f"Fetched {len(lessons)} lessons from memory")

    collected = 0

    with output_file.open("a") as f:  # Append mode
        for lesson in lessons:
            if collected >= limit:
                break

            parsed = parse_memory_lesson(lesson)
            if not parsed:
                continue

            # Skip if we don't have required fields
            if not parsed.get("strategy"):
                continue

            # For memory lessons, we may not have bbox/image
            # Store as text-only example for now
            example = {
                "image_path": None,  # No image from memory
                "source_pdf": parsed["source_pdf"],
                "page": None,
                "bbox": None,
                "strategy": parsed["strategy"],
                "params": parsed["params"],
                "quality_score": parsed["quality_score"],
                "fallback_used": parsed["fallback_used"],
                "preset": parsed["preset"],
                "domain": parsed["domain"],
                "taxonomy": extract_table_taxonomy(
                    f"Table extraction: {parsed['strategy']}",
                    parsed["preset"]
                ),
                "from_memory": True,
            }

            f.write(json.dumps(example) + "\n")
            collected += 1

    logger.info(f"Collected {collected} examples from memory")
    return collected


@app.command()
def collect(
    corpus: Path = typer.Option(..., help="Path to PDF corpus"),
    extractor_results: Path = typer.Option(
        None, help="Path to S05 extraction results"
    ),
    memory_url: str = typer.Option(
        "http://localhost:8880", help="Memory API URL"
    ),
    output: Path = typer.Option(
        LABELS_DIR / "collected.jsonl", help="Output JSONL file"
    ),
    limit: int = typer.Option(5000, help="Maximum examples to collect"),
    include_memory: bool = typer.Option(True, help="Include lessons from /memory"),
):
    """
    Collect training data from S05 outputs and /memory.

    Examples:
        ./run.sh collect --corpus /path/to/pdfs --limit 5000
        ./run.sh collect --corpus /data/corpus --extractor-results /data/s05
    """
    logger.info(f"Collecting training data (limit={limit})")

    total = 0

    # Collect from S05 results
    if extractor_results and extractor_results.exists():
        count = collect_from_s05_outputs(
            extractor_results, corpus, output, limit
        )
        total += count
        logger.info(f"Collected {count} from S05 outputs")

    # Collect from memory
    if include_memory:
        remaining = limit - total
        if remaining > 0:
            count = collect_from_memory(
                memory_url, corpus, output, remaining
            )
            total += count
            logger.info(f"Collected {count} from /memory")

    # Summary
    logger.info(f"Total collected: {total} examples")
    logger.info(f"Output: {output}")

    # Show class distribution
    if output.exists():
        strategies = {}
        with output.open() as f:
            for line in f:
                ex = json.loads(line)
                s = ex.get("strategy", "unknown")
                strategies[s] = strategies.get(s, 0) + 1

        logger.info("Strategy distribution:")
        for s, count in sorted(strategies.items(), key=lambda x: -x[1]):
            logger.info(f"  {s}: {count}")


@app.command()
def from_fixtures(
    fixtures_dir: Path = typer.Option(..., help="Path to fixture PDFs"),
    output: Path = typer.Option(
        LABELS_DIR / "fixtures.jsonl", help="Output JSONL file"
    ),
):
    """
    Collect training data from manually annotated fixtures.

    Expects fixtures to have accompanying .json metadata files.
    """
    ensure_dirs()

    collected = 0
    fixture_files = list(fixtures_dir.glob("**/*.pdf"))

    with output.open("w") as f:
        for pdf_path in fixture_files:
            # Look for metadata file
            meta_path = pdf_path.with_suffix(".json")
            if not meta_path.exists():
                continue

            try:
                meta = json.loads(meta_path.read_text())

                # Process annotated tables
                for i, table in enumerate(meta.get("tables", [])):
                    bbox = table.get("bbox")
                    if not bbox:
                        continue

                    page = table.get("page", 0)

                    # Generate image
                    img_name = f"{pdf_path.stem}_page{page}_table{i}.png"
                    img_path = IMAGES_DIR / "eval" / img_name  # Fixtures go to eval

                    if not extract_table_image(pdf_path, page, tuple(bbox), img_path):
                        continue

                    example = {
                        "image_path": str(img_path.relative_to(SKILL_DIR)),
                        "source_pdf": pdf_path.name,
                        "page": page,
                        "bbox": bbox,
                        "strategy": table.get("strategy", "lattice"),
                        "params": table.get("params", {}),
                        "quality_score": table.get("quality_score", 1.0),
                        "fallback_used": False,
                        "preset": meta.get("preset", "unknown"),
                        "domain": meta.get("domain", "unknown"),
                        "taxonomy": extract_table_taxonomy(
                            f"Fixture table: {table.get('description', '')}",
                            meta.get("preset")
                        ),
                        "is_fixture": True,
                    }

                    f.write(json.dumps(example) + "\n")
                    collected += 1

            except Exception as e:
                logger.warning(f"Error processing fixture {pdf_path}: {e}")

    logger.info(f"Collected {collected} fixture examples")


if __name__ == "__main__":
    app()
