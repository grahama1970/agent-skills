#!/usr/bin/env python3
"""
Data Collection Script - Mine Labeled Data from Pipeline Outputs

Optimized for /mnt/storage12tb/extractor_corpus/results structure.

Usage:
    python collect_labels.py --task document_type --source /mnt/storage12tb/extractor_corpus/results
"""

import typer
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger
import sys

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

logger.remove()
logger.add(sys.stderr, level="INFO")


def collect_document_type_labels(corpus_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Collect document type labels from S00 profile.json outputs."""
    labels = []
    
    # Find all pipeline result directories (each contains 00_profile_detector/)
    pipeline_dirs = [d for d in corpus_path.iterdir() if d.is_dir()]
    
    logger.info(f"Found {len(pipeline_dirs)} potential pipeline runs in {corpus_path}")
    
    for i, pipeline_dir in enumerate(pipeline_dirs):
        if limit and i >= limit:
            break
            
        try:
            # Look for profile.json in 00_profile_detector/
            profile_path = pipeline_dir / "00_profile_detector" / "profile.json"
            if not profile_path.exists():
                continue
            
            # Load profile
            profile = json.loads(profile_path.read_text())
            
            # Extract preset label
            preset = profile.get("detected_preset") or profile.get("preset_match", {}).get("matched")
            if not preset:
                logger.debug(f"No preset in {profile_path}")
                continue
            
            # Extract confidence
            confidence = profile.get("preset_match", {}).get("confidence", 0.0)
            
            # Find PDF path
            pdf_path = profile.get("file")
            if not pdf_path or not Path(pdf_path).exists():
                logger.debug(f"PDF not found: {pdf_path}")
                continue
            
            # Generate unique ID
            doc_id = hashlib.sha256(str(pdf_path).encode()).hexdigest()[:16]
            
            # Find pre-extracted images (searching all subdirs)
            image_paths = []
            dataset_root = Path(__file__).parent.parent / "data" / "dataset_inbox"
            
            # Search all subdirectories for the doc_id folder
            if dataset_root.exists():
                potential_dirs = list(dataset_root.glob(f"*/{doc_id}"))
                if potential_dirs:
                    inbox_dir = potential_dirs[0]
                    for i in range(1, 4): # Check first 3 pages
                        img_path = inbox_dir / f"page_{i}.jpg"
                        if img_path.exists():
                            image_paths.append(str(img_path))
            
            # Extract text features from profile
            text_features = {
                "page_count": profile.get("page_count", 0),
                "has_formulas": profile.get("elements", {}).get("formulas", False),
                "has_tables": profile.get("elements", {}).get("tables", False),
                "section_style": profile.get("hierarchy", {}).get("section_style"),
                "layout": profile.get("layout", {}).get("style"),
            }
            
            labels.append({
                "id": doc_id,
                "task": "document_type",
                "input": {
                    "pdf_path": str(pdf_path),
                    "text_features": text_features,
                    "image_paths": image_paths,
                },
                "label": preset,
                "confidence": confidence,
                "source": "successful_extraction",
                "metadata": {
                    "pipeline_dir": str(pipeline_dir),
                    "extraction_date": profile.get("timestamp"),
                }
            })
            
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(pipeline_dirs)} pipelines, collected {len(labels)} labels")
        
        except Exception as e:
            logger.error(f"Error processing {pipeline_dir}: {e}")
            continue
    
    logger.info(f"Collected {len(labels)} document type labels")
    return labels


def save_labels(labels: List[Dict[str, Any]], output_path: Path):
    """Save labels to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w") as f:
        for label in labels:
            f.write(json.dumps(label) + "\n")
    
    logger.info(f"Saved {len(labels)} labels to {output_path}")


app = typer.Typer(help="Collect labeled data from pipeline outputs")


@app.command()
def main(
    task: str = typer.Option(..., help="Task to collect labels for"),
    source: Path = typer.Option(..., help="Path to corpus/results directory"),
    output: Path = typer.Option(Path("data/labels"), help="Output directory for labels"),
    limit: Optional[int] = typer.Option(None, help="Limit number of examples to collect"),
    append: bool = typer.Option(False, help="Append to existing labels file instead of overwriting"),
):
    logger.info(f"Collecting {task} labels from {source}")

    monitor = TaskClient("create-classifier/collect-labels", total=1, description=f"Collecting {task} labels") if TaskClient else None

    # Collect labels
    labels = collect_document_type_labels(source, limit)

    if not labels:
        logger.error("No labels collected! Check --source path and profile.json structure")
        raise typer.Exit(code=1)

    # Save to JSONL
    output_path = output / f"{task}.jsonl"
    save_mode = "a" if append else "w"

    with output_path.open(save_mode) as f:
        for label in labels:
            f.write(json.dumps(label) + "\n")

    logger.info(f"Saved/Appended {len(labels)} labels to {output_path}")

    # Print statistics
    label_counts = {}
    for label in labels:
        label_value = label["label"]
        label_counts[label_value] = label_counts.get(label_value, 0) + 1

    logger.info("\nLabel distribution:")
    for label_value, count in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {label_value}: {count} ({count/len(labels)*100:.1f}%)")

    if monitor:
        monitor.update(item=f"{len(labels)} labels collected")
        monitor.finish()


if __name__ == "__main__":
    app()
