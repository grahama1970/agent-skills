#!/usr/bin/env python3
"""audit_images - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import typer
from pathlib import Path
from PIL import Image
import numpy as np
from loguru import logger
import random

app = typer.Typer()


def audit_images(labels_path: Path, sample_size: int = 50):
    with open(labels_path) as f:
        labels = [json.loads(line) for line in f]
    
    logger.info(f"Loaded {len(labels)} labels")
    
    # Sample
    if len(labels) > sample_size:
        sample = random.sample(labels, sample_size)
    else:
        sample = labels
        
    issues = 0
    
    for item in sample:
        pdf_path = item["input"]["pdf_path"]
        image_paths = item["input"].get("image_paths", [])
        
        if not image_paths:
            logger.warning(f"No images for {pdf_path}")
            issues += 1
            continue
            
        for img_path_str in image_paths:
            img_path = Path(img_path_str)
            if not img_path.exists():
                logger.error(f"Image missing: {img_path}")
                issues += 1
                continue
                
            try:
                img = Image.open(img_path)
                img_data = np.array(img)
                
                # Check for empty/black/white
                if img_data.size == 0:
                    logger.error(f"Empty image: {img_path}")
                    issues += 1
                    continue
                    
                mean = np.mean(img_data)
                std = np.std(img_data)
                
                if std < 5.0: # Very low variance (flat color)
                    logger.warning(f"Low variance ({std:.1f}) in {img_path} (Mean: {mean:.1f})")
                    issues += 1
                
            except Exception as e:
                logger.error(f"Failed to read {img_path}: {e}")
                issues += 1

    logger.info(f"Audit complete. Found {issues} issues in {len(sample)} samples.")

@app.command()
def main(labels: Path = typer.Argument(..., help="Path to labels file")):
    """Audit images from labels file."""
    audit_images(labels)


if __name__ == "__main__":
    app()
