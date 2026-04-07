#!/usr/bin/env python3
"""
Prepare image dataset for vision classifier training.

Extracts first N pages from PDFs as 224x224 images.
"""

import typer
import json
from pathlib import Path
from typing import List
from loguru import logger
import sys

try:
    import fitz  # PyMuPDF
    from PIL import Image
    import io
except ImportError:
    logger.error("Missing dependencies: pip install pymupdf pillow")
    sys.exit(1)

logger.remove()
logger.add(sys.stderr, level="INFO")


def extract_pdf_pages(pdf_path: Path, output_dir: Path, max_pages: int = 3) -> List[Path]:
    """Extract first N pages from PDF as images using PyMuPDF (fast)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        doc = fitz.open(pdf_path)
        image_paths = []
        
        for i in range(min(max_pages, len(doc))):
            page = doc[i]
            # Use a matrix to scale to roughly 224x224
            # Most PDF pages are ~600x800. Scale factor ~0.3
            # But let's just use 2.0 zoom for quality then resize
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            
            # Resize to exactly 224x224
            img_resized = img.resize((224, 224), Image.Resampling.LANCZOS)
            
            # Save as JPEG
            output_path = output_dir / f"page_{i+1}.jpg"
            img_resized.save(output_path, "JPEG", quality=90)
            image_paths.append(output_path)
        
        doc.close()
        return image_paths
    
    except Exception as e:
        logger.error(f"Failed to extract pages from {pdf_path}: {e}")
        return []


def prepare_dataset(labels_path: Path, output_dir: Path, max_pages: int = 3):
    """Prepare image dataset from JSONL labels."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load labels
    labels = []
    with open(labels_path) as f:
        for line in f:
            labels.append(json.loads(line))
    
    logger.info(f"Loaded {len(labels)} labels from {labels_path}")
    
    # Process each PDF
    processed = 0
    failed = 0
    
    for i, label in enumerate(labels):
        pdf_path = Path(label["input"]["pdf_path"])
        doc_id = label["id"]
        preset = label["label"]
        
        # Create output directory for this document
        doc_output_dir = output_dir / preset / doc_id
        
        # Extract pages
        image_paths = extract_pdf_pages(pdf_path, doc_output_dir, max_pages)
        
        if image_paths:
            processed += 1
            
            # Update label with image paths
            label["input"]["image_paths"] = [str(p) for p in image_paths]
        else:
            failed += 1
        
        if (i + 1) % 50 == 0:
            logger.info(f"Processed {i+1}/{len(labels)} PDFs ({processed} ok, {failed} failed)")
    
    logger.info(f"\nDataset preparation complete:")
    logger.info(f"  Processed: {processed}/{len(labels)}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Output: {output_dir}")
    
    # Save updated labels
    updated_labels_path = output_dir / "labels_with_images.jsonl"
    with open(updated_labels_path, "w") as f:
        for label in labels:
            if "image_paths" in label["input"]:
                f.write(json.dumps(label) + "\n")
    
    logger.info(f"  Labels: {updated_labels_path}")


app = typer.Typer(help="Prepare image dataset for vision classifier")


@app.command()
def main(
    labels: str = typer.Option(..., help="Path to labels JSONL"),
    output: str = typer.Option(..., help="Output directory for images"),
    max_pages: int = typer.Option(3, help="Max pages to extract per PDF"),
):
    prepare_dataset(labels, output, max_pages)


if __name__ == "__main__":
    app()
